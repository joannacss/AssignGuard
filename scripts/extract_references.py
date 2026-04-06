#!/usr/bin/env python3

import argparse
import re
from pathlib import Path
from typing import Optional

from pypdf import PdfReader, PdfWriter

from utils import BASE_DIR

OUTPUT_DIR = BASE_DIR / "out"
REFERENCE_HEADING_RE = re.compile(
    r"^(references|bibliography|works cited|literature cited)$",
    re.IGNORECASE,
)
STOP_HEADING_PREFIX_RE = re.compile(
    r"^(appendix|appendices)\b",
    re.IGNORECASE,
)
STOP_HEADING_EXACT_RE = re.compile(
    r"^(supplementary material|supplemental material|"
    r"author biography|author biographies|about the authors|biographies)$",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed CLI arguments containing the input source.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Extract pages containing the references section from one PDF or from all PDFs "
            "found recursively under a folder."
        )
    )
    parser.add_argument(
        "source",
        help="Path to a PDF file or a folder to scan recursively for PDFs.",
    )
    return parser.parse_args()


def iter_pdf_files(folder: Path) -> list[Path]:
    """Recursively collect PDF files from a directory.

    Args:
        folder: Directory to scan for PDF files.

    Returns:
        list[Path]: Sorted paths for all PDF files found below the directory.
    """
    return sorted(path for path in folder.rglob("*.pdf") if path.is_file())


def resolve_inputs(source: str) -> list[Path]:
    """Resolve the user input into one or more local PDF paths.

    Args:
        source: Input string representing a PDF path or folder path.

    Returns:
        list[Path]: Local PDF paths to process.

    Raises:
        FileNotFoundError: If the input path does not exist or a folder contains no PDFs.
        ValueError: If the input is neither a PDF nor a folder.
    """
    path = Path(source).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Input does not exist: {source}")

    if path.is_dir():
        pdfs = iter_pdf_files(path)
        if not pdfs:
            raise FileNotFoundError(f"No PDF files found under {path}")
        return pdfs

    if path.is_file() and path.suffix.lower() == ".pdf":
        return [path]

    raise ValueError(f"Unsupported input: {source}")


def normalize_line(line: str) -> str:
    """Normalize whitespace in an extracted text line.

    Args:
        line: Raw line extracted from a PDF page.

    Returns:
        str: The same line with repeated whitespace collapsed.
    """
    return " ".join(line.split())


def page_lines(page_text: str) -> list[str]:
    """Split page text into normalized, non-empty lines.

    Args:
        page_text: Raw extracted text for a single PDF page.

    Returns:
        list[str]: Non-empty normalized lines from the page.
    """
    return [normalize_line(line) for line in page_text.splitlines() if normalize_line(line)]


def page_reference_score(page_text: str) -> int:
    """Score how reference-like a page appears.

    Args:
        page_text: Raw extracted text for a single PDF page.

    Returns:
        int: Heuristic score based on common bibliography patterns.
    """
    lines = page_lines(page_text)
    if not lines:
        return 0

    score = 0
    for line in lines:
        if re.match(r"^\[\d+\]", line):
            score += 2
        elif re.match(r"^\d+\.", line):
            score += 1
        elif re.search(r"\b(19|20)\d{2}\b", line):
            score += 1
        elif re.search(r"\bet al\.\b", line, re.IGNORECASE):
            score += 1
        elif "doi" in line.lower():
            score += 1
    return score


def find_reference_start(page_texts: list[str]) -> Optional[int]:
    """Locate the first page that starts a references section.

    Args:
        page_texts: Extracted text for each page in a PDF.

    Returns:
        Optional[int]: Zero-based page index of the references heading, or None if absent.
    """
    for page_index, page_text in enumerate(page_texts):
        lines = page_lines(page_text)
        for line in lines[:12]:
            if REFERENCE_HEADING_RE.fullmatch(line):
                return page_index
    return None


def should_stop_after_references(page_text: str) -> bool:
    """Detect whether a page likely starts a section after references.

    Args:
        page_text: Raw extracted text for a single PDF page.

    Returns:
        bool: True when the page begins with a strong stop heading such as `Appendix`.
    """
    lines = page_lines(page_text)
    if not lines:
        return False

    top_lines = lines[:10]
    if any(
        STOP_HEADING_PREFIX_RE.match(line) or STOP_HEADING_EXACT_RE.fullmatch(line)
        for line in top_lines
    ):
        return True

    return False


def find_reference_page_range(page_texts: list[str]) -> Optional[tuple[int, int]]:
    """Find the inclusive range of pages containing references.

    Args:
        page_texts: Extracted text for each page in a PDF.

    Returns:
        Optional[tuple[int, int]]: Inclusive zero-based start and end page indexes,
        or None when no references section is found.
    """
    start = find_reference_start(page_texts)
    if start is None:
        return None

    end = len(page_texts) - 1
    for page_index in range(start + 1, len(page_texts)):
        if should_stop_after_references(page_texts[page_index]):
            previous_page = page_index - 1
            if previous_page >= start:
                return start, previous_page
            return None

    return start, end


def extract_reference_pages(
    pdf_path: Path, output_dir: Path
) -> Optional[tuple[Path, int, int]]:
    """Extract detected references pages from a PDF into a new PDF file.

    Args:
        pdf_path: Path to the source PDF.
        output_dir: Directory where the extracted references PDF should be written.

    Returns:
        Optional[tuple[Path, int, int]]: Output PDF path plus one-based start and end
        page numbers for the extracted reference section, or None if no references
        section is detected.
    """
    reader = PdfReader(str(pdf_path))
    page_texts = [page.extract_text() or "" for page in reader.pages]
    page_range = find_reference_page_range(page_texts)

    if page_range is None:
        return None

    start, end = page_range
    writer = PdfWriter()
    for page_index in range(start, end + 1):
        writer.add_page(reader.pages[page_index])

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{pdf_path.stem}_references.pdf"
    with output_path.open("wb") as handle:
        writer.write(handle)

    return output_path, start + 1, end + 1


def main() -> None:
    """Run the command-line extraction workflow.

    This resolves the input source, extracts reference pages from each PDF, and
    writes the resulting PDFs into the repository `out/` directory.
    """
    args = parse_args()
    pdf_paths = resolve_inputs(args.source)
    extracted_count = 0

    for pdf_path in pdf_paths:
        result = extract_reference_pages(pdf_path, OUTPUT_DIR)
        if result is None:
            print(f"Skipped {pdf_path}: could not find a references section")
            continue

        output_path, start_page, end_page = result
        extracted_count += 1
        print(
            f"Wrote {output_path} from {pdf_path} "
            f"(pages {start_page}-{end_page})"
        )

    print(f"Processed {len(pdf_paths)} PDF(s); extracted references from {extracted_count}.")


if __name__ == "__main__":
    main()
