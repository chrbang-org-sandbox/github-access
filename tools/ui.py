#!/usr/bin/env python3
"""Local web UI for editing team membership in access.yaml. No GitHub writes.
Reads access.yaml + latest.json, serves http://127.0.0.1:8787, edits only the members/maintainers
lists of a team with line-based edits so comments survive. Commit + PR is done by you afterwards.
Usage: tools/ui.py [--port 8787] [--no-browser]"""
import argparse, json, os, re, subprocess, sys, threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import yaml
from common import ROOT, RANK, load_snapshot

ACCESS = os.path.join(ROOT, "access.yaml")
LOCK = threading.Lock()

# ---------------------------------------------------------------- line-based YAML editing
def _team_block(lines, slug):
    """(start, end) line indexes of `  <slug>:` under top-level `teams:`; end is exclusive."""
    in_teams, start = False, None
    for i, l in enumerate(lines):
        if re.match(r"^[A-Za-z_][^:]*:", l):          # top-level key
            if start is not None:
                return start, i
            in_teams = l.startswith("teams:")
            continue
        if in_teams and re.match(rf"^  {re.escape(slug)}:\s*$", l):
            start = i
        elif start is not None and re.match(r"^  [^\s#-][^:]*:\s*$", l):
            return start, i
    if start is None:
        raise KeyError(f"team {slug} does not exist in access.yaml")
    return start, len(lines)

def _list_section(lines, start, end, key):
    """(k, items_end, items) for `    <key>:` inside a team block; k=None if absent. items=[(login, rest_of_line)]."""
    for i in range(start, end):
        m = re.match(rf"^    {key}:(.*)$", lines[i])
        if not m:
            continue
        inline = m.group(1).strip()
        if inline.startswith("["):                      # `members: []` or `members: [a, b]`
            vals = [v.strip() for v in inline.strip("[]").split(",") if v.strip()]
            return i, i + 1, [(v, "") for v in vals]
        items, j = [], i + 1
        while j < end and re.match(r"^    - ", lines[j]):
            m2 = re.match(r"^    - (\S+)(.*)$", lines[j])
            items.append((m2.group(1), m2.group(2)))
            j += 1
        return i, j, items
    return None, None, []

def _render(key, items):
    if not items:
        return [f"    {key}: []"]
    return [f"    {key}:"] + [f"    - {u}{rest}" for u, rest in sorted(items, key=lambda x: x[0])]

def edit_team(text, slug, op, login, role="member"):
    """op: add | remove | role. Returns new text."""
    lines = text.split("\n")
    start, end = _team_block(lines, slug)
    sections = {}
    for key in ("maintainers", "members"):
        k, j, items = _list_section(lines, start, end, key)
        sections[key] = {"k": k, "j": j, "items": items}
    have = {u for s in sections.values() for u, _ in s["items"]}
    if op == "add" and login in have:
        raise ValueError(f"{login} is already in {slug}")
    if op in ("remove", "role") and login not in have:
        raise ValueError(f"{login} is not in {slug}")
    # remove everywhere, keep the trailing comment if any
    rest = ""
    for s in sections.values():
        for u, r in s["items"]:
            if u == login:
                rest = r
        s["items"] = [(u, r) for u, r in s["items"] if u != login]
    if op in ("add", "role"):
        target = "maintainers" if role == "maintainer" else "members"
        sections[target]["items"].append((login, rest if op == "role" else ""))
    # rewrite: replace existing sections in place (from the bottom up), create missing ones before `repos:`/end of block
    edits = []
    for key, s in sections.items():
        if s["k"] is not None:
            edits.append((s["k"], s["j"], _render(key, s["items"]) if (s["items"] or key == "members") else []))
    for k0, j0, new in sorted(edits, key=lambda e: -e[0]):
        lines[k0:j0] = new
    start, end = _team_block(lines, slug)
    for key in ("maintainers", "members"):
        s = sections[key]
        if s["k"] is None and s["items"]:
            # insert before `    members:` for maintainers, else before `    repos:` or at block end
            anchor = end
            for i in range(start + 1, end):
                if (key == "maintainers" and re.match(r"^    members:", lines[i])) or re.match(r"^    repos:", lines[i]):
                    anchor = i; break
            while anchor > start + 1 and lines[anchor - 1].strip() == "":
                anchor -= 1
            lines[anchor:anchor] = _render(key, s["items"])
            start, end = _team_block(lines, slug)
    new_text = "\n".join(lines)
    yaml.safe_load(new_text)                              # must still parse
    return new_text

