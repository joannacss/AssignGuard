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

spec = importlib.util.spec_from_file_location("assignguard_main", SCRIPTS_DIR / "main.py")
main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main)


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

        report = main.build_conflict_report(assignments, pc_info, preferences)

        self.assertEqual(report["summary"]["paper_count"], 1)
        self.assertEqual(report["summary"]["conflict_group_count"], 1)
        self.assertEqual(report["summary"]["conflicted_reviewer_count"], 1)
        conflict = report["papers_with_conflicts"][0]["conflicts"][0]
        self.assertEqual(conflict["affiliation"], "Shared University")
        self.assertEqual(conflict["keep_reviewer"]["email"], "winner@example.test")
        self.assertEqual(conflict["conflict_reviewers"][0]["email"], "loser@example.test")
        self.assertEqual(conflict["conflict_reviewers"][0]["assignment_role"], "secondaryreview")

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

        report = main.build_conflict_report(assignments, pc_info, preferences)

        self.assertEqual(report["papers_with_conflicts"], [])
        self.assertEqual(report["summary"]["missing_pc_info_emails"], ["missing@example.test"])


class FixtureAndCliTests(unittest.TestCase):
    def test_sample_fixtures_produce_two_conflicts(self):
        preferences = main.load_preferences(REPO_ROOT / "data" / "icse2027-allprefs.csv")
        pc_info = main.load_pc_info(REPO_ROOT / "data" / "icse2027-pcinfo.csv")
        assignments = main.load_assignments(REPO_ROOT / "data" / "icse2027-pcassignments.csv")

        report = main.build_conflict_report(assignments, pc_info, preferences)

        self.assertEqual(report["summary"]["paper_count"], 2)
        self.assertEqual(report["summary"]["conflict_group_count"], 2)
        self.assertEqual(report["summary"]["conflicted_reviewer_count"], 2)

        papers = {paper["paper"]: paper for paper in report["papers_with_conflicts"]}
        self.assertEqual(papers["101"]["conflicts"][0]["keep_reviewer"]["email"], "alex.carter@example.test")
        self.assertEqual(
            papers["101"]["conflicts"][0]["conflict_reviewers"][0]["email"],
            "morgan.lee@example.test",
        )
        self.assertEqual(papers["102"]["conflicts"][0]["keep_reviewer"]["email"], "quinn.hughes@example.test")
        self.assertEqual(
            papers["102"]["conflicts"][0]["conflict_reviewers"][0]["email"],
            "riley.chen@example.test",
        )

    def test_main_writes_json_report_to_requested_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "conflicts.json"
            stdout = io.StringIO()

            with mock.patch.object(
                sys,
                "argv",
                [
                    "main.py",
                    "--preferences",
                    str(REPO_ROOT / "data" / "icse2027-allprefs.csv"),
                    "--assignments",
                    str(REPO_ROOT / "data" / "icse2027-pcassignments.csv"),
                    "--pc-info",
                    str(REPO_ROOT / "data" / "icse2027-pcinfo.csv"),
                    "--output",
                    str(output_path),
                ],
            ):
                with contextlib.redirect_stdout(stdout):
                    main.main()

            self.assertTrue(output_path.exists())
            report = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(report["summary"]["paper_count"], 2)
            self.assertIn("Wrote", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
