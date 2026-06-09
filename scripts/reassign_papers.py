#!/usr/bin/env python3
"""
This script recommends replacement reviewers for regular-reviewer conflicts detected by `find_assignments_coi.py`.
It reads the COI JSON report, TPMS preference scores, HotCRP assignments, and PC info, then selects the highest-scoring available replacement for each conflicted `Main` or `Main_AR` reviewer.
Replacement candidates must have the `RegRev` PC tag, must not already be assigned to the paper, and must be below the maximum workload specified by program argument.
Conflict groups that mix regular reviewers with `Main_MR` metareviewers are skipped instead of reassigned.
@Author: Joanna C. S. Santos
"""
import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from find_assignments_coi import load_assignments, load_pc_info, load_preferences
from utils import EXAMPLE1_DATA_DIR, RESULTS_DIR

REGULAR_REVIEW_ROUNDS = {"Main", "Main_AR"}
META_REVIEW_ROUNDS = {"Main_MR"}
REGULAR_REVIEWER_TAG = "RegRev"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Recommend replacement reviewers for papers reported by find_assignments_coi.py, "
            "using the highest available TPMS preference score."
        )
    )
    parser.add_argument(
        "--conflicts",
        type=Path,
        default=RESULTS_DIR / "example1-affiliation-conflicts.json",
        help="Path to the JSON output from find_assignments_coi.py.",
    )
    parser.add_argument(
        "--preferences",
        type=Path,
        default=EXAMPLE1_DATA_DIR / "icse2027-allprefs.csv",
        help="Path to the TPMS preferences CSV.",
    )
    parser.add_argument(
        "--assignments",
        type=Path,
        default=EXAMPLE1_DATA_DIR / "icse2027-pcassignments.csv",
        help="Path to the HotCRP assignments CSV.",
    )
    parser.add_argument(
        "--pc-info",
        type=Path,
        default=EXAMPLE1_DATA_DIR / "icse2027-pcinfo.csv",
        help="Path to the HotCRP PC info CSV.",
    )
    parser.add_argument(
        "--max-workload",
        type=int,
        default=14,
        help="Maximum number of reviews allowed per reviewer.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=RESULTS_DIR / "example1-reassignment-recommendations.json",
        help="Path to the generated reassignment recommendation JSON.",
    )
    return parser.parse_args()