# ---------------------------------------------------------------- state
def git_diff():
    for args in (["git", "diff", "HEAD", "--", "access.yaml"], ["git", "diff", "--", "access.yaml"]):
        r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout
    return ""

def state():
    snap = load_snapshot()
    cfg = yaml.safe_load(open(ACCESS))
    write_all, write_active = {}, {}
    active = {r["name"] for r in snap["repos"] if r["active"]}
    for e in snap["effective"]:
        if RANK.get(e["level"], 0) >= 3:
            write_all[e["login"]] = write_all.get(e["login"], 0) + 1
            if e["repo"] in active:
                write_active[e["login"]] = write_active.get(e["login"], 0) + 1
    def expand(names):
        # keep "*" literal: the UI shows wildcard grants separately and does not count them as coverage
        return sorted(names or [])
    return {
        "access": {"owners": cfg.get("owners") or [],
                   "teams": {s: {"name": (t or {}).get("name") or s, "description": (t or {}).get("description") or "",
                                 "maintainers": (t or {}).get("maintainers") or [], "members": (t or {}).get("members") or [],
                                 "repos": {k: expand(v) for k, v in ((t or {}).get("repos") or {}).items()}} for s, t in (cfg.get("teams") or {}).items()},
                   "direct": {r: (spec or {}).get("collaborators") or {} for r, spec in (cfg.get("repos") or {}).items()}},
        "snapshot": {"generated_at": snap["generated_at"], "members": snap["members"], "owners": snap["owners"], "outside": snap["outside"],
                     "teams": {t["slug"]: {"members": t["members"], "maintainers": t.get("maintainers") or []} for t in snap["teams"]},
                     "repos": [{"name": r["name"], "active": r["active"], "archived": r["archived"], "pushed_at": r["pushed_at"]} for r in snap["repos"]],
                     "write_all": write_all, "write_active": write_active},
        "diff": git_diff(),
    }

# ---------------------------------------------------------------- http
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _json(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path == "/":
            b = HTML.encode(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        elif self.path == "/api/state":
            with LOCK: self._json(200, state())
        else:
            self._json(404, {"error": "not found"})
    def do_POST(self):
        if self.path != "/api/edit":
            return self._json(404, {"error": "not found"})
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
        try:
            with LOCK:
                snap = load_snapshot()
                known = set(snap["members"]) | set(snap["outside"])
                if body.get("op") == "add" and body.get("login") not in known:
                    raise ValueError(f"{body.get('login')} is not a member of the org (must be invited first)")
                text = open(ACCESS, encoding="utf-8").read()
                new = edit_team(text, body["team"], body["op"], body["login"], body.get("role", "member"))
                tmp = ACCESS + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f: f.write(new)
                os.replace(tmp, ACCESS)
                self._json(200, state())
        except (KeyError, ValueError) as e:
            self._json(400, {"error": str(e)})

HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>access.yaml · teams</title>
<style>
:root{--bg:#fafafa;--fg:#1a1a1a;--muted:#666;--line:#ddd;--card:#fff;--accent:#0a5;--bad:#c33;--warn:#b70}
@media(prefers-color-scheme:dark){:root{--bg:#111;--fg:#eee;--muted:#999;--line:#333;--card:#1a1a1a}}
body{font:14px/1.45 -apple-system,system-ui,sans-serif;margin:0;background:var(--bg);color:var(--fg)}
header{padding:12px 20px;border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:baseline;flex-wrap:wrap}
header h1{font-size:16px;margin:0} header .meta{color:var(--muted);font-size:12px}
main{display:grid;grid-template-columns:280px 1fr;gap:0;min-height:calc(100vh - 46px)}
@media(max-width:700px){main{grid-template-columns:1fr}}
nav{border-right:1px solid var(--line);padding:12px;overflow:auto;max-height:calc(100vh - 46px)}
nav input{width:100%;box-sizing:border-box;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg);margin-bottom:8px}
nav .tabs{display:flex;gap:4px;margin-bottom:8px} nav .tabs button{flex:1} nav label{display:block;font-size:12px;color:var(--muted);margin:-4px 0 8px}
nav li .sub{display:block;font-size:11px;color:var(--muted)} .repolist{margin:6px 0 0 0;padding-left:18px;font-size:12px;columns:2} .repolist li{margin:1px 0}
nav ul{list-style:none;margin:0;padding:0} nav li{padding:4px 8px;border-radius:4px;cursor:pointer;display:flex;justify-content:space-between;gap:8px}
nav li:hover{background:var(--card)} nav li.sel{background:var(--card);outline:1px solid var(--line)} nav li .n{color:var(--muted);font-size:12px}
section{padding:16px 20px;overflow:auto}
h2{font-size:16px;margin:0 0 4px} .sub{color:var(--muted);margin-bottom:12px}
table{border-collapse:collapse;width:100%;font-size:13px} th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--line);vertical-align:middle} th{color:var(--muted);font-weight:600}
button{font:inherit;padding:4px 10px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg);cursor:pointer} button:hover{border-color:var(--fg)} button.primary{border-color:var(--accent)} button.danger{color:var(--bad)}
select{font:inherit;padding:4px 8px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg)}
.tag{display:inline-block;padding:0 6px;border-radius:4px;border:1px solid var(--line);font-size:12px;white-space:nowrap} .tag.maint{border-color:var(--warn)} .tag.owner{border-color:var(--bad)}
.ok{color:var(--accent)} .bad{color:var(--bad)} .muted{color:var(--muted)} .row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:12px 0}
pre{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:10px;font-size:12px;overflow:auto;max-height:40vh;margin:0}
pre .add{color:var(--accent)} pre .del{color:var(--bad)} pre .hunk{color:var(--muted)}
details{margin-top:20px} summary{cursor:pointer;color:var(--muted)} .err{color:var(--bad);margin:8px 0}
a{color:inherit}
</style></head><body>
<header><h1>access.yaml · teams, members and repos</h1><span class="meta" id="meta"></span></header>
<main>
<nav>
  <div class="tabs"><button id="tab-p" class="primary">People</button><button id="tab-t">Teams</button><button id="tab-r">Repos</button></div>
  <input type="search" id="q" placeholder="search…">
  <label id="only-uncovered-wrap" hidden><input type="checkbox" id="only-uncovered"> only repos without a team</label>
  <ul id="list"></ul>
