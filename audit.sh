#!/usr/bin/env bash
# Deterministic read-only snapshot of who has access to what in a GitHub org.
# Output: snapshots/<timestamp>.json, latest.json, report.html
# Requires: gh (logged in; admin:org scope for org rulesets), jq. Env: ORG (default: owner of git remote origin), DAYS (default 365).
#
# Effective access comes from GET /repos/{org}/{repo}/collaborators (all affiliations),
# which is GitHub's own computed permission per user per repo. Team grants come from
# GET /repos/{org}/{repo}/teams. (The org-level team→repos listing is incomplete and
# must not be used as truth.)
set -euo pipefail
ORG="${ORG:-$(gh repo view --json owner --jq .owner.login 2>/dev/null)}"
[ -n "$ORG" ] || { echo "Set ORG=<github-org>" >&2; exit 1; }
DAYS="${DAYS:-365}"
PAR="${PAR:-6}"
cd "$(dirname "$0")"
mkdir -p snapshots
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
TS=$(date -u +%Y-%m-%dT%H%M%SZ)
if date -u -v-1d +%F >/dev/null 2>&1; then SINCE=$(date -u -v-"${DAYS}"d +%Y-%m-%dT00:00:00Z); else SINCE=$(date -u -d "-${DAYS} days" +%Y-%m-%dT00:00:00Z); fi
log(){ printf '%s %s\n' "$(date +%H:%M:%S)" "$*" >&2; }
api_or_null(){ local out; if out=$(gh api "$@" 2>/dev/null); then printf '%s' "$out"; else printf 'null'; fi; }
lines_to_json(){ jq -Rs 'split("\n")|map(select(length>0))|sort'; }

log "org $ORG, activity window since $SINCE"
gh api "orgs/$ORG" > "$WORK/org.json"
# org rulesets need admin:org; degrade to null (not []) when the scope is missing so the report can say "not readable"
if rl=$(gh api "orgs/$ORG/rulesets" --paginate --jq '.[].id' 2>/dev/null); then
  for id in $rl; do gh api "orgs/$ORG/rulesets/$id" --jq '{id, name, enforcement, target, conditions, rules: [.rules[].type], bypass_actors: [.bypass_actors[]? | {actor_type, actor_id, bypass_mode}]}'; done | jq -s 'sort_by(.name)' > "$WORK/org_rulesets.json"
else echo null > "$WORK/org_rulesets.json"; fi
gh api "orgs/$ORG/repos" --paginate --jq '.[] | {name, archived, pushed_at, default_branch, visibility}' | jq -s 'sort_by(.name)' > "$WORK/repos.json"
gh api "orgs/$ORG/members" --paginate --jq '.[].login' | lines_to_json > "$WORK/members.json"
gh api "orgs/$ORG/members?role=admin" --paginate --jq '.[].login' | lines_to_json > "$WORK/owners.json"
gh api "orgs/$ORG/outside_collaborators" --paginate --jq '.[].login' | lines_to_json > "$WORK/outside.json"
log "repos: $(jq length "$WORK/repos.json"), members: $(jq length "$WORK/members.json"), owners: $(jq length "$WORK/owners.json")"

log "team members"
: > "$WORK/teams.ndjson"
for t in $(gh api "orgs/$ORG/teams" --paginate --jq '.[].slug' | sort); do
  # a team deleted between listing and fetching (concurrent apply) must not abort the snapshot
  tj=$(gh api "orgs/$ORG/teams/$t" 2>/dev/null) || { log "team $t disappeared while reading, skipping"; continue; }
  desc=$(jq -r '.description // ""' <<<"$tj")
  tname=$(jq -r '.name' <<<"$tj")
  m=$(gh api "orgs/$ORG/teams/$t/members" --paginate --jq '.[].login' | lines_to_json)
  mt=$(gh api "orgs/$ORG/teams/$t/members?role=maintainer" --paginate --jq '.[].login' | lines_to_json)
  priv=$(gh api "orgs/$ORG/teams/$t" --jq '.privacy')
  jq -cn --arg slug "$t" --arg desc "$desc" --arg tname "$tname" --arg priv "$priv" --argjson m "$m" --argjson mt "$mt" '{slug:$slug, name:$tname, description:$desc, privacy:$priv, members:$m, maintainers:$mt}' >> "$WORK/teams.ndjson"
done

