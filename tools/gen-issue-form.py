#!/usr/bin/env python3
"""Generate .github/ISSUE_TEMPLATE/access-request.yml.
Issue Forms cannot load options dynamically, so two lists are baked in:
  - teams: from access.yaml. CI runs --check to keep them in sync.
  - users: all org members, from GitHub (gh api). Refreshed with --users; --check ignores them, so a PR never fails
    because someone joined the org yesterday. .github/workflows/refresh-form.yml refreshes them on a schedule.
Usage: tools/gen-issue-form.py            # teams from access.yaml, users kept from the existing form
       tools/gen-issue-form.py --users    # also refresh users from GitHub (needs gh, env ORG or org: in access.yaml)
       tools/gen-issue-form.py --check    # exit 1 if the team list is out of sync"""
import os, subprocess, sys
import yaml
from common import ROOT

OUT = os.path.join(ROOT, ".github", "ISSUE_TEMPLATE", "access-request.yml")
HIDDEN = {"developers"}          # roster-only team; nobody requests membership there
SELF = "Meg selv (den som sender inn)"   # first option, preselected; the workflow swaps it for the issue author

cfg = yaml.safe_load(open(os.path.join(ROOT, "access.yaml")))
teams = [(t.get("name") or slug, slug) for slug, t in (cfg.get("teams") or {}).items() if slug not in HIDDEN and t is not None]
team_options = [f"{name} ({slug})" if name != slug else slug for name, slug in sorted(teams, key=lambda x: x[0].lower())]

def existing_users():
    """User options from the form already on disk, minus the SELF entry."""
    if not os.path.exists(OUT):
        return []
    for field in (yaml.safe_load(open(OUT, encoding="utf-8")) or {}).get("body") or []:
        if field.get("id") == "who":
            return [o for o in field["attributes"]["options"] if o != SELF]
    return []

def github_users():
    org = os.environ.get("ORG") or cfg.get("org")
    if not org:
        sys.exit("Sett ORG=<github-org> eller org: i access.yaml")
    out = subprocess.run(["gh", "api", f"orgs/{org}/members", "--paginate", "--jq", ".[].login"],
                         check=True, capture_output=True, text=True).stdout
    return sorted({l.strip() for l in out.splitlines() if l.strip()}, key=str.lower)

if "--users" in sys.argv:
    users = github_users()
else:
    users = existing_users()
    if not users and "--check" not in sys.argv:
        users = github_users()

def render(users):
    form = {
        "name": "Be om tilgang til et team",
        "description": "Legg deg selv eller kolleger til i et team, eller fjern. Lager en pull request som platform-teamet godkjenner.",
        "title": "Tilgangsforespørsel",     # settes automatisk av workflowen ut fra valgene, f.eks. "Add octocat to Kunde A team"
        "labels": ["access-request"],
        "body": [
            {"type": "markdown", "attributes": {"value": "Når du sender inn, lages en pull request mot `access.yaml` automatisk. "
                "Når den er godkjent og merget, oppdateres tilgangen i GitHub av seg selv. Se FLYT.md for detaljer.\n\n"
                "La tittelen stå. Den settes automatisk ut fra valgene under."}},
            {"type": "dropdown", "id": "action", "attributes": {"label": "Hva", "options": ["Legg til", "Fjern"]}, "validations": {"required": True}},
            {"type": "dropdown", "id": "team", "attributes": {"label": "Team", "options": team_options}, "validations": {"required": True}},
            {"type": "dropdown", "id": "who", "attributes": {"label": "Hvem", "description": "Deg selv er forhåndsvalgt. Velg flere for å be på vegne av kolleger.",
                "multiple": True, "options": [SELF] + users, "default": 0}},
            {"type": "textarea", "id": "reason", "attributes": {"label": "Begrunnelse", "description": "Hvilket prosjekt, fra når, hvor lenge."}, "validations": {"required": True}},
        ],
    }
    return ("# Generert av tools/gen-issue-form.py. Team fra access.yaml, brukere fra orgen (--users). Ikke rediger for hånd.\n"
            + yaml.safe_dump(form, sort_keys=False, allow_unicode=True, width=120))

text = render(users)
if "--check" in sys.argv:
    cur = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
    if cur != render(existing_users()):
        sys.exit("Issue-skjemaet er ute av synk med access.yaml. Kjør tools/gen-issue-form.py og commit.")
    print("issue-skjema i synk"); sys.exit(0)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w", encoding="utf-8").write(text)
print(f"skrev {os.path.relpath(OUT, ROOT)} med {len(team_options)} team og {len(users)} brukere")
