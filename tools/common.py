"""Shared helpers: load desired state (access.yaml) and actual state (audit snapshot)."""
import fnmatch, json, os, sys, yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RANK = {"admin": 5, "maintain": 4, "write": 3, "triage": 2, "read": 1, "none": 0}

def load_snapshot(path=None):
    path = path or os.path.join(ROOT, "latest.json")
    with open(path) as f:
        return json.load(f)

def load_access(path=None):
    path = path or os.path.join(ROOT, "access.yaml")
    with open(path) as f:
        return yaml.safe_load(f)

def expand_repos(patterns, all_repos):
    """'*' means every repo. A pattern with * ? or [ is a case-insensitive glob over the org's repos (e.g. 'Grieg.*'),
    so new repos matching it are covered automatically. Anything else is an exact name; unknown names are returned
    too so plan can flag them."""
    out = set()
    for p in patterns or []:
        if p == "*":
            out |= set(all_repos)
        elif any(c in p for c in "*?["):
            out |= {r for r in all_repos if fnmatch.fnmatchcase(r.lower(), p.lower())}
        else:
            out.add(p)
    return out

def desired_state(cfg, snap):
    """Normalise access.yaml into the same shape as the snapshot for diffing."""
    all_repos = [r["name"] for r in snap["repos"]]
    owners = set(cfg.get("owners") or [])
    teams = {}
    for slug, t in (cfg.get("teams") or {}).items():
        t = t or {}
        grants = {}
        for role, repos in (t.get("repos") or {}).items():
            for r in expand_repos(repos, all_repos):
                grants[r] = role
        teams[slug] = {
            "name": t.get("name") or slug,
            "description": t.get("description") or "",
            "privacy": t.get("privacy") or "closed",
            "members": set(t.get("members") or []) | set(t.get("maintainers") or []),
            # org owners are implicit maintainers of every team; GitHub reports them as such, so an owner listed
            # under maintainers would otherwise produce a role change on every run
            "maintainers": set(t.get("maintainers") or []) - owners,
            "repos": grants,
        }
    direct = {}
    for repo, spec in (cfg.get("repos") or {}).items():
        for login, role in ((spec or {}).get("collaborators") or {}).items():
            direct.setdefault(repo, {})[login] = role
    return {
        "base_permission": cfg.get("base_permission") or "none",
        "owners": owners,
        "teams": teams,
        "direct": direct,
        "all_repos": set(all_repos),
    }

def actual_state(snap):
    owners = set(snap["owners"])
    teams = {}
    for t in snap["teams"]:
        teams[t["slug"]] = {
            "name": t.get("name"),   # None in snapshots taken before audit.sh recorded names
            "description": t.get("description") or "",
            "privacy": t.get("privacy") or "closed",
            "members": set(t["members"]),
            # org owners are implicit maintainers of every team; only explicit ones are tracked
            "maintainers": set(t.get("maintainers") or []) - owners,
            "repos": {r["name"]: r["role"] for r in t["repos"]},
        }
    direct = {}
    for r in snap["repos"]:
        for d in r["direct"]:
            direct.setdefault(r["name"], {})[d["login"]] = d["role"]
    return {
        "base_permission": snap["org_info"]["base_permission"],
        "owners": owners,
        "teams": teams,
        "direct": direct,
        "all_repos": {r["name"] for r in snap["repos"]},
    }
