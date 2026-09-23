#!/usr/bin/env python3
"""Execute plan.json via gh api, one action at a time. Refuses if the snapshot the plan was based on is not the latest.
Usage: tools/apply.py [--plan plan.json] [--yes] [--only kind,kind]"""
import argparse, json, os, subprocess, sys
from common import ROOT, load_snapshot

ap = argparse.ArgumentParser()
ap.add_argument("--plan", default=os.path.join(ROOT, "plan.json"))
ap.add_argument("--yes", action="store_true", help="do not ask per action")
ap.add_argument("--only", help="comma-separated kinds, e.g. team+,member+,grant+")
ap.add_argument("--auto", action="store_true", help="unattended run (GitHub Actions): implies --yes and stops on structural changes")
ap.add_argument("--allow-structural", action="store_true", help="allow owner+/owner-/org/team- in --auto")
args = ap.parse_args()
if args.auto: args.yes = True
# In unattended runs these kinds are never applied silently: a merged PR must not be able to change owners,
# base permission or delete teams without an owner explicitly allowing it (label or workflow_dispatch).
STRUCTURAL = {"owner+", "owner-", "org", "team-"}

plan = json.load(open(args.plan))
latest = load_snapshot()
if plan["snapshot"] != latest["generated_at"]:
    sys.exit(f"plan.json is based on an older snapshot than latest.json (plan {plan['snapshot']}, latest {latest['generated_at']}). Run tools/plan.py again.")
actions = plan["actions"]
if args.only:
    kinds = set(args.only.split(","))
    actions = [a for a in actions if a["kind"] in kinds]
if not actions:
    sys.exit("no actions to apply")
if args.auto and not args.allow_structural:
    blocked = [a for a in actions if a["kind"] in STRUCTURAL]
    if blocked:
        print("STOP: Structural change requires --allow-structural (or the label approved-structural-change on the PR):")
        for a in blocked: print(f"  {a['kind']:8s} {a['desc']}")
        print("An owner must run workflow_dispatch with allow_structural, or set the label 'approved-structural-change' on the PR before merge.")
        sys.exit(3)

print(f"{len(actions)} actions against {plan['org']}:")
for a in actions:
    print(f"  {a['kind']:8s} {a['desc']}")
if not args.yes and input("\nApply all? [y/N] ").strip().lower() != "y":
    sys.exit("aborted")

failed = 0
for a in actions:
    cmd = ["gh", "api", "-X", a["method"], a["path"]]
    for k, v in (a.get("body") or {}).items():
        cmd += ["-f", f"{k}={v}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    ok = r.returncode == 0
    failed += not ok
    print(f"  {'ok ' if ok else 'FAIL'} {a['desc']}" + ("" if ok else f"\n       {r.stderr.strip() or r.stdout.strip()}"))
print(f"\n{len(actions) - failed} ok, {failed} failed. Run ./audit.sh and then tools/plan.py to verify that the plan is now empty.")
sys.exit(1 if failed else 0)
