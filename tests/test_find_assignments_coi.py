"""
This test module verifies institutional conflict detection for paper assignments.
It covers reviewer grouping, conflict reporting, sample fixtures, and the CLI output.
@Author: Joanna C. S. Santos
"""

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

spec = importlib.util.spec_from_file_location(
    "find_assignments_coi", SCRIPTS_DIR / "find_assignments_coi.py"
)
find_assignments_coi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(find_assignments_coi)


class BuildConflictReportTests(unittest.TestCase):
    def test_keeps_highest_preference_within_same_affiliation(self):
        assignments = {
            "200": {
                "title": "Dummy Paper",
                "reviewers": [
                    {"email": "winner@example.test", "action": "primaryreview"},
                    {"email": "loser@example.test", "action": "secondaryreview"},
                    {"email": "other@example.test", "action": "primaryreview"},
                ],
            }
        }
        pc_info = {
            "winner@example.test": {
                "given_name": "Winner",
                "family_name": "One",
                "email": "winner@example.test",
                "affiliation": "Shared University",
            },
            "loser@example.test": {
                "given_name": "Loser",
                "family_name": "Two",
                "email": "loser@example.test",
                "affiliation": "Shared University",
            },
            "other@example.test": {
                "given_name": "Other",
                "family_name": "Three",
                "email": "other@example.test",
                "affiliation": "Independent Lab",
            },
        }
        preferences = {
            ("200", "winner@example.test"): 14.0,
            ("200", "loser@example.test"): 6.0,
            ("200", "other@example.test"): 20.0,
        }

        report = find_assignments_coi.build_conflict_report(assignments, pc_info, preferences)

        self.assertEqual(report["summary"]["paper_count"], 1)
        self.assertEqual(report["summary"]["conflict_group_count"], 1)
        self.assertEqual(report["summary"]["conflicted_reviewer_count"], 1)
        conflict = report["papers_with_conflicts"][0]["conflicts"][0]
        self.assertEqual(conflict["affiliation"], "Shared University")
        self.assertEqual(conflict["keep_reviewer"]["email"], "winner@example.test")
        self.assertIsNone(conflict["keep_reviewer"]["round"])
        self.assertEqual(conflict["conflict_reviewers"][0]["email"], "loser@example.test")
        self.assertEqual(conflict["conflict_reviewers"][0]["assignment_role"], "secondaryreview")
        self.assertIsNone(conflict["conflict_reviewers"][0]["round"])

    def test_missing_pc_info_is_reported_but_not_grouped_as_conflict(self):
        assignments = {
            "201": {
                "title": "Another Dummy Paper",
                "reviewers": [
                    {"email": "known@example.test", "action": "primaryreview"},
                    {"email": "missing@example.test", "action": "primaryreview"},
                ],
            }
        }
        pc_info = {
            "known@example.test": {
                "given_name": "Known",
                "family_name": "Reviewer",
                "email": "known@example.test",
                "affiliation": "Known Institute",
            }
        }
        preferences = {
            ("201", "known@example.test"): 3.0,
            ("201", "missing@example.test"): 10.0,
        }

        report = find_assignments_coi.build_conflict_report(assignments, pc_info, preferences)

        self.assertEqual(report["papers_with_conflicts"], [])
        self.assertEqual(report["summary"]["missing_pc_info_emails"], ["missing@example.test"])

    def test_load_assignments_preserves_reviewer_round_when_present(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            assignments_path = Path(tmpdir) / "assignments.csv"
            assignments_path.write_text(
                "\n".join(
                    [
                        "paper,action,email,round,title",
                        "301,clearreview,#pc,,Round Trip Paper",
                        "301,primaryreview,reviewer@example.test,Main,",
                        "301,metareview,meta@example.test,Main_MR,",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            assignments = find_assignments_coi.load_assignments(assignments_path)

        self.assertEqual(assignments["301"]["title"], "Round Trip Paper")
        self.assertEqual(assignments["301"]["reviewers"][0]["round"], "Main")
        self.assertEqual(assignments["301"]["reviewers"][1]["round"], "Main_MR")


class FixtureAndCliTests(unittest.TestCase):
    def test_sample_fixtures_produce_two_conflicts(self):
        preferences = find_assignments_coi.load_preferences(
            REPO_ROOT / "data" / "example1" / "icse2027-allprefs.csv"
        )
        pc_info = find_assignments_coi.load_pc_info(REPO_ROOT / "data" / "example1" / "icse2027-pcinfo.csv")
        assignments = find_assignments_coi.load_assignments(
            REPO_ROOT / "data" / "example1" / "icse2027-pcassignments.csv"
        )

        report = find_assignments_coi.build_conflict_report(assignments, pc_info, preferences)

        self.assertEqual(report["summary"]["paper_count"], 2)
        self.assertEqual(report["summary"]["conflict_group_count"], 2)
        self.assertEqual(report["summary"]["conflicted_reviewer_count"], 2)

        papers = {paper["paper"]: paper for paper in report["papers_with_conflicts"]}
        self.assertEqual(papers["101"]["conflicts"][0]["keep_reviewer"]["email"], "alex.carter@northbu.edu")
        self.assertEqual(
            papers["101"]["conflicts"][0]["conflict_reviewers"][0]["email"],
            "morgan.lee@northbu.edu",
        )
        self.assertEqual(papers["102"]["conflicts"][0]["keep_reviewer"]["email"], "quinn.hughes@cedarlabs.org")
        self.assertEqual(
            papers["102"]["conflicts"][0]["conflict_reviewers"][0]["email"],
            "riley.chen@cedarlabs.org",
        )

    def test_cli_writes_json_report_to_requested_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "conflicts.json"
            stdout = io.StringIO()

            with mock.patch.object(
                sys,
                "argv",
                [
                    "find_assignments_coi.py",
                    "--preferences",
                    str(REPO_ROOT / "data" / "example1" / "icse2027-allprefs.csv"),
                    "--assignments",
                    str(REPO_ROOT / "data" / "example1" / "icse2027-pcassignments.csv"),
                    "--pc-info",
                    str(REPO_ROOT / "data" / "example1" / "icse2027-pcinfo.csv"),
                    "--output",
                    str(output_path),
                ],
            ):
                with contextlib.redirect_stdout(stdout):
                    find_assignments_coi.main()

            self.assertTrue(output_path.exists())
            report = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(report["summary"]["paper_count"], 2)
            self.assertIn("Wrote", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
