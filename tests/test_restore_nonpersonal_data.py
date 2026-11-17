from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from restore_nonpersonal_data import artifact, reject_personal_or_secrets, sanitized_diagnostics
from capture_nonpersonal_data import make_profile, year_series


class NonpersonalRestoreTests(unittest.TestCase):
    def test_nested_personal_and_credential_fields_are_rejected(self):
        for key in ["user_id","password","access_token","refresh_token","authorization","api_key"]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                reject_personal_or_secrets({"history":[{"nested":{key:"fixture"}}]})
        reject_personal_or_secrets({"shareholders":[{"name":"Public issuer owner","pct":2}],"bids":[{"price":100,"quantity":5}]})

    def test_diagnostics_exclude_personal_records_and_redact_keys(self):
        rows=[{'$id':'a','$permissions':['user:fixture-owner'],'message':'generic market error'},
              {'$id':'b','context':'account fixture-owner failed'},
              {'$id':'c','message':'request failed with fixture-secret'},
              {'$id':'d','context':'person@example.invalid'}]
        retained,counts=sanitized_diagnostics(rows,{'fixture-owner'},['fixture-secret'])
        self.assertEqual(counts,{'records_retained':2,'personal_records_omitted':2,'credential_records_redacted':1})
        self.assertNotIn('fixture-secret',json.dumps(retained))
        self.assertNotIn('$permissions',retained[0])

    def test_archive_hash_and_path_escape_are_checked_before_import(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            content=b'fixture-public-market-data'
            (root/'market.gz').write_bytes(content)
            entry={"path":"market.gz","bytes":len(content),"sha256":hashlib.sha256(content).hexdigest()}
            self.assertEqual(artifact(root,entry,"market_storage")["source_bytes"],len(content))
            (root/'market.gz').write_bytes(b'changed')
            with self.assertRaises(ValueError):artifact(root,entry,"market_storage")
            with self.assertRaises(ValueError):artifact(root,dict(entry,path='../outside.gz'),"market_storage")

    def test_complete_annual_tables_and_forecasts_survive_without_mixing_fiscal_inputs(self):
        response={"data":{"Société":"Fixture","2024":100,"2025":110,"2026p":120,"2027p":None}}
        self.assertEqual(year_series(response),{"2024":100,"2025":110,"2026p":120})
        raw={"TABLE/ca-corpo":response,"TABLE/tn-corpo":{"data":{"2025":-20}},
             "TABLE/trim-corpo":{"data":{"T12026":30}},"TABLE/sem-corpo":{"data":{"S12026":50}}}
        result={"symbol":"FIX","computed":{"fiscal_year":2024,"revenue":100,"fy_est":2026,"rnpg_est":120}}
        profile=make_profile("FIX","Fixture",result,raw,datetime.now(timezone.utc).isoformat())
        self.assertEqual(profile["annual_statements"]["ca"],response["data"])
        self.assertEqual(profile["charts"]["tn"],{"2025":-20})
        self.assertEqual(profile["computed"]["revenue"],100)
        self.assertEqual(profile["trim"],{"T12026":30})
        self.assertEqual(profile["sem"],{"S12026":50})
        self.assertFalse(profile["historical_baseline_overwritten"])


if __name__ == '__main__': unittest.main()
