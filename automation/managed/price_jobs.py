"""Original price job's listing/enrichment decisions, without SDK or side effects.

Inputs use application names/symbols, not native provider bindings. The caller
persists approved listing changes before dispatching enrichment through the
existing fundamental collector. Merely planning work never fetches or publishes.
"""

from datetime import datetime, timezone


def new_listings(instruments, symbol_to_name, companies):
    """Missing mapping + bare company, as in the old job; flag identity conflicts.

    ``instruments`` are normalized {symbol, name} catalog rows. Unlike the old
    first-row-wins behavior, contradictory catalog identities require review.
    Existing mappings and company records are never replaced.
    """
    names = {}
    for row in instruments:
        symbol, name = row.get('symbol'), row.get('name')
        if isinstance(symbol, str) and symbol and isinstance(name, str) and name.strip():
            names.setdefault(symbol, set()).add(name.strip())
    additions, conflicts = [], []
    # Detect two unknown symbols claiming the same name before proposing either.
    owners = {}
    for symbol, choices in names.items():
        for name in choices:
            owners.setdefault(name, set()).add(symbol)
    for symbol, name in symbol_to_name.items():
        owners.setdefault(name, set()).add(symbol)
    for symbol, choices in names.items():
        if len(choices) != 1:
            conflicts.append({'symbol': symbol, 'reason': 'CONFLICTING_CATALOG_NAMES'})
            continue
        name = next(iter(choices))
        if symbol in symbol_to_name:
            if symbol_to_name[symbol] != name:
                conflicts.append({'symbol': symbol, 'reason': 'EXISTING_MAPPING_DIFFERS'})
            continue
        if len(owners[name]) != 1:
            conflicts.append({'symbol': symbol, 'reason': 'COMPANY_NAME_HAS_ANOTHER_SYMBOL'})
            continue
        additions.append({'format': {'symbol': symbol, 'name': name},
                          'company': None if name in companies else {'name': name}})
    return {'additions': additions, 'conflicts': conflicts}


def enrichment_jobs(companies, symbol_to_name, observed_at, *, initial_limit=5, refresh_limit=5):
    """Port the old job's capped onboarding and first-quarter-hour refresh.

    A sector marks completed enrichment even if earnings are unavailable. Initial
    requests and the fiscal-year refresh have separate limits, as originally.
    ``observed_at`` is explicit so tests/replays never consult the current clock.
    """
    if not isinstance(observed_at, datetime) or observed_at.tzinfo is None:
        raise ValueError('Aware observation time required')
    if any(type(limit) is not int or not 0 <= limit <= 5 for limit in (initial_limit, refresh_limit)):
        raise ValueError('Enrichment limit must be between zero and five')
    name_to_symbol = {}
    for symbol, name in symbol_to_name.items():
        if name in name_to_symbol and name_to_symbol[name] != symbol:
            raise ValueError('Ambiguous company symbol')
        name_to_symbol[name] = symbol
    jobs, triggered = [], set()
    for name, company in companies.items():
        if len(jobs) >= initial_limit:
            break
        if not company.get('bpa') and not company.get('sector') and name_to_symbol.get(name):
            jobs.append({'name': name, 'symbol': name_to_symbol[name], 'reason': 'INITIAL'})
            triggered.add(name)
    if observed_at.astimezone(timezone.utc).minute < 15:
        stale = sorted(((company.get('fiscal_year') or 0, name)
                        for name, company in companies.items()
                        if name not in triggered and name_to_symbol.get(name)), key=lambda item: item[0])
        jobs.extend({'name': name, 'symbol': name_to_symbol[name], 'reason': 'REFRESH'}
                    for _, name in stale[:refresh_limit])
    return jobs
