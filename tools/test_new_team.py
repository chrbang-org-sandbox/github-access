#!/usr/bin/env python3
"""Unit tests for tools/parse-new-team.py and tools/new-team.py. Run: python3 tools/test_new_team.py"""
import importlib.util, os, shutil, subprocess, sys, tempfile, unittest
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("parse_new_team", os.path.join(HERE, "parse-new-team.py"))
pnt = importlib.util.module_from_spec(spec); spec.loader.exec_module(pnt)

def body(name="Kunde AS", repos="Kunde.*, kunde-web", members="Myself (the requester), hungqt", reason="New project"):
    return f"### Customer name\n\n{name}\n\n### Repos\n\n{repos}\n\n### Members\n\n{members}\n\n### Reason\n\n{reason}"

class ParseNewTeam(unittest.TestCase):
    def test_basic(self):
        r = pnt.parse(body(), "octocat")
        self.assertEqual(r, {"name": "Kunde AS", "slug": "kunde-as", "globs": ["Kunde.*", "kunde-web"],
                             "logins": ["octocat", "hungqt"], "reason": "New project"})

    def test_no_members(self):
        self.assertEqual(pnt.parse(body(members="_No response_"), "o")["logins"], [])

    def test_norwegian_name_slug(self):
        self.assertEqual(pnt.parse(body(name="Söderberg & Partners"), "o")["slug"], "soderberg-partners")

    def test_existing_team_refused(self):
        with self.assertRaises(SystemExit):
            pnt.parse(body(), "o", existing_teams={"kunde-as"})

    def test_star_alone_refused(self):
        with self.assertRaises(SystemExit):
            pnt.parse(body(repos="*"), "o")

    def test_bad_glob_refused(self):
        with self.assertRaises(SystemExit):
            pnt.parse(body(repos="Kunde.*; rm -rf"), "o")

    def test_empty_name_refused(self):
        with self.assertRaises(SystemExit):
            pnt.parse(body(name=""), "o")

ACCESS = """# header
org: sandbox
base_permission: read
owners:
- chrbang

teams:
  developers:
    members: []

  kunde-a:
    name: Kunde A
    members:
    - a
    repos:
      admin:
      - repository-1

  platform:
    name: Platform
    members:
    - chrbang
    repos:
      write:
      - github-access

  internal:
    name: Internal
    members: []
    repos:
      admin:
      - repository-5

# Direct collaborators: only externals (outside collaborators). Employees get access via teams.
repos: {}
"""
CLIENTS = """# Repo -> customer
clients:
  kunde-a:
    name: Kunde A
    match: [repository-1]
internal:
  match: [repository-5]
exclude: [github-access]
"""

class NewTeamTool(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "tools"))
        for f in ("new-team.py", "common.py"):
            shutil.copy(os.path.join(HERE, f), os.path.join(self.root, "tools", f))
        open(os.path.join(self.root, "access.yaml"), "w").write(ACCESS)
        open(os.path.join(self.root, "clients.yaml"), "w").write(CLIENTS)
        open(os.path.join(self.root, "repos.txt"), "w").write("repository-1\nKunde.Web\nKunde.Api\nOther\n")

    def tearDown(self):
        shutil.rmtree(self.root)

    def run_tool(self, *args):
        return subprocess.run([sys.executable, os.path.join(self.root, "tools", "new-team.py"), *args],
                              capture_output=True, text=True, cwd=self.root)

    def test_adds_team_and_client_preserving_text(self):
        r = self.run_tool("--name", "Kunde AS", "--glob", "Kunde.*", "--login", "hungqt", "--repos", "repos.txt")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        a = open(os.path.join(self.root, "access.yaml")).read()
        c = open(os.path.join(self.root, "clients.yaml")).read()
        self.assertTrue(a.startswith("# header\n"))                       # comments kept
        self.assertLess(a.index("  kunde-as:"), a.index("  platform:"))   # inserted before platform
        cfg = yaml.safe_load(a)
        self.assertEqual(cfg["teams"]["kunde-as"], {"name": "Kunde AS", "description": "Kunde AS", "members": ["hungqt"], "repos": {"admin": ["Kunde.*"]}})
        self.assertEqual(yaml.safe_load(c)["clients"]["kunde-as"], {"name": "Kunde AS", "match": ["Kunde.*"]})
        self.assertIn("matches 2 repos today: Kunde.Api, Kunde.Web", r.stdout)

    def test_no_members(self):
        r = self.run_tool("--name", "Kunde AS", "--glob", "Kunde.*")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(yaml.safe_load(open(os.path.join(self.root, "access.yaml")))["teams"]["kunde-as"]["members"], [])

    def test_existing_refused(self):
        r = self.run_tool("--name", "Kunde A", "--glob", "x")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("already exists", r.stderr + r.stdout)

    def test_no_match_refused_and_nothing_written(self):
        before = open(os.path.join(self.root, "access.yaml")).read()
        r = self.run_tool("--name", "Kunde AS", "--glob", "Nope.*", "--repos", "repos.txt")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(open(os.path.join(self.root, "access.yaml")).read(), before)

if __name__ == "__main__":
    unittest.main(verbosity=1)
