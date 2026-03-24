#!/usr/bin/env python3

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from utils import DATA_DIR, RESULTS_DIR

GENERIC_AFFILIATION_WORDS = {
    "academy",
    "campus",
    "center",
    "centre",
    "college",
    "corporation",
    "department",
    "faculty",
    "hospital",
    "institute",
    "laboratories",
    "laboratory",
    "lab",
    "labs",
    "research",
    "school",
    "university",
}
AFFILIATION_STOPWORDS = {
    "a",
    "an",
    "and",
    "at",
    "for",
    "in",
    "of",
    "the",
}

MIN_TYPO_SIMILARITY = 0.88
MAX_TOKEN_EDIT_DISTANCE = 2


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Find issues in reviewer affiliations in the PC info CSV, including acronyms and likely typos."
        )
    )
    parser.add_argument(
        "--pc-info",
        type=Path,
        default=DATA_DIR / "icse2027-pcinfo.csv",
        help="Path to the HotCRP PC info CSV.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=RESULTS_DIR / "institution-name-issues.json",
        help="Path to the generated JSON report.",
    )
    return parser.parse_args()


def normalize_whitespace(value):
    return " ".join(value.strip().split())


def normalize_affiliation(value):
    return normalize_whitespace(value).casefold()


def tokenize_affiliation(value):
    return re.findall(r"[A-Za-z0-9]+", value.casefold())


def affiliation_initialisms(value):
    tokens = tokenize_affiliation(value)
    if not tokens:
        return set()

    variants = set()
    variants.add("".join(token[0] for token in tokens))

    significant = [
        token
        for token in tokens
        if token not in GENERIC_AFFILIATION_WORDS and token not in AFFILIATION_STOPWORDS
    ]
    if significant:
        variants.add("".join(token[0] for token in significant))

    return {variant.upper() for variant in variants if len(variant) >= 2}


def is_acronym_like(value):
    compact = re.sub(r"[\s.\-&/]", "", value.strip())
    if len(compact) < 2 or len(compact) > 10:
        return False
    has_letter = any(character.isalpha() for character in compact)
    return has_letter and compact.upper() == compact


def edit_distance(left, right):
    rows = len(left) + 1
    cols = len(right) + 1
    matrix = [[0] * cols for _ in range(rows)]

    for row in range(rows):
        matrix[row][0] = row
    for col in range(cols):
        matrix[0][col] = col

    for row in range(1, rows):
        for col in range(1, cols):
            substitution_cost = 0 if left[row - 1] == right[col - 1] else 1
            matrix[row][col] = min(
                matrix[row - 1][col] + 1,
                matrix[row][col - 1] + 1,
                matrix[row - 1][col - 1] + substitution_cost,
            )

    return matrix[-1][-1]


def load_pc_rows(path):
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader, start=2):
            affiliation = normalize_whitespace(row.get("affiliation", ""))
            rows.append(
                {
                    "row_number": index,
                    "given_name": normalize_whitespace(row.get("given_name", "")),
                    "family_name": normalize_whitespace(row.get("family_name", "")),
                    "email": normalize_whitespace(row.get("email", "")).lower(),
                    "affiliation": affiliation,
                    "normalized_affiliation": normalize_affiliation(affiliation),
                }
            )
    return rows


def build_affiliation_index(rows):
    grouped_rows = defaultdict(list)
    display_counts = Counter()

    for row in rows:
        normalized = row["normalized_affiliation"]
        if not normalized:
            continue
        grouped_rows[normalized].append(row)
        display_counts[row["affiliation"]] += 1

    canonical_display = {}
    for normalized, members in grouped_rows.items():
        canonical_display[normalized] = max(
            members,
            key=lambda item: (display_counts[item["affiliation"]], len(item["affiliation"]), item["affiliation"]),
        )["affiliation"]

    return grouped_rows, canonical_display


