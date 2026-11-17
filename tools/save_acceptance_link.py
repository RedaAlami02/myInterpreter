#!/usr/bin/env python3
"""Privately save an owner-supplied recovery link for browser acceptance."""
import getpass
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit, parse_qs
from stage_supabase import local_config


def main():
    if not sys.stdin.isatty():
        raise SystemExit('Run this command in your terminal; the link will not be displayed.')
    root = Path(__file__).resolve().parents[1]
    config = local_config(root / '.supabase-migration.env')
    expected = urlsplit(config['SUPABASE_PROJECT_URL']).hostname
    value = getpass.getpass('Paste the Reset password link, then press Enter (hidden): ').strip()
    parsed = urlsplit(value)
    query = parse_qs(parsed.query)
    if (parsed.scheme != 'https' or parsed.hostname != expected
            or parsed.path != '/auth/v1/verify' or parsed.username or parsed.password
            or parsed.port not in (None, 443) or parsed.fragment
            or query.get('type') != ['recovery']
            or not (query.get('token') or query.get('token_hash'))
            or len(value) > 8192):
        raise SystemExit('This is not the expected project recovery link. Copy the email button link again.')
    os.umask(0o077)
    folder = Path.home() / '.config/myinterpreter/credentials'
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = folder / 'acceptance-recovery-link'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as handle:
        handle.write(value)
    print('Saved privately. Tell the assistant: saved the reset link.')


if __name__ == '__main__':
    main()
