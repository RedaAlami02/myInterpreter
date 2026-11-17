#!/usr/bin/env python3
"""Run local PHP regression suites, without live credentials or backend requests."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    failed = 0
    for path in sorted((ROOT / 'tests').glob('*_test.php')):
        if path.name == 'lcp_queries_test.php':
            print(f'SKIP {path.name}: legacy live-backend integration test')
            continue
        command = ['php']
        if path.name == 'partial_curl_test.php':
            command += ['-d', 'disable_functions=curl_multi_exec']
        try:
            result = subprocess.run(command + [str(path)], cwd=ROOT,
                                    capture_output=True, text=True, timeout=30)
            passed = result.returncode == 0
        except subprocess.TimeoutExpired:
            passed = False
        print(f'{"PASS" if passed else "FAIL"} {path.name}')
        # Do not echo diagnostics that might contain private runtime configuration.
        failed += not passed
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
