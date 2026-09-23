#!/usr/bin/env python3
"""Parse a new-team issue (Issue Form body) into GITHUB_OUTPUT lines.
Env: ISSUE_BODY, ISSUE_USER. Reads access.yaml and clients.yaml to refuse duplicates.
Output keys: name, slug, globs (space-separated), logins (space-separated), title, reason (multiline).
Usage: ISSUE_BODY=... ISSUE_USER=... tools/parse-new-team.py >> "$GITHUB_OUTPUT" """
import os, re, sys
import yaml
from common import ROOT, slugify

SELF_PREFIX = "Myself"
LOGIN_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")
GLOB_RE = re.compile(r"[A-Za-z0-9._*?\[\]-]+")

def fields(body):
    f = {m.group(1).strip(): m.group(2).strip() for m in re.finditer(r"### (.+?)\n+(.*?)(?=\n### |\Z)", body, re.S)}
    return {k: ("" if v in ("_No response_", "None") else v) for k, v in f.items()}

def parse(body, author, existing_teams=(), existing_clients=()):
    f = fields(body)
    name = " ".join(f.get("Customer name", "").split())
    if not name or len(name) > 60 or any(c in name for c in ':#"\'{}[]\n'):
        raise SystemExit(f"invalid customer name: {name!r}")
    slug = slugify(name)
    if not slug:
        raise SystemExit(f"customer name gives an empty slug: {name!r}")
    if slug in existing_teams or slug in existing_clients:
        raise SystemExit(f"team '{slug}' already exists")
    globs = [g.strip() for g in re.split(r"[,\s]+", f.get("Repos", "")) if g.strip()]
    if not globs:
        raise SystemExit("no repo names or globs given")
    for g in globs:
        if not GLOB_RE.fullmatch(g) or g == "*":
            raise SystemExit(f"invalid repo pattern: {g!r}")
    logins = []
    for raw in f.get("Members", "").split(","):
        raw = raw.strip()
        if raw:
            logins.append(author if raw.startswith(SELF_PREFIX) else raw)
    logins = list(dict.fromkeys(logins))
    for l in logins:
        if not LOGIN_RE.fullmatch(l):
            raise SystemExit(f"invalid username: {l!r}")
    return {"name": name, "slug": slug, "globs": globs, "logins": logins, "reason": f.get("Reason", "")}

if __name__ == "__main__":
    cfg = yaml.safe_load(open(os.path.join(ROOT, "access.yaml")))
    clients = yaml.safe_load(open(os.path.join(ROOT, "clients.yaml"))) or {}
    r = parse(os.environ["ISSUE_BODY"], os.environ["ISSUE_USER"],
              existing_teams=(cfg.get("teams") or {}).keys(),
              existing_clients={slugify((c or {}).get("name") or k) for k, c in (clients.get("clients") or {}).items()})
    print(f"name={r['name']}"); print(f"slug={r['slug']}")
    print("globs=" + " ".join(r["globs"])); print("logins=" + " ".join(r["logins"]))
    print(f"title=New team {r['name']}")
    print("reason<<EOR"); print(r["reason"]); print("EOR")
