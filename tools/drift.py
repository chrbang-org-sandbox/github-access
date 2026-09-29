#!/usr/bin/env python3
"""Daily drift report: what in the org is not covered by access.yaml, as Markdown on stdout.
Reads latest.json (from audit.sh), access.yaml, clients.yaml and plan.json (from plan.py) if present.
Exit 2 when there is something to report, 0 when clean. Used by .github/workflows/drift.yml.
Usage: ./audit.sh && tools/plan.py; tools/drift.py > drift.md"""
import fnmatch, json, os, sys
import yaml
from common import ROOT, RANK, load_snapshot, load_access, desired_state

snap = load_snapshot()
cfg = load_access()
want = desired_state(cfg, snap)
clients = yaml.safe_load(open(os.path.join(ROOT, "clients.yaml"))) or {}
members = set(snap["members"])
active = [r for r in snap["repos"] if r["active"] and not r["archived"]]

def matches(name, globs):
    return any(fnmatch.fnmatchcase(name.lower(), g.lower()) for g in globs or [])

sections = []

# 1. active repos no team can write to (owners don't count). Show who has direct admin today: usually the creator.
covered = {r for t in want["teams"].values() for r, role in t["repos"].items() if RANK.get(role, 0) >= 3}
rows = []
for r in sorted(active, key=lambda r: r["name"].lower()):
    if r["name"] in covered:
        continue
    admins = ", ".join(f"@{d['login']}" for d in r["direct"] if d["role"] == "admin" and d["login"] in members) or "nobody but owners"
    rows.append(f"| `{r['name']}` | {r['pushed_at'][:10]} | {admins} |")
if rows:
    sections.append("### Active repos without a team\n\nNo team has write or admin here. Ask for a team with the "
                    "\"Request a new team\" form, or add the repo to an existing team's `repos` in `access.yaml`.\n\n"
                    "| Repo | Last push | Direct admin today |\n|---|---|---|\n" + "\n".join(rows))

# 2. direct grants that exist in GitHub but not in access.yaml: removed on the next apply
rows = []
for r in sorted(snap["repos"], key=lambda r: r["name"].lower()):
    for d in r["direct"]:
        if want["direct"].get(r["name"], {}).get(d["login"]) != d["role"]:
            kind = "employee" if d["login"] in members else "external"
            rows.append(f"| `{r['name']}` | @{d['login']} | {d['role']} | {kind} |")
if rows:
    sections.append("### Direct grants not in access.yaml\n\nGranted in the GitHub UI. Removed on the next apply unless added to the file "
                    "(externals) or replaced by team membership (employees).\n\n| Repo | User | Role | |\n|---|---|---|---|\n" + "\n".join(rows))

# 3. active repos that match no customer in clients.yaml
globs = [g for c in (clients.get("clients") or {}).values() for g in ((c or {}).get("match") or [])]
globs += ((clients.get("internal") or {}).get("match") or []) + (clients.get("exclude") or [])
unmatched = [r["name"] for r in active if not matches(r["name"], globs)]
if unmatched:
    sections.append("### Active repos that match no customer in clients.yaml\n\nThe report cannot attribute them. Add a glob to the "
                    "customer (or `internal`) in `clients.yaml`.\n\n" + "\n".join(f"- `{n}`" for n in sorted(unmatched, key=str.lower)))

# 4. pending plan: the file and the org differ
plan_path = os.path.join(ROOT, "plan.json")
if os.path.exists(plan_path):
    actions = json.load(open(plan_path)).get("actions") or []
    if actions:
        counts = {}
        for a in actions:
            counts[a["kind"]] = counts.get(a["kind"], 0) + 1
        lines = [f"- `{a['kind']}` {a['desc']}" for a in actions[:25]]
        if len(actions) > 25:
            lines.append(f"- … {len(actions) - 25} more")
        sections.append(f"### access.yaml and the org differ ({len(actions)} pending changes)\n\n"
                        + ", ".join(f"`{k}` × {v}" for k, v in sorted(counts.items())) + "\n\n" + "\n".join(lines))

if not sections:
    print("Clean: every active repo has a team, no direct grants outside access.yaml, all repos attributed, plan empty.")
    sys.exit(0)
print(f"Snapshot `{snap['generated_at']}`, activity window {snap['activity_days']} days.\n")
print("\n\n".join(sections))
sys.exit(2)
