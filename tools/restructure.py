#!/usr/bin/env python3
"""Generate a restructured access.yaml: one client-<slug> team per active customer (from clients.yaml),
members = employees who committed to the customer's active repos in the snapshot's activity window.
--phase 1 (default) is additive: developers keeps write on *, legacy teams and employees' direct grants are kept
verbatim, so tools/plan.py only proposes creations and grants. --phase 2 drops all of that.
Usage: tools/restructure.py [--snapshot file] [--clients clients.yaml] > access.yaml"""
import argparse, fnmatch, os, re, sys, unicodedata
from collections import Counter, defaultdict
import yaml
from common import ROOT, RANK, load_snapshot, actual_state

ap = argparse.ArgumentParser()
ap.add_argument("--snapshot"); ap.add_argument("--clients", default=os.path.join(ROOT, "clients.yaml"))
ap.add_argument("--phase", type=int, choices=[1, 2], default=1,
                help="1 = additiv: behold developers write *, legacy-team og ansattes direkte grants. 2 = fjern dem.")
args = ap.parse_args()
snap = load_snapshot(args.snapshot)
act = actual_state(snap)
clients = yaml.safe_load(open(args.clients))
members, owners, outside = set(snap["members"]), set(snap["owners"]), set(snap["outside"])
is_employee = lambda u: u in members and "[bot]" not in u and not u.startswith("~")

def slugify(name):
    """GitHub-style team slug: lowercase ASCII, non-alphanumerics -> '-'. ø/æ/å/ö transliterated so the slug is stable."""
    s = name.lower().replace("ø", "o").replace("æ", "ae").replace("å", "a").replace("ö", "o").replace("ä", "a").replace("ü", "u")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s)).strip("-")

def matches(name, globs):
    return any(fnmatch.fnmatchcase(name.lower(), g.lower()) for g in globs or [])

active = [r for r in snap["repos"] if r["active"] and not r["archived"]]
by_client, unmatched = defaultdict(list), []
internal_globs = (clients.get("internal") or {}).get("match") or []
exclude_globs = clients.get("exclude") or []          # repos whose grants are written by hand in access.yaml (e.g. github-access)
for r in active:
    if matches(r["name"], exclude_globs):
        continue
    hit = [slug for slug, c in clients["clients"].items() if matches(r["name"], c.get("match"))]
    if len(hit) > 1:
        sys.exit(f"{r['name']} matcher flere kunder: {hit}")
    if hit:
        by_client[hit[0]].append(r)
    elif matches(r["name"], internal_globs):
        by_client["__internal__"].append(r)
    else:
        unmatched.append(r["name"])

def team_from_repos(repos):
    """members + suggested maintainer from commit activity on these repos"""
    commits = Counter()
    for r in repos:
        for c in r["committers"]:
            if is_employee(c["login"]):
                commits[c["login"]] += c["commits"]
    non_owner = [u for u, _ in commits.most_common() if u not in owners]
    return sorted(commits), (non_owner[0] if non_owner else None), commits

def dump(obj, indent=0):
    text = yaml.safe_dump(obj, sort_keys=False, allow_unicode=True, width=120, default_flow_style=False)
    return "".join(" " * indent + l + "\n" for l in text.rstrip("\n").split("\n"))

out = []
out.append(f"# Ønsket tilgangstilstand for {snap['org']}. Fasit. Endres via PR; utføres med tools/apply.py.")
out.append(f"# Generert av tools/restructure.py fra snapshot {snap['generated_at']} (aktivitetsvindu {snap['activity_days']} dager) og clients.yaml.")
out.append("# Modell: alle har read via base permission. Write kun via ett team per kunde (navn = fullt kundenavn) på kundens aktive repos, og internal-teamet på interne repos.")
out.append("# Sovende repos (ingen push i vinduet) har ingen write-grants. Direkte collaborators kun for eksterne.")
if unmatched:
    out.append("# TODO aktive repos uten kunde i clients.yaml (får ingen write): " + ", ".join(sorted(unmatched)))
out.append(dump({"org": snap["org"], "base_permission": "read", "owners": sorted(owners)}))
out.append("teams:")

# developers: roster only
dev = act["teams"].get("developers", {"members": set(), "maintainers": set()})
dev_entry = {"description": "Alle utviklere. Kun read (via base permission); write gis per kunde i kundeteam.",
             "privacy": "secret", "members": sorted(dev["members"])}
if args.phase == 1:
    dev_entry["repos"] = {"write": ["*"]}
