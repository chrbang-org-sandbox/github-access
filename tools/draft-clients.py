#!/usr/bin/env python3
"""Draft clients.yaml from the latest snapshot: group active repos by name prefix.
Usage: tools/draft-clients.py [snapshot.json] > clients.yaml
Edit the result by hand: merge prefixes that are the same customer, move misclassified repos."""
import re, sys
from collections import defaultdict
import yaml
from common import ROOT, load_snapshot

# Optional hints in draft-hints.yaml next to access.yaml:
#   internal_prefixes: [tools, sandbox]    # prefixes that are internal work, not customers
#   names: { acme: "ACME Corp" }           # full customer names per prefix
# Without the file: only "internal" is treated as internal, and names are title-cased prefixes.
import os
_hints = {}
_hp = os.path.join(ROOT, "draft-hints.yaml")
if os.path.exists(_hp):
    _hints = yaml.safe_load(open(_hp)) or {}
INTERNAL_PREFIXES = set(_hints.get("internal_prefixes") or []) | {"internal"}
KNOWN_NAMES = _hints.get("names") or {}

snap = load_snapshot(sys.argv[1] if len(sys.argv) > 1 else None)
active = [r["name"] for r in snap["repos"] if r["active"] and not r["archived"]]

def prefix(name):
    return re.split(r"[.\-_]", name, 1)[0].lower()

groups = defaultdict(list)
for n in sorted(active, key=str.lower):
    groups[prefix(n)].append(n)

def globs(names):
    """One glob per distinct casing of the prefix, e.g. ['Acme.*'] or ['AcmeCorp.*', 'Acmecorp.*']. Single repo -> exact name."""
    out = []
    for n in names:
        m = re.match(r"^([^.\-_]+)([.\-_])", n)
        g = f"{m.group(1)}{m.group(2)}*" if m and len(names) > 1 else n
        if g not in out:
            out.append(g)
    return out

clients, internal = {}, []
for p, names in sorted(groups.items()):
    if p in INTERNAL_PREFIXES:
        internal += globs(names)
    else:
        raw = re.match(r"^[^.\-_]+", names[0]).group(0)
        clients[p] = {"name": KNOWN_NAMES.get(p, raw[0].upper() + raw[1:]), "match": globs(names)}

# the access repo itself is granted to platform by hand in access.yaml, never to a customer team
excluded = [n for n in active if n.lower() == "github-access"]
clients = {p: c for p, c in clients.items() if not (len(c["match"]) == 1 and c["match"][0] in excluded)}
doc = {"clients": clients, "internal": {"match": internal}, "exclude": excluded or ["github-access"]}
print(f"# Repo -> kunde. Utkast generert fra snapshot {snap['generated_at']} ({len(active)} aktive repos, {len(groups)} prefikser).")
print("# match = glob på reponavn, case-insensitive. Slå sammen prefikser som er samme kunde. Alt som ikke er kunde legges under internal.")
print("# Aktive repos som ikke matcher noe gir advarsel i tools/plan.py.")
print("# name = fullt kundenavn med stor forbokstav. Blir team-navn i GitHub; team-slug utledes (Kunde A -> kunde-a).")
text = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=140)
for p, c in clients.items():
    if p not in KNOWN_NAMES:
        text = text.replace(f"    name: {c['name']}\n", f"    name: {c['name']}  # TODO fullt kundenavn\n", 1)
print(text)
