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
    "find_institution_name_issues", SCRIPTS_DIR / "find_institution_name_issues.py"
)
finder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(finder)


class SuspiciousInstitutionDetectionTests(unittest.TestCase):
    def test_detects_acronym_with_matching_long_form(self):
        rows = [
            {
                "row_number": 2,
                "given_name": "Alex",
                "family_name": "Reviewer",
                "email": "alex@example.test",
                "affiliation": "University of Notre Dame",
                "normalized_affiliation": finder.normalize_affiliation("University of Notre Dame"),
            },
            {
                "row_number": 3,
                "given_name": "Blair",
                "family_name": "Reviewer",
                "email": "blair@example.test",
                "affiliation": "ND",
                "normalized_affiliation": finder.normalize_affiliation("ND"),
            },
        ]

        report = finder.build_report(rows)

        self.assertEqual(report["summary"]["acronym_count"], 1)
        finding = report["findings"][0]
        self.assertEqual(finding["issue_type"], "acronym")
        self.assertEqual(finding["affiliation"], "ND")
        self.assertEqual(finding["suggested_affiliation"], "University of Notre Dame")

    def test_detects_single_token_typo_variant(self):
        rows = [
            {
                "row_number": 2,
                "given_name": "Casey",
                "family_name": "Reviewer",
                "email": "casey@example.test",
                "affiliation": "Microsoft",
                "normalized_affiliation": finder.normalize_affiliation("Microsoft"),
            },
            {
                "row_number": 3,
                "given_name": "Drew",
                "family_name": "Reviewer",
                "email": "drew@example.test",
                "affiliation": "Microsft",
                "normalized_affiliation": finder.normalize_affiliation("Microsft"),
            },
        ]

        report = finder.build_report(rows)

        self.assertEqual(report["summary"]["typo_count"], 1)
        finding = report["findings"][0]
        self.assertEqual(finding["issue_type"], "typo")
        self.assertEqual(finding["affiliation"], "Microsft")
        self.assertEqual(finding["suggested_affiliation"], "Microsoft")


class SuspiciousInstitutionCliTests(unittest.TestCase):
    def test_cli_writes_json_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "pcinfo.csv"
            output_path = Path(tmpdir) / "report.json"
            input_path.write_text(
                "\n".join(
                    [
                        "given_name,family_name,email,affiliation,orcid,country,roles,collaborators,follow",
                        "Alex,Reviewer,alex@example.test,University of Notre Dame,,US,pc,,review",
                        "Blair,Reviewer,blair@example.test,ND,,US,pc,,review",
                        "Casey,Reviewer,casey@example.test,Microsoft,,US,pc,,review",
                        "Drew,Reviewer,drew@example.test,Microsft,,US,pc,,review",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()

            with mock.patch.object(
                sys,
                    "argv",
                    [
                    "find_institution_name_issues.py",
                    "--pc-info",
                    str(input_path),
                    "--output",
                    str(output_path),
                ],
            ):
                with contextlib.redirect_stdout(stdout):
                    finder.main()

            report = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(report["summary"]["suspicious_entry_count"], 2)
            self.assertIn("Wrote", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
