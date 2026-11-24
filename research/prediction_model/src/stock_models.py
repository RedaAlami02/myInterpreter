"""Chronological stock-model ladder with optional third-party boosters."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class Fold:
    name: str
    phase: str
    validation_start: pd.Timestamp
    validation_end: pd.Timestamp


def dependency_status() -> dict[str, str]:
    packages = ["duckdb", "lightgbm", "xgboost", "catboost"]
    return {
        package: "available" if importlib.util.find_spec(package) else "not installed"
        for package in packages
    }


def make_folds(
    dates: list[pd.Timestamp],
    minimum_training_dates: int,
    validation_dates: int,
    final_holdout_dates: int,
) -> list[Fold]:
    dates = sorted(pd.Timestamp(value) for value in dates)
    holdout_start_index = len(dates) - final_holdout_dates
    if holdout_start_index <= minimum_training_dates:
        raise ValueError("Not enough dates for requested training and final holdout")
    folds: list[Fold] = []
    start = minimum_training_dates
    fold_number = 1
    while start < holdout_start_index:
        end = min(start + validation_dates, holdout_start_index)
        if end - start < max(20, validation_dates // 2):
            break
        folds.append(Fold(f"development_{fold_number}", "development", dates[start], dates[end - 1]))
        start = end
        fold_number += 1
    folds.append(Fold("final_holdout", "final_holdout", dates[holdout_start_index], dates[-1]))
    return folds


def regression_factories(seed: int, include_optional: bool = True) -> dict[str, Callable[[], object]]:
    factories: dict[str, Callable[[], object]] = {
        "ridge": lambda: make_pipeline(
            SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True),
            StandardScaler(),
            Ridge(alpha=10.0),
        ),
        "sklearn_hist_gradient_boosting": lambda: make_pipeline(
            SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True),
            HistGradientBoostingRegressor(
                learning_rate=0.05,
                max_iter=120,
                max_leaf_nodes=15,
                l2_regularization=1.0,
                random_state=seed,
            ),
        ),
    }
    if include_optional and importlib.util.find_spec("lightgbm"):
        from lightgbm import LGBMRegressor

        factories["lightgbm"] = lambda: LGBMRegressor(
            n_estimators=250,
            learning_rate=0.03,
            num_leaves=15,
            reg_lambda=2.0,
            random_state=seed,
            verbosity=-1,
        )
    if include_optional and importlib.util.find_spec("xgboost"):
        from xgboost import XGBRegressor

        factories["xgboost"] = lambda: XGBRegressor(
            n_estimators=250,
            learning_rate=0.03,
            max_depth=4,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_lambda=2.0,
            random_state=seed,
            n_jobs=1,
        )
    if include_optional and importlib.util.find_spec("catboost"):
        from catboost import CatBoostRegressor

        factories["catboost"] = lambda: CatBoostRegressor(
            iterations=250,
            learning_rate=0.03,
            depth=5,
            l2_leaf_reg=5.0,
            random_seed=seed,
            verbose=False,
        )
    return factories


def _finite_features(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return frame[columns].replace([np.inf, -np.inf], np.nan).astype(float)


def walk_forward_regression(
    frame: pd.DataFrame,
    features: list[str],
    folds: list[Fold],
    target: str,
    label_end: str,
    seed: int,
    feature_block: str,
) -> pd.DataFrame:
    results: list[pd.DataFrame] = []
    factories = regression_factories(seed)
    for fold in folds:
        train = frame[
            frame["eligible"]
            & frame[target].notna()
            & frame[label_end].lt(fold.validation_start)
        ]
        validation = frame[
            frame["eligible"]
            & frame[target].notna()
            & frame["date"].between(fold.validation_start, fold.validation_end)
        ]
        if train.empty or validation.empty:
            continue
        base = validation[
            [
                "date",
                "c_name",
                "symbol",
                "sector",
                target,
                "stock_total_return_20d",
                "masi_return_20d",
                "stale_fraction_20d",
                "volume_known",
            ]
        ].copy()
        base = base.rename(columns={target: "actual"})

        baseline_predictions = {
            "zero_excess": np.zeros(len(validation)),
            "relative_momentum_20d": validation["relative_return_20d"].fillna(0).to_numpy(),
        }
        for model_name, prediction in baseline_predictions.items():
            output = base.copy()
            output["prediction"] = prediction
            output["model"] = model_name
            output["feature_block"] = "baseline"
            output["fold"] = fold.name
            output["phase"] = fold.phase
            output["train_rows"] = len(train)
            results.append(output)

        train_x = _finite_features(train, features)
        validation_x = _finite_features(validation, features)
        for model_name, factory in factories.items():
            model = factory()
            model.fit(train_x, train[target].to_numpy())
            output = base.copy()
            output["prediction"] = model.predict(validation_x)
            output["model"] = model_name
            output["feature_block"] = feature_block
            output["fold"] = fold.name
            output["phase"] = fold.phase
            output["train_rows"] = len(train)
            results.append(output)
    return pd.concat(results, ignore_index=True) if results else pd.DataFrame()


def walk_forward_classification(
    frame: pd.DataFrame,
    features: list[str],
    folds: list[Fold],
    target: str,
    label_end: str,
    threshold: float,
    seed: int,
) -> pd.DataFrame:
    outputs: list[pd.DataFrame] = []
    labels = np.array(["DOWN", "STABLE", "UP"])
    for fold in folds:
        train = frame[
            frame["eligible"]
            & frame[target].notna()
            & frame[label_end].lt(fold.validation_start)
        ].copy()
        validation = frame[
            frame["eligible"]
            & frame[target].notna()
            & frame["date"].between(fold.validation_start, fold.validation_end)
        ].copy()
        train["class"] = np.select(
            [train[target].lt(-threshold), train[target].gt(threshold)],
            ["DOWN", "UP"],
            default="STABLE",
        )
        validation["class"] = np.select(
            [validation[target].lt(-threshold), validation[target].gt(threshold)],
            ["DOWN", "UP"],
            default="STABLE",
        )
        if len(train) == 0 or train["class"].nunique() < 3 or len(validation) == 0:
            continue
        model = make_pipeline(
            SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True),
            StandardScaler(),
            LogisticRegression(
                C=0.2,
                class_weight="balanced",
                max_iter=1000,
                random_state=seed,
            ),
        )
        model.fit(_finite_features(train, features), train["class"])
        probabilities = model.predict_proba(_finite_features(validation, features))
        probability_frame = pd.DataFrame(
            probabilities, columns=model.classes_, index=validation.index
        ).reindex(columns=labels, fill_value=0.0)
        output = validation[["date", "c_name", "symbol", "class"]].copy()
        output["predicted_class"] = model.predict(_finite_features(validation, features))
        for label in labels:
            output[f"prob_{label.lower()}"] = probability_frame[label]
        output["fold"] = fold.name
        output["phase"] = fold.phase
        output["model"] = "multinomial_logistic"
        output["train_rows"] = len(train)
        outputs.append(output)
    return pd.concat(outputs, ignore_index=True) if outputs else pd.DataFrame()


def fit_predict_latest(
    frame: pd.DataFrame,
    features: list[str],
    model_name: str,
    target: str,
    label_end: str,
    seed: int,
    threshold: float,
    uncertainty_scale: float,
) -> tuple[pd.DataFrame, object, object]:
    latest_date = frame["date"].max()
    latest = frame[frame["date"].eq(latest_date)].copy()
    train = frame[frame["eligible"] & frame[target].notna() & frame[label_end].lt(latest_date)]
    factories = regression_factories(seed)
    if model_name not in factories:
        model_name = "ridge"
    regressor = factories[model_name]()
    regressor.fit(_finite_features(train, features), train[target])
    eligible = latest[latest["eligible"]].copy()
    eligible["predicted_excess_return_20d"] = regressor.predict(
        _finite_features(eligible, features)
    )
    eligible["model_score"] = eligible["predicted_excess_return_20d"].rank(pct=True)
    eligible["rank"] = eligible["predicted_excess_return_20d"].rank(
        ascending=False, method="first"
    ).astype(int)

    train_classes = np.select(
        [train[target].lt(-threshold), train[target].gt(threshold)],
        ["DOWN", "UP"],
        default="STABLE",
    )
    classifier = make_pipeline(
        SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True),
        StandardScaler(),
        LogisticRegression(C=0.2, class_weight="balanced", max_iter=1000, random_state=seed),
    )
    classifier.fit(_finite_features(train, features), train_classes)
    probabilities = classifier.predict_proba(_finite_features(eligible, features))
    for position, label in enumerate(classifier.classes_):
        eligible[f"prob_{str(label).lower()}"] = probabilities[:, position]
    eligible["predicted_class"] = classifier.predict(_finite_features(eligible, features))

    # Walk-forward residual dispersion is a deliberately simple empirical
    # uncertainty proxy; it is passed in so training residuals cannot flatter it.
    eligible["uncertainty_1sigma"] = uncertainty_scale
    signal_ratio = eligible["predicted_excess_return_20d"].abs() / uncertainty_scale
    eligible["confidence"] = np.select(
        [signal_ratio.ge(1.0), signal_ratio.ge(0.5)], ["HIGH", "MEDIUM"], default="LOW"
    )
    eligible["data_quality_warning"] = np.where(
        ~eligible["volume_known"],
        "historical volume unavailable",
        np.where(eligible["stale_fraction_20d"].gt(0.25), "frequent stale prices", ""),
    )

    abstained = latest[~latest["eligible"]].copy()
    abstained["predicted_excess_return_20d"] = np.nan
    abstained["model_score"] = np.nan
    abstained["rank"] = pd.NA
    abstained["predicted_class"] = "NO_PREDICTION"
    abstained["uncertainty_1sigma"] = np.nan
    abstained["confidence"] = "NO_PREDICTION"
    abstained["data_quality_warning"] = abstained["eligibility_reason"]
    for label in ["down", "stable", "up"]:
        abstained[f"prob_{label}"] = np.nan
    columns = [
        "date",
        "c_name",
        "symbol",
        "model_score",
        "predicted_excess_return_20d",
        "rank",
        "predicted_class",
        "prob_down",
        "prob_stable",
        "prob_up",
        "uncertainty_1sigma",
        "confidence",
        "data_quality_warning",
        "eligible",
        "eligibility_reason",
    ]
    ranking = pd.concat([eligible[columns], abstained[columns]], ignore_index=True).sort_values(
        ["eligible", "rank"], ascending=[False, True], na_position="last"
    )
    return ranking, regressor, classifier