def find_acronym_matches(rows, canonical_display):
    matches = []
    long_forms = {
        normalized: display
        for normalized, display in canonical_display.items()
        if len(tokenize_affiliation(display)) >= 2
    }

    for row in rows:
        affiliation = row["affiliation"]
        if not affiliation or not is_acronym_like(affiliation):
            continue

        compact = re.sub(r"[^A-Za-z0-9]", "", affiliation).upper()
        candidates = []
        for normalized, display in long_forms.items():
            if normalized == row["normalized_affiliation"]:
                continue
            if compact in affiliation_initialisms(display):
                candidates.append(display)

        if candidates:
            candidates.sort(key=lambda value: (-len(value.split()), value))
            matches.append(
                {
                    "row_number": row["row_number"],
                    "reviewer_name": build_reviewer_name(row),
                    "email": row["email"],
                    "affiliation": affiliation,
                    "issue_type": "acronym",
                    "suggested_affiliation": candidates[0],
                    "candidate_matches": candidates,
                }
            )
        else:
            matches.append(
                {
                    "row_number": row["row_number"],
                    "reviewer_name": build_reviewer_name(row),
                    "email": row["email"],
                    "affiliation": affiliation,
                    "issue_type": "acronym",
                    "suggested_affiliation": None,
                    "candidate_matches": [],
                }
            )

    return matches


def looks_like_typo_variant(left, right):
    left_tokens = tokenize_affiliation(left)
    right_tokens = tokenize_affiliation(right)
    if not left_tokens or not right_tokens:
        return False
    if len(left_tokens) != len(right_tokens):
        return False

    differing_pairs = []
    for left_token, right_token in zip(left_tokens, right_tokens):
        if left_token == right_token:
            continue
        differing_pairs.append((left_token, right_token))

    if len(differing_pairs) != 1:
        return False

    left_token, right_token = differing_pairs[0]
    if min(len(left_token), len(right_token)) < 5:
        return False

    similarity = SequenceMatcher(None, left, right).ratio()
    if similarity < MIN_TYPO_SIMILARITY:
        return False

    return edit_distance(left_token, right_token) <= MAX_TOKEN_EDIT_DISTANCE


def choose_typo_canonical(left, right, grouped_rows, canonical_display):
    left_count = len(grouped_rows[left])
    right_count = len(grouped_rows[right])
    left_display = canonical_display[left]
    right_display = canonical_display[right]
    left_score = (left_count, len(left_display), left_display)
    right_score = (right_count, len(right_display), right_display)
    return left if left_score >= right_score else right


def find_typo_matches(rows, grouped_rows, canonical_display):
    findings_by_row = {}
    normalized_affiliations = sorted(grouped_rows)

    for index, left in enumerate(normalized_affiliations):
        for right in normalized_affiliations[index + 1 :]:
            if not looks_like_typo_variant(left, right):
                continue

            canonical = choose_typo_canonical(left, right, grouped_rows, canonical_display)
            variant = right if canonical == left else left
            suggested = canonical_display[canonical]
            variant_display = canonical_display[variant]

            for row in grouped_rows[variant]:
                findings_by_row[row["row_number"]] = {
                    "row_number": row["row_number"],
                    "reviewer_name": build_reviewer_name(row),
                    "email": row["email"],
                    "affiliation": row["affiliation"],
                    "issue_type": "typo",
                    "suggested_affiliation": suggested,
                    "candidate_matches": [variant_display, suggested],
                }

    return sorted(findings_by_row.values(), key=lambda item: item["row_number"])


def build_reviewer_name(row):
    return " ".join(part for part in [row["given_name"], row["family_name"]] if part) or row["email"]


def build_report(rows):
    grouped_rows, canonical_display = build_affiliation_index(rows)
    acronym_findings = find_acronym_matches(rows, canonical_display)
    typo_findings = find_typo_matches(rows, grouped_rows, canonical_display)
    findings = sorted(
        acronym_findings + typo_findings,
        key=lambda item: (item["row_number"], item["issue_type"], item["affiliation"]),
    )

    return {
        "summary": {
            "reviewer_count": len(rows),
            "distinct_affiliation_count": len(grouped_rows),
            "suspicious_entry_count": len(findings),
            "acronym_count": sum(1 for item in findings if item["issue_type"] == "acronym"),
            "typo_count": sum(1 for item in findings if item["issue_type"] == "typo"),
        },
        "findings": findings,
    }


def main():
    args = parse_args()
    rows = load_pc_rows(args.pc_info)
    report = build_report(rows)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")

    summary = report["summary"]
    print(f"Wrote {args.output}")
    print(f"Reviewers scanned: {summary['reviewer_count']}")
    print(f"Distinct affiliations: {summary['distinct_affiliation_count']}")
    print(f"Suspicious entries: {summary['suspicious_entry_count']}")
    print(f"Acronym-like affiliations: {summary['acronym_count']}")
    print(f"Likely typos: {summary['typo_count']}")


if __name__ == "__main__":
    main()
