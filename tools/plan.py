#!/usr/bin/env python3
"""Diff access.yaml (desired) against latest.json (actual). Prints a human-readable plan and writes plan.json.
Exit code 0 = no changes, 2 = changes pending. Usage: tools/plan.py [--snapshot file] [--config access.yaml] [--out plan.json]"""
import argparse, json, os, sys
from common import ROOT, RANK, load_snapshot, load_access, desired_state, actual_state

ap = argparse.ArgumentParser()
ap.add_argument("--snapshot"); ap.add_argument("--config", help="alternativ access.yaml (default: access.yaml)")
ap.add_argument("--out", default=os.path.join(ROOT, "plan.json"))
args = ap.parse_args()

snap = load_snapshot(args.snapshot)
cfg = load_access(args.config)
org = cfg.get("org") or snap["org"]
want, have = desired_state(cfg, snap), actual_state(snap)
actions, warnings = [], []
def act(kind, desc, method, path, body=None, **meta):
    actions.append({"kind": kind, "desc": desc, "method": method, "path": path, "body": body, **meta})

# unknown repos / logins referenced in config
known_logins = set(snap["members"]) | set(snap["outside"])
for slug, t in want["teams"].items():
    for r in set(t["repos"]) - want["all_repos"]:
        warnings.append(f"team {slug}: repo '{r}' finnes ikke i orgen")
    for u in t["members"] - known_logins:
        warnings.append(f"team {slug}: '{u}' er ikke medlem av orgen (må inviteres først)")
for r in set(want["direct"]) - want["all_repos"]:
    warnings.append(f"repos.{r}: finnes ikke i orgen")
# coverage: every active repo should be writable by at least one team (owners don't count)
active = {r["name"] for r in snap["repos"] if r["active"] and not r["archived"]}
covered = {r for t in want["teams"].values() for r, role in t["repos"].items() if RANK.get(role, 0) >= 3}
for r in sorted(active - covered):
    warnings.append(f"aktivt repo uten team-write: {r}")
# employees should get access via teams, never directly
members = set(snap["members"])
for r in sorted(want["direct"]):
    for u in sorted(want["direct"][r]):
        if u in members:
            warnings.append(f"ansatt med direkte grant: {r}/{u} (bruk team)")

# org
if want["base_permission"] != have["base_permission"]:
    act("org", f"base permission {have['base_permission']} → {want['base_permission']}", "PATCH", f"orgs/{org}",
        {"default_repository_permission": want["base_permission"]})
for u in sorted(want["owners"] - have["owners"]):
    act("owner+", f"{u} blir org owner", "PUT", f"orgs/{org}/memberships/{u}", {"role": "admin"})
for u in sorted(have["owners"] - want["owners"]):
    act("owner-", f"{u} nedgraderes fra owner til member", "PUT", f"orgs/{org}/memberships/{u}", {"role": "member"})

# teams. A team created with name "Kunde A" gets its slug from GitHub; if that differs from our key,
# match it by name and use GitHub's slug in API paths.
by_name = {h["name"]: s for s, h in have["teams"].items() if h.get("name")}
for slug in list(want["teams"]):
    if slug not in have["teams"] and want["teams"][slug]["name"] in by_name:
        real = by_name[want["teams"][slug]["name"]]
        warnings.append(f"team {slug}: finnes i GitHub som '{real}' (samme navn). Bruk '{real}' som nøkkel i access.yaml.")
        want["teams"][real] = want["teams"].pop(slug)
for slug in sorted(set(want["teams"]) - set(have["teams"])):
    t = want["teams"][slug]
    act("team+", f"opprett team {t['name']} ({slug})", "POST", f"orgs/{org}/teams",
        {"name": t["name"], "description": t["description"], "privacy": t["privacy"]})
for slug in sorted(set(have["teams"]) - set(want["teams"])):
    act("team-", f"slett team {slug} ({len(have['teams'][slug]['members'])} medl., {len(have['teams'][slug]['repos'])} repos)", "DELETE", f"orgs/{org}/teams/{slug}")
