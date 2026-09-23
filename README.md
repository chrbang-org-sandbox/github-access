# github-access

Access management for a GitHub org as code. One YAML file is the source of truth, an audit script reads
reality, and plan/apply carries out the difference.

```
./audit.sh                      # read actual state -> snapshots/, latest.json, report.html
tools/ui.py                     # web UI for team membership -> edits access.yaml
tools/plan.py                   # diff access.yaml against latest.json -> plan.json (exit 2 = changes)
tools/apply.py                  # carry out plan.json via gh api, with confirmation
./audit.sh && tools/plan.py     # verify: the plan should be empty
open report.html                # report with changes since the previous snapshot
```

Requires `gh` logged in as org owner with scopes `repo`, `admin:org`, plus `jq` and `python3` with PyYAML.

## Files

| File | Role |
|---|---|
| `access.yaml` | Desired state: base permission, owners, teams with members/maintainers/repo grants, direct collaborators. Changed only via PR. |
| `audit.sh` | Read-only. Snapshots actual state to `snapshots/<ts>.json` and `latest.json`, and generates `report.html` (latest vs. previous). These are not in git; in CI they are stored as workflow artifacts. |
| `tools/plan.py` | Diff desired vs. actual. Writes `plan.json` with one gh API action per change. Additive actions first, removals last. |
| `tools/apply.py` | Carries out `plan.json`. Refuses if the plan is based on an older snapshot than `latest.json`. `--only kind,kind` for partial execution. |
| `clients.yaml` | Repo → customer, as globs on repo names. Everything that is not a customer goes under `internal`. |
| `tools/draft-clients.py` | *Temporary, deleted after phase 2.* Drafts `clients.yaml` from the prefixes of active repos. Rewrites the whole file. |
| `tools/restructure.py` | *Temporary, deleted after phase 2.* Builds `access.yaml` following the model below: one team per active customer. `--phase 1` (default) is additive, `--phase 2` removes legacy. Overwrites manual fixes. |
| `tools/ui.py` | Local web UI (127.0.0.1:8787) to see a person's teams and roles, and add/remove members. Writes only `access.yaml`; commit and PR are done afterwards. |
| `tools/gen-issue-form.py` | Generates the issue form: teams from `access.yaml`, users from the org membership (`--users`). `--check` only checks the team list. |
| `tools/parse-issue.py` | Reads a submitted form into action, team and user list. Used by `access-request.yml`; tests in `tools/test_parse_issue.py`. |
| `report.template.html` | Template for the report. |

## access.yaml

```yaml
org: <org>
base_permission: none          # none | read | write
owners: [chrbang, ...]         # org owners. Everyone else becomes "member".
teams:
  kunde-a:
    name: Kunde A
    members: [tech-lead, utvikler-1]
    repos:
      admin: [repository-1, "Kunde.*"]   # exact names or globs; new repos matching a glob are covered automatically
      read: ["*"]                        # "*" = all repos in the org
repos:
  repository-3:
    collaborators:             # direct grants, typically external people
      ekstern-konsulent: read
```

Org owners are implicitly maintainers in every team and are not listed under `maintainers`.
Teams not present in the file are deleted by apply. Direct collaborators not present in the file are removed.

## For developers: requesting access

Open an issue with the form "Request team access". The rest happens automatically. Read [FLOW.md](FLOW.md).

## Automation (GitHub Actions)

| Workflow | Trigger | Does |
|---|---|---|
| `access-request.yml` | new issue with label `access-request` | reads the form with `tools/parse-issue.py` (one or more users), sets the title ("Add octocat to Kunde A team"), runs `tools/request.py` per user, creates a branch and PR, comments on the issue |
| `refresh-form.yml` | daily, manually, and after `apply.yml` | regenerates the user list ("Who") in the issue form from the org membership and opens a PR if it changed |
| `check.yml` | PR that changes `access.yaml` etc. | validates YAML and form, takes a snapshot, posts the plan as a PR comment |
| `apply.yml` | merge to `main` with changed `access.yaml` | snapshot → plan → `tools/apply.py --auto` → new snapshot → the plan should be empty. Comments the result on the PR |

`apply.py --auto` stops on `owner+`, `owner-`, `org` and `team-`. Such changes require the label `approved-structural-change`
on the PR (set by an owner) or `workflow_dispatch` with `allow_structural`.

### One-time setup in GitHub

1. Push this repo as private repo `<org>/github-access`. Do not allow forks.
2. **GitHub App** "github-access" on the org. Permissions: Repository → Contents *write*, Pull requests *write*, Issues *write*,
   Administration *write*; Organization → Members *write*, Administration *write*. Install on the whole org.
   Add App ID and private key as secrets `ACCESS_APP_ID` and `ACCESS_APP_PRIVATE_KEY` in an **Environment** `github-app`.
   Deployment branches: *No restriction*. `check.yml` runs on PR merge refs, which a branch policy would reject. The trust boundary is
   write on the repo either way, which only `platform` has.
3. **Team `platform`** with write on the repo (defined in `access.yaml`). Everyone else has read via base permission.
4. **Ruleset on `main`**: require PR, 1 approval, approval from code owner, dismiss approvals on new push,
   block force push. Empty bypass list.
5. Repo settings: Pull requests → "Allow auto-merge" *on*, if approval alone should be enough.
   ("Allow GitHub Actions to create and approve pull requests" is not needed: PRs are created with the App token, not `GITHUB_TOKEN`.)
6. Notifications: `/github subscribe <org>/github-access pulls issues` in a Slack channel, and Scheduled reminders on team `platform`.
7. Labels `access-request` and `approved-structural-change` must exist in the repo (the issue form does not set labels that are missing):
   `gh label create access-request` and `gh label create approved-structural-change`.