log "effective permissions via REST ($(jq length "$WORK/repos.json") repos, $PAR parallel)"
mkdir -p "$WORK/collab"
export ORG WORK
fetch_repo() {
  local r="$1"
  local all direct teams
  all=$( (gh api "repos/$ORG/$r/collaborators" --paginate --jq '.[] | {login, level: .role_name}' 2>/dev/null || true) | jq -s 'sort_by(.login)')
  direct=$( (gh api "repos/$ORG/$r/collaborators?affiliation=direct" --paginate --jq '.[] | {login, role: .role_name}' 2>/dev/null || true) | jq -s 'sort_by(.login)')
  teams=$( (gh api "repos/$ORG/$r/teams" --paginate --jq '.[] | {team: .slug, role: ({pull:"read", push:"write", admin:"admin", maintain:"maintain", triage:"triage"}[.permission] // .permission)}' 2>/dev/null || true) | jq -s 'sort_by(.team)')
  jq -cn --arg repo "$r" --argjson a "$all" --argjson d "$direct" --argjson t "$teams" '{repo:$repo, collaborators:$a, direct:$d, teams:$t}' > "$WORK/collab/$r.json"
}
export -f fetch_repo
jq -r '.[].name' "$WORK/repos.json" | xargs -P "$PAR" -I{} bash -c 'fetch_repo "$1"' _ {}
cat "$WORK"/collab/*.json > "$WORK/collab.ndjson"
log "collaborator records: $(wc -l < "$WORK/collab.ndjson")"

ACTIVE=$(jq -r --arg s "$SINCE" '.[] | select((.archived|not) and .pushed_at > $s) | .name' "$WORK/repos.json")
log "protection + committers ($(printf '%s\n' "$ACTIVE" | grep -c . || true) active repos)"
: > "$WORK/active.ndjson"
for r in $ACTIVE; do
  b=$(jq -r --arg r "$r" '.[] | select(.name==$r) | .default_branch' "$WORK/repos.json")
  p=$(api_or_null "repos/$ORG/$r/branches/$b/protection" | jq -c 'if . == null then {protected:false} else {protected:true, reviews:(.required_pull_request_reviews.required_approving_review_count // 0), force_push:(.allow_force_pushes.enabled // false), code_owners:(.required_pull_request_reviews.require_code_owner_reviews // false)} end')
  rs=$(api_or_null "repos/$ORG/$r/rulesets" | jq -c 'if . == null then [] else map(.name) end')
  cm=$( (gh api "repos/$ORG/$r/commits?since=$SINCE&per_page=100" --paginate --jq '.[] | (.author.login // ("~" + .commit.author.name))' 2>/dev/null || true) | sort | uniq -c | awk '{printf "{\"login\":\"%s\",\"commits\":%d}\n",$2,$1}' | jq -s 'sort_by(-.commits, .login)')
  jq -cn --arg repo "$r" --argjson p "$p" --argjson rs "$rs" --argjson cm "$cm" '{repo:$repo, protection:$p, rulesets:$rs, committers:$cm}' >> "$WORK/active.ndjson"
done

log "assembling snapshot"
jq -n \
  --arg ts "$TS" --arg org "$ORG" --arg since "$SINCE" --argjson days "$DAYS" \
  --slurpfile org_info "$WORK/org.json" \
  --slurpfile org_rulesets "$WORK/org_rulesets.json" \
  --slurpfile repos "$WORK/repos.json" \
  --slurpfile members "$WORK/members.json" \
  --slurpfile owners "$WORK/owners.json" \
  --slurpfile outside "$WORK/outside.json" \
  --slurpfile teams "$WORK/teams.ndjson" \
  --slurpfile collab "$WORK/collab.ndjson" \
  --slurpfile active "$WORK/active.ndjson" '
  def rank: {"admin":5,"maintain":4,"write":3,"triage":2,"read":1}[.] // 0;
  def is_human: (test("^~")|not) and (test("\\[bot\\]")|not);
  ($org_info[0]) as $oi
  | ($repos[0]) as $repos
  | ($members[0]) as $members | ($owners[0]) as $owners | ($outside[0]) as $outside
  | ($collab | map({key:.repo, value:.}) | from_entries) as $cmap
  | ($active | map({key:.repo, value:.}) | from_entries) as $amap
  | (($oi.default_repository_permission // "none")) as $base
  | ($repos | map(.name as $n | ($cmap[$n].collaborators // []) as $cs | . + {
      active: ($amap[$n] != null),
      protection: ($amap[$n].protection // null),
      rulesets: ($amap[$n].rulesets // []),
      committers: ($amap[$n].committers // []),
      direct: ($cmap[$n].direct // []),
      teams:  ($cmap[$n].teams // [])
    })) as $R
  | ($teams | map(.slug as $s | . + { repos: ([ $R[] | .name as $n | .teams[] | select(.team==$s) | {name:$n, role} ] | unique | sort_by(.name)) })) as $T
  | ($T | map({key:.slug, value:.members}) | from_entries) as $tmembers
  | ([ $R[] | . as $r | .name as $rn | ($cmap[$rn].collaborators // [])[] | . as $c
        | { repo:$rn, login:$c.login, level:$c.level,
            source: (if ($owners|index($c.login)) != null and $c.level=="admin" then "owner"
                     elif ([ $r.direct[] | select(.login==$c.login and .role==$c.level) ] | length) > 0 then "direct"
                     else (([ $r.teams[] | select(.role==$c.level) | select(($tmembers[.team] // []) | index($c.login) != null) | .team ][0]) as $t
                           | if $t != null then "team:"+$t elif $c.level==$base then "base" else "?" end) end) }
     ] | sort_by(.login,.repo)) as $eff
  | ($eff | map({key:(.repo+"|"+.login), value:.}) | from_entries) as $emap
  | ([ $R[] | select(.active) | .name as $rn | .committers[] | select(.login|is_human) | . as $c
        | ($emap[$rn+"|"+$c.login].level // "none") as $lvl
        | select(($lvl|rank) < 3) | {repo:$rn, login:$c.login, commits:$c.commits, level:$lvl} ]) as $gaps
  | ($R | map(select((.teams|length)==0 and (.direct|length)==0) | .name)) as $owners_only
  | {
      generated_at: $ts, org: $org, activity_since: $since, activity_days: $days,
      org_info: { base_permission: $base, two_factor_required: $oi.two_factor_requirement_enabled,
                  members_can_create_repos: $oi.members_can_create_repositories,
                  members_can_create_public_repos: $oi.members_can_create_public_repositories,
                  members_can_fork_private_repos: $oi.members_can_fork_private_repositories,
                  plan: ($oi.plan.name // null) },
      members: $members, owners: $owners, outside: $outside,
      org_rulesets: $org_rulesets[0],
      teams: $T,
      repos: $R,
      effective: $eff,
      gaps: $gaps,
      owners_only_repos: $owners_only,
      summary: {
        repos: ($R|length), archived: ([$R[]|select(.archived)]|length), active: ([$R[]|select(.active)]|length),
        members: ($members|length), owners: ($owners|length), outside: ($outside|length),
        active_unprotected: ([$R[]|select(.active and (.protection.protected|not))]|length),
        active_no_review: ([$R[]|select(.active and .protection.protected and ((.protection.reviews // 0) == 0))]|length),
        owners_only_repos: ($owners_only|length),
        owners_only_active: ([$R[]|select(.active and ((.teams|length)==0) and ((.direct|length)==0))]|length),
        direct_grants: ([$R[].direct[]]|length),
        write_plus_grants: ([$eff[]|select((.level|rank)>=3)]|length),
        gaps: ($gaps|length),
        org_rulesets_active: (if $org_rulesets[0] == null then null else ([$org_rulesets[0][]|select(.enforcement=="active")]|length) end)
      }
    }' > "snapshots/$TS.json"
ln -sf "snapshots/$TS.json" latest.json
PREV=$(ls snapshots/*.json | sort | tail -2 | head -1)
[ "$PREV" = "snapshots/$TS.json" ] && PREV=""
log "snapshot snapshots/$TS.json (previous: ${PREV:-none})"

# clients.yaml -> JSON (null if missing) so the report can label repos by customer
if [ -f clients.yaml ]; then python3 -c 'import sys,json,yaml; json.dump(yaml.safe_load(open("clients.yaml")), sys.stdout)' > "$WORK/clients.json"; else echo null > "$WORK/clients.json"; fi
if [ -n "$PREV" ]; then jq -n --slurpfile a "snapshots/$TS.json" --slurpfile b "$PREV" --slurpfile c "$WORK/clients.json" '{latest:$a[0], previous:$b[0], clients:$c[0]}' > "$WORK/data.json"
else jq -n --slurpfile a "snapshots/$TS.json" --slurpfile c "$WORK/clients.json" '{latest:$a[0], previous:null, clients:$c[0]}' > "$WORK/data.json"; fi
awk -v f="$WORK/data.json" '/^__DATA__$/{while((getline l < f)>0) print l; next}1' report.template.html > report.html
log "report.html written"
