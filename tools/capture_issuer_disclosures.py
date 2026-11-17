#!/usr/bin/env python3
"""Validate saved official issuer records; --fetch captures missing records.

URLs/host allowlist live in ignored issuer_gaps/sources.local.json. No backend
credentials are loaded or sent. Existing captures are hash-checked and retained.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
from urllib.parse import urlsplit

import requests

from issuer_disclosures import parse_issuer
from stage_supabase import ROOT, sha256


def run(fetch=False):
    root = ROOT/'backup_live_nonpersonal_20261024/issuer_gaps'
    settings = json.loads((root/'sources.local.json').read_text())
    manifest_path = root/'manifest.json'
    manifest = (json.loads(manifest_path.read_text()) if manifest_path.exists()
                else {'captured_at': datetime.now(timezone.utc).isoformat(), 'files': []})
    formats = json.loads((ROOT/'backup_live_recovery_20261022/baseline/format.json').read_text())
    names = {row['symbol']: row['name'] for row in formats}
    indexed = {row['symbol']: row for row in manifest['files']}
    if len(indexed) != len(manifest['files']):
        raise ValueError('Duplicate issuer evidence')
    added = verified = 0
    for symbol, config in settings['issuers'].items():
        if not re.fullmatch(r'[A-Z0-9]{2,8}', symbol) or symbol not in names:
            raise ValueError('Invalid issuer identity')
        url = config['registry_url']
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.hostname not in settings['allowed_hosts']
                or parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment):
            raise ValueError('Unapproved or credential-bearing issuer URL')
        path = root/(symbol+'.html')
        entry = indexed.get(symbol)
        if entry is not None:
            if (entry['path'] != path.name or entry['url'] != url or path.is_symlink()
                    or path.stat().st_size != entry['bytes'] or sha256(path) != entry['sha256']):
                raise ValueError('Saved issuer capture differs from manifest')
            content = path.read_bytes()
        else:
            if not fetch:
                raise ValueError('Missing capture; use --fetch for approved public URLs')
            if path.exists():
                raise ValueError('Refusing unregistered evidence file overwrite')
            with requests.get(url, timeout=(10, 30), allow_redirects=False, stream=True) as response:
                if response.status_code != 200:
                    raise ValueError('Issuer page fetch failed')
                chunks = []
                size = 0
                for block in response.iter_content(65536):
                    size += len(block)
                    if size > 2_000_000:
                        raise ValueError('Issuer page exceeds capture bound')
                    chunks.append(block)
                content = b''.join(chunks)
        disclosure = parse_issuer(content, names[symbol])
        if not disclosure['sector_label'] or not disclosure['shareholders']:
            raise ValueError('Official issuer characteristics incomplete')
        if entry is None:
            path.write_bytes(content)
            manifest['files'].append({'symbol': symbol, 'path': path.name, 'url': url,
                'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest(),
                'captured_at': datetime.now(timezone.utc).isoformat()})
            temporary = root/'manifest.json.tmp'
            temporary.write_text(json.dumps(manifest, indent=2)+'\n')
            temporary.replace(manifest_path)
            added += 1
        verified += 1
    return {'official_issuer_records_verified': verified, 'new_captures': added,
            'backend_writes': False, 'personal_accounts_included': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.fetch)), flush=True)
    except Exception as error:
        print(json.dumps({'ok': False, 'error_category': type(error).__name__}), flush=True)
        raise SystemExit(1)