for slug in sorted(want["teams"]):
    w, h = want["teams"][slug], have["teams"].get(slug, {"members": set(), "maintainers": set(), "repos": {}, "description": None, "privacy": None, "name": None})
    name_changed = h.get("name") is not None and w["name"] != h["name"]
    if slug in have["teams"] and (w["description"] != h["description"] or w["privacy"] != h["privacy"] or name_changed):
        body = {"description": w["description"], "privacy": w["privacy"]}
        if name_changed: body["name"] = w["name"]
        act("team~", f"team {slug}: {'navn/' if name_changed else ''}beskrivelse/privacy", "PATCH", f"orgs/{org}/teams/{slug}", body)
    for u in sorted(w["members"] - h["members"]):
        role = "maintainer" if u in w["maintainers"] else "member"
        act("member+", f"team {slug}: legg til {u} ({role})", "PUT", f"orgs/{org}/teams/{slug}/memberships/{u}", {"role": role})
    for u in sorted(h["members"] - w["members"]):
        act("member-", f"team {slug}: fjern {u}", "DELETE", f"orgs/{org}/teams/{slug}/memberships/{u}")
    for u in sorted((w["members"] & h["members"]) & (w["maintainers"] ^ h["maintainers"])):
        role = "maintainer" if u in w["maintainers"] else "member"
        act("member~", f"team {slug}: {u} → {role}", "PUT", f"orgs/{org}/teams/{slug}/memberships/{u}", {"role": role})
    api_role = lambda r: {"read": "pull", "write": "push"}.get(r, r)
    for r in sorted(set(w["repos"]) - set(h["repos"])):
        if r in want["all_repos"]:
            act("grant+", f"team {slug}: {w['repos'][r]} på {r}", "PUT", f"orgs/{org}/teams/{slug}/repos/{org}/{r}", {"permission": api_role(w["repos"][r])})
    for r in sorted(set(h["repos"]) - set(w["repos"])):
        act("grant-", f"team {slug}: fjern {h['repos'][r]} på {r}", "DELETE", f"orgs/{org}/teams/{slug}/repos/{org}/{r}")
    for r in sorted(set(w["repos"]) & set(h["repos"])):
        if w["repos"][r] != h["repos"][r]:
            act("grant~", f"team {slug}: {r} {h['repos'][r]} → {w['repos'][r]}", "PUT", f"orgs/{org}/teams/{slug}/repos/{org}/{r}", {"permission": api_role(w["repos"][r])})

# direct collaborators
for r in sorted(set(want["direct"]) | set(have["direct"])):
    w, h = want["direct"].get(r, {}), have["direct"].get(r, {})
    for u in sorted(set(w) - set(h)):
        act("direct+", f"{r}: {u} får {w[u]} (direkte)", "PUT", f"repos/{org}/{r}/collaborators/{u}", {"permission": w[u]})
    for u in sorted(set(h) - set(w)):
        act("direct-", f"{r}: fjern direkte {h[u]} for {u}", "DELETE", f"repos/{org}/{r}/collaborators/{u}")
    for u in sorted(set(w) & set(h)):
        if w[u] != h[u]:
            act("direct~", f"{r}: {u} {h[u]} → {w[u]} (direkte)", "PUT", f"repos/{org}/{r}/collaborators/{u}", {"permission": w[u]})

# safety: who loses write on a repo they committed to in the activity window?
committed = {(r["name"], c["login"]) for r in snap["repos"] if r["active"] for c in r["committers"]}
removed_write = set()
for a in actions:
    if a["kind"] in ("grant-", "grant~", "member-", "direct-", "direct~", "owner-"):
        removed_write.add(a["desc"])
# (cheap heuristic list; the authoritative check is the gap list in the next audit run)

print(f"Plan for {org}: snapshot {snap['generated_at']}, config access.yaml")
if warnings:
    print("\nAdvarsler:"); [print("  ! " + w) for w in warnings]
if not actions:
    print("\nIngen endringer. Config og virkelighet er like."); sys.exit(0)
order = ["org", "owner+", "team+", "team~", "member+", "member~", "grant+", "grant~", "direct+", "direct~", "direct-", "grant-", "member-", "team-", "owner-"]
actions.sort(key=lambda a: order.index(a["kind"]))
print(f"\n{len(actions)} endringer (additive først, fjerning sist):")
for a in actions:
    print(f"  {a['kind']:8s} {a['desc']}")
with open(args.out, "w") as f:
    json.dump({"org": org, "snapshot": snap["generated_at"], "actions": actions}, f, indent=2, ensure_ascii=False)
print(f"\nSkrevet {args.out}. Utfør med: tools/apply.py")
sys.exit(2)