8. Run `tools/gen-issue-form.py` after every change to the team list, otherwise `check.yml` fails. The user list in the form
   ("Who", all org members) is kept up to date by `refresh-form.yml`; locally: `tools/gen-issue-form.py --users`.

## Model

- **Everyone has read** via base permission.
- **Admin only via teams.** One team per customer with activity (push in the last 365 days), with **admin** on the customer's active repos. Admin, not write, because Actions secrets, variables and environments can only be managed by repo admins. What admin could otherwise be abused for is blocked at org level, see "Org-level guardrails". The team is named after the full customer name, capitalised (`name: Kunde A`); the key in the file is the slug GitHub derives from the name (`kunde-a`). The `internal` team has write on internal repos.
- **No team maintainers.** Membership is changed through the request flow, not in the GitHub UI. Owners are implicitly maintainers in every team. `maintainers:` can be set by hand in `access.yaml` for a team that needs it.
- **Dormant repos have no team grants.** If needed, the repo is added to the customer's team via PR.
- **Direct collaborators only for external people** (the customer's staff, integration accounts). Employees always get access via teams; `tools/plan.py` warns about violations.
- `developers` is just a list of all developers.

`clients.yaml` is the mapping repo → customer. New repos should follow the naming convention `Customer.Name` so they match automatically; `tools/plan.py` warns about active repos without team write.

## Org-level guardrails that MUST be on before customer teams get admin

A repo admin can delete the repo, change visibility, invite collaborators and turn off repo-level branch protection.
These settings take away what cannot be confined to the admin's own customer. All are org level, under
Org → Settings, and must be checked **before** `apply` of a new `access.yaml`:

| Setting | Value | Where |
|---|---|---|
| Base permissions | **Read** | Member privileges |
| Repository creation | **Private** only (or off) | Member privileges |
| Repository forking | **off** | Member privileges |
| Repository deletion and transfer | **off** ("Members with admin permissions cannot delete or transfer") | Member privileges |
| Repository visibility change | **off** | Member privileges |
| Allow members to create teams | **off** | Member privileges |
| Two-factor authentication | **Require** | Authentication security |
| Org ruleset on default branch, all repos | PR + 1 approval, block force push and deletion, empty bypass list | Repository → Rulesets |
| Org ruleset on tags `v*` | block update/deletion, only via PR flow | Repository → Rulesets |
| Actions: workflow permissions | **Read** as default | Actions → General |
| Actions: fork pull request workflows | off (irrelevant when forking is off) | Actions → General |

Org rulesets are the key: repo admins can delete the repo's own branch protection, but **not** override an org ruleset.
That is why customer teams can have admin without any single account being able to push straight to main in their own repos.

`audit.sh` records base permission, 2FA, forking and public repo creation; the report shows them at the top.
Deletion, visibility and team creation are not available via the API and must be checked in the UI.

Once everything is set: `./audit.sh` should show `fork of private: no` and `public repo creation: no` in the report.

## Migration from "everyone has write on everything"

1. `./audit.sh` (365-day window), `tools/draft-clients.py > clients.yaml`, fix the file by hand.
2. `tools/restructure.py > access.yaml`. Read through, PR.
3. `tools/plan.py` should only show `org`, `team+`, `member+`, `grant+`. `tools/apply.py`.
4. `./audit.sh` → `report.html`: gap = 0, new teams under "Changes". Let it run for a week; tech leads add those who are missing.
   `clients.yaml` is reviewed first: `name` must be the full customer name, it becomes the team name in GitHub.
5. **Phase 2**: remove the blocks marked `PHASE 2` in `access.yaml` (or `tools/restructure.py --phase 2 > access.yaml`), PR, notify the developers with a date. `tools/plan.py` now shows `grant-`, `direct-`, `team-`. `tools/apply.py`.
6. `./audit.sh && tools/plan.py` → "No changes", gap = 0.

Downgrading owners is a separate step after this.

## Flow for a change

1. Branch, edit `access.yaml`, PR. Someone in the platform team approves. Edit by hand or with `tools/ui.py`,
   which shows teams per person and lets you add, remove and change role. It only edits the member lists, so
   comments in the file are preserved, and it shows `git diff` with the commands for branch and PR.
2. An owner runs `./audit.sh` (fresh snapshot), `tools/plan.py`, reads the plan, `tools/apply.py`.
3. `./audit.sh && tools/plan.py` should now say "No changes".

Access granted directly in the GitHub UI shows up as drift: `tools/plan.py` will propose removing it.
Bring it into the file via PR if it should be kept.

## Security

The file does nothing by itself. A change requires a merge in this repo **and** an owner running apply
with their own login. The repo should have a ruleset on main (PR + one approval, no bypass) and write
only for the platform team.

## Data sources in audit

| Data | Endpoint |
|---|---|
| Effective access per person per repo | `GET /repos/{org}/{repo}/collaborators` (all affiliations, GitHub's own computation) |
| Direct grants | same with `?affiliation=direct` |
| Team grants per repo | `GET /repos/{org}/{repo}/teams` |
| Team members and maintainers | `GET /orgs/{org}/teams/{slug}/members[?role=maintainer]` |
| Branch protection, repo rulesets, committers | per active repo (push in the last 365 days) |
| Org rulesets | `GET /orgs/{org}/rulesets` + details |

Do not use `GET /orgs/{org}/teams/{slug}/repos` as the source of truth: it returned 176 of 370 repos for a
team that actually had access to all of them.

"Gap" in the report = a person who has committed to an active repo within the window but has less than write
today. Should be empty throughout the migration.
