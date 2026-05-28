"""
Appwrite collection setup for myInterpreter.
Run once to create all 7 collections with correct attributes and indexes.

Usage:
    pip install appwrite
    python3 appwrite_setup.py
"""

from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.id import ID

PROJECT_ID = "6a12447800077d5113ae"
API_ENDPOINT = "https://fra.cloud.appwrite.io/v1"
API_KEY = input("Paste your Appwrite API key: ").strip()

DB_ID = "myinterpreter"
DB_NAME = "myInterpreter"

client = Client()
client.set_endpoint(API_ENDPOINT).set_project(PROJECT_ID).set_key(API_KEY)
db = Databases(client)

# ── helpers ──────────────────────────────────────────────────────────────────

def create_db():
    try:
        db.create(DB_ID, DB_NAME)
        print(f"Created database '{DB_NAME}'")
    except Exception as e:
        if "already exist" in str(e).lower():
            print(f"Database '{DB_NAME}' already exists, skipping.")
        else:
            raise

def collection(col_id, col_name):
    try:
        db.create_collection(DB_ID, col_id, col_name,
                             document_security=True)
        print(f"  Created collection '{col_name}'")
    except Exception as e:
        if "already exist" in str(e).lower():
            print(f"  Collection '{col_name}' already exists, skipping.")
        else:
            raise

def str_attr(col_id, key, size=255, required=False, default=None):
    try:
        db.create_string_attribute(DB_ID, col_id, key, size,
                                   required=required, default=default)
    except Exception as e:
        if "already exist" in str(e).lower():
            pass
        else:
            print(f"    WARN {col_id}.{key}: {e}")

def float_attr(col_id, key, required=False, default=None):
    try:
        db.create_float_attribute(DB_ID, col_id, key,
                                  required=required, default=default)
    except Exception as e:
        if "already exist" in str(e).lower():
            pass
        else:
            print(f"    WARN {col_id}.{key}: {e}")

def datetime_attr(col_id, key, required=False):
    try:
        db.create_datetime_attribute(DB_ID, col_id, key, required=required)
    except Exception as e:
        if "already exist" in str(e).lower():
            pass
        else:
            print(f"    WARN {col_id}.{key}: {e}")

def index(col_id, idx_id, idx_type, attributes):
    try:
        db.create_index(DB_ID, col_id, idx_id, idx_type, attributes)
    except Exception as e:
        if "already exist" in str(e).lower():
            pass
        else:
            print(f"    WARN index {col_id}.{idx_id}: {e}")

# ── main ──────────────────────────────────────────────────────────────────────

