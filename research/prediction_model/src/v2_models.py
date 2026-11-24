"""CPU-only regression and date-grouped learning-to-rank models for V2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from .stock_models import Fold


@dataclass
class ModelBundle:
    imputer: SimpleImputer
    model: Any
    scaler: StandardScaler | None
    model_name: str
    objective: str
    features: list[str]


def _model(model_name: str, objective: str, settings: dict, seed: int) -> Any:
    iterations = settings["iterations"]
    learning_rate = settings["learning_rate"]
    depth = settings["max_depth"]
    leaves = settings["num_leaves"]
    minimum_leaf = settings["minimum_leaf_samples"]
    l2 = settings["l2_regularization"]
    threads = settings["cpu_threads"]
    if model_name == "ridge":
        if objective == "ranking":
            raise ValueError("Ridge has no dedicated ranking objective")
        return Ridge(alpha=10.0)
    if model_name == "hist_gradient_boosting":
        if objective == "ranking":
            raise ValueError("HistogramGradientBoosting has no ranking objective")
        return HistGradientBoostingRegressor(
            learning_rate=0.05,
            max_iter=120,
            max_leaf_nodes=15,
            l2_regularization=1.0,
            random_state=seed,
        )
    if model_name == "lightgbm":
        from lightgbm import LGBMRanker, LGBMRegressor

        common = dict(
            n_estimators=iterations,
            learning_rate=learning_rate,
            num_leaves=leaves,
            max_depth=depth,
            min_child_samples=minimum_leaf,
            reg_lambda=l2,
            random_state=seed,
            n_jobs=threads,
            verbosity=-1,
            deterministic=True,
            force_col_wise=True,
        )
        return LGBMRanker(objective="lambdarank", **common) if objective == "ranking" else LGBMRegressor(**common)
    if model_name == "xgboost":
        from xgboost import XGBRanker, XGBRegressor

        common = dict(
            n_estimators=iterations,
            learning_rate=learning_rate,
            max_depth=depth,
            min_child_weight=minimum_leaf,
            reg_lambda=l2,
            subsample=0.9,
            colsample_bytree=0.9,
            tree_method="hist",
            device="cpu",
            random_state=seed,
            n_jobs=threads,
        )
        return XGBRanker(objective="rank:ndcg", **common) if objective == "ranking" else XGBRegressor(objective="reg:squarederror", **common)
    if model_name == "catboost":
        from catboost import CatBoostRanker, CatBoostRegressor

        common = dict(
            iterations=iterations,
            learning_rate=learning_rate,
            depth=depth,
            l2_leaf_reg=l2,
            random_seed=seed,
            thread_count=threads,
            task_type="CPU",
            verbose=False,
            allow_writing_files=False,
        )
        if objective == "ranking":
            # YetiRank is materially slower than the regression families on grouped
            # CPU data. V2 predeclares a compact cap rather than spending its small
            # sample on an expensive search.
            common["iterations"] = min(iterations, settings.get("catboost_ranking_iteration_cap", 60))
            return CatBoostRanker(loss_function="YetiRank", **common)
        return CatBoostRegressor(loss_function="RMSE", **common)
    raise ValueError(f"Unknown model: {model_name}")


def _feature_frame(frame: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    return frame[features].replace([np.inf, -np.inf], np.nan).astype(float)


def _prepare_training(
    train: pd.DataFrame,
    strategy: str,
    rolling_dates: int | None,
    half_life_dates: int | None,
) -> tuple[pd.DataFrame, np.ndarray | None]:
    output = train.copy()
    if strategy.startswith("rolling_"):
        unique_dates = sorted(output["date"].unique())
        if not rolling_dates:
            raise ValueError("rolling_dates is required")
        keep = set(unique_dates[-rolling_dates:])
        output = output[output["date"].isin(keep)].copy()
    weights = None
    if strategy.startswith("recency_weighted_"):
        if not half_life_dates:
            raise ValueError("half_life_dates is required")
        ordered_dates = {date: index for index, date in enumerate(sorted(output["date"].unique()))}
        age = output["date"].map(lambda date: len(ordered_dates) - 1 - ordered_dates[date])
        weights = np.power(0.5, age.to_numpy() / half_life_dates)
    return output, weights


def fit_bundle(
    train: pd.DataFrame,
    features: list[str],
    target_column: str,
    relevance_column: str,
    model_name: str,
    objective: str,
    settings: dict,
    seed: int,
    sample_weight: np.ndarray | None = None,
) -> ModelBundle:
    ordered = train.sort_values(
        ["date", "c_name"] if objective == "ranking" else ["c_name", "date"]
    ).copy()
    if sample_weight is not None:
        weight_map = pd.Series(sample_weight, index=train.index)
        sample_weight = weight_map.loc[ordered.index].to_numpy()
    imputer = SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)
    x = imputer.fit_transform(_feature_frame(ordered, features))
    scaler = None
    if model_name == "ridge":
        scaler = StandardScaler()
        x = scaler.fit_transform(x)
    model = _model(model_name, objective, settings, seed)
    if objective == "ranking":
        groups = ordered.groupby("date", sort=True).size().to_list()
        qid = pd.factorize(ordered["date"], sort=True)[0]
        if model_name == "lightgbm":
            model.fit(x, ordered[relevance_column], group=groups, sample_weight=sample_weight)
        elif model_name == "xgboost":
            model.fit(x, ordered[relevance_column], qid=qid, sample_weight=sample_weight)
        elif model_name == "catboost":
            model.fit(
                x,
                ordered[target_column],
                group_id=qid,
                sample_weight=sample_weight,
            )
        else:
            raise ValueError(f"No ranker for {model_name}")
    else:
        model.fit(x, ordered[target_column], sample_weight=sample_weight)
    return ModelBundle(imputer, model, scaler, model_name, objective, features)


def predict_bundle(bundle: ModelBundle, frame: pd.DataFrame) -> np.ndarray:
    x = bundle.imputer.transform(_feature_frame(frame, bundle.features))
    if bundle.scaler is not None:
        x = bundle.scaler.transform(x)
    return np.asarray(bundle.model.predict(x), dtype=float)


def walk_forward_configuration(
    frame: pd.DataFrame,
    features: list[str],
    folds: list[Fold],
    horizon: int,
    model_name: str,
    target_formulation: str,
    feature_block: str,
    training_strategy: str,
    settings: dict,
    seed: int,
    rolling_dates: int | None = None,
    half_life_dates: int | None = None,
) -> tuple[pd.DataFrame, list[dict]]:
    target_columns = {
        "raw": f"target_raw_{horizon}d",
        "percentile": f"target_percentile_{horizon}d",
        "robust_z": f"target_robust_z_{horizon}d",
        "dedicated_rank": f"target_percentile_{horizon}d",
    }
    target = target_columns[target_formulation]
    relevance = f"target_rank_relevance_{horizon}d"
    label_end = f"label_end_date_{horizon}d"
    objective = "ranking" if target_formulation == "dedicated_rank" else "regression"
    outputs: list[pd.DataFrame] = []
    decisions: list[dict] = []
    for fold in folds:
        raw_train = frame[
            frame["eligible"]
            & frame[target].notna()
            & frame[label_end].lt(fold.validation_start)
        ]
        validation = frame[
            frame["eligible"]
            & frame[target].notna()
            & frame["date"].between(fold.validation_start, fold.validation_end)
        ].copy()
        train, weights = _prepare_training(
            raw_train, training_strategy, rolling_dates, half_life_dates
        )
        if train.empty or validation.empty:
            continue
        bundle = fit_bundle(
            train,
            features,
            target,
            relevance,
            model_name,
            objective,
            settings,
            seed,
            weights,
        )
        output = validation[
            [
                "date",
                "c_name",
                "symbol",
                "sector",
                f"excess_return_{horizon}d",
                f"stock_total_return_{horizon}d",
                f"masi_return_{horizon}d",
                f"target_percentile_{horizon}d",
                "stale_fraction_20d",
                "volume_known",
                "eligibility_reason",
            ]
        ].copy()
        output = output.rename(
            columns={
                f"excess_return_{horizon}d": "actual",
                f"stock_total_return_{horizon}d": "stock_total_return",
                f"masi_return_{horizon}d": "masi_return",
                f"target_percentile_{horizon}d": "actual_percentile",
            }
        )
        output["prediction"] = predict_bundle(bundle, validation)
        output["model"] = model_name
        output["target_formulation"] = target_formulation
        output["feature_block"] = feature_block
        output["training_strategy"] = training_strategy
        output["horizon"] = horizon
        output["fold"] = fold.name
        output["phase"] = fold.phase
        output["train_rows"] = len(train)
        output["train_dates"] = train["date"].nunique()
        outputs.append(output)
        decisions.append(
            {
                "fold": fold.name,
                "phase": fold.phase,
                "validation_start": fold.validation_start,
                "validation_end": fold.validation_end,
                "maximum_training_label_end": train[label_end].max(),
                "train_rows": len(train),
                "train_dates": train["date"].nunique(),
                "model": model_name,
                "target_formulation": target_formulation,
                "feature_block": feature_block,
                "training_strategy": training_strategy,
                "horizon": horizon,
            }
        )
    predictions = pd.concat(outputs, ignore_index=True) if outputs else pd.DataFrame()
    return predictions, decisions
