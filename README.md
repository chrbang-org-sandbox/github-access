# github-access

Tilgangsstyring for en GitHub-org som kode. Én YAML-fil er fasit, et audit-script leser
virkeligheten, og plan/apply utfører differansen.

```
./audit.sh                      # les faktisk tilstand -> snapshots/, latest.json, report.html
tools/ui.py                     # web-grensesnitt for team-medlemskap -> endrer access.yaml
tools/plan.py                   # diff access.yaml mot latest.json -> plan.json (exit 2 = endringer)
tools/apply.py                  # utfør plan.json via gh api, med bekreftelse
./audit.sh && tools/plan.py     # verifiser: planen skal være tom
open report.html                # rapport med endringer siden forrige snapshot
```

Krever `gh` innlogget som org owner med scope `repo`, `admin:org`, og `jq` + `python3` med PyYAML.

## Filer

| Fil | Rolle |
|---|---|
| `access.yaml` | Ønsket tilstand: base permission, owners, team med medlemmer/maintainers/repo-grants, direkte collaborators. Endres kun via PR. |
| `audit.sh` | Kun lesende. Snapshot av faktisk tilstand til `snapshots/<ts>.json` og `latest.json`, og genererer `report.html` (siste vs. forrige). Disse er ikke i git; i CI lagres de som workflow-artefakter. |
| `tools/plan.py` | Diff ønsket vs. faktisk. Skriver `plan.json` med én gh-API-handling per endring. Additive handlinger først, fjerning sist. |
| `tools/apply.py` | Utfører `plan.json`. Nekter hvis planen er basert på et eldre snapshot enn `latest.json`. `--only kind,kind` for delvis utførelse. |
| `clients.yaml` | Repo → kunde, som glob på reponavn. Alt som ikke er kunde ligger under `internal`. |
| `tools/draft-clients.py` | *Midlertidig, slettes etter fase 2.* Utkast til `clients.yaml` fra prefiksene i aktive repos. Skriver hele fila på nytt. |
| `tools/restructure.py` | *Midlertidig, slettes etter fase 2.* Lager `access.yaml` etter modellen under: ett team per aktiv kunde. `--phase 1` (default) er additiv, `--phase 2` fjerner legacy. Overskriver manuelle rettelser. |
| `tools/ui.py` | Lokalt web-grensesnitt (127.0.0.1:8787) for å se en persons team og roller, og legge til/fjerne medlemmer. Skriver kun `access.yaml`; commit og PR gjøres etterpå. |
| `report.template.html` | Mal for rapporten. |

## access.yaml

```yaml
org: <org>
base_permission: none          # none | read | write
owners: [chrbang, ...]         # org owners. Alle andre medlemmer blir "member".
teams:
  kunde-a:
    name: Kunde A
    members: [tech-lead, utvikler-1]
    repos:
      admin: [repository-1, repository-2]
      read: ["*"]              # "*" = alle repos i orgen, også nye
repos:
  repository-3:
    collaborators:             # direkte grants, typisk eksterne
      ekstern-konsulent: read
```

Org owners er implisitt maintainers i alle team og tas ikke med under `maintainers`.
Team som ikke finnes i fila blir slettet av apply. Direkte collaborators som ikke finnes i fila blir fjernet.

## For utviklere: be om tilgang

Åpne et issue med skjemaet «Be om tilgang til et team». Resten skjer automatisk. Les [FLYT.md](FLYT.md).

## Automatikk (GitHub Actions)

| Workflow | Trigger | Gjør |
|---|---|---|
| `access-request.yml` | nytt issue med label `access-request` | leser skjemaet, setter tittel («Add octocat to Kunde A team»), kjører `tools/request.py`, lager branch og PR, kommenterer på issuet |
| `check.yml` | PR som endrer `access.yaml` m.m. | validerer YAML og skjema, tar snapshot, poster planen som PR-kommentar |
| `apply.yml` | merge til `main` med endret `access.yaml` | snapshot → plan → `tools/apply.py --auto` → nytt snapshot → planen skal være tom. Kommenterer resultat på PR-en |