text = dump({"developers": dev_entry}, 2)
if args.phase == 1:
    text = text.replace("    repos:\n", "    repos:  # FASE 2: fjern denne blokken. Da har developers kun read.\n")
out.append(text)

# client teams: key = slug derived from the full name, e.g. "Kunde A" -> kunde-a
merged = set()
team_slugs = {}
for ckey in sorted(by_client):
    if ckey == "__internal__":
        continue
    repos = by_client[ckey]
    name = clients["clients"][ckey].get("name") or ckey
    slug = slugify(name)
    if slug in team_slugs:
        sys.exit(f"to kunder gir samme team-slug '{slug}': {team_slugs[slug]} og {ckey}")
    team_slugs[slug] = ckey
    mem, maint, commits = team_from_repos(repos)
    entry = {"name": name, "description": name}
    members_set, grants = set(mem), {r["name"]: "write" for r in repos}
    existing = act["teams"].get(slug)
    maintainers = {maint} if maint else set()
    if existing:                                   # same slug already in GitHub: take it over; phase 1 never lowers anything it has
        merged.add(slug)
        members_set |= existing["members"]
        maintainers |= existing["maintainers"]
        if args.phase == 1:
            for repo, role in existing["repos"].items():
                if RANK.get(role, 0) > RANK.get(grants.get(repo, "none"), 0):
                    grants[repo] = role
    if maintainers:
        entry["maintainers"] = sorted(maintainers)
    entry["members"] = sorted(members_set - maintainers)
    by_role = defaultdict(list)
    for repo, role in grants.items():
        by_role[role].append(repo)
    entry["repos"] = {role: sorted(names) for role, names in sorted(by_role.items(), key=lambda kv: -len(kv[1]))}
    text = dump({slug: entry}, 2)
    if existing:
        text = text.replace(f"  {slug}:\n", f"  {slug}:  # eksisterende team, overtatt som kundeteam\n", 1)
    if maint:
        text = text.replace(f"    - {maint}\n", f"    - {maint}  # TODO bekreft tech lead ({commits[maint]} commits)\n", 1)
    if not mem:
        text = text.replace("    members: []\n", "    members: []  # TODO ingen ansatte har committet i vinduet\n")
    out.append(text)

# internal
internal_repos = by_client.get("__internal__", [])
out.append(dump({"internal": {
    "name": "Internal",
    "description": "Interne repos: pakker, verktøy, eksperimenter.",
    "members": sorted(dev["members"]),
    "repos": {"write": sorted(r["name"] for r in internal_repos)}}}, 2))

# legacy teams, verbatim, removed in phase 2
legacy = sorted(s for s in act["teams"] if s != "developers" and s not in merged) if args.phase == 1 else []
if legacy:
    out.append("  # --- FASE 2: fjern legacy-teamene under når client-*-teamene er verifisert (gap = 0 i rapporten) ---")
    for slug in legacy:
        t = act["teams"][slug]
        entry = {}
        if t["description"]: entry["description"] = t["description"]
        if t["privacy"] != "closed": entry["privacy"] = t["privacy"]
        if t["maintainers"]: entry["maintainers"] = sorted(t["maintainers"])
        entry["members"] = sorted(t["members"] - t["maintainers"])
        by_role = defaultdict(list)
        for repo, role in t["repos"].items():
            by_role[role].append(repo)
        if by_role:
            entry["repos"] = {role: (["*"] if set(names) == act["all_repos"] else sorted(names)) for role, names in sorted(by_role.items(), key=lambda kv: -len(kv[1]))}
        out.append(dump({slug: entry}, 2))

# direct collaborators: externals only
direct = {}
for repo in sorted(act["direct"]):
    cols = {u: role for u, role in sorted(act["direct"][repo].items()) if u in outside or args.phase == 1}
    if cols:
        direct[repo] = {"collaborators": cols}
if args.phase == 1:
    out.append("# Direkte collaborators. FASE 2: fjern ansatte her (tools/plan.py advarer om hver), behold kun eksterne.")
else:
    out.append("# Direkte collaborators: kun eksterne (outside collaborators). Ansatte får tilgang via team.")
text = dump({"repos": direct})
if args.phase == 1:
    for repo, spec in direct.items():
        for u, role in spec["collaborators"].items():
            if u in members:
                text = text.replace(f"      {u}: {role}\n", f"      {u}: {role}  # ansatt, FASE 2: fjern\n", 1)
out.append(text)
print("\n".join(out))
