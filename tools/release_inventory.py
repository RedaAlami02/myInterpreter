#!/usr/bin/env python3
"""Hash explicitly selected release files; output is private and is not deployment proof."""
import argparse
import hashlib
import json
from pathlib import Path


def inventory(root, names):
    files = []
    for name in names:
        relative = Path(name)
        path = root / relative
        if relative.is_absolute() or '..' in relative.parts or path.is_symlink():
            raise ValueError('INVALID_RELEASE_PATH')
        if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError('INVALID_RELEASE_PATH')
        files.append({'path': relative.as_posix(),
                      'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    return {'contract': 'release-inventory/v1', 'deployed_verified': False,
            'files': sorted(files, key=lambda item: item['path'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--files', type=Path, required=True,
                        help='Explicit newline-separated relative paths; no automatic worktree scan')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    names = [line.strip() for line in args.files.read_text().splitlines() if line.strip()]
    if not names:
        parser.error('The release selection must not be empty')
    result = inventory(root, names)
    with args.output.open('x') as output:
        json.dump(result, output, indent=2)
        output.write('\n')


if __name__ == '__main__':
    main()