`apply.py --auto` stopper på `owner+`, `owner-`, `org` og `team-`. Slike endringer krever label `godkjent-strukturendring`
på PR-en (satt av en owner) eller `workflow_dispatch` med `allow_structural`.

### Oppsett som må gjøres i GitHub (én gang)

1. Push dette repoet som privat repo `<org>/github-access`. Ikke tillat forks.
2. **GitHub App** «github-access» på orgen. Rettigheter: Repository → Contents *write*, Pull requests *write*, Issues *write*,
   Administration *write*; Organization → Members *write*, Administration *write*. Installer på hele orgen.
   Legg App ID og privat nøkkel som secrets `ACCESS_APP_ID` og `ACCESS_APP_PRIVATE_KEY` i et **Environment** `github-app`.
   Deployment branches: *No restriction*. `check.yml` kjører på PR-merge-refs, som en branch-policy ville avvist. Tillitsgrensen er
   uansett write på repoet, som bare `platform` har.
3. **Team `platform`** med write på repoet (står i `access.yaml`). Alle andre har read via base permission.
4. **Ruleset på `main`**: krev PR, 1 godkjenning, godkjenning fra code owner, forkast godkjenning ved ny push,
   blokker force push. Tom bypass-liste.
5. Repo-innstillinger: Pull requests → «Allow auto-merge» *på*, hvis godkjenning skal være nok.
   («Allow GitHub Actions to create and approve pull requests» trengs ikke: PR-er lages med App-tokenet, ikke `GITHUB_TOKEN`.)
6. Varsling: `/github subscribe <org>/github-access pulls issues` i en Slack-kanal, og Scheduled reminders på team `platform`.
7. Labels `access-request` og `godkjent-strukturendring` må finnes i repoet (issue-skjemaet setter ikke labels som mangler):
   `gh label create access-request` og `gh label create godkjent-strukturendring`.
8. Kjør `tools/gen-issue-form.py` etter hver endring av team-lista, ellers feiler `check.yml`.

## Modell

- **Alle har read** via base permission.
- **Admin kun via team.** Ett team per kunde med aktivitet (push siste 365 dager), med **admin** på kundens aktive repos. Admin, ikke write, fordi Actions-secrets, variabler og environments bare kan styres av repo-admins. Det admin ellers kunne misbrukt til sperres på org-nivå, se «Org-sperrer». Teamet heter det fulle kundenavnet med stor forbokstav (`name: Kunde A`); nøkkelen i fila er slug-en GitHub lager av navnet (`kunde-a`). `internal`-teamet har write på interne repos.
- **Ingen team-maintainers.** Medlemskap endres via forespørselsflyten, ikke i GitHub-UI. Owners er implisitt maintainers i alle team. `maintainers:` kan settes for hånd i `access.yaml` for et team som trenger det.
- **Sovende repos har ingen team-grants.** Trengs det, legges repoet inn i kundens team via PR.
- **Direkte collaborators kun for eksterne** (kundens folk, integrasjonskontoer). Ansatte får alltid tilgang via team; `tools/plan.py` advarer om brudd.
- `developers` er kun en liste over alle utviklere.

`clients.yaml` er koblingen repo → kunde. Nye repos bør følge navnekonvensjonen `Kunde.Navn` så de matcher automatisk; `tools/plan.py` advarer om aktive repos uten team-write.

## Org-sperrer som MÅ være på før kundeteam får admin

Repo-admin kan slette repo, endre visibility, invitere collaborators og skru av repo-nivå branch protection.
Disse innstillingene tar bort det som ikke lar seg begrense til egen kunde. Alle er org-nivå, under
Org → Settings, og må sjekkes **før** `apply` av ny `access.yaml`:

