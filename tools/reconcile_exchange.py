#!/usr/bin/env python3
"""Reconcile an exchange instrument snapshot with saved application company rows.

Read-only: writes three report files to a new output directory and never contacts
a database. Input snapshot format is the list produced by the coverage scan:
symbol, company, isin, sector, shares, nominal, price, cap, annual_rows,
capital_actions.
"""
import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'automation/managed'))
import exchange_reconciliation as recon


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def saved_rows(companies_path, format_path):
    if not companies_path or not format_path:
        return {}
    companies = load_json(companies_path)
    formats = load_json(format_path)
    by_name = {c['name'].strip().upper(): c for c in companies if isinstance(c.get('name'), str)}
    return {f['symbol']: by_name[f['name'].strip().upper()]
            for f in formats
            if isinstance(f.get('symbol'), str)
            and isinstance(f.get('name'), str)
            and f['name'].strip().upper() in by_name}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', required=True, type=Path)
    parser.add_argument('--companies', type=Path)
    parser.add_argument('--format', type=Path)
    parser.add_argument('--pages-dir', type=Path)
    parser.add_argument('--out-dir', required=True, type=Path)
    parser.add_argument('--as-of')
    args = parser.parse_args()
    try:
        payload = load_json(args.snapshot)
        records = payload.get('companies') if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            raise ValueError('INVALID_SNAPSHOT')
        if args.out_dir.exists() and any(args.out_dir.iterdir()):
            raise ValueError('OUTPUT_DIRECTORY_NOT_EMPTY')
        saved = saved_rows(args.companies, args.format)
        report = recon.reconcile(
            records, pages_dir=str(args.pages_dir) if args.pages_dir else None,
            saved_by_symbol=saved)
        if args.as_of:
            report['summary']['generated_at'] = args.as_of
        args.out_dir.mkdir(parents=True, exist_ok=True)
        (args.out_dir / 'reconciliation.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
        rows = recon.to_csv_rows(report)
        with (args.out_dir / 'reconciliation.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        (args.out_dir / 'reconciliation.md').write_text(
            recon.to_markdown(report), encoding='utf-8')
        print(json.dumps({
            'status': 'OK',
            'summary': report['summary'],
            'outputs': ['reconciliation.json', 'reconciliation.csv', 'reconciliation.md'],
            'production_writes': 0,
        }, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps({'status': 'FAILED',
                          'code': str(error) if isinstance(error, ValueError) else 'RECONCILIATION_FAILED'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
