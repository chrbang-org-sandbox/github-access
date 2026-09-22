# Runbook: innføring i en ekte org

Rekkefølgen under er testet i en sandkasse-org (september 2026). Feilene som ble funnet der er bakt inn.
Alt som skrives til GitHub skjer i steg 6 og senere. Fram til da er alt lesing og forberedelse.

## 0. Forutsetninger

- GitHub **Team**-plan (rulesets på private repos, org-rulesets).
- `gh` innlogget som org owner med scope `repo`, `read:org`, `admin:org`. `jq`, `python3` med PyYAML.
- Minst **to** personer som skal sitte i `platform`.

## 1. Org-sperrer (UI, owner)

Gjør alle punktene i README → «Org-sperrer som MÅ være på». Særlig: sletting/visibility/forking av, 2FA påkrevd,
org-ruleset på default branch i alle repos med tom bypass-liste. Uten org-rulesets kan repo-admins pushe rett til main.

## 2. Repo og App (UI, owner)

README → «Oppsett som må gjøres i GitHub», punkt 1–9. Husk:
- `platform` med to personer og write på `github-access`.
- Labels `access-request` og `godkjent-strukturendring`.
- Environment `github-app` uten branch-restriksjon, med begge secrets.
- Auto-merge på.
- **Deaktiver «Utfør tilganger»** til fase 1 er gjennomgått (punkt 10).

## 3. Kartlegg (lokalt, kun lesing)

```
./audit.sh                       # ORG hentes fra git remote; ellers ORG=<org> ./audit.sh
open report.html
```
Se på: antall owners, aktive repos uten protection, direkte grants, gap-lista. Dette er utgangspunktet.

## 4. Kunder og team (lokalt)

```
tools/draft-clients.py > clients.yaml
```
Rett for hånd: slå sammen prefikser som er samme kunde, flytt interne repos til `internal`, sett fullt kundenavn i `name`.
Legg gjerne kjente navn og interne prefikser i `draft-hints.yaml` (gitignored) så utkastet blir riktig neste gang.
Aktive repos uten match gir advarsel i `tools/plan.py`.

```
tools/restructure.py > access.yaml           # fase 1: additiv, beholder developers write * og legacy-team
```
Legg til `platform`-teamet for hånd (se README-eksempel). Les gjennom hele fila. Sjekk `tools/plan.py`:
kun `org`, `team+`, `member+`, `grant+`, `grant~`. `tools/gen-issue-form.py`. Commit og push.

## 5. Fase 1 (første apply)

Planen inneholder `org` (base permission → read). Det er en strukturendring, så `apply.py --auto` stopper.
Kjør derfor første apply **manuelt**:
```
./audit.sh && tools/plan.py && tools/apply.py
./audit.sh && tools/plan.py            # skal si «Ingen endringer»
```
Deretter aktiver «Utfør tilganger». Fra nå går alle endringer via PR.

Varsle utviklerne: lenke til FLYT.md, skjemaet, og at ingenting er tatt bort ennå.
La det gå én til to uker. Forespørsler avslører hvem som mangler i hvilke team. Rapporten skal vise gap = 0.

## 6. Fase 2 (fjern gammel tilgang)

Varsle med dato. Så:
```
tools/restructure.py --phase 2 > access.yaml
```
Legg til `platform` igjen (eller behold blokken fra fase 1). PR. Planen viser `grant-` (developers mister write på alt),
`direct-` (ansattes direkte grants), `team-` (legacy-team). `team-` er strukturendring: sett label
`godkjent-strukturendring` på PR-en før merge, ellers stopper apply.

Etter merge: rapporten skal vise gap = 0 og «Effektive write+ grants» redusert til noen hundre.
Slett `tools/restructure.py`, `tools/draft-clients.py` og `clients.yaml` når dette er gjort, de overskriver manuelle rettelser.

## 7. Owners (eget steg)

Nedgrader owners til 2–3 personer pluss én break-glass-konto. Bot-kontoer skal ikke være owner.
Gjør det i `access.yaml` under `owners:`, PR med label `godkjent-strukturendring`. Sjekk først at alle som nedgraderes
er i de kundeteamene de trenger, ellers mister de admin på alt uten å få noe igjen.

## 8. Vedlikehold

- Nye repos: følg navnekonvensjonen `Kunde.Navn`. Legg repoet i kundens team via PR. `tools/plan.py` advarer om aktive repos uten team.
- Nye kunder: nytt team i `access.yaml`, `tools/gen-issue-form.py`, PR.
- Kvartalsvis: `./audit.sh`, se på gap, direkte grants og owners i rapporten.
- Rotér App-nøkkelen årlig.

## Feil som ble funnet i sandkassen, og løsningen

| Symptom | Årsak | Løsning (allerede i koden) |
|---|---|---|
| PR-workflow: `Permission denied to github-actions[bot]` ved push | `actions/checkout` lagrer `GITHUB_TOKEN` i git-config | `persist-credentials: false` |
| `check.yml` feiler uten steg | Environment med branch-policy avviser PR-merge-refs | Environment uten branch-restriksjon |
| Issue får ikke label, workflow trigges ikke | Issue Forms setter ikke labels som ikke finnes | Opprett labels først |
| Audit avbryter med 404 | Team slettet mellom listing og henting | Hopper over teamet |
| Plan foreslår rollebytte hver gang | Owner oppført som maintainer | Owners trekkes fra ønskede maintainers |
| Rerun av feilet workflow feiler likt | Rerun bruker workflow-versjonen fra da issuet ble laget | Lukk issuet, opprett nytt |
| Plan-kommentaren stemmer ikke ved merge | Kommentaren er et øyeblikksbilde fra PR-tidspunkt | Apply-kommentaren viser det som faktisk ble gjort |
