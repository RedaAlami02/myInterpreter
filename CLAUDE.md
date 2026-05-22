# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**myInterpreter** is a full-stack stock market analysis platform for the Moroccan Bourse (CDG Capital Bourse). It allows users to:
- Create accounts and manage authentication
- Build and track investment portfolios (buy/sell stocks)
- Screen stocks using fundamental analysis metrics
- View market data and statistics
- Perform financial ratio analysis (PER, PEG, P/ROE, P/B)

The application pulls live market data from the CDG Bourse API via a Python scraper and displays analysis to authenticated users.

## Architecture

### Core Stack
- **Backend**: PHP (procedural, no framework)
- **Frontend**: Server-rendered HTML/CSS with vanilla JS
- **Database**: MySQL (local dev: `stock` database on localhost)
- **Data Scraping**: Python with `requests`, `mysql-connector-python`, `flask`, `rich`

### Directory Structure

```
myInterpreter/
├── index.php                  # Login/logout, main entry point
├── portfolio.php              # Buy/sell stocks, portfolio management
├── screener.php               # Stock screening by financial ratios
├── statistics.php             # Market-wide statistics
├── results.php                # Search results
├── infoAction.php             # Stock detail view
├── Update.php                 # Manual data update trigger
├── debug_sync.php             # Debug tool for data sync
├── stock.sql                  # Database schema
│
├── config/
│   └── config.php             # Database credentials, app constants, CSRF helpers
│
├── core/
│   ├── Database.php           # PDO wrapper, singleton connection
│   ├── Action.php             # Company class with ratio calculations
│   └── auth.php               # requireLogin() middleware
│
├── handlers/
│   ├── operations.php         # Backend for portfolio/stock ops
│   └── storing.php            # Data storage operations
│
├── scrapping/
│   ├── requirements.txt        # Python dependencies
│   ├── GETjson.py             # Fetch live market data from CDG Bourse API
│   ├── GetSymbols.py          # List available stock symbols
│   └── format.py              # Data formatting utilities
│
└── assets/                    # (placeholder for CSS/JS/images)
```

### Key Concepts

#### Database Layer
- **Database.php**: Singleton PDO instance with error handling, UTF-8, prepared statements enforced
- Connection details in `config/config.php` (host, port, credentials)
- All queries use parameterized statements to prevent SQL injection

#### Authentication
- Session-based with optional persistent cookies (HttpOnly, 30-day expiry)
- Password stored as bcrypt hash; legacy plain-text passwords auto-upgraded on login
- `requireLogin()` redirects unauthenticated users to index.php
- CSRF protection via `csrf_token()`, `csrf_verify()`, `csrf_field()` helpers

#### Financial Models
- **Company class** (Action.php):
  - Raw inputs: PA (stock price), BPA (earnings per share), TC5 (growth rate), ROE, NA (shares), CP (book value)
  - Calculated metrics: CB (market cap), PER, PEG, PR (P/ROE), PB (P/Book)
  - `test()` method rates each metric as green/orange/red based on config thresholds
  - Thresholds defined in `config/config.php` (PER_GREEN, PEG_ORANGE, etc.)

#### Portfolio Management
- **achats** table: buy transactions (date, symbol, quantity, price, user)
- **ventes** table: sell transactions (date, symbol, quantity, price, user)
- **portefeuille** table: current holdings (symbol, quantity, total cost basis, user)
- Buy/sell operations in portfolio.php with CSRF protection and validation

#### Data Scraping
- **GETjson.py**: Fetches live quotes from `https://www.cdgcapitalbourse.ma/api/`
- Spoofs browser headers (User-Agent, Referer, etc.)
- Returns JSON with stock symbols, prices, and metrics
- Can be called from handlers or Update.php to refresh the data table

### Page Flows

1. **index.php** (public)
   - Login form with session + cookie persistence
   - Logout (CSRF-protected)
   - Legacy password auto-upgrade on successful login

2. **portfolio.php** (protected)
   - Add buy: insert into achats and update portefeuille
   - Add sell: validate shares available, insert into ventes, update portefeuille
   - Flash messages for success/error feedback

3. **screener.php** (protected)
   - Fetch latest data snapshot per company
   - Display ratios with color-coded health (green/orange/red)
   - Sort/filter by symbol or metric

