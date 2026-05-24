"""
One-time migration: MySQL (stock DB) → Appwrite collections.

Before running:
  1. In Appwrite Console → Auth → Users → Create User (email + password)
     Copy the resulting User ID (looks like: 6a1abc123...)
  2. In Appwrite Console → Settings → API Keys → Create Key
     Scopes needed: databases.read, databases.write, documents.read, documents.write
  3. Run appwrite_setup.py first so all collections exist

Usage:
    pip install appwrite mysql-connector-python
    python3 migrate.py
"""

import time
import mysql.connector
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.id import ID

# ── config ────────────────────────────────────────────────────────────────────

PROJECT_ID  = "6a12447800077d5113ae"
API_ENDPOINT = "https://fra.cloud.appwrite.io/v1"
DB_ID       = "myinterpreter"

MYSQL_CONFIG = dict(host="localhost", port=3306, user="root", password="", database="stock")

# ── helpers ───────────────────────────────────────────────────────────────────

def to_iso(d):
    """Convert a MySQL date/datetime to ISO 8601 string, or None for invalid dates."""
    if d is None:
        return None
    s = str(d)
    if s.startswith("0000"):
        return None
    # mysql-connector returns datetime.date or datetime.datetime objects
    try:
        return d.isoformat() + "T00:00:00.000+00:00" if hasattr(d, "year") else None
    except Exception:
        return None

def insert_all(db, col_id, rows, label):
    total = len(rows)
    for i, data in enumerate(rows, 1):
        clean = {k: v for k, v in data.items() if v is not None}
        for attempt in range(5):
            try:
                db.create_document(DB_ID, col_id, ID.unique(), clean)
                break
            except Exception as e:
                if attempt == 4:
                    raise
                wait = 2 ** attempt
                print(f"  {label}: row {i} failed ({e}), retrying in {wait}s...")
                time.sleep(wait)
        if i % 50 == 0 or i == total:
            print(f"  {label}: {i}/{total}")

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    api_key = input("Appwrite API key: ").strip()
    user_id = input("Your Appwrite User ID: ").strip()

    client = Client()
    client.set_endpoint(API_ENDPOINT).set_project(PROJECT_ID).set_key(api_key)
    db = Databases(client)

    conn = mysql.connector.connect(**MYSQL_CONFIG)
    cur = conn.cursor(dictionary=True)

    # ── company ──────────────────────────────────────────────────────────────
    print("\nMigrating company...")
    cur.execute("SELECT NAME, BPA, TC5, ROE, NA, CP, DATE FROM company")
    rows = [
        dict(name=r["NAME"], bpa=r["BPA"], tc5=r["TC5"], roe=r["ROE"],
             na=r["NA"], cp=r["CP"], date=to_iso(r["DATE"]))
        for r in cur.fetchall()
    ]
    insert_all(db, "company", rows, "company")

    # ── data ─────────────────────────────────────────────────────────────────
    print("\nMigrating data (may take a while)...")
    cur.execute("SELECT DATE, PA, CB, PER, PEG, PR, PB, C_NAME FROM data")
    rows = [
        dict(date=to_iso(r["DATE"]), pa=r["PA"], cb=r["CB"], per=r["PER"],
             peg=r["PEG"], pr=r["PR"], pb=r["PB"], c_name=r["C_NAME"])
        for r in cur.fetchall()
    ]
    insert_all(db, "data", rows, "data")

    # ── format ───────────────────────────────────────────────────────────────
    print("\nMigrating format...")
    cur.execute("SELECT NAME, SYMBOL FROM format")
    rows = [dict(name=r["NAME"], symbol=r["SYMBOL"]) for r in cur.fetchall()]
    insert_all(db, "format", rows, "format")

    # ── achats ───────────────────────────────────────────────────────────────
    print("\nMigrating achats...")
    cur.execute("SELECT DATE, C_NAME, NUMBER, PRIX_ACHAT FROM achats WHERE ID_USER = 1")
    rows = [
        dict(date=to_iso(r["DATE"]), c_name=r["C_NAME"],
             number=float(r["NUMBER"]), prix_achat=float(r["PRIX_ACHAT"]),
             user_id=user_id)
        for r in cur.fetchall()
    ]
    insert_all(db, "achats", rows, "achats")

    # ── ventes ───────────────────────────────────────────────────────────────
    print("\nMigrating ventes...")
    cur.execute("SELECT DATE, C_NAME, NUMBER, PRIX_VENTE FROM ventes WHERE ID_USER = 1")
    rows = [
        dict(date=to_iso(r["DATE"]), c_name=r["C_NAME"],
             number=float(r["NUMBER"]), prix_vente=float(r["PRIX_VENTE"]),
             user_id=user_id)
        for r in cur.fetchall()
    ]
    insert_all(db, "ventes", rows, "ventes")

    # ── portefeuille ──────────────────────────────────────────────────────────
    print("\nMigrating portefeuille...")
    cur.execute("SELECT C_NAME, NUMBER, MONTANT FROM portefeuille WHERE ID_USER = 1")
    rows = [
        dict(c_name=r["C_NAME"], quantity=float(r["NUMBER"]),
             total_cost=float(r["MONTANT"]), user_id=user_id)
        for r in cur.fetchall()
    ]
    insert_all(db, "portefeuille", rows, "portefeuille")

    # ── benefits ──────────────────────────────────────────────────────────────
    print("\nMigrating benefits...")
    cur.execute("SELECT DATE, VALUE FROM benefits WHERE ID_USER = 1")
    rows = [
        dict(date=to_iso(r["DATE"]), value=float(r["VALUE"]), user_id=user_id)
        for r in cur.fetchall()
    ]
    insert_all(db, "benefits", rows, "benefits")

    cur.close()
    conn.close()
    print("\nMigration complete.")

if __name__ == "__main__":
    main()
