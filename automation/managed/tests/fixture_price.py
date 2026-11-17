"""Synthetic company inputs shared by standalone and legacy parity suites."""
from datetime import timedelta
from test_market_frame import CAPTURED


def companies():
    return {letter.lower(): {'name': 'Company ' + letter, 'bpa': 2, 'tc5': 10,
                            'date': (CAPTURED - timedelta(days=10)).isoformat(),
                            'roe': 15, 'na': 1000, 'cp': 10000, 'net_profit': 1}
            for letter in ('A', 'B')}
