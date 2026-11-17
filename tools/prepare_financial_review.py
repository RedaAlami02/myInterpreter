#!/usr/bin/env python3
"""Prepare exact, unpromoted financial facts from a captured archive. No remote writes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'automation/managed'))
import financial_evidence
import worker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['config', 'index', 'archive', 'output']:
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--sha256', required=True)
    args = parser.parse_args()
    try:
        vault = Path.home() / '.local/share/myinterpreter'
        output = args.output.resolve()
        if not output.is_relative_to(vault.resolve()) or args.output.exists():
            raise ValueError('PRIVATE_NEW_OUTPUT_REQUIRED')
        blob = args.archive.read_bytes()
        if hashlib.sha256(blob).hexdigest() != args.sha256:
            raise ValueError('ARCHIVE_HASH_MISMATCH')
        result = financial_evidence.build(blob, args.sha256,
            worker.decode(args.config.read_bytes()), worker.decode(args.index.read_bytes()))
        output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.umask(0o077)
        with output.open('x') as stream:
            json.dump(result, stream, ensure_ascii=False, sort_keys=True)
        print(json.dumps({'status':'REVIEW_REQUIRED','reported_facts':len(result['reported_facts']),
            'estimated_facts':len(result['estimated_facts']),'issues':len(result['issues']),
            'publication_eligible':False,'production_writes':0}))
        return 0
    except Exception as error:
        print(json.dumps({'status':'FAILED','code':str(error) if isinstance(error,ValueError)
            and str(error) in ['PRIVATE_NEW_OUTPUT_REQUIRED','ARCHIVE_HASH_MISMATCH'] else 'REVIEW_PREPARATION_FAILED'}))
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
