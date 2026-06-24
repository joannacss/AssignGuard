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
                            "keep_reviewer": {"email": "kept@example.test", "preference": 15.0},
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
                            "keep_reviewer": {"email": "kept@example.test", "preference": 15.0},
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
                            "keep_reviewer": {"email": "kept@example.test", "preference": 15.0},
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
                            "keep_reviewer": {
                                "email": "kept@example.test",
                                "round": "Main",
                                "preference": 15.0,
                            },
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

    def test_replaces_regular_reviewer_in_regular_meta_conflict_group(self):
        conflict_report = {
            "papers_with_conflicts": [
                {
                    "paper": "204",
                    "title": "Mixed Round Paper",
                    "conflicts": [
                        {
                            "affiliation": "Shared University",
                            "keep_reviewer": {
                                "email": "meta@example.test",
                                "round": "Main_MR",
                                "preference": 15.0,
                            },
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

        recommendation = report["reassignments"][0]["recommendations"][0]
        self.assertEqual(recommendation["replace_reviewer"]["email"], "old@example.test")
        self.assertEqual(recommendation["new_reviewer"]["email"], "regrev@example.test")
        self.assertEqual(report["summary"]["skipped_count"], 0)
        self.assertEqual(report["summary"]["replacement_count"], 1)

    def test_replaces_meta_reviewer_with_area_chair(self):
        conflict_report = {
            "papers_with_conflicts": [
                {
                    "paper": "205",
                    "title": "Meta Round Paper",
                    "conflicts": [
                        {
                            "affiliation": "Shared University",
                            "keep_reviewer": {
                                "email": "regular@example.test",
                                "round": "Main",
                                "preference": 30.0,
                            },
                            "conflict_reviewers": [
                                {
                                    "name": "Old Meta",
                                    "email": "old-meta@example.test",
                                    "affiliation": "Shared University",
                                    "assignment_role": "primaryreview",
                                    "round": "Main_MR",
                                    "preference": 10.0,
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        preferences = {
            ("205", "regular-candidate@example.test"): 100.0,
            ("205", "area-chair@example.test"): 80.0,
        }
        assignments = {
            "205": {
                "title": "Meta Round Paper",
                "reviewers": [
                    {"email": "regular@example.test", "action": "review", "round": "Main"},
                    {"email": "old-meta@example.test", "action": "review", "round": "Main_MR"},
                ],
            },
            "300": {
                "title": "Regular Workload Paper",
                "reviewers": [{"email": "area-chair@example.test", "action": "review", "round": "Main"}],
            },
        }
        pc_info = {
            "regular-candidate@example.test": {
                "given_name": "Regular",
                "family_name": "Candidate",
                "email": "regular-candidate@example.test",
                "affiliation": "Regular Lab",
                "roles": "pc",
                "tags": "RegRev",
            },
            "area-chair@example.test": {
                "given_name": "Area",
                "family_name": "Chair",
                "email": "area-chair@example.test",
                "affiliation": "Chair Lab",
                "roles": "pc",
                "tags": "AreaChair",
            },
        }

        report = reassign_papers.build_reassignment_report(
            conflict_report,
            preferences,
            assignments,
            pc_info,
            max_workload=1,
        )

        recommendation = report["reassignments"][0]["recommendations"][0]
        self.assertEqual(recommendation["replace_reviewer"]["email"], "old-meta@example.test")
        self.assertEqual(recommendation["new_reviewer"]["email"], "area-chair@example.test")
        self.assertEqual(recommendation["new_reviewer"]["current_workload"], 0)

    def test_uses_tpms_before_meta_workload(self):
        conflict_report = {
            "papers_with_conflicts": [
                {
                    "paper": "207",
                    "title": "Balanced Meta Paper",
                    "conflicts": [
                        {
                            "affiliation": "Shared University",
                            "keep_reviewer": {
                                "email": "regular@example.test",
                                "round": "Main",
                                "preference": 30.0,
                            },
                            "conflict_reviewers": [
                                {
                                    "name": "Old Meta",
                                    "email": "old-meta@example.test",
                                    "affiliation": "Shared University",
                                    "assignment_role": "primaryreview",
                                    "round": "Main_MR",
                                    "preference": 10.0,
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        preferences = {
            ("207", "busy-chair@example.test"): 100.0,
            ("207", "available-chair@example.test"): 80.0,
        }
        assignments = {
            "207": {
                "title": "Balanced Meta Paper",
                "reviewers": [
                    {"email": "regular@example.test", "action": "review", "round": "Main"},
                    {"email": "old-meta@example.test", "action": "review", "round": "Main_MR"},
                ],
            },
            "301": {
                "title": "Existing Meta Paper One",
                "reviewers": [{"email": "busy-chair@example.test", "action": "review", "round": "Main_MR"}],
            },
            "302": {
                "title": "Existing Meta Paper Two",
                "reviewers": [{"email": "busy-chair@example.test", "action": "review", "round": "Main_MR"}],
            },
        }
        pc_info = {
            "busy-chair@example.test": {
                "given_name": "Busy",
                "family_name": "Chair",
                "email": "busy-chair@example.test",
                "affiliation": "Busy Chair Lab",
                "roles": "pc",
                "tags": "AreaChair",
            },
            "available-chair@example.test": {
                "given_name": "Available",
                "family_name": "Chair",
                "email": "available-chair@example.test",
                "affiliation": "Available Chair Lab",
                "roles": "pc",
                "tags": "AreaChair",
            },
        }

        report = reassign_papers.build_reassignment_report(
            conflict_report,
            preferences,
            assignments,
            pc_info,
            max_workload=1,
        )

        recommendation = report["reassignments"][0]["recommendations"][0]
        self.assertEqual(recommendation["new_reviewer"]["email"], "busy-chair@example.test")
        self.assertEqual(recommendation["new_reviewer"]["current_workload"], 2)

    def test_reranks_conflict_group_by_preference_before_replacing(self):
        conflict_report = {
            "papers_with_conflicts": [
                {
                    "paper": "206",
                    "title": "Rerank Paper",
                    "conflicts": [
                        {
                            "affiliation": "Shared University",
                            "keep_reviewer": {
                                "name": "Lower Preference",
                                "email": "lower@example.test",
                                "affiliation": "Shared University",
                                "assignment_role": "primaryreview",
                                "round": "Main",
                                "preference": 4.0,
                            },
                            "conflict_reviewers": [
                                {
                                    "name": "Higher Preference",
                                    "email": "higher@example.test",
                                    "affiliation": "Shared University",
                                    "assignment_role": "primaryreview",
                                    "round": "Main",
                                    "preference": 20.0,
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        preferences = {("206", "candidate@example.test"): 30.0}
        assignments = {
            "206": {
                "title": "Rerank Paper",
                "reviewers": [
                    {"email": "lower@example.test", "action": "review"},
                    {"email": "higher@example.test", "action": "review"},
                ],
            }
        }
        pc_info = {
            "candidate@example.test": {
                "given_name": "Replacement",
                "family_name": "Reviewer",
                "email": "candidate@example.test",
                "affiliation": "Replacement Lab",
                "roles": "pc",
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
        self.assertEqual(recommendation["replace_reviewer"]["email"], "lower@example.test")
        self.assertEqual(recommendation["new_reviewer"]["email"], "candidate@example.test")


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
