#!/usr/bin/env python3
"""Upload the PHP site to InfinityFree over FTP.

    python3 deploy.py            # upload changed files
    python3 deploy.py --all      # upload everything, ignoring size comparison
    python3 deploy.py --dry-run  # list what would go up, touch nothing
    python3 deploy.py config/sources.php index.php    # only these paths

Two config files the site cannot start without are gitignored, so a
"deploy the repo" step that walks git would silently skip them and leave the
host with a fatal error. They are listed in ALWAYS_INCLUDE below and uploaded
like any other file — that is the whole reason this script walks the working
tree instead.

Credentials come from FTP.md (gitignored) or from the environment:
FTP_HOST, FTP_USER, FTP_PASS, FTP_REMOTE_PATH.

Nothing on the host is ever deleted. Files that exist remotely and not
locally are left alone.
"""

import ftplib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Extensions that make up the site. Anything else is local-only tooling.
SITE_SUFFIXES = {".php", ".css", ".js", ".svg", ".ico", ".png", ".jpg", ".webp", ".woff2"}

# Directories never uploaded, matched against the path's first component.
SKIP_DIRS = {
    ".git", ".github", ".claude", ".agents", "__pycache__", "node_modules",
    "myinterpreter_app",   # Flutter client
    "cloud_function",      # deployed with the Appwrite CLI, not FTP
    "scrapping", "private", "session", "tmp", "docs",
}

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
            rel = Path(p).as_posix().lstrip("./")
            if not (ROOT / rel).is_file():
                sys.exit(f"Not a file: {rel}")
            out.append(rel)
        return out

    found = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if any(part in SKIP_DIRS for part in Path(rel).parts[:-1]):
            continue
        if rel.startswith("backup") or rel in SKIP_FILES:
            continue
        if path.suffix.lower() in SITE_SUFFIXES:
            found.append(rel)

    for rel in ALWAYS_INCLUDE:
        if (ROOT / rel).is_file():
            if rel not in found:
                found.append(rel)
        else:
            print(f"  !! {rel} missing locally — the site will fatal without it")
    return sorted(found)


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

    print(f"{len(files)} file(s) → {host}{base}" + ("  [dry run]" if dry else ""))
    if dry:
        for rel in files:
            print("   ", rel)
        return

    ftp = ftplib.FTP(host, timeout=30)
    ftp.login(user, password)
    made, sent, same = set(), 0, 0
    try:
        for rel in files:
            local = ROOT / rel
            remote = f"{base}/{rel}"
            remote_dir = remote.rsplit("/", 1)[0]
            if remote_dir not in made:
                ensure_dir(ftp, remote_dir)
                made.add(remote_dir)

            if not force:
                try:
                    if ftp.size(remote) == local.stat().st_size:
                        same += 1
                        continue
                except ftplib.error_perm:
                    pass  # not there yet

            with local.open("rb") as fh:
                ftp.storbinary(f"STOR {remote}", fh)
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
