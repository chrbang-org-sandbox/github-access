#!/usr/bin/env python3
"""Apply one access request to access.yaml (same edit as tools/ui.py, comments preserved).
Used by .github/workflows/access-request.yml; works locally too.
Usage: tools/request.py --team kunde-a --login octocat [--role member|maintainer] [--action add|remove]
Prints a one-line summary suitable as commit/PR title."""
import argparse, os, sys
import yaml
from common import ROOT
from ui import edit_team

ap = argparse.ArgumentParser()
ap.add_argument("--team", required=True, help="team-nøkkel i access.yaml (slug)")
ap.add_argument("--login", required=True, help="GitHub-brukernavn")
ap.add_argument("--role", choices=["member", "maintainer"], default="member")
ap.add_argument("--action", choices=["add", "remove"], default="add")
a = ap.parse_args()

path = os.path.join(ROOT, "access.yaml")
text = open(path, encoding="utf-8").read()
cfg = yaml.safe_load(text)
team = (cfg.get("teams") or {}).get(a.team)
if team is None:
    sys.exit(f"team '{a.team}' finnes ikke i access.yaml")
name = team.get("name") or a.team
try:
    if a.action == "add":
        have = set(team.get("members") or []) | set(team.get("maintainers") or [])
        if a.login in have:
            # already there: treat as role change if role differs, otherwise nothing to do
            current = "maintainer" if a.login in (team.get("maintainers") or []) else "member"
            if current == a.role:
                sys.exit(f"{a.login} er allerede {a.role} i {name}")
            new = edit_team(text, a.team, "role", a.login, a.role)
            summary = f"{name}: {a.login} {current} → {a.role}"
        else:
            new = edit_team(text, a.team, "add", a.login, a.role)
            summary = f"{name}: legg til {a.login} ({a.role})"
    else:
        new = edit_team(text, a.team, "remove", a.login)
        summary = f"{name}: fjern {a.login}"
except (KeyError, ValueError) as e:
    sys.exit(str(e))
with open(path, "w", encoding="utf-8") as f:
    f.write(new)
print(summary)
