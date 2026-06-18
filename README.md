# myInterpreter

**A Casablanca Stock Exchange (Bourse de Casablanca) analysis app** — tracks live prices for the Moroccan market, scores listed companies on valuation ratios, and manages a personal portfolio with realized P&L. Available as a Flutter mobile app and a PHP web client over a shared Appwrite backend.

---

## Screenshots

> _Placeholders — replace with real captures._

| Screener | Stock detail | Portfolio |
|---|---|---|
| ![Screener](docs/screenshots/screener.png) | ![Stock detail](docs/screenshots/stock_detail.png) | ![Portfolio](docs/screenshots/portfolio.png) |

| Statistics (FIFO P&L) | Mobile app |
|---|---|
| ![Statistics](docs/screenshots/statistics.png) | ![Mobile](docs/screenshots/mobile.png) |

---

## Tech stack

![Flutter](https://img.shields.io/badge/Flutter-02569B?logo=flutter&logoColor=white)
![PHP](https://img.shields.io/badge/PHP-777BB4?logo=php&logoColor=white)
![Appwrite](https://img.shields.io/badge/Appwrite-FD366E?logo=appwrite&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)

- **Mobile:** Flutter (Dart) — Android client
- **Web:** plain PHP (no framework, no Composer)
- **Backend:** Appwrite Cloud — auth + database
- **Data pipeline:** Python serverless function (Appwrite Cloud Function)

---

## Features

- **Scheduled serverless data pipeline** — a Python Appwrite Cloud Function pulls a financial JSON API on a fixed schedule (every 15 min during market hours, Mon–Fri) across **70+ listed tickers**, writing one historical record per company per run plus a fast "latest price" lookup row.
- **Reverse-engineered an undocumented JSON API** — the market endpoint is private and browser-gated; the scraper replicates the required `origin`/`referer`/`user-agent` headers and session priming to retrieve data, then normalizes it into a clean schema.
- **Four valuation ratios with visual scoring** — computes **PER** (price/earnings), **PEG** (PER vs. growth), **P/ROE** (price vs. return on equity), and **P/B** (price/book) per company, each rendered with a color-coded score against configurable thresholds so undervalued names stand out at a glance.
- **FIFO portfolio P&L** — buy/sell tracking with first-in-first-out cost-basis accounting to compute realized profit and loss per position.
- **Two clients, one backend** — a Flutter mobile app and a PHP web app share the same Appwrite project (auth, database, and the scheduled function), so data stays consistent across platforms.

---

## Setup & install

### 1. Clone

```bash
git clone https://github.com/RedaAlami02/myInterpreter.git
cd myInterpreter
```

### 2. Configure environment

Copy the example and fill in your own Appwrite values (see [`.env.example`](.env.example)):

```bash
cp .env.example .env
# set APPWRITE_ENDPOINT, APPWRITE_PROJECT_ID, APPWRITE_API_KEY
```

- The **Cloud Function** reads `APPWRITE_ENDPOINT`, `APPWRITE_PROJECT_ID`, `APPWRITE_API_KEY` from environment variables.
- The **PHP web app** reads its server key from `config/secrets.php` (gitignored). Create it:
  ```php
  <?php
  define('APPWRITE_API_KEY', 'your_appwrite_server_api_key');
  ```
  The endpoint and project ID are non-secret constants in `core/Appwrite.php`.

### 3. Per-component dependencies

**Flutter (mobile)**
```bash
cd myinterpreter_app
flutter pub get
flutter run            # debug build on a connected device/emulator
```

**PHP (web)** — no Composer; serve the repo root with any PHP runtime:
```bash
php -S localhost:8000   # then open http://localhost:8000
```

**Python (data pipeline / setup scripts)**
```bash
pip install appwrite requests
python appwrite_setup.py   # one-time: create collections
```

### 4. Deploy the Cloud Function

Deploy `cloud_function/` to Appwrite (Console or CLI), set the three `APPWRITE_*` environment variables on the function, and configure its schedule (cron) to run during market hours.

```bash
appwrite deploy function
```

---

## Architecture

```
 ┌─────────────┐     ┌─────────────┐
 │ Flutter app │     │  PHP web    │
 │  (mobile)   │     │  client     │
 └──────┬──────┘     └──────┬──────┘
        │   auth + queries  │
        └─────────┬─────────┘
                  ▼
          ┌───────────────┐
          │   Appwrite    │  auth + database
          └───────┬───────┘
                  ▲ writes prices
        ┌─────────┴──────────┐
        │ Scheduled Python   │  pulls financial JSON API
        │ Cloud Function     │  every 15 min, market hours
        └────────────────────┘
```

Mobile and web clients read/write through Appwrite (auth + database). A scheduled Python Cloud Function fetches the market JSON API and writes prices into the same database, which both clients then read.

---

## Note

Educational project. The market-data pipeline consumes a **publicly available JSON API**; replicated request headers are used only to retrieve data already served to any browser visiting the site.
