#!/usr/bin/env python3
"""Unit tests for tools/common.py. Run: python3 tools/test_common.py"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import expand_repos

REPOS = ["Grieg.Web", "Grieg.Spa.Trading", "grieg-legacy", "Dult.Api", "OXX.MCP", "github-access"]

class ExpandRepos(unittest.TestCase):
    def test_star_is_everything(self):
        self.assertEqual(expand_repos(["*"], REPOS), set(REPOS))

    def test_exact_names_including_unknown(self):
        self.assertEqual(expand_repos(["Dult.Api", "Nope"], REPOS), {"Dult.Api", "Nope"})

    def test_glob_case_insensitive(self):
        self.assertEqual(expand_repos(["grieg.*"], REPOS), {"Grieg.Web", "Grieg.Spa.Trading"})

    def test_glob_without_hit_is_empty(self):
        self.assertEqual(expand_repos(["Nope.*"], REPOS), set())

    def test_mix(self):
        self.assertEqual(expand_repos(["Grieg.*", "grieg-*", "OXX.MCP"], REPOS), {"Grieg.Web", "Grieg.Spa.Trading", "grieg-legacy", "OXX.MCP"})

    def test_empty(self):
        self.assertEqual(expand_repos(None, REPOS), set())

if __name__ == "__main__":
    unittest.main(verbosity=1)
