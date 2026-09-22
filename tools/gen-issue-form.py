#!/usr/bin/env python3
"""Generate .github/ISSUE_TEMPLATE/access-request.yml from the teams in access.yaml.
Issue Forms cannot load options dynamically, so the team list is baked in; CI runs --check to keep it in sync.
Usage: tools/gen-issue-form.py [--check]"""
import os, sys
import yaml
from common import ROOT

OUT = os.path.join(ROOT, ".github", "ISSUE_TEMPLATE", "access-request.yml")
HIDDEN = {"developers"}          # roster-only team; nobody requests membership there

cfg = yaml.safe_load(open(os.path.join(ROOT, "access.yaml")))
teams = [(t.get("name") or slug, slug) for slug, t in (cfg.get("teams") or {}).items() if slug not in HIDDEN and t is not None]
options = [f"{name} ({slug})" if name != slug else slug for name, slug in sorted(teams, key=lambda x: x[0].lower())]

form = {
    "name": "Be om tilgang til et team",
    "description": "Legg deg selv eller en kollega til i et team, eller fjern. Lager en pull request som platform-teamet godkjenner.",
    "title": "Tilgang: ",
    "labels": ["access-request"],
    "body": [
        {"type": "markdown", "attributes": {"value": "Når du sender inn, lages en pull request mot `access.yaml` automatisk. "
            "Når den er godkjent og merget, oppdateres tilgangen i GitHub av seg selv. Se FLYT.md for detaljer."}},
        {"type": "dropdown", "id": "action", "attributes": {"label": "Hva", "options": ["Legg til", "Fjern"]}, "validations": {"required": True}},
        {"type": "dropdown", "id": "team", "attributes": {"label": "Team", "options": options}, "validations": {"required": True}},
        {"type": "dropdown", "id": "role", "attributes": {"label": "Rolle", "description": "member = write på teamets repos. maintainer = det samme, pluss kan legge til/fjerne medlemmer (tech lead).",
            "options": ["member", "maintainer"], "default": 0}},
        {"type": "input", "id": "login", "attributes": {"label": "GitHub-brukernavn", "description": "La stå tomt for deg selv. Fyll inn for å be på vegne av en kollega.", "placeholder": "f.eks. octocat"}},
        {"type": "textarea", "id": "reason", "attributes": {"label": "Begrunnelse", "description": "Hvilket prosjekt, fra når, hvor lenge."}, "validations": {"required": True}},
    ],
}
text = "# Generert av tools/gen-issue-form.py fra access.yaml. Ikke rediger for hånd.\n" + yaml.safe_dump(form, sort_keys=False, allow_unicode=True, width=120)
if "--check" in sys.argv:
    cur = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
    if cur != text:
        sys.exit("Issue-skjemaet er ute av synk med access.yaml. Kjør tools/gen-issue-form.py og commit.")
    print("issue-skjema i synk"); sys.exit(0)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w", encoding="utf-8").write(text)
print(f"skrev {os.path.relpath(OUT, ROOT)} med {len(options)} team")