</nav>
<section id="view"></section>
</main>
<script>
let S=null, tab='p', sel=null, q='', onlyUncovered=false;
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const api=async(path,body)=>{const r=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const j=await r.json();if(!r.ok)throw new Error(j.error||r.statusText);return j};
const load=async()=>{S=await api('/api/state');render()};
const people=()=>{const set=new Set([...S.snapshot.members,...S.snapshot.outside,...S.access.owners]);for(const t of Object.values(S.access.teams))[...t.members,...t.maintainers].forEach(u=>set.add(u));return [...set].sort((a,b)=>a.localeCompare(b,undefined,{sensitivity:'base'}))};
const kind=u=>S.access.owners.includes(u)?'owner':S.snapshot.members.includes(u)?'member':S.snapshot.outside.includes(u)?'external':'not in org';
const repoTeams=r=>Object.entries(S.access.teams).flatMap(([s,t])=>Object.entries(t.repos).filter(([role,list])=>list.includes(r)).map(([role])=>({slug:s,name:t.name,role})));
const wildcardTeams=()=>Object.entries(S.access.teams).flatMap(([s,t])=>Object.entries(t.repos).filter(([role,list])=>list.includes('*')).map(([role])=>({slug:s,name:t.name,role})));
const repoInfo=r=>S.snapshot.repos.find(x=>x.name===r)||{name:r};
const status=r=>r.archived?'archived':r.active?'active':'quiet';
const teamsOf=u=>Object.entries(S.access.teams).filter(([s,t])=>t.members.includes(u)||t.maintainers.includes(u)).map(([s,t])=>({slug:s,role:t.maintainers.includes(u)?'maintainer':'member',inGit:!!(S.snapshot.teams[s]&&S.snapshot.teams[s].members.includes(u))}));
function render(){
  document.getElementById('meta').textContent=`snapshot ${S.snapshot.generated_at.replace(/T(\d\d)(\d\d)\d\dZ/,' $1:$2')} · ${Object.keys(S.access.teams).length} teams in the file · ${S.access.owners.length} owners`;
  for(const k of ['p','t','r']) document.getElementById('tab-'+k).className=tab===k?'primary':'';
  document.getElementById('only-uncovered-wrap').hidden=tab!=='r';
  let items;
  if(tab==='p') items=people().filter(u=>u.toLowerCase().includes(q)).map(u=>({id:u,label:u,n:teamsOf(u).length+' teams'}));
  else if(tab==='t') items=Object.keys(S.access.teams).sort((a,b)=>S.access.teams[a].name.localeCompare(S.access.teams[b].name)).filter(s=>(s+' '+S.access.teams[s].name).toLowerCase().includes(q))
    .map(s=>({id:s,label:S.access.teams[s].name,sub:s!==S.access.teams[s].name?s:'',n:(S.access.teams[s].members.length+S.access.teams[s].maintainers.length)+' members'}));
  else items=S.snapshot.repos.filter(r=>r.name.toLowerCase().includes(q)).filter(r=>!onlyUncovered||repoTeams(r.name).length===0)
    .map(r=>{const n=repoTeams(r.name).length;return {id:r.name,label:r.name,cls:n===0&&r.active?'bad':n===0?'muted':'',n:n===0?'no team':n+' teams'}});
  document.getElementById('list').innerHTML=items.map(i=>`<li class="${i.id===sel?'sel':''}" data-id="${esc(i.id)}"><span>${esc(i.label)}${i.sub?`<span class="sub">${esc(i.sub)}</span>`:''}</span><span class="n ${i.cls||''}">${i.n}</span></li>`).join('');
  document.querySelectorAll('#list li').forEach(li=>li.onclick=()=>{sel=li.dataset.id;render()});
  const v=document.getElementById('view');
  if(!sel||(tab==='p'&&!people().includes(sel))||(tab==='t'&&!S.access.teams[sel])||(tab==='r'&&!S.snapshot.repos.some(r=>r.name===sel))){v.innerHTML=(tab==='r'?reposOverview():'<p class="muted">Select a person or a team on the left.</p>')+diffPanel();return}
  v.innerHTML=(tab==='p'?personView(sel):tab==='t'?teamView(sel):repoView(sel))+diffPanel();
  wire();
}
function personView(u){
  const k=kind(u), ts=teamsOf(u), gitOnly=Object.entries(S.snapshot.teams).filter(([s,t])=>t.members.includes(u)&&!ts.some(x=>x.slug===s));
  return `<h2>${esc(u)} <span class="tag ${k==='owner'?'owner':''}">${k}</span></h2>
  <div class="sub">write+ on ${S.snapshot.write_all[u]||0} repos in GitHub today (${S.snapshot.write_active[u]||0} active)${k==='owner'?' · owners are implicit maintainers of every team':''}</div>
  <table><thead><tr><th>Team</th><th>Role in file</th><th>In GitHub today</th><th></th></tr></thead><tbody>
  ${ts.map(t=>`<tr><td><a href="#" data-team="${esc(t.slug)}">${esc(S.access.teams[t.slug].name)}</a> <span class="muted">${esc(t.slug!==S.access.teams[t.slug].name?t.slug:'')}</span></td>
    <td><span class="tag ${t.role==='maintainer'?'maint':''}">${t.role}</span></td><td>${t.inGit?'<span class="ok">yes</span>':'<span class="muted">no, only in the file</span>'}</td>
    <td><button data-op="role" data-team="${esc(t.slug)}" data-login="${esc(u)}" data-role="${t.role==='maintainer'?'member':'maintainer'}">→ ${t.role==='maintainer'?'member':'maintainer'}</button>
        <button class="danger" data-op="remove" data-team="${esc(t.slug)}" data-login="${esc(u)}">remove</button></td></tr>`).join('')||'<tr><td colspan="4" class="muted">no teams in the file</td></tr>'}
  ${gitOnly.map(([s])=>`<tr><td>${esc(s)}</td><td class="muted">–</td><td class="bad">yes, but not in the file (drift)</td><td></td></tr>`).join('')}
  </tbody></table>
  <div class="row"><select id="add-team">${Object.keys(S.access.teams).sort().filter(s=>!ts.some(t=>t.slug===s)).map(s=>`<option>${esc(s)}</option>`).join('')}</select>
  <select id="add-role"><option value="member">member</option><option value="maintainer">maintainer</option></select>
  <button class="primary" id="add-btn" data-mode="person" data-login="${esc(u)}">add to team</button></div><div class="err" id="err"></div>`;
}
function teamView(s){
  const t=S.access.teams[s], g=S.snapshot.teams[s], rows=[...t.maintainers.map(u=>[u,'maintainer']),...t.members.map(u=>[u,'member'])];
  const gitOnly=g?g.members.filter(u=>!t.members.includes(u)&&!t.maintainers.includes(u)):[];
  const candidates=[...S.snapshot.members,...S.snapshot.outside].filter(u=>!t.members.includes(u)&&!t.maintainers.includes(u)).sort((a,b)=>a.localeCompare(b,undefined,{sensitivity:'base'}));
  const grants=Object.entries(t.repos).map(([role,list])=>list.includes('*')?`<div class="sub">${role} on <b>all</b> repos (<code>*</code>, ${S.snapshot.repos.length} today)</div>`
    :`<details><summary>${role} on ${list.length} repos</summary><ul class="repolist">${list.map(r=>{const i=repoInfo(r);return `<li><a href="#" data-repo="${esc(r)}">${esc(r)}</a> <span class="${i.active?'ok':'muted'}">${status(i)}</span></li>`}).join('')}</ul></details>`).join('');
  return `<h2>${esc(t.name)} ${t.name!==s?`<span class="muted" style="font-size:13px">${esc(s)}</span>`:''}</h2><div class="sub">${esc(t.description)||'<i>no description</i>'} · ${g?'exists in GitHub':'<span class="bad">does not exist in GitHub yet</span>'}</div>
  ${grants||'<div class="sub muted">no repo grants</div>'}
  <table><thead><tr><th>Person</th><th>Type</th><th>Role in file</th><th>In GitHub today</th><th></th></tr></thead><tbody>
  ${rows.map(([u,role])=>`<tr><td><a href="#" data-person="${esc(u)}">${esc(u)}</a></td><td><span class="tag ${kind(u)==='owner'?'owner':''}">${kind(u)}</span></td>
    <td><span class="tag ${role==='maintainer'?'maint':''}">${role}</span></td><td>${g&&g.members.includes(u)?'<span class="ok">yes</span>':'<span class="muted">no, only in the file</span>'}</td>
    <td><button data-op="role" data-team="${esc(s)}" data-login="${esc(u)}" data-role="${role==='maintainer'?'member':'maintainer'}">→ ${role==='maintainer'?'member':'maintainer'}</button>
        <button class="danger" data-op="remove" data-team="${esc(s)}" data-login="${esc(u)}">remove</button></td></tr>`).join('')||'<tr><td colspan="5" class="muted">no members</td></tr>'}
  ${gitOnly.map(u=>`<tr><td>${esc(u)}</td><td>${kind(u)}</td><td class="muted">–</td><td class="bad">yes, but not in the file (drift)</td><td><button data-op="add" data-team="${esc(s)}" data-login="${esc(u)}" data-role="member">add to file</button></td></tr>`).join('')}
  </tbody></table>
  <div class="row"><select id="add-login">${candidates.map(u=>`<option>${esc(u)}</option>`).join('')}</select>
  <select id="add-role"><option value="member">member</option><option value="maintainer">maintainer</option></select>
  <button class="primary" id="add-btn" data-mode="team" data-team="${esc(s)}">add</button></div><div class="err" id="err"></div>`;
}
function reposOverview(){
  const rs=S.snapshot.repos, unc=rs.filter(r=>!r.archived&&repoTeams(r.name).length===0), uncA=unc.filter(r=>r.active);
  const wc=wildcardTeams();
  return `<h2>Repos</h2><div class="sub">${rs.length} repos · ${rs.filter(r=>r.active).length} active · <span class="${uncA.length?'bad':'ok'}">${uncA.length} active without a team of their own</span> · ${unc.length-uncA.length} quiet without a team of their own (read via base permission)</div>
  ${wc.length?`<div class="sub">Does not count as coverage: ${wc.map(t=>`<b>${esc(t.name)}</b> has ${t.role} on all repos (<code>*</code>)`).join(', ')}. Removed in phase 2.</div>`:''}
  <p class="muted">Select a repo on the left, or tick "only repos without a team".</p>
  ${uncA.length?`<table><thead><tr><th>Active repos without a team grant</th><th>Direct collaborators in the file</th></tr></thead><tbody>${uncA.map(r=>`<tr><td><a href="#" data-repo="${esc(r.name)}">${esc(r.name)}</a></td><td>${Object.entries(S.access.direct[r.name]||{}).map(([u,role])=>`<span class="tag">${esc(u)}: ${esc(role)}</span>`).join(' ')||'<span class="muted">–</span>'}</td></tr>`).join('')}</tbody></table>`:''}`;
}
function repoView(name){
  const i=repoInfo(name), ts=repoTeams(name), d=S.access.direct[name]||{};
  return `<h2>${esc(name)} <span class="tag ${i.active?'':'muted'}">${status(i)}</span></h2><div class="sub">last push ${esc((i.pushed_at||'').slice(0,10))}</div>
  <table><thead><tr><th>Team</th><th>Role</th><th>Members</th></tr></thead><tbody>
  ${ts.map(t=>`<tr><td><a href="#" data-team="${esc(t.slug)}">${esc(t.name)}</a></td><td><span class="tag">${esc(t.role)}</span></td><td class="muted">${[...S.access.teams[t.slug].maintainers,...S.access.teams[t.slug].members].map(esc).join(', ')||'none'}</td></tr>`).join('')||`<tr><td colspan="3" class="${i.active?'bad':'muted'}">no team has a grant of its own${i.active?' – active repo without write for anyone except owners':' (quiet repo, read via base permission)'}</td></tr>`}
  ${wildcardTeams().map(t=>`<tr class="muted"><td><a href="#" data-team="${esc(t.slug)}">${esc(t.name)}</a> <span class="muted">via <code>*</code></span></td><td><span class="tag">${esc(t.role)}</span></td><td class="muted">${S.access.teams[t.slug].members.length+S.access.teams[t.slug].maintainers.length} members</td></tr>`).join('')}
  </tbody></table>
  ${Object.keys(d).length?`<h3 style="font-size:14px;margin:16px 0 4px">Direct collaborators in the file</h3><div>${Object.entries(d).map(([u,role])=>`<span class="tag">${esc(u)}: ${esc(role)}</span>`).join(' ')}</div>`:''}
  <p class="muted" style="margin-top:16px">Repo grants are for now edited by hand in <code>access.yaml</code> (the team's <code>repos:</code> block).</p>`;
}
function diffPanel(){
  const d=S.diff.trim(); const lines=d?d.split('\n').map(l=>`<span class="${l.startsWith('+')&&!l.startsWith('+++')?'add':l.startsWith('-')&&!l.startsWith('---')?'del':l.startsWith('@@')?'hunk':''}">${esc(l)}</span>`).join('\n'):'<span class="muted">no changes in access.yaml</span>';
  return `<details ${d?'open':''}><summary>git diff access.yaml ${d?`(${d.split('\n').filter(l=>/^[+-][^+-]/.test(l)).length} lines)`:''}</summary><pre>${lines}</pre>
  <pre style="margin-top:8px">git checkout -b access/$(date +%Y%m%d)-change
git add access.yaml && git commit -m "access: …"
git push -u origin HEAD && gh pr create --fill</pre></details>`;
}
function wire(){
  document.querySelectorAll('[data-op]').forEach(b=>b.onclick=()=>edit({op:b.dataset.op,team:b.dataset.team,login:b.dataset.login,role:b.dataset.role}));
  const add=document.getElementById('add-btn'); if(add) add.onclick=()=>{const role=document.getElementById('add-role').value;
    edit(add.dataset.mode==='team'?{op:'add',team:add.dataset.team,login:document.getElementById('add-login').value,role}:{op:'add',team:document.getElementById('add-team').value,login:add.dataset.login,role})};
  document.querySelectorAll('[data-team]:not(button)').forEach(a=>a.onclick=e=>{e.preventDefault();tab='t';sel=a.dataset.team;render()});
  document.querySelectorAll('[data-person]').forEach(a=>a.onclick=e=>{e.preventDefault();tab='p';sel=a.dataset.person;render()});
  document.querySelectorAll('[data-repo]').forEach(a=>a.onclick=e=>{e.preventDefault();tab='r';sel=a.dataset.repo;render()});
}
async function edit(body){try{S=await api('/api/edit',body);render()}catch(e){const el=document.getElementById('err');if(el)el.textContent=e.message;else alert(e.message)}}
document.getElementById('tab-p').onclick=()=>{tab='p';sel=null;render()};document.getElementById('tab-t').onclick=()=>{tab='t';sel=null;render()};document.getElementById('tab-r').onclick=()=>{tab='r';sel=null;render()};
document.getElementById('only-uncovered').onchange=e=>{onlyUncovered=e.target.checked;render()};
document.getElementById('q').oninput=e=>{q=e.target.value.toLowerCase();render()};
load();
</script></body></html>"""

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8787); ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"access.yaml UI: {url}  (Ctrl-C to stop)")
    if not a.no_browser: webbrowser.open(url)
    try: srv.serve_forever()
    except KeyboardInterrupt: pass
