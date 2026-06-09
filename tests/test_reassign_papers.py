"""
This test module verifies replacement reviewer recommendations.
It covers TPMS ranking, workload limits, unassigned replacements, and the CLI output.
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
    "reassign_papers", SCRIPTS_DIR / "reassign_papers.py"
)
reassign_papers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reassign_papers)


class ReassignmentRecommendationTests(unittest.TestCase):
    def test_recommends_highest_tpms_reviewer_not_already_assigned(self):
        conflict_report = {
            "papers_with_conflicts": [
                {
                    "paper": "200",
                    "title": "Dummy Paper",
                    "conflicts": [
                        {
                            "affiliation": "Shared University",
                            "keep_reviewer": {"email": "kept@example.test"},
                            "conflict_reviewers": [
                                {
                                    "name": "Old Reviewer",
                                    "email": "old@example.test",
                                    "affiliation": "Shared University",
                                    "assignment_role": "primaryreview",
                                    "round": "Main",
                                    "preference": 4.0,
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        preferences = {
            ("200", "kept@example.test"): 15.0,
            ("200", "old@example.test"): 4.0,
            ("200", "best@example.test"): 20.0,
            ("200", "second@example.test"): 17.0,
        }
        assignments = {
            "200": {
                "title": "Dummy Paper",
                "reviewers": [
                    {"email": "kept@example.test", "action": "primaryreview"},
                    {"email": "old@example.test", "action": "primaryreview"},
                ],
            }
        }
        pc_info = {
            "best@example.test": {
                "given_name": "Best",
                "family_name": "Match",
                "email": "best@example.test",
                "affiliation": "Independent Lab",
                "tags": "RegRev",
            }
        }

        report = reassign_papers.build_reassignment_report(
            conflict_report,
            preferences,
            assignments,
            pc_info,
            max_workload=14,
        )

        recommendation = report["reassignments"][0]["recommendations"][0]
        self.assertEqual(recommendation["new_reviewer"]["email"], "best@example.test")
        self.assertEqual(recommendation["new_reviewer"]["tpms_score"], 20.0)
        self.assertEqual(recommendation["replace_reviewer"]["current_workload"], 1)
        self.assertEqual(report["summary"]["replacement_count"], 1)

    def test_skips_reviewers_at_max_workload(self):
        conflict_report = {
            "papers_with_conflicts": [
                {
                    "paper": "201",
                    "title": "Workload Paper",
                    "conflicts": [
                        {
                            "affiliation": "Shared University",
                            "keep_reviewer": {"email": "kept@example.test"},
                            "conflict_reviewers": [
                                {
                                    "name": "Old Reviewer",
                                    "email": "old@example.test",
                                    "affiliation": "Shared University",
                                    "assignment_role": "primaryreview",
                                    "round": "Main_AR",
                                    "preference": 4.0,
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        preferences = {
            ("201", "busy@example.test"): 30.0,
            ("201", "available@example.test"): 12.0,
        }
        pc_info = {
            "busy@example.test": {
                "given_name": "Busy",
                "family_name": "Reviewer",
                "email": "busy@example.test",
                "affiliation": "Busy Lab",
                "tags": "RegRev",
            },
            "available@example.test": {
                "given_name": "Available",
                "family_name": "Reviewer",
                "email": "available@example.test",
                "affiliation": "Available Lab",
                "tags": "RegRev",
            },
        }
        assignments = {
            "201": {
                "title": "Workload Paper",
                "reviewers": [{"email": "old@example.test", "action": "review"}],
            },
            "300": {"title": "", "reviewers": [{"email": "busy@example.test", "action": "review"}]},
            "301": {"title": "", "reviewers": [{"email": "busy@example.test", "action": "review"}]},
        }

        report = reassign_papers.build_reassignment_report(
            conflict_report,
            preferences,
            assignments,
            pc_info,
            max_workload=2,
        )

        recommendation = report["reassignments"][0]["recommendations"][0]
        self.assertEqual(recommendation["new_reviewer"]["email"], "available@example.test")
        self.assertEqual(recommendation["new_reviewer"]["current_workload"], 0)

    def test_reports_unassigned_when_no_candidate_is_available(self):
        conflict_report = {
            "papers_with_conflicts": [
                {
                    "paper": "202",
                    "title": "No Candidate Paper",
                    "conflicts": [
                        {
                            "affiliation": "Shared University",
                            "keep_reviewer": {"email": "kept@example.test"},
                            "conflict_reviewers": [
                                {
                                    "name": "Old Reviewer",
                                    "email": "old@example.test",
                                    "affiliation": "Shared University",
                                    "assignment_role": "primaryreview",
                                    "round": "Main",
                                    "preference": 4.0,
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        preferences = {("202", "old@example.test"): 4.0}
        assignments = {
            "202": {
                "title": "No Candidate Paper",
                "reviewers": [{"email": "old@example.test", "action": "review"}],
            }
        }

        report = reassign_papers.build_reassignment_report(
            conflict_report,
            preferences,
            assignments,
            {},
            max_workload=14,
        )

        self.assertEqual(report["reassignments"], [])
        self.assertEqual(report["summary"]["unassigned_count"], 1)
        self.assertEqual(report["unassigned"][0]["paper"], "202")
        self.assertEqual(report["unassigned"][0]["replace_reviewer"]["current_workload"], 1)

    def test_requires_regrev_tag_for_regular_reviewer_replacement(self):
        conflict_report = {
            "papers_with_conflicts": [
                {
                    "paper": "203",
                    "title": "Tag Paper",
                    "conflicts": [
                        {
                            "affiliation": "Shared University",
                            "keep_reviewer": {"email": "kept@example.test", "round": "Main"},
                            "conflict_reviewers": [
                                {
                                    "name": "Old Reviewer",
                                    "email": "old@example.test",
                                    "affiliation": "Shared University",
                                    "assignment_role": "primaryreview",
                                    "round": "Main",
                                    "preference": 4.0,
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        preferences = {
            ("203", "untagged@example.test"): 30.0,
            ("203", "regrev@example.test"): 20.0,
        }
        assignments = {
            "203": {
                "title": "Tag Paper",
                "reviewers": [{"email": "old@example.test", "action": "review"}],
            }
        }
        pc_info = {
            "untagged@example.test": {
                "given_name": "No",
                "family_name": "Tag",
                "email": "untagged@example.test",
                "affiliation": "Untagged Lab",
                "tags": "MetaRev",
            },
            "regrev@example.test": {
                "given_name": "Regular",
                "family_name": "Reviewer",
                "email": "regrev@example.test",
                "affiliation": "Tagged Lab",
                "tags": "RegRev",
            },
        }

        report = reassign_papers.build_reassignment_report(
            conflict_report,
            preferences,
            assignments,
            pc_info,
            max_workload=14,
        )

        recommendation = report["reassignments"][0]["recommendations"][0]
        self.assertEqual(recommendation["new_reviewer"]["email"], "regrev@example.test")

    def test_skips_regular_meta_conflict_groups(self):
        conflict_report = {
            "papers_with_conflicts": [
                {
                    "paper": "204",
                    "title": "Mixed Round Paper",
                    "conflicts": [
                        {
                            "affiliation": "Shared University",
                            "keep_reviewer": {"email": "meta@example.test", "round": "Main_MR"},
                            "conflict_reviewers": [
                                {
                                    "name": "Old Reviewer",
                                    "email": "old@example.test",
                                    "affiliation": "Shared University",
                                    "assignment_role": "primaryreview",
                                    "round": "Main",
                                    "preference": 4.0,
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        preferences = {("204", "regrev@example.test"): 20.0}
        assignments = {
            "204": {
                "title": "Mixed Round Paper",
                "reviewers": [
                    {"email": "meta@example.test", "action": "review"},
                    {"email": "old@example.test", "action": "review"},
                ],
            }
        }
        pc_info = {
            "regrev@example.test": {
                "given_name": "Regular",
                "family_name": "Reviewer",
                "email": "regrev@example.test",
                "affiliation": "Tagged Lab",
                "tags": "RegRev",
            }
        }

        report = reassign_papers.build_reassignment_report(
            conflict_report,
            preferences,
            assignments,
            pc_info,
            max_workload=14,
        )

        self.assertEqual(report["reassignments"], [])
        self.assertEqual(report["summary"]["skipped_count"], 1)
        self.assertEqual(report["summary"]["replacement_count"], 0)


class ReassignmentCliTests(unittest.TestCase):
    def test_cli_writes_reassignment_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "reassignments.json"
            stdout = io.StringIO()

            with mock.patch.object(
                sys,
                "argv",
                [
                    "reassign_papers.py",
                    "--conflicts",
                    str(REPO_ROOT / "results" / "example1-affiliation-conflicts.json"),
                    "--preferences",
                    str(REPO_ROOT / "data" / "example1" / "icse2027-allprefs.csv"),
                    "--assignments",
                    str(REPO_ROOT / "data" / "example1" / "icse2027-pcassignments.csv"),
                    "--pc-info",
                    str(REPO_ROOT / "data" / "example1" / "icse2027-pcinfo.csv"),
                    "--max-workload",
                    "14",
                    "--output",
                    str(output_path),
                ],
            ):
                with contextlib.redirect_stdout(stdout):
                    reassign_papers.main()

            self.assertTrue(output_path.exists())
            report = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(report["summary"]["replacement_count"], 1)
            self.assertEqual(report["summary"]["unassigned_count"], 1)
            self.assertIn("Wrote", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
