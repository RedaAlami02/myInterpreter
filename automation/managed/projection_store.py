"""Write-only projection gateway client. CI never receives a privileged key."""

import hashlib
import json
from datetime import datetime, timezone
import math
import re
from urllib.parse import urlsplit

import requests

from worker import AcquisitionError, NoAmbientAuth, utc

RECEIPT = "projection-receipt/v1"
KINDS = {"dividends", "fundamentals"}
PRICE_FIELDS={'name','bpa','tc5','roe','na','cp','net_profit','date','available_at'}


class ProjectionPublisher:
    def __init__(self, url, token, project_reference, *, session=None):
        parsed = urlsplit(url)
        if (
            not re.fullmatch(
                r"https://[a-z0-9]{10,40}\.supabase\.co/functions/v1/private-projection-publisher",
                url,
            )
            or parsed.query
            or parsed.fragment
            or not re.fullmatch(r"proj_publish_[a-f0-9]{64}", token)
            or not isinstance(project_reference, str)
            or parsed.hostname != project_reference + ".supabase.co"
        ):
            raise AcquisitionError("INVALID_PROJECTION_CREDENTIAL")
        self.url, self.token = url, token
        self.http = session or requests

    def _post(self, body, *, maximum=4096):
        for attempt in range(2):
            try:
                with self.http.post(
                    self.url,
                    data=body,
                    headers={
                        "Authorization": "Bearer " + self.token,
                        "Content-Type": "application/json",
                    },
                    auth=NoAmbientAuth(),
                    timeout=(8, 25),
                    allow_redirects=False,
                    stream=True,
                ) as response:
                    if (
                        response.status_code in {429, 500, 502, 503, 504}
                        and attempt == 0
                    ):
                        continue
                    if response.status_code != 200:
                        raise AcquisitionError("PROJECTION_GATEWAY_REJECTED")
                    value = bytearray()
                    for block in response.iter_content(1024):
                        value.extend(block)
                        if len(value) > maximum:
                            raise AcquisitionError("INVALID_PROJECTION_RECEIPT")
                    try:
                        result = json.loads(value)
                    except (ValueError, UnicodeError):
                        raise AcquisitionError("INVALID_PROJECTION_RECEIPT") from None
                    if not isinstance(result, dict):
                        raise AcquisitionError("INVALID_PROJECTION_RECEIPT")
                    return result
            except requests.RequestException:
                if attempt == 1:
                    raise AcquisitionError("PROJECTION_GATEWAY_UNAVAILABLE") from None
        raise AcquisitionError("PROJECTION_GATEWAY_UNAVAILABLE")

    def read_context(self, provider, index_sha256, *, clock=lambda: datetime.now(timezone.utc)):
        if not re.fullmatch(r'feed_[a-f0-9]{16}', provider) or not re.fullmatch(r'[a-f0-9]{64}', index_sha256):
            raise AcquisitionError('INVALID_CONTEXT_REQUEST')
        value = self._post(json.dumps({'operation':'read_enrichment_context',
            'provider_namespace':provider,'index_sha256':index_sha256}).encode(), maximum=524288)
        try:
            age = (clock() - utc(value['observed_at'])).total_seconds()
            version=value.get('contract')
            expected={'contract','provider_namespace','index_sha256','observed_at','companies'}
            if version=='private-enrichment-context/v2': expected.add('price_companies')
            if (set(value) != expected
                    or version not in {'private-enrichment-context/v1','private-enrichment-context/v2'}
                    or value['provider_namespace'] != provider or value['index_sha256'] != index_sha256
                    or not -30 <= age <= 600 or not isinstance(value['companies'],dict)
                    or len(value['companies']) > 2000):
                raise ValueError()
            for name, row in value['companies'].items():
                if (not isinstance(name,str) or not 1 <= len(name) <= 200 or any(ord(c)<32 for c in name)
                        or not isinstance(row,dict) or set(row) != {'bpa','sector','fiscal_year'}
                        or (row['bpa'] is not None and (type(row['bpa']) not in (int,float) or not math.isfinite(row['bpa']) or abs(row['bpa'])>1e15))
                        or (row['sector'] is not None and (not isinstance(row['sector'],str) or len(row['sector'])>200 or any(ord(c)<32 for c in row['sector'])))
                        or (row['fiscal_year'] is not None and (type(row['fiscal_year']) is not int or not 1900<=row['fiscal_year']<=2100))):
                    raise ValueError()
            if version=='private-enrichment-context/v2':
                if not isinstance(value['price_companies'],dict) or len(value['price_companies'])>2000: raise ValueError()
                for identifier,row in value['price_companies'].items():
                    if not isinstance(identifier,str) or not identifier or not isinstance(row,dict) or set(row)!=PRICE_FIELDS:
                        raise ValueError()
                    if row['name'] not in value['companies']: raise ValueError()
                    for key in PRICE_FIELDS-{'name','date','available_at'}:
                        if row[key] is not None and (type(row[key]) not in (int,float) or not math.isfinite(row[key]) or abs(row[key])>1e15): raise ValueError()
                    for key in ('date','available_at'):
                        if row[key] is not None and utc(row[key])>clock(): raise ValueError()
        except (ValueError,KeyError,TypeError,OverflowError):
            raise AcquisitionError('INVALID_ENRICHMENT_CONTEXT') from None
        return value

    def publish(self, document):
        # The exact prepared document is sent; no re-serialization changes the hash.
        if not isinstance(document, str):
            raise AcquisitionError("INVALID_PROJECTION_DOCUMENT")
        if len(document.encode()) > 2 * 1024 * 1024:
            raise AcquisitionError("INVALID_PROJECTION_DOCUMENT")
        try:
            candidate = json.loads(document)
            contract = candidate.get('contract')
            if contract == 'dividend-projection/v1' and isinstance(candidate.get('rows'), list):
                expected_kind, expected_count = 'dividends', len(candidate['rows'])
            elif contract == 'fundamental-projection/v1' and isinstance(candidate.get('fields'), dict):
                expected_kind, expected_count = 'fundamentals', len(candidate['fields'])
            else:
                raise ValueError('Unsupported document')
        except (ValueError, AttributeError):
            raise AcquisitionError("INVALID_PROJECTION_DOCUMENT") from None
        payload_sha256 = hashlib.sha256(document.encode()).hexdigest()
        value = self._post(
            json.dumps(
                {"document": document, "sha256": payload_sha256},
                separators=(",", ":"),
            ).encode()
        )
        if (
            value.get("contract") != RECEIPT
            or value.get("status") != "PUBLISHED"
            or value.get("kind") != expected_kind
            or value.get("sha256") != payload_sha256
            or type(value.get("records")) is not int
            or value.get('records') != expected_count
        ):
            raise AcquisitionError("INVALID_PROJECTION_RECEIPT")
        return {
            "status": "PUBLISHED",
            "kind": value["kind"],
            "sha256": payload_sha256,
            "records": value["records"],
        }