4. **statistics.php** (protected)
   - Market aggregates: top gainers, volume, sector trends

5. **infoAction.php** (protected)
   - Detailed view for a single stock
   - Historical price + ratio trends
   - Buy/sell quick-entry forms

## Configuration

Edit `config/config.php` to:
- **DB_HOST, DB_USER, DB_PASS, DB_NAME**: MySQL connection
- **SCRAPER_API_KEY**: Secret for authenticating Python scraper calls (currently placeholder)
- **TAX_RATE**: Tax percentage applied to portfolio gains (default 10%)
- **PER_GREEN / PER_ORANGE, etc.**: Ratio thresholds for color coding (adjust as needed)

## Database Setup

1. Create the `stock` database in MySQL
2. Import `stock.sql` to set up tables (utilisateur, data, achats, ventes, portefeuille, etc.)
3. Update `config/config.php` with your DB credentials

## Running the Application

### PHP Development Server
```bash
php -S localhost:8000
# Then navigate to http://localhost:8000/myInterpreter/index.php
```

### Python Data Scraper
```bash
cd scrapping
python3 -m venv venv          # Create virtualenv if needed
source venv/bin/activate      # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python3 GETjson.py            # Fetch and store market data
```

### Database Dump/Restore
```bash
# Dump current schema + data
mysqldump -u root -p stock > stock_backup.sql

# Restore from SQL file
mysql -u root -p stock < stock.sql
```

## Common Development Tasks

### Add a New Page
1. Create `.php` file in root (or subdirectory)
2. Include `config/config.php` at top
3. Call `requireLogin()` if protected
4. Get DB connection: `$db = (new Database())->opendb()`
5. Use prepared statements: `$db->prepare('..')->execute([...])`
6. Include CSRF token in forms: `csrf_field()`

### Modify Financial Ratios
- Edit Company::calcul() in `core/Action.php` for calculation logic
- Edit Company::test() for color thresholds
- Update threshold constants in `config/config.php`

### Add a New Table
- Modify `stock.sql` schema
- Update corresponding code that reads/writes to the table
- Ensure prepared statements with bound parameters

### Debug Data Sync Issues
- Check `debug_sync.php` for manual sync diagnostics
- Verify `GETjson.py` is pulling data correctly (test headers, API endpoint)
- Check MySQL error logs if inserts fail

## Security Notes

- **SQL Injection**: All queries use parameterized statements (PDO with false emulation)
- **CSRF Protection**: Token in session, verified on POST; use `csrf_field()` in forms
- **Password Hashing**: bcrypt with automatic legacy password upgrade
- **Cookies**: HttpOnly + SameSite flags to prevent XSS theft
- **Session**: PHP native sessions in server-side storage
- **API Key**: Set SCRAPER_API_KEY in config (validate headers in handlers if scraper is public)

## Testing Notes

- No automated test suite; test manually in browser
- Integration tests would benefit MySQL test database to avoid polluting dev DB
- Python scraper has no unit tests; test with mock responses or staging API

## Performance Considerations

- **Database indexes**: Add on utilisateur.USERNAME, data.C_NAME, portefeuille.ID_USER
- **Ratio calculations**: Currently in-memory per page; no caching layer
- **Scraper API calls**: Rate-limited by CDG Bourse; consider batch/scheduled updates
- **Session handling**: PHP's default file-based; upgrade to Redis if scaling

## Known Quirks

- **BASE_URL calculation** (config.php): Derived from SCRIPT_NAME to handle symlinks correctly; avoid using __FILE__ or realpath()
- **Manual password upgrade**: Legacy plain-text passwords auto-convert to bcrypt on login (no separate migration script)
- **Ratio color coding**: Duplicated in both Company::test() and rateColor() function in screener.php; consider consolidating
- **Python 2 vs 3**: Scraper uses Python 3 (requires `python3` command)
- **Table name casing**: All table names are lowercase. Windows MySQL exports them lowercase naturally; Linux imports as-is (no transformation). Never use uppercase table names in SQL queries.

## Future Improvements

- Add automated tests (PHPUnit for PHP, pytest for Python)
- Consolidate ratio evaluation logic (avoid duplication)
- Implement caching layer for frequently-read data (Redis)
- Add API versioning if scraper endpoints change
- Separate concerns with a lightweight MVC framework
- Add activity logging for audit trail
