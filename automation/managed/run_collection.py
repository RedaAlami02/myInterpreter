#!/usr/bin/env python3
"""Dispatch only versioned collectors. Legacy recipes require an explicit migration."""

import argparse

import depth_collect
import dividend_collect
import fundamental_collect
import market_collect

COLLECTORS = {
    "quotes": market_collect,
    "depth": depth_collect,
    "dividends": dividend_collect,
    "fundamentals": fundamental_collect,
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=sorted(COLLECTORS))
    parser.add_argument("--config")
    parser.add_argument("--isolated-store")
    parser.add_argument("--publish-profile")
    parser.add_argument("--publication-spool")
    for name in ['companies','application-bindings','company-index']:
        parser.add_argument('--'+name)
    parser.add_argument("--symbol")
    parser.add_argument('--publish-index')
    for name in ('enrichment-config','enrichment-index','enrichment-spool','enrichment-max-jobs'):
        parser.add_argument('--'+name)
    args = parser.parse_args(argv)
    if args.publish_profile is not None and args.kind != "quotes":
        parser.error("--publish-profile is only valid for quotes")
    if args.publication_spool is not None and args.kind not in ['quotes','dividends']:
        parser.error('--publication-spool is only valid for quote/dividend publication')
    if args.kind != 'quotes' and any(getattr(args,n) is not None for n in
            ('enrichment_config','enrichment_index','enrichment_spool','enrichment_max_jobs','companies','application_bindings','company_index')):
        parser.error('Enrichment options are only valid for quotes')
    if args.kind == "fundamentals" and not args.symbol:
        parser.error("--symbol is required for fundamentals")
    if args.kind != "fundamentals" and args.symbol is not None:
        parser.error("--symbol is only valid for fundamentals")
    forwarded = []
    names = ["config", "isolated_store"]
    if args.kind == "quotes":
        names.append("publish_profile")
        names.append("publication_spool")
        names.extend(['companies','application_bindings','company_index'])
        names.extend(['enrichment_config','enrichment_index','enrichment_spool','enrichment_max_jobs'])
    if args.kind == "fundamentals":
        names.append("symbol")
    if args.kind=='dividends':
        names.extend(['publish_index','publication_spool'])
    elif args.publish_index is not None:
        parser.error('--publish-index is only valid for dividends')
    for name in names:
        value = getattr(args, name)
        if value is not None:
            forwarded.extend(["--" + name.replace("_", "-"), value])
    return COLLECTORS[args.kind].main(forwarded)


if __name__ == "__main__":
    raise SystemExit(main())
