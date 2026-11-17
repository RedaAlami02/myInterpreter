#!/usr/bin/env python3
"""Capture fresh company API evidence in a private bounded batch; never write company data."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'automation/managed'))
import profile_refresh
import worker


def write_new(path, body):
    with path.open('xb') as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    return {'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)}


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['config', 'index', 'baseline', 'output']:
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--reviewed-symbol', action='append', default=[])
    args = parser.parse_args(argv)
    previous_mask = os.umask(0o077)
    try:
        output = args.output.resolve()
        vault = (Path.home() / '.local/share/myinterpreter').resolve()
        if not output.is_relative_to(vault) or output == vault or output.exists():
            raise ValueError('PRIVATE_NEW_OUTPUT_REQUIRED')
        config_raw, index_raw, baseline_raw = (p.read_bytes() for p in [args.config,args.index,args.baseline])
        config, index, baseline = (worker.decode(raw) for raw in [config_raw,index_raw,baseline_raw])
        if not isinstance(baseline, dict) or not 1 <= len(baseline) <= profile_refresh.MAX_COMPANIES:
            raise ValueError('INVALID_REFRESH_BATCH')
        output.mkdir(mode=0o700, parents=True, exist_ok=False)
        write_new(output / 'request.json', encoded({'started_at':datetime.now(timezone.utc).isoformat(),
                  'companies':list(baseline), 'config_sha256':hashlib.sha256(config_raw).hexdigest(),
                  'index_sha256':hashlib.sha256(index_raw).hexdigest(),
                  'baseline_sha256':hashlib.sha256(baseline_raw).hexdigest(), 'production_writes':0}))

        def persist(symbol, result):
            folder = output / symbol
            folder.mkdir(mode=0o700, exist_ok=False)
            files = {}
            for key, value in result.items():
                name = 'archive.private.json.gz' if key == 'archive' else key + '.private.json'
                files[name] = write_new(folder / name, value if key == 'archive' else encoded(value))
            write_new(folder / 'manifest.json', encoded(files))
            report = result['report']
            print(json.dumps({'symbol':symbol, 'status':report['status'],
                              'responses':report.get('responses',0), 'production_writes':0}), flush=True)

        result = profile_refresh.capture_batch(config,index,baseline,
                    primary_reviewed=set(args.reviewed_symbol),on_result=persist)
        write_new(output / 'summary.private.json', encoded(result))
        failures = sum(r['status'] != 'CAPTURED_FOR_REVIEW' for r in result['reports'])
        print(json.dumps({'companies':len(result['reports']), 'partial_or_failed':failures,
                          'network_requests':result['network_requests'],
                          'registry_reuses':result['registry_reuses'], 'production_writes':0}),flush=True)
        return 2 if failures else 0
    except Exception:
        print(json.dumps({'status':'FAILED','code':'PRIVATE_REFRESH_CAPTURE_FAILED','production_writes':0}),flush=True)
        return 1
    finally:
        os.umask(previous_mask)


if __name__ == '__main__':
    raise SystemExit(main())
