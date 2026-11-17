# Repository Guidelines

## Project Structure & Module Organization

Root-level `*.php` files are web pages; shared PHP code lives in `core/`, request handlers in `handlers/`, and browser code in `assets/`. The Flutter app is under `myinterpreter_app/`, with screens in `lib/screens/` and tests in `test/`. Scheduled Python functions live in `cloud_function/functions/<name>/src/`; root Python and SQL files support setup, migration, and deployment.

Keep equivalent dividend rules in `core/dividends.php` and `myinterpreter_app/lib/dividends.dart` synchronized.

## Build, Test, and Development Commands

- `php -S localhost:8000` serves the PHP site locally; no Composer install is required.
- `cd myinterpreter_app && flutter pub get` resolves mobile dependencies.
- `cd myinterpreter_app && flutter run` starts a debug build on a device or emulator.
- `cd myinterpreter_app && flutter analyze` runs the analyzer and `flutter_lints`.
- `cd myinterpreter_app && flutter test` runs Flutter tests.
- `python3 deploy.py --dry-run` previews the PHP deployment; omit `--dry-run` only after reviewing it.
- `appwrite deploy function` deploys configured cloud functions after their environment variables are set.

Never build Flutter locally with `--release`; the release APK is built by GitHub Actions on pushes to `master`.

## Coding Style & Naming Conventions

Follow existing style: Dart formatter defaults and two-space indentation, Python PEP 8 with four spaces and `snake_case`, and PSR-like PHP with four spaces and `camelCase` methods. Use lowercase Appwrite collection names. Prefer descriptive filenames such as `stock_detail.dart`; cloud functions use `src/main.py` as their entry point. Run `dart format lib test` before submitting Dart changes.

## Testing Guidelines

Name Flutter tests `*_test.dart` and group behavior with `testWidgets` or `test`. Add focused regression coverage for changed calculations and parsing. When touching PHP, run `php -l path/to/file.php`; for Python, use `python3 -m compileall` on the affected function. Validate data-dependent financial logic against representative Appwrite records, especially FIFO P&L and negative-denominator ratios.

## Commit & Pull Request Guidelines

History follows Conventional Commit-style subjects: `feat(scope): ...`, `fix(scope): ...`, `docs: ...`, and `chore: ...`. Keep commits narrow and imperative. Pull requests should explain the user-visible effect, list verification commands, link relevant issues, and include screenshots for web or Flutter UI changes. Call out schema, schedule, or deployment changes explicitly.

## Security & Configuration

Copy example configuration files and keep real credentials and upstream provider endpoints in ignored files or environment variables. Never commit API keys, `config/secrets.php`, `config/sources.php`, function `sources.py` files, or provider names. Preserve per-user Appwrite permissions on portfolio documents.

The owner confirmed source authority and approval on 2026-10-26. Treat source-use authorization as supplied. Keep source identities, names, domains and identifying aliases private: exclude them from public code, filenames, documentation, logs, screenshots, commit messages, pull requests and pushes. Review proposed publication contents before pushing; preserve unsanitized historical evidence privately rather than rewriting original records or accepted source pins.
