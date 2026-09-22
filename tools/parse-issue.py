#!/usr/bin/env python3
"""Parse an access-request issue (Issue Form body) into GITHUB_OUTPUT lines.
Env: ISSUE_BODY, ISSUE_USER. Reads access.yaml for the team's display name.
Output keys: action, team, logins (space-separated), title, reason (multiline).
The "Hvem" dropdown is multi-select and renders as a comma-separated line; "Meg selv …" means the issue author.
Usage: ISSUE_BODY=... ISSUE_USER=... tools/parse-issue.py >> "$GITHUB_OUTPUT" """
import os, re, sys
import yaml
from common import ROOT

SELF_PREFIX = "Meg selv"
LOGIN_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")

def fields(body):
    f = {m.group(1).strip(): m.group(2).strip() for m in re.finditer(r"### (.+?)\n+(.*?)(?=\n### |\Z)", body, re.S)}
    return {k: ("" if v in ("_No response_", "None") else v) for k, v in f.items()}

def parse(body, author):
    f = fields(body)
    m = re.search(r"\(([^()]+)\)\s*$", f.get("Team", ""))
    team = m.group(1) if m else f.get("Team", "")
    if not re.fullmatch(r"[a-z0-9-]+", team):
        raise SystemExit(f"ugyldig team: {team!r}")
    logins = []
    for raw in f.get("Hvem", "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        logins.append(author if raw.startswith(SELF_PREFIX) else raw)
    for raw in re.split(r"[,\s]+", f.get("Andre brukernavn", "")):
        if raw.strip():
            logins.append(raw.strip().lstrip("@"))
    logins = list(dict.fromkeys(logins)) or [author]
    for l in logins:
        if not LOGIN_RE.fullmatch(l):
            raise SystemExit(f"ugyldig brukernavn: {l!r}")
    action = "remove" if f.get("Hva", "").lower().startswith("fjern") else "add"
    return {"action": action, "team": team, "logins": logins, "reason": f.get("Begrunnelse", "")}

def title(action, logins, team_name):
    who = ", ".join(logins) if len(logins) <= 3 else f"{len(logins)} users"
    return f"Add {who} to {team_name} team" if action == "add" else f"Remove {who} from {team_name} team"

if __name__ == "__main__":
    r = parse(os.environ["ISSUE_BODY"], os.environ["ISSUE_USER"])
    cfg = yaml.safe_load(open(os.path.join(ROOT, "access.yaml")))
    tname = ((cfg.get("teams") or {}).get(r["team"]) or {}).get("name") or r["team"]
    print(f"action={r['action']}"); print(f"team={r['team']}"); print("logins=" + " ".join(r["logins"]))
    print("title=" + title(r["action"], r["logins"], tname))
    print("reason<<EOR"); print(r["reason"]); print("EOR")