def load_conflict_report(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def display_name(profile: Optional[dict[str, str]], email: str) -> str:
    if profile is None:
        return email
    return " ".join(
        part for part in [profile["given_name"], profile["family_name"]] if part
    ) or email


def reviewer_tags(profile: Optional[dict[str, str]]) -> set[str]:
    if profile is None:
        return set()
    return set(profile.get("tags", "").split())


def reviewer_has_tag(profile: Optional[dict[str, str]], tag: str) -> bool:
    return tag in reviewer_tags(profile)


def serialize_candidate(
    email: str,
    score: float,
    workload: int,
    pc_info: dict[str, dict[str, str]],
) -> dict[str, Any]:
    profile = pc_info.get(email)
    return {
        "name": display_name(profile, email),
        "email": email,
        "affiliation": profile["affiliation"] if profile is not None else "",
        "tpms_score": score,
        "current_workload": workload,
    }


def reviewer_round(reviewer: dict[str, Any]) -> str:
    return str(reviewer.get("round") or "Main")


def is_regular_review_round(round_name: str) -> bool:
    return round_name in REGULAR_REVIEW_ROUNDS


def is_meta_review_round(round_name: str) -> bool:
    return round_name in META_REVIEW_ROUNDS


def serialize_replaced_reviewer(
    reviewer: dict[str, Any],
    workloads: Counter[str],
) -> dict[str, Any]:
    email = reviewer["email"]
    enriched = dict(reviewer)
    enriched["current_workload"] = workloads[email]
    return enriched


def current_workloads(assignments: dict[str, dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for paper_data in assignments.values():
        for reviewer in paper_data["reviewers"]:
            counts[reviewer["email"]] += 1
    return counts


def assigned_reviewers_for_paper(
    assignments: dict[str, dict[str, Any]],
    paper: str,
) -> set[str]:
    return {
        reviewer["email"]
        for reviewer in assignments.get(paper, {}).get("reviewers", [])
    }


def conflict_group_reviewers(conflict: dict[str, Any]) -> list[dict[str, Any]]:
    return [conflict["keep_reviewer"]] + conflict["conflict_reviewers"]


def has_regular_meta_mix(conflict: dict[str, Any]) -> bool:
    rounds = {reviewer_round(reviewer) for reviewer in conflict_group_reviewers(conflict)}
    return any(is_regular_review_round(round_name) for round_name in rounds) and any(
        is_meta_review_round(round_name) for round_name in rounds
    )


def candidate_sort_key(candidate: dict[str, Any]) -> tuple[float, int, str]:
    return (-candidate["tpms_score"], candidate["current_workload"], candidate["email"])


def replacement_sort_key(paper_report: dict[str, Any]) -> tuple[int, Any]:
    paper = str(paper_report["paper"])
    if paper.isdigit():
        return (0, int(paper))
    return (1, paper)


def find_replacement(
    paper: str,
    unavailable: set[str],
    preferences: dict[tuple[str, str], float],
    pc_info: dict[str, dict[str, str]],
    workloads: Counter[str],
    max_workload: int,
    required_tag: Optional[str],
) -> Optional[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for (preference_paper, email), score in preferences.items():
        if preference_paper != paper:
            continue
        if email in unavailable:
            continue
        workload = workloads[email]
        if workload >= max_workload:
            continue
        if required_tag and not reviewer_has_tag(pc_info.get(email), required_tag):
            continue
        candidates.append(serialize_candidate(email, score, workload, pc_info))

    if not candidates:
        return None
    return sorted(candidates, key=candidate_sort_key)[0]


def build_reassignment_report(
    conflict_report: dict[str, Any],
    preferences: dict[tuple[str, str], float],
    assignments: dict[str, dict[str, Any]],
    pc_info: dict[str, dict[str, str]],
    max_workload: int,
) -> dict[str, Any]:
    workloads = current_workloads(assignments)
    recommendations: list[dict[str, Any]] = []
    unassigned: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for paper_report in sorted(conflict_report["papers_with_conflicts"], key=replacement_sort_key):
        paper = str(paper_report["paper"])
        unavailable = assigned_reviewers_for_paper(assignments, paper)
        paper_recommendations: list[dict[str, Any]] = []

        for conflict in paper_report["conflicts"]:
            if has_regular_meta_mix(conflict):
                skipped.append(
                    {
                        "paper": paper,
                        "title": paper_report.get("title", ""),
                        "conflict": conflict,
                        "reason": "Skipped conflict group containing both regular and meta reviewers.",
                    }
                )
                continue

            for old_reviewer in conflict["conflict_reviewers"]:
                old_round = reviewer_round(old_reviewer)
                if not is_regular_review_round(old_round):
                    skipped.append(
                        {
                            "paper": paper,
                            "title": paper_report.get("title", ""),
                            "replace_reviewer": old_reviewer,
                            "reason": "Only Main and Main_AR reviewer replacements are supported.",
                        }
                    )
                    continue

                replaced_reviewer = serialize_replaced_reviewer(old_reviewer, workloads)
                replacement = find_replacement(
                    paper,
                    unavailable,
                    preferences,
                    pc_info,
                    workloads,
                    max_workload,
                    REGULAR_REVIEWER_TAG,
                )
                if replacement is None:
                    unassigned.append(
                        {
                            "paper": paper,
                            "title": paper_report.get("title", ""),
                            "replace_reviewer": replaced_reviewer,
                            "reason": "No available reviewer with a TPMS score, required PC tag, and workload under the limit.",
                        }
                    )
                    continue

                paper_recommendations.append(
                    {
                        "replace_reviewer": replaced_reviewer,
                        "new_reviewer": replacement,
                    }
                )
                unavailable.add(replacement["email"])
                workloads[replacement["email"]] += 1

        if paper_recommendations:
            recommendations.append(
                {
                    "paper": paper,
                    "title": paper_report.get("title", ""),
                    "recommendations": paper_recommendations,
                }
            )

    return {
        "reassignments": recommendations,
        "unassigned": unassigned,
        "skipped": skipped,
        "summary": {
            "paper_count": len(recommendations),
            "replacement_count": sum(len(item["recommendations"]) for item in recommendations),
            "unassigned_count": len(unassigned),
            "skipped_count": len(skipped),
            "max_workload": max_workload,
        },
    }


def main() -> None:
    args = parse_args()
    if args.max_workload < 1:
        raise ValueError("--max-workload must be at least 1")

    conflict_report = load_conflict_report(args.conflicts)
    preferences = load_preferences(args.preferences)
    assignments = load_assignments(args.assignments)
    pc_info = load_pc_info(args.pc_info)

    report = build_reassignment_report(
        conflict_report,
        preferences,
        assignments,
        pc_info,
        args.max_workload,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")

    summary = report["summary"]
    print(f"Wrote {args.output}")
    print(f"Papers with recommendations: {summary['paper_count']}")
    print(f"Replacement recommendations: {summary['replacement_count']}")
    print(f"Unassigned replacements: {summary['unassigned_count']}")
    print(f"Skipped conflict groups/reviewers: {summary['skipped_count']}")


if __name__ == "__main__":
    main()
