#!/usr/bin/env python3
"""Static inventory; not a runtime network trace or a security certification."""
import collections
import pathlib
import re
import subprocess

root = pathlib.Path(__file__).resolve().parents[1]
files = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
extensions = {".kt", ".java", ".xml", ".json", ".js", ".html", ".cpp", ".h", ".kts", ".toml", ".properties", ".yml", ".yaml", ".md", ".txt", ".py"}
domains = collections.defaultdict(set)
credentials = collections.defaultdict(set)
upstream = collections.defaultdict(list)
locale = collections.Counter()
scanned = 0
url = re.compile(r"(?:https?|wss?)://([a-z0-9][a-z0-9.-]*\.[a-z]{2,})(?=[:/\"'\s?#]|$)", re.I)
key = re.compile(r'(?:BuildConfig\.|System\.getenv\(\s*"|getProperty\(\s*")([A-Z][A-Z0-9_]*(?:KEY|SECRET|TOKEN|CLIENT_ID|PASSWORD)[A-Z0-9_]*)')
marker = re.compile(r"realidkroo|realkeichii?|mochy-module-feed|mochyy\.workers\.dev|discord\.gg/4DAafDMxZb|raw\.githubusercontent\.com|api\.github\.com|github\.com/", re.I)
for rel in files:
    if not rel or rel == "scripts/void_dependency_audit.py":
        continue
    p = root / rel
    if p.suffix not in extensions or not p.is_file() or p.stat().st_size > 4_000_000:
        continue
    scanned += 1
    for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        for host in url.findall(line):
            domains[host.lower()].add(rel)
        for name in key.findall(line):
            credentials[name].add(rel)
        for token in set(marker.findall(line)):
            upstream[token.lower()].append(f"{rel}:{i}")
        if "/res/values-" in rel and re.search(r">[^<]*\bmoch(?:y|a)\b", line, re.I):
            locale[rel] += 1
print(f"Static audit: {scanned} text files, {len(domains)} literal domains, {len(credentials)} credential names.")
print("\n## External domains (literal only; includes docs and tests)")
for host, paths in sorted(domains.items()):
    print(f"{host}: {len(paths)} files; " + ", ".join(sorted(paths)[:3]))
print("\n## Credential configuration names (values never printed)")
for name, paths in sorted(credentials.items()):
    print(f"{name}: " + ", ".join(sorted(paths)[:5]))
print("\n## Upstream and repository references (location only)")
for token, locations in sorted(upstream.items()):
    print(f"{token}: {len(locations)} matches; " + ", ".join(locations[:15]))
print(f"\n## Localized legacy name: {sum(locale.values())} matches in {len(locale)} files")
for path, n in sorted(locale.items()):
    print(f"{path}: {n}")
print("\nLimitations: dynamic URLs, native code, bundled libraries, credentials, actual network traffic and permissions require separate verification.")
