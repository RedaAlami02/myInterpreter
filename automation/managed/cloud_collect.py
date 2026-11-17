#!/usr/bin/env python3
"""Wire existing collectors to one restored private runner state."""
import argparse
import os
from pathlib import Path
import tempfile

import run_collection
import runner_checkpoint
import worker


def run(kind,state,*,symbol=None):
    previous=os.environ.get('APP_CHECKPOINT_ROOT')
    os.environ['APP_CHECKPOINT_ROOT']=str(state)
    try:return _run(kind,state,symbol=symbol)
    finally:
        if previous is None:os.environ.pop('APP_CHECKPOINT_ROOT',None)
        else:os.environ['APP_CHECKPOINT_ROOT']=previous


def _run(kind, state, *, symbol=None, due=False):
    if kind == 'official_close':
        import json,official_close_collect
        os.environ['APP_ARCHIVE_SPOOL_DIR'] = str(state / 'archive')
        config = worker.decode(os.environ['APP_OFFICIAL_CLOSE_CONFIG'])
        result = official_close_collect.run(config,state)
        print(json.dumps(result))
        return 0 if result['status'] in ['COMPLETE','ALREADY_COMPLETE','OUTSIDE_WINDOW','AWAITING_INDEPENDENT_REVIEW'] else 2
    if kind not in run_collection.COLLECTORS:
        raise worker.AcquisitionError('INVALID_COLLECTION_KIND')
    if (kind == 'fundamentals') != bool(symbol) and not (due and kind == 'fundamentals'):
        raise worker.AcquisitionError('FUNDAMENTAL_SYMBOL_REQUIRED')
    state = runner_checkpoint.private_directory(state)
    runner_checkpoint.inventory(state)
    import receipt_history
    receipt_history.compact(state)
    # Recipe material never enters the checkpoint or workspace artifact tree.
    source = os.environ[{'quotes': 'APP_MARKET_CONFIG', 'depth': 'APP_DEPTH_CONFIG',
                         'dividends': 'APP_DIVIDEND_CONFIG', 'fundamentals': 'APP_FUNDAMENTAL_CONFIG'}[kind]]
    os.environ['APP_ARCHIVE_SPOOL_DIR'] = str(state / 'archive')
    os.environ['APP_PRICE_PUBLICATION_SPOOL_DIR'] = str(state / 'quotes')
    with tempfile.TemporaryDirectory(prefix='private-job-config-') as temporary:
        folder = Path(temporary)
        saved = {}

        def secret(name):
            if name in saved:
                return saved[name]
            value = os.environ.get(name)
            if not value:
                raise worker.AcquisitionError('PRIVATE_JOB_CONFIGURATION_MISSING')
            target = folder / name.lower()
            runner_checkpoint.write_new(target, value.encode())
            saved[name] = str(target)
            return saved[name]

        config = folder / 'source.json'
        runner_checkpoint.write_new(config, source.encode())
        args = [kind, '--config', str(config)]
        if kind == 'fundamentals':
            import enrichment_jobs
            import json
            result=enrichment_jobs.execute(config,secret('APP_FUNDAMENTAL_INDEX'),state/'enrichment',
                                            max_jobs=1,only_symbol=symbol)
            progress = due and not any(result.get(key,0) for key in ['failed','incomplete','pending'])
            if progress and result['status'] != 'COMPLETE':
                result = {**result, 'status':'PROGRESS'}
            print(json.dumps(result))
            return 0 if result['status']=='COMPLETE' or progress else 2
        if kind == 'dividends':
            args.extend(['--publish-index',secret('APP_DIVIDEND_INDEX'),
                         '--publication-spool',str(state/'dividends')])
        if kind == 'quotes':
            # This workflow requires the full existing price/publication path,
            # rather than silently completing raw acquisition only.
            args.extend(['--publish-profile', secret('APP_PUBLISH_PROFILE'),
                         '--publication-spool', str(state / 'quotes'),
                         '--application-bindings', secret('APP_APPLICATION_BINDINGS')])
            if os.environ.get('APP_ENRICHMENT_CONFIG'):
                args.extend(['--enrichment-config', secret('APP_ENRICHMENT_CONFIG'),
                             '--enrichment-index', secret('APP_COMPANY_INDEX'),
                             '--enrichment-spool', str(state / 'enrichment'),
                             '--enrichment-max-jobs', '1'])
        return run_collection.main(args)


def main(argv=None):
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=sorted(run_collection.COLLECTORS) + ['auto','official_close'])
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--symbol')
    args = parser.parse_args(argv)
    previous_mask = os.umask(0o077)
    try:
        if args.kind == 'auto':
            import recurring_schedule
            from datetime import datetime, timezone
            import json
            if os.environ.get('APP_SCHEDULE_CONTRACT') != recurring_schedule.CONTRACT or args.symbol:
                raise worker.AcquisitionError('RECURRING_SCHEDULE_CONTRACT_REQUIRED')
            results = {}
            previous = os.environ.get('APP_CHECKPOINT_ROOT')
            os.environ['APP_CHECKPOINT_ROOT'] = str(args.state)
            try:
                for kind in recurring_schedule.due(datetime.now(timezone.utc)):
                    if kind == 'official_close' and os.environ.get('APP_OFFICIAL_CLOSE_COLLECTION_ENABLED') != 'true':
                        continue
                    try:
                        results[kind] = _run(kind,args.state,due=True)
                    except Exception as error:
                        import re
                        code = str(error) if isinstance(error, worker.AcquisitionError) else 'PRIVATE_JOB_FAILED'
                        if not re.fullmatch('[A-Z][A-Z0-9_]{0,79}',code):code='PRIVATE_JOB_FAILED'
                        print(json.dumps({'status':'FAILED','kind':kind,'code':code}))
                        results[kind] = 1
                print(json.dumps({'status':'COMPLETE' if all(v == 0 for v in results.values()) else 'DEGRADED', 'jobs':results}))
                return 0 if all(v == 0 for v in results.values()) else 2
            finally:
                if previous is None: os.environ.pop('APP_CHECKPOINT_ROOT',None)
                else: os.environ['APP_CHECKPOINT_ROOT'] = previous
        return run(args.kind, args.state, symbol=args.symbol)
    except Exception as error:
        print(json.dumps({'status': 'FAILED', 'code': str(error) if isinstance(error, worker.AcquisitionError) else 'PRIVATE_JOB_FAILED'}))
        return 1
    finally:
        os.umask(previous_mask)


if __name__ == '__main__':
    raise SystemExit(main())
