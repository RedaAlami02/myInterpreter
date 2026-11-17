"""Write-only gateway client. CI never receives a project-wide credential."""

import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

import requests

from worker import AcquisitionError, NoAmbientAuth, packed, unpacked
from outbox import Outbox


class ArchiveGatewayStore:
    def __init__(self, url, token, project_reference, *, session=None, spool_dir=None):
        parsed = urlsplit(url)
        if (
            not re.fullmatch(
                r"https://[a-z0-9]{10,40}\.supabase\.co/functions/v1/private-market-archive",
                url,
            )
            or parsed.query
            or parsed.fragment
            or not re.fullmatch(r"arc_write_[a-f0-9]{64}", token)
            or not isinstance(project_reference, str)
            or parsed.hostname != project_reference + ".supabase.co"
        ):
            raise AcquisitionError("INVALID_ARCHIVE_CREDENTIAL")
        self.url, self.token = url, token
        self.http = session or requests
        self.outbox = Outbox(
            spool_dir
            or os.environ.get("APP_ARCHIVE_SPOOL_DIR")
            or Path(tempfile.gettempdir())
            / ("private-market-outbox-" + project_reference)
        )

    def _post(self, body, content_type):
        for attempt in range(2):
            try:
                with self.http.post(
                    self.url,
                    data=body,
                    headers={
                        "Authorization": "Bearer " + self.token,
                        "Content-Type": content_type,
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
                        raise AcquisitionError("ARCHIVE_GATEWAY_REJECTED")
                    value = bytearray()
                    for block in response.iter_content(1024):
                        value.extend(block)
                        if len(value) > 4096:
                            raise AcquisitionError("INVALID_ARCHIVE_RECEIPT")
                    try:
                        result = json.loads(value)
                    except (ValueError, UnicodeError):
                        raise AcquisitionError("INVALID_ARCHIVE_RECEIPT") from None
                    if not isinstance(result, dict):
                        raise AcquisitionError("INVALID_ARCHIVE_RECEIPT")
                    return result
            except requests.RequestException:
                if attempt == 1:
                    raise AcquisitionError("ARCHIVE_GATEWAY_UNAVAILABLE") from None
        raise AcquisitionError("ARCHIVE_GATEWAY_UNAVAILABLE")

    def official_complete(self, provider, digest, document_sha):
        value = self._post(json.dumps({'operation':'official_close_status','provider_namespace':provider,
            'archive_sha256':digest,'document_sha256':document_sha}).encode(),'application/json')
        if value.get('contract') != 'private-archive-receipt/v1' or type(value.get('complete')) is not bool:
            raise AcquisitionError('INVALID_ARCHIVE_RECEIPT')
        return value['complete']

    def complete(self, provider, kind, slot):
        value = self._post(
            json.dumps(
                {
                    "operation": "slot_complete",
                    "provider_namespace": provider,
                    "kind": kind,
                    "slot": slot,
                }
            ).encode(),
            "application/json",
        )
        if (
            value.get("contract") != "private-archive-receipt/v1"
            or type(value.get("complete")) is not bool
        ):
            raise AcquisitionError("INVALID_ARCHIVE_RECEIPT")
        return value["complete"]

    def subject_complete(self, provider, kind, slot, subject):
        value = self._post(json.dumps({'operation':'subject_slot_complete', 'provider_namespace':provider,
            'kind':kind, 'slot':slot, 'subject_key':subject}).encode(), 'application/json')
        if value.get('contract') != 'private-archive-receipt/v1' or type(value.get('complete')) is not bool:
            raise AcquisitionError('INVALID_ARCHIVE_RECEIPT')
        return value['complete']

    def admit_subject(self, provider, subject, *, projection=False):
        value = self._post(json.dumps({"operation": "subject_acquisition_admission",
            "provider_namespace": provider, "subject_key": subject,
            "projection": projection}).encode(), "application/json")
        if value.get("contract") != "private-archive-receipt/v1" or type(value.get("admitted")) is not bool:
            raise AcquisitionError("INVALID_ARCHIVE_RECEIPT")
        return value["admitted"]

    def admit(self, provider, kind, slot, *, shadow=False, projection=False):
        value = self._post(json.dumps({'operation':'acquisition_admission',
            'provider_namespace':provider,'kind':kind,'slot':slot,
            'shadow':shadow,'projection':projection}).encode(), 'application/json')
        if value.get('contract') != 'private-archive-receipt/v1' or type(value.get('admitted')) is not bool:
            raise AcquisitionError('INVALID_ARCHIVE_RECEIPT')
        return value['admitted']

    def save(self, envelope):
        digest, blob = packed(envelope)
        return self.save_blob(digest, blob)

    def save_blob(self, digest, blob):
        envelope = unpacked(digest, blob)
        # Replays/diagnostics can never leave isolated storage through this client.
        if envelope.get("execution") != "CURRENT_ACQUISITION":
            raise AcquisitionError("REMOTE_ARCHIVE_REQUIRES_CURRENT_ACQUISITION")
        self.outbox.put(digest, blob)
        self._send(digest, blob)
        return digest

    def flush_pending(self):
        completed = 0
        for path in self.outbox.entries():
            blob = self.outbox.read(path)
            self._send(path.name[:64], blob)
            completed += 1
        return completed

    def _send(self, digest, blob):
        value = self._post(blob, "application/gzip")
        if (
            value.get("contract") != "private-archive-receipt/v1"
            or value.get("status") != "STORED"
            or value.get("sha256") != digest
            or type(value.get("bytes")) is not int
            or value["bytes"] != len(blob)
            or value.get("prediction_eligible") is not False
        ):
            raise AcquisitionError("INVALID_ARCHIVE_RECEIPT")
        self.outbox.acknowledge(digest)
