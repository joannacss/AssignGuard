#!/usr/bin/env python3
"""
This script re-assign a new reviewer to a list of papers detected by `find_assignments_coi.py`.
The input is the JSON file output from our COI detection script, and the  output should is the best-matching (i.e., highest TPMS matching score) reviewers based on the TPMS score.
The script also skips those reviewers whose workload has reached the maximum review workload (specified as program argument).
@Author: Joanna C. S. Santos
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from find_assignments_coi import load_assignments, load_pc_info, load_preferences
from utils import EXAMPLE1_DATA_DIR, RESULTS_DIR


def parse_args():
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


def load_conflict_report(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def display_name(profile, email):
    if profile is None:
        return email
    return " ".join(
        part for part in [profile["given_name"], profile["family_name"]] if part
    ) or email


def serialize_candidate(email, score, workload, pc_info):
    profile = pc_info.get(email)
    return {
        "name": display_name(profile, email),
        "email": email,
        "affiliation": profile["affiliation"] if profile is not None else "",
        "tpms_score": score,
        "current_workload": workload,
    }


def serialize_replaced_reviewer(reviewer, workloads):
    email = reviewer["email"]
    enriched = dict(reviewer)
    enriched["current_workload"] = workloads[email]
    return enriched


def current_workloads(assignments):
    counts = Counter()
    for paper_data in assignments.values():
        for reviewer in paper_data["reviewers"]:
            counts[reviewer["email"]] += 1
    return counts


def assigned_reviewers_for_paper(assignments, paper):
    return {
        reviewer["email"]
        for reviewer in assignments.get(paper, {}).get("reviewers", [])
    }


def conflict_reviewers_for_paper(paper_report):
    reviewers = []
    for conflict in paper_report["conflicts"]:
        reviewers.extend(conflict["conflict_reviewers"])
    return reviewers


def candidate_sort_key(candidate):
    return (-candidate["tpms_score"], candidate["current_workload"], candidate["email"])


def replacement_sort_key(paper_report):
    paper = str(paper_report["paper"])
    if paper.isdigit():
        return (0, int(paper))
    return (1, paper)


def find_replacement(paper, unavailable, preferences, pc_info, workloads, max_workload):
    candidates = []
    for (preference_paper, email), score in preferences.items():
        if preference_paper != paper:
            continue
        if email in unavailable:
            continue
        workload = workloads[email]
        if workload >= max_workload:
            continue
        candidates.append(serialize_candidate(email, score, workload, pc_info))

    if not candidates:
        return None
    return sorted(candidates, key=candidate_sort_key)[0]


def build_reassignment_report(conflict_report, preferences, assignments, pc_info, max_workload):
    workloads = current_workloads(assignments)
    recommendations = []
    unassigned = []

    for paper_report in sorted(conflict_report["papers_with_conflicts"], key=replacement_sort_key):
        paper = str(paper_report["paper"])
        unavailable = assigned_reviewers_for_paper(assignments, paper)
        paper_recommendations = []

        for old_reviewer in conflict_reviewers_for_paper(paper_report):
            replaced_reviewer = serialize_replaced_reviewer(old_reviewer, workloads)
            replacement = find_replacement(
                paper,
                unavailable,
                preferences,
                pc_info,
                workloads,
                max_workload,
            )
            if replacement is None:
                unassigned.append(
                    {
                        "paper": paper,
                        "title": paper_report.get("title", ""),
                        "replace_reviewer": replaced_reviewer,
                        "reason": "No available reviewer with a TPMS score under the workload limit.",
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
        "summary": {
            "paper_count": len(recommendations),
            "replacement_count": sum(len(item["recommendations"]) for item in recommendations),
            "unassigned_count": len(unassigned),
            "max_workload": max_workload,
        },
    }


def main():
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


if __name__ == "__main__":
    main()