def setup():
    create_db()

    # ── company ──────────────────────────────────────────────────────────────
    print("\nSetting up 'company'...")
    collection("company", "company")
    str_attr("company", "name", size=60, required=True)
    float_attr("company", "bpa")        # Bénéfice par action (MAD/share)
    float_attr("company", "dpa")        # Dividende par action (MAD/share)
    float_attr("company", "tc5")        # Taux de croissance annuel moyen 5 ans (%)
    float_attr("company", "roe")        # Return on equity (%)
    float_attr("company", "na")         # Nombre d'actions (count)
    float_attr("company", "cp")         # Capitaux propres (raw MAD)
    datetime_attr("company", "date")
    # external enrichment fields
    str_attr("company", "ext_name",    size=80)     # external registry name for API lookups
    str_attr("company", "sector",      size=20)     # corporate / banque / assurance
    str_attr("company", "description", size=4000)   # company description
    str_attr("company", "shareholders",size=1500)   # JSON [{"name":"...","pct":65.4}]
    float_attr("company", "beta_3y")    # 3-year beta
    float_attr("company", "beta_5y")    # 5-year beta
    float_attr("company", "revenue")    # latest annual CA (MMAD)
    float_attr("company", "ebitda")     # latest annual EBE (MMAD)
    float_attr("company", "ebit")       # latest annual EBIT (MMAD)
    float_attr("company", "net_profit") # latest annual RNPG (MMAD)
    float_attr("company", "fcf")        # latest annual Free Cash Flow (MMAD)
    float_attr("company", "net_debt")   # latest annual dette nette (MMAD, neg = cash)
    float_attr("company", "net_cash")   # latest annual trésorerie nette (MMAD)
    float_attr("company", "total_assets")   # latest actif total (MMAD)
    float_attr("company", "rev_growth_5y")  # CA CAGR 5 ans (%)
    float_attr("company", "rnpg_growth_5y") # RNPG CAGR 5 ans (%)
    float_attr("company", "profit_margin")  # marge nette % (RNPG/CA*100)
    index("company", "name_idx", "key", ["name"])

    # ── data ─────────────────────────────────────────────────────────────────
    print("\nSetting up 'data'...")
    collection("data", "data")
    datetime_attr("data", "date", required=True)
    float_attr("data", "pa")
    float_attr("data", "cb")
    float_attr("data", "per")
    float_attr("data", "peg")
    float_attr("data", "pr")
    float_attr("data", "pb")
    str_attr("data", "c_name", size=60, required=True)
    str_attr("data", "per_rating", size=10)   # green / orange / red
    str_attr("data", "peg_rating", size=10)
    str_attr("data", "pr_rating",  size=10)
    str_attr("data", "pb_rating",  size=10)
    # API-sourced fields (skipped if already exist)
    float_attr("data", "variation")       # % change today
    float_attr("data", "variation_v")     # absolute MAD change
    float_attr("data", "cours_ref")       # yesterday's closing price (reference)
    float_attr("data", "open_price")      # today's opening price
    float_attr("data", "high")            # today's intraday high
    float_attr("data", "low")             # today's intraday low
    float_attr("data", "volume")          # traded volume in MAD
    float_attr("data", "qty_traded")      # number of shares traded
    float_attr("data", "market_cap")      # market capitalisation
    str_attr("data",  "symbol",    size=20)   # ticker (ATW, BCP…)
    str_attr("data",  "data_chart", size=200) # 30-day price points "p1;p2;…|flag"
    index("data", "c_name_idx",   "key",  ["c_name"])
    index("data", "date_idx",     "key",  ["date"])
    index("data", "c_name_date",  "key",  ["c_name", "date"])

    # ── format ───────────────────────────────────────────────────────────────
    print("\nSetting up 'format'...")
    collection("format", "format")
    str_attr("format", "symbol", size=20, required=True)
    str_attr("format", "name",   size=60, required=True)
    index("format", "symbol_idx", "unique", ["symbol"])

    # ── achats ───────────────────────────────────────────────────────────────
    print("\nSetting up 'achats'...")
    collection("achats", "achats")
    datetime_attr("achats", "date", required=True)
    str_attr("achats", "c_name",     size=60,  required=True)
    float_attr("achats", "number",   required=True)
    float_attr("achats", "prix_achat", required=True)
    str_attr("achats", "user_id",    size=36,  required=True)
    index("achats", "user_idx", "key", ["user_id"])

    # ── ventes ───────────────────────────────────────────────────────────────
    print("\nSetting up 'ventes'...")
    collection("ventes", "ventes")
    datetime_attr("ventes", "date", required=True)
    str_attr("ventes", "c_name",      size=60, required=True)
    float_attr("ventes", "number",    required=True)
    float_attr("ventes", "prix_vente", required=True)
    str_attr("ventes", "user_id",     size=36, required=True)
    index("ventes", "user_idx", "key", ["user_id"])

    # ── portefeuille ──────────────────────────────────────────────────────────
    print("\nSetting up 'portefeuille'...")
    collection("portefeuille", "portefeuille")
    str_attr("portefeuille", "c_name",     size=60, required=True)
    float_attr("portefeuille", "quantity",  required=True)
    float_attr("portefeuille", "total_cost", required=True)
    str_attr("portefeuille", "user_id",    size=36, required=True)
    index("portefeuille", "user_idx",        "key",    ["user_id"])
    index("portefeuille", "user_cname_idx",  "unique", ["user_id", "c_name"])

    # ── benefits ──────────────────────────────────────────────────────────────
    print("\nSetting up 'benefits'...")
    collection("benefits", "benefits")
    datetime_attr("benefits", "date",    required=True)
    float_attr("benefits",    "value",   required=True)
    str_attr("benefits",      "user_id", size=36, required=True)
    index("benefits", "user_idx", "key", ["user_id"])

    print("\nDone. All 7 collections are ready.")

if __name__ == "__main__":
    setup()
