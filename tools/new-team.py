#!/usr/bin/env python3
"""Add a customer team to access.yaml and clients.yaml as text edits, so comments and ordering are preserved.
Used by .github/workflows/new-team.yml; works locally too.
Usage: tools/new-team.py --name "Kunde AS" --glob "Kunde.*" [--glob ...] [--login user ...] [--repos repos.txt]
  --repos: file with one repo name per line (the org's repos); the globs must match at least one, else exit 1.
Prints a summary suitable as PR body."""
import argparse, fnmatch, os, sys
import yaml
from common import ROOT, slugify

ap = argparse.ArgumentParser()
ap.add_argument("--name", required=True, help="full customer name; the team slug is derived from it")
ap.add_argument("--glob", action="append", required=True, help="repo name or glob, repeatable")
ap.add_argument("--login", action="append", default=[], help="initial member, repeatable")
ap.add_argument("--repos", help="file with the org's repo names, one per line, to check that the globs match something")
ap.add_argument("--role", default="admin", choices=["admin", "write", "read"])
a = ap.parse_args()

slug = slugify(a.name)
if not slug:
    sys.exit(f"customer name gives an empty slug: {a.name!r}")

def q(s):
    """Quote a YAML scalar only when needed (globs contain * which is fine unquoted, but be explicit)."""
    return '"' + s.replace('"', '\\"') + '"' if any(c in s for c in "*?[]{}:#,&") else s

def insert_before(text, markers, block, what):
    """Insert block before the first line that equals one of the markers (in order of preference)."""
    lines = text.split("\n")
    for m in markers:
        for i, l in enumerate(lines):
            if l.rstrip() == m:
                return "\n".join(lines[:i] + block.rstrip("\n").split("\n") + [""] + lines[i:])
    sys.exit(f"{what}: none of the insertion points found: {markers}")

# --- access.yaml
apath = os.path.join(ROOT, "access.yaml")
atext = open(apath, encoding="utf-8").read()
cfg = yaml.safe_load(atext)
if slug in (cfg.get("teams") or {}):
    sys.exit(f"team '{slug}' already exists in access.yaml")
members = "\n".join(f"    - {l}" for l in a.login) if a.login else "    members: []"
if a.login:
    members = "    members:\n" + members
block = (f"  {slug}:\n    name: {a.name}\n    description: {a.name}\n{members}\n    repos:\n      {a.role}:\n"
         + "\n".join(f"      - {q(g)}" for g in a.glob) + "\n")
atext = insert_before(atext, ["  platform:", "  internal:", "# Direct collaborators. PHASE 2: remove employees here (tools/plan.py warns about each), keep externals only.",
                              "# Direct collaborators: only externals (outside collaborators). Employees get access via teams.", "repos: {}", "repos:"],
                      block, "access.yaml")

# --- clients.yaml
cpath = os.path.join(ROOT, "clients.yaml")
ctext = open(cpath, encoding="utf-8").read()
clients = yaml.safe_load(ctext) or {}
if slug in (clients.get("clients") or {}) or any(slugify((c or {}).get("name") or k) == slug for k, c in (clients.get("clients") or {}).items()):
    sys.exit(f"customer '{slug}' already exists in clients.yaml")
cblock = f"  {slug}:\n    name: {a.name}\n    match: [" + ", ".join(q(g) for g in a.glob) + "]\n"
ctext = insert_before(ctext, ["internal:", "exclude:"], cblock, "clients.yaml")

# --- repo match check
matched = None
if a.repos:
    repos = [l.strip() for l in open(a.repos) if l.strip()]
    matched = sorted({r for r in repos if any(fnmatch.fnmatchcase(r.lower(), g.lower()) for g in a.glob)})
    if not matched:
        sys.exit(f"no repo in the org matches {a.glob}")

# --- validate the result parses and write
yaml.safe_load(atext); yaml.safe_load(ctext)
open(apath, "w", encoding="utf-8").write(atext)
open(cpath, "w", encoding="utf-8").write(ctext)

print(f"team {slug} «{a.name}»: {a.role} on {', '.join(a.glob)}")
print(f"members: {', '.join(a.login) if a.login else '(none yet, request via the access form)'}")
if matched is not None:
    print(f"matches {len(matched)} repos today: {', '.join(matched[:15])}{' …' if len(matched) > 15 else ''}")
