#!/usr/bin/env python3
"""Upload the PHP site over encrypted FTP, with private local rollback backups.

    python3 deploy.py            # upload changed files
    python3 deploy.py --all      # upload everything, ignoring content comparison
    python3 deploy.py --dry-run  # list what would go up, touch nothing
    python3 deploy.py config/sources.php index.php    # only these paths

Two config files the site cannot start without are gitignored, so a
"deploy the repo" step that walks git would silently skip them and leave the
host with a fatal error. They are listed in ALWAYS_INCLUDE below. Other files
must be tracked runtime files; local tests, research and screenshots are excluded.

Credentials come from FTP.md (gitignored) or from the environment:
FTP_HOST, FTP_USER, FTP_PASS, FTP_REMOTE_PATH.

Nothing on the host is ever deleted. Files that exist remotely and not
locally are left alone.
"""

import ftplib
import os
import re
import sys
import subprocess
import ssl
import io
import hashlib
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Extensions that make up the site. Anything else is local-only tooling.
SITE_SUFFIXES = {".php", ".css", ".js", ".svg", ".ico", ".png", ".jpg", ".webp", ".woff2"}
SITE_DIRS = {"assets", "core", "config", "handlers", "locales"}

# Gitignored, required at runtime, and therefore easy to forget by hand.
ALWAYS_INCLUDE = [
    "config/sources.php",   # upstream endpoints — index.php + market_proxy.php require it
    "config/secrets.php",   # Appwrite server API key
]

# Local-only files that happen to match SITE_SUFFIXES.
SKIP_FILES = {"config/sources.example.php", "deploy.py"}


def credentials():
    env = {k: os.environ.get(k) for k in ("FTP_HOST", "FTP_USER", "FTP_PASS", "FTP_REMOTE_PATH")}
    if env["FTP_HOST"] and env["FTP_USER"] and env["FTP_PASS"]:
        return env["FTP_HOST"], env["FTP_USER"], env["FTP_PASS"], env["FTP_REMOTE_PATH"] or "/htdocs/"

    ftp_md = ROOT / "FTP.md"
    if not ftp_md.exists():
        sys.exit("No credentials: set FTP_HOST/FTP_USER/FTP_PASS or create FTP.md")
    text = ftp_md.read_text()
    def get(key, default=None):
        m = re.search(rf"^{key}=(.+)$", text, re.M)
        if not m and default is None:
            sys.exit(f"FTP.md is missing {key}")
        return m.group(1).strip() if m else default
    return get("FTP_HOST"), get("FTP_USER"), get("FTP_PASS"), get("FTP_REMOTE_PATH", "/htdocs/")


def local_files(explicit):
    """Repo-relative POSIX paths to upload."""
    if explicit:
        out = []
        for p in explicit:
            path = Path(p)
            if path.is_absolute() or '..' in path.parts:
                sys.exit("Explicit paths must stay inside the project")
            rel = path.as_posix()
            if not (ROOT / rel).resolve().is_relative_to(ROOT.resolve()):
                sys.exit("Explicit paths must stay inside the project")
            if not (ROOT / rel).is_file():
                sys.exit(f"Not a file: {rel}")
            out.append(rel)
        return out

    found = []
    # Only tracked runtime files; local screenshots, fixtures and research must
    # never be published. Private runtime config is handled explicitly below.
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    for rel in tracked:
        path = Path(rel)
        if not rel or not (ROOT / rel).is_file():
            continue
        if len(path.parts) > 1 and path.parts[0] not in SITE_DIRS:
            continue
        if rel in SKIP_FILES or ".example." in path.name or path.is_absolute():
            continue
        if path.suffix.lower() in SITE_SUFFIXES or (path.parent == Path("locales") and path.suffix == ".json"):
            found.append(rel)

    for rel in ALWAYS_INCLUDE:
        if (ROOT / rel).is_file():
            if rel not in found:
                found.append(rel)
        else:
            print(f"  !! {rel} missing locally — the site will fatal without it")
    # Install catalogs and shared dependencies before switching page templates.
    return sorted(found, key=lambda rel: (0 if rel.startswith('locales/') else 1 if '/' in rel else 2, rel))


def ensure_dir(ftp, remote_dir):
    parts, built = [p for p in remote_dir.split("/") if p], ""
    for part in parts:
        built += "/" + part
        try:
            ftp.mkd(built)
        except ftplib.error_perm:
            pass  # already exists


def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    force = "--all" in args
    explicit = [a for a in args if not a.startswith("--")]

    files = local_files(explicit)
    host, user, password, base = credentials()
    base = "/" + base.strip("/")

    print(f"{len(files)} file(s) → configured website host" + ("  [dry run]" if dry else ""))
    if dry:
        for rel in files:
            print("   ", rel)
        return

    ftp = ftplib.FTP_TLS(context=ssl.create_default_context(), timeout=30)
    ftp.connect(host)
    ftp.login(user, password)
    ftp.prot_p()
    made, sent, same = set(), 0, 0
    try:
        # Snapshot every existing target before changing anything. The backup
        # lives outside the served tree in a private temporary directory.
        backup = Path(tempfile.mkdtemp(prefix="myinterpreter-deploy-"))
        previous = {}
        ftp.voidcmd('TYPE I')
        for rel in files:
            buf = io.BytesIO()
            try:
                ftp.retrbinary(f"RETR {base}/{rel}", buf.write)
            except ftplib.error_perm as exc:
                if not str(exc).startswith('550'):
                    raise
                previous[rel] = None
                continue
            previous[rel] = buf.getvalue()
            target = backup / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(previous[rel])
        (backup / 'new-files.txt').write_text('\n'.join(rel for rel in files if previous[rel] is None))
        print(f"Rollback backup: {backup}")
        for rel in files:
            local = ROOT / rel
            remote = f"{base}/{rel}"
            remote_dir = remote.rsplit("/", 1)[0]
            if remote_dir not in made:
                ensure_dir(ftp, remote_dir)
                made.add(remote_dir)

            payload = local.read_bytes()
            if not force and previous[rel] == payload:
                same += 1
                continue

            with local.open("rb") as fh:
                ftp.storbinary(f"STOR {remote}", fh)
            verified = io.BytesIO()
            ftp.retrbinary(f"RETR {remote}", verified.write)
            if hashlib.sha256(verified.getvalue()).digest() != hashlib.sha256(payload).digest():
                raise RuntimeError(f"Upload verification failed: {rel}; restore from {backup}")
            sent += 1
            print(f"  ↑ {rel}")
    finally:
        ftp.quit()

    print(f"\nuploaded {sent}, unchanged {same}")
    for rel in ALWAYS_INCLUDE:
        if rel in files:
            print(f"  ✓ {rel} is on the host")


if __name__ == "__main__":
    main()
