import contextlib
import importlib.util
import io
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
    "extract_references", SCRIPTS_DIR / "extract_references.py"
)
extract_references = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract_references)


class ReferenceDetectionTests(unittest.TestCase):
    def test_finds_reference_pages_until_appendix(self):
        page_texts = [
            "Introduction\nThis is the paper body.",
            "References\n[1] First citation\n[2] Second citation",
            "[3] Third citation\nDoe et al. 2022",
            "Appendix\nExtra material starts here.",
        ]

        page_range = extract_references.find_reference_page_range(page_texts)

        self.assertEqual(page_range, (1, 2))

    def test_stops_on_titled_appendix_heading(self):
        page_texts = [
            "Conclusion\nFinal remarks",
            "References\n[1] First citation",
            "[2] Second citation",
            "Appendix A Data Sources\nTable A1",
        ]

        page_range = extract_references.find_reference_page_range(page_texts)

        self.assertEqual(page_range, (1, 2))

    def test_returns_none_when_no_reference_heading_exists(self):
        page_texts = [
            "Introduction\nBody text",
            "Related Work\nStill body text",
        ]

        page_range = extract_references.find_reference_page_range(page_texts)

        self.assertIsNone(page_range)


class InputResolutionTests(unittest.TestCase):
    def test_resolve_inputs_recursively_finds_pdfs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            nested = root / "nested"
            nested.mkdir()
            first = root / "first.pdf"
            second = nested / "second.pdf"
            first.write_bytes(b"%PDF-1.4\n")
            second.write_bytes(b"%PDF-1.4\n")
            (nested / "notes.txt").write_text("ignore me", encoding="utf-8")

            resolved = extract_references.resolve_inputs(str(root))

            self.assertEqual(resolved, [first.resolve(), second.resolve()])


class ExtractionTests(unittest.TestCase):
    def test_extract_reference_pages_writes_selected_pages(self):
        reader = mock.Mock()
        reader.pages = [
            mock.Mock(extract_text=mock.Mock(return_value="Intro")),
            mock.Mock(extract_text=mock.Mock(return_value="References\n[1] First")),
            mock.Mock(extract_text=mock.Mock(return_value="[2] Second")),
        ]

        writer_instance = mock.Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "paper.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n")
            output_dir = Path(tmpdir) / "out"

            with mock.patch.object(extract_references, "PdfReader", return_value=reader):
                with mock.patch.object(
                    extract_references, "PdfWriter", return_value=writer_instance
                ):
                    result = extract_references.extract_reference_pages(pdf_path, output_dir)

            self.assertEqual(result[0], output_dir / "paper_references.pdf")
            self.assertEqual(result[1:], (2, 3))
            self.assertEqual(writer_instance.add_page.call_count, 2)
            writer_instance.write.assert_called_once()


class CliTests(unittest.TestCase):
    def test_main_reports_when_references_are_extracted(self):
        stdout = io.StringIO()
        fake_output = REPO_ROOT / "out" / "paper_references.pdf"

        with mock.patch.object(
            sys,
            "argv",
            ["extract_references.py", "/tmp/paper.pdf"],
        ):
            with mock.patch.object(
                extract_references,
                "resolve_inputs",
                return_value=[Path("/tmp/paper.pdf")],
            ):
                with mock.patch.object(
                    extract_references,
                    "extract_reference_pages",
                    return_value=(fake_output, 4, 6),
                ):
                    with contextlib.redirect_stdout(stdout):
                        extract_references.main()

        output = stdout.getvalue()
        self.assertIn("Wrote", output)
        self.assertIn("Processed 1 PDF(s); extracted references from 1.", output)


if __name__ == "__main__":
    unittest.main()
