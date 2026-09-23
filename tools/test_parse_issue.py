#!/usr/bin/env python3
"""Unit tests for tools/parse-issue.py. Run: python3 tools/test_parse_issue.py"""
import importlib.util, os, unittest

spec = importlib.util.spec_from_file_location("parse_issue", os.path.join(os.path.dirname(os.path.abspath(__file__)), "parse-issue.py"))
pi = importlib.util.module_from_spec(spec); spec.loader.exec_module(pi)

def body(action="Add", team="Kunde A (kunde-a)", who="Myself (the requester)", reason="Project X"):
    return f"### Action\n\n{action}\n\n### Team\n\n{team}\n\n### Who\n\n{who}\n\n### Reason\n\n{reason}"

class ParseIssue(unittest.TestCase):
    def test_self_only(self):
        r = pi.parse(body(), "octocat")
        self.assertEqual(r, {"action": "add", "team": "kunde-a", "logins": ["octocat"], "reason": "Project X"})

    def test_multi_with_self(self):
        r = pi.parse(body(who="Myself (the requester), hungqt, pedarn"), "octocat")
        self.assertEqual(r["logins"], ["octocat", "hungqt", "pedarn"])

    def test_others_without_self(self):
        r = pi.parse(body(who="hungqt, pedarn"), "octocat")
        self.assertEqual(r["logins"], ["hungqt", "pedarn"])

    def test_empty_who_means_self(self):
        self.assertEqual(pi.parse(body(who="_No response_"), "octocat")["logins"], ["octocat"])

    def test_dedupe(self):
        r = pi.parse(body(who="Myself (the requester), octocat"), "octocat")
        self.assertEqual(r["logins"], ["octocat"])

    def test_remove(self):
        self.assertEqual(pi.parse(body(action="Remove"), "o")["action"], "remove")

    def test_bad_login(self):
        with self.assertRaises(SystemExit):
            pi.parse(body(who="bad name!"), "o")

    def test_bad_team(self):
        with self.assertRaises(SystemExit):
            pi.parse(body(team="Kunde A (Kunde A)"), "o")

    def test_title(self):
        self.assertEqual(pi.title("add", ["a"], "Kunde A"), "Add a to Kunde A team")
        self.assertEqual(pi.title("add", ["a", "b", "c"], "Kunde A"), "Add a, b, c to Kunde A team")
        self.assertEqual(pi.title("remove", ["a", "b", "c", "d"], "Kunde A"), "Remove 4 users from Kunde A team")

if __name__ == "__main__":
    unittest.main(verbosity=1)
