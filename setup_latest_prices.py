"""
One-time script: create the 'latest_prices' collection in Appwrite.
One row per company, updated in-place by the scraper on every run.
"""
import warnings; warnings.filterwarnings("ignore")
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.id import ID
import time

PROJECT_ID   = "6a12447800077d5113ae"
API_ENDPOINT = "https://fra.cloud.appwrite.io/v1"
DB_ID        = "myinterpreter"
API_KEY      = input("Appwrite API key: ").strip()

client = Client()
client.set_endpoint(API_ENDPOINT).set_project(PROJECT_ID).set_key(API_KEY)
db = Databases(client)

print("Creating 'latest_prices' collection...")
try:
    db.create_collection(DB_ID, "latest_prices", "latest_prices",
                         document_security=False)
    print("  Created.")
except Exception as e:
    print(f"  Already exists or error: {e}")

time.sleep(1)

def attr(fn, *args, **kwargs):
    try: fn(DB_ID, "latest_prices", *args, **kwargs)
    except Exception as e:
        if "already exist" not in str(e).lower(): print(f"  WARN: {e}")

attr(db.create_string_attribute,   "c_name", 60,  required=True)
attr(db.create_float_attribute,    "pa",          required=True)
attr(db.create_datetime_attribute, "date",        required=True)

time.sleep(2)  # wait for attributes to be ready before creating index

try:
    db.create_index(DB_ID, "latest_prices", "c_name_unique", "unique", ["c_name"])
    print("  Index created.")
except Exception as e:
    print(f"  Index: {e}")

print("Done. Set collection permissions to read('any') in Appwrite console.")