| Innstilling | Verdi | Hvor |
|---|---|---|
| Base permissions | **Read** | Member privileges |
| Repository creation | kun **Private** (eller av) | Member privileges |
| Repository forking | **av** | Member privileges |
| Repository deletion and transfer | **av** («Members with admin permissions cannot delete or transfer») | Member privileges |
| Repository visibility change | **av** | Member privileges |
| Allow members to create teams | **av** | Member privileges |
| Two-factor authentication | **Require** | Authentication security |
| Org-ruleset på default branch, alle repos | PR + 1 godkjenning, blokker force push og sletting, tom bypass-liste | Repository → Rulesets |
| Org-ruleset på tags `v*` | blokker oppdatering/sletting, kun via PR-flyt | Repository → Rulesets |
| Actions: workflow permissions | **Read** som default | Actions → General |
| Actions: fork pull request workflows | av (irrelevant når forking er av) | Actions → General |

Org-rulesets er nøkkelen: repo-admins kan slette repoets egen branch protection, men **ikke** overstyre et org-ruleset.
Det er derfor kundeteam kan ha admin uten at én konto kan pushe rett til main i egne repos.

`audit.sh` registrerer base permission, 2FA, forking og public repo-opprettelse; rapporten viser dem i toppen.
Sletting, visibility og team-opprettelse er ikke tilgjengelig via API og må sjekkes i UI.

Etter at alt er satt: `./audit.sh` skal vise `fork av private: nei` og `public repo-opprettelse: nei` i rapporten.

## Omlegging fra «alle har write på alt»

1. `./audit.sh` (365 dagers vindu), `tools/draft-clients.py > clients.yaml`, rett fila for hånd.
2. `tools/restructure.py > access.yaml`. Les gjennom, PR.
3. `tools/plan.py` skal kun vise `org`, `team+`, `member+`, `grant+`. `tools/apply.py`.
4. `./audit.sh` → `report.html`: gap = 0, nye team under «Endringer». La det gå en uke; tech leads legger til de som mangler.\n   `clients.yaml` gjennomgås først: `name` skal være fullt kundenavn, det blir team-navnet i GitHub.
5. **Fase 2**: fjern blokkene merket `FASE 2` i `access.yaml` (eller `tools/restructure.py --phase 2 > access.yaml`), PR, varsle utviklerne med dato. `tools/plan.py` viser nå `grant-`, `direct-`, `team-`. `tools/apply.py`.
6. `./audit.sh && tools/plan.py` → «Ingen endringer», gap = 0.

Owners-nedgradering er et eget steg etter dette.

## Flyt for en endring

1. Branch, endre `access.yaml`, PR. En i platform-teamet godkjenner. Redigér for hånd eller med `tools/ui.py`,
   som viser team per person og lar deg legge til, fjerne og bytte rolle. Den redigerer bare medlemslistene, så
   kommentarer i fila bevares, og viser `git diff` med kommandoene for branch og PR.
2. Owner kjører `./audit.sh` (ferskt snapshot), `tools/plan.py`, leser planen, `tools/apply.py`.
3. `./audit.sh && tools/plan.py` skal nå si «Ingen endringer».

Tilgang gitt direkte i GitHub-UI vises som drift: `tools/plan.py` vil foreslå å fjerne den.
Ta den inn i fila via PR hvis den skal beholdes.

## Sikkerhet

Fila gjør ingenting selv. Endring krever merge i dette repoet **og** at en owner kjører apply
med egen innlogging. Repoet skal ha ruleset på main (PR + én godkjenning, ingen bypass) og write
kun for platform-teamet.

## Datakilder i audit

| Data | Endepunkt |
|---|---|
| Effektiv tilgang per person per repo | `GET /repos/{org}/{repo}/collaborators` (alle affiliations, GitHubs egen utregning) |
| Direkte grants | samme med `?affiliation=direct` |
| Team-grants per repo | `GET /repos/{org}/{repo}/teams` |
| Team-medlemmer og maintainers | `GET /orgs/{org}/teams/{slug}/members[?role=maintainer]` |
| Branch protection, repo-rulesets, committere | per aktivt repo (push siste 365 dager) |
| Org-rulesets | `GET /orgs/{org}/rulesets` + detaljer |

Ikke bruk `GET /orgs/{org}/teams/{slug}/repos` som fasit: den returnerte 176 av 370 repos for et
team som faktisk hadde tilgang til alle.

«Gap» i rapporten = person som har committet til et aktivt repo i vinduet men har lavere enn write
i dag. Skal være tom gjennom hele migreringen.
