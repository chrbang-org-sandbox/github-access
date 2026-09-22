#!/usr/bin/env python3
"""Execute plan.json via gh api, one action at a time. Refuses if the snapshot the plan was based on is not the latest.
Usage: tools/apply.py [--plan plan.json] [--yes] [--only kind,kind]"""
import argparse, json, os, subprocess, sys
from common import ROOT, load_snapshot

ap = argparse.ArgumentParser()
ap.add_argument("--plan", default=os.path.join(ROOT, "plan.json"))
ap.add_argument("--yes", action="store_true", help="ikke spør per handling")
ap.add_argument("--only", help="kommaseparerte kinds, f.eks. team+,member+,grant+")
ap.add_argument("--auto", action="store_true", help="kjøring uten menneske (GitHub Actions): impliserer --yes og stopper på strukturendringer")
ap.add_argument("--allow-structural", action="store_true", help="tillat owner+/owner-/org/team- i --auto")
args = ap.parse_args()
if args.auto: args.yes = True
# In unattended runs these kinds are never applied silently: a merged PR must not be able to change owners,
# base permission or delete teams without an owner explicitly allowing it (label or workflow_dispatch).
STRUCTURAL = {"owner+", "owner-", "org", "team-"}

plan = json.load(open(args.plan))
latest = load_snapshot()
if plan["snapshot"] != latest["generated_at"]:
    sys.exit(f"plan.json er basert på snapshot {plan['snapshot']}, men latest.json er {latest['generated_at']}. Kjør tools/plan.py på nytt.")
actions = plan["actions"]
if args.only:
    kinds = set(args.only.split(","))
    actions = [a for a in actions if a["kind"] in kinds]
if not actions:
    sys.exit("ingen handlinger å utføre")
if args.auto and not args.allow_structural:
    blocked = [a for a in actions if a["kind"] in STRUCTURAL]
    if blocked:
        print("STOPP: planen inneholder strukturendringer som ikke kjøres automatisk:")
        for a in blocked: print(f"  {a['kind']:8s} {a['desc']}")
        print("En owner må kjøre workflow_dispatch med allow_structural, eller sette label 'godkjent-strukturendring' på PR-en før merge.")
        sys.exit(3)

print(f"{len(actions)} handlinger mot {plan['org']}:")
for a in actions:
    print(f"  {a['kind']:8s} {a['desc']}")
if not args.yes and input("\nUtfør alle? [y/N] ").strip().lower() != "y":
    sys.exit("avbrutt")

failed = 0
for a in actions:
    cmd = ["gh", "api", "-X", a["method"], a["path"]]
    for k, v in (a.get("body") or {}).items():
        cmd += ["-f", f"{k}={v}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    ok = r.returncode == 0
    failed += not ok
    print(f"  {'ok ' if ok else 'FEIL'} {a['desc']}" + ("" if ok else f"\n       {r.stderr.strip() or r.stdout.strip()}"))
print(f"\n{len(actions) - failed} ok, {failed} feilet. Kjør ./audit.sh og deretter tools/plan.py for å verifisere at planen nå er tom.")
sys.exit(1 if failed else 0)
