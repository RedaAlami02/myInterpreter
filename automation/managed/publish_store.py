"""Write-only publish gateway client. CI never receives a privileged key."""

import hashlib
import json
import re
import math
from datetime import datetime, timezone
from urllib.parse import urlsplit

import requests

import app_feed
from worker import AcquisitionError, NoAmbientAuth, utc

RECEIPT = "private-app-publish-receipt/v1"


class AppPublisherStore:
    def __init__(self, url, token, project_reference, *, session=None):
        parsed = urlsplit(url)
        if (
            not re.fullmatch(
                r"https://[a-z0-9]{10,40}\.supabase\.co/functions/v1/private-app-publisher",
                url,
            )
            or parsed.query
            or parsed.fragment
            or not re.fullmatch(r"app_publish_[a-f0-9]{64}", token)
            or not isinstance(project_reference, str)
            or parsed.hostname != project_reference + ".supabase.co"
        ):
            raise AcquisitionError("INVALID_PUBLISHER_CREDENTIAL")
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
                        raise AcquisitionError("PUBLISH_GATEWAY_REJECTED")
                    value = bytearray()
                    for block in response.iter_content(1024):
                        value.extend(block)
                        if len(value) > maximum:
                            raise AcquisitionError("INVALID_PUBLISH_RECEIPT")
                    try:
                        result = json.loads(value)
                    except (ValueError, UnicodeError):
                        raise AcquisitionError("INVALID_PUBLISH_RECEIPT") from None
                    if not isinstance(result, dict):
                        raise AcquisitionError("INVALID_PUBLISH_RECEIPT")
                    return result
            except requests.RequestException:
                if attempt == 1:
                    raise AcquisitionError("PUBLISH_GATEWAY_UNAVAILABLE") from None
        raise AcquisitionError("PUBLISH_GATEWAY_UNAVAILABLE")

    def read_context(self, config, profile, *, clock=lambda: datetime.now(timezone.utc)):
        """Read exact mapped inputs using the price job's own approved pins/lease."""
        import app_publish
        mapping = app_publish.approved_mapping(profile, config)
        fields_sha = profile.get('application_fields_sha256')
        if not isinstance(fields_sha, str) or not re.fullmatch(r'[a-f0-9]{64}', fields_sha):
            raise AcquisitionError('APPLICATION_FIELDS_PIN_REQUIRED')
        pins = {'provider_namespace': config['provider_namespace'],
                'mapping_sha256': profile['mapping_sha256'],
                'recipe_sha256': profile['recipe_sha256'],
                'application_fields_sha256': fields_sha}
        value = self._post(app_feed.canonical({'operation': 'read_price_company_context',
            'mapping_document': app_feed.canonical(mapping), **pins}).encode(), maximum=524288)
        required = {'name', 'bpa', 'tc5', 'roe', 'na', 'cp', 'net_profit', 'date', 'available_at'}
        expected = {r['company_id']: r['c_name'] for r in mapping['stocks']}
        try:
            observed = utc(value['observed_at'])
            age = (clock() - observed).total_seconds()
            if (set(value) != {'contract', 'observed_at', 'price_companies'} | set(pins)
                    or value['contract'] != 'private-price-company-context/v1'
                    or any(value[k] != v for k, v in pins.items())
                    or not -30 <= age <= 600 or not isinstance(value['price_companies'], dict)
                    or set(value['price_companies']) != set(expected)):
                raise ValueError()
            for identifier, row in value['price_companies'].items():
                if not isinstance(row, dict) or set(row) != required or row['name'] != expected[identifier]:
                    raise ValueError()
                for key in required - {'name', 'date', 'available_at'}:
                    if row[key] is not None and (type(row[key]) not in (int, float)
                            or not math.isfinite(row[key]) or abs(row[key]) > 1e15):
                        raise ValueError()
                for key in ('date', 'available_at'):
                    if row[key] is not None and utc(row[key]) > observed:
                        raise ValueError()
                if row['date'] is not None and (row['available_at'] is None
                        or utc(row['available_at']) < utc(row['date'])):
                    raise ValueError()
        except (ValueError, KeyError, TypeError, OverflowError, AcquisitionError):
            raise AcquisitionError('INVALID_PRICE_COMPANY_CONTEXT') from None
        return value

    def publish(self, candidate, mapping, *, application_rows=None):
        # The boundary re-derives nothing: only an exact builder output is offered.
        document = app_feed.canonical(candidate)
        mapping_document = app_feed.canonical(mapping)
        mapping_sha256 = app_feed.fingerprint(mapping)
        if candidate.get("mapping_sha256") != mapping_sha256:
            raise AcquisitionError("MAPPING_PIN_MISMATCH")
        payload_sha256 = hashlib.sha256(document.encode()).hexdigest()
        request = {
            "document": document,
            "mapping_document": mapping_document,
            "mapping_sha256": mapping_sha256,
            "sha256": payload_sha256,
        }
        application_sha = None
        if application_rows is not None:
            if application_rows.get('quote_payload_sha256') != payload_sha256:
                raise AcquisitionError('APPLICATION_QUOTE_HEAD_MISMATCH')
            application_document = app_feed.canonical(application_rows)
            application_sha = hashlib.sha256(application_document.encode()).hexdigest()
            request.update(application_document=application_document, application_sha256=application_sha)
        value = self._post(app_feed.canonical(request).encode())
        if (
            value.get("contract") != RECEIPT
            or value.get("status") != "PUBLISHED"
            or value.get("sha256") != payload_sha256
            or value.get("captured_at") != candidate.get("captured_at")
            or value.get("prediction_eligible") is not False
            or value.get("portfolio_valuation_eligible") is not False
            or (application_sha is not None and value.get('application_rows_sha256') != application_sha)
        ):
            raise AcquisitionError("INVALID_PUBLISH_RECEIPT")
        return {
            "status": "PUBLISHED",
            "sha256": payload_sha256,
            "captured_at": value["captured_at"],
            **({'application_rows_sha256': application_sha} if application_sha is not None else {}),
        }
