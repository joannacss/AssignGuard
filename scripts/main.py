#!/usr/bin/env python3

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from utils import DATA_DIR, RESULTS_DIR

REVIEW_ACTIONS = {
    "primaryreview",
    "secondaryreview",
    "optionalreview",
    "review",
    "metareview",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Detect papers with multiple assigned reviewers from the same institution and generate a conflict JSON report."
        )
    )
    parser.add_argument(
        "--preferences",
        type=Path,
        default=DATA_DIR / "icse2027-allprefs.csv",
        help="Path to the preferences CSV.",
    )
    parser.add_argument(
        "--assignments",
        type=Path,
        default=DATA_DIR / "icse2027-pcassignments.csv",
        help="Path to the HotCRP assignments CSV.",
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
        default=RESULTS_DIR / "icse2027-affiliation-conflicts.json",
        help="Path to the generated conflict JSON.",
    )
    return parser.parse_args()


def load_preferences(path):
    preferences = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            paper = row["paper"].strip()
            email = normalize_email(row["email"])
            value = row["preference"].strip()
            preferences[(paper, email)] = float(value) if value else 0.0
    return preferences


def load_pc_info(path):
    pc_info = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            email = normalize_email(row["email"])
            pc_info[email] = {
                "given_name": row["given_name"].strip(),
                "family_name": row["family_name"].strip(),
                "email": email,
                "affiliation": row["affiliation"].strip(),
            }
    return pc_info


def load_assignments(path):
    papers = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            paper = row["paper"].strip()
            papers.setdefault(paper, {"title": "", "reviewers": []})

            action = row["action"].strip().lower()
            if action == "clearreview":
                papers[paper]["title"] = (row.get("title") or "").strip()
                continue

            if action in REVIEW_ACTIONS:
                papers[paper]["reviewers"].append(
                    {
                        "email": normalize_email(row["email"]),
                        "action": action,
                    }
                )
    return papers


def normalize_email(email):
    return email.strip().lower()


def normalize_affiliation(affiliation):
    return " ".join(affiliation.strip().lower().split())


def reviewer_sort_key(reviewer):
    return (-reviewer["preference"], reviewer["assignment_order"], reviewer["email"])


def build_conflict_report(assignments, pc_info, preferences):
    report = []
    missing_pc_info = set()

    for paper, paper_data in sorted(assignments.items(), key=lambda item: int(item[0])):
        reviewers_by_affiliation = defaultdict(list)

        for index, reviewer in enumerate(paper_data["reviewers"]):
            email = reviewer["email"]
            profile = pc_info.get(email)
            if profile is None:
                missing_pc_info.add(email)
                affiliation = ""
                display_name = email
            else:
                affiliation = profile["affiliation"]
                display_name = " ".join(
                    part for part in [profile["given_name"], profile["family_name"]] if part
                ) or email

            normalized_affiliation = normalize_affiliation(affiliation)
            if not normalized_affiliation:
                continue

            enriched = {
                "email": email,
                "name": display_name,
                "affiliation": affiliation,
                "assignment_role": reviewer["action"],
                "preference": preferences.get((paper, email), 0.0),
                "assignment_order": index,
            }
            reviewers_by_affiliation[normalized_affiliation].append(enriched)

        paper_conflicts = []
        for grouped_reviewers in reviewers_by_affiliation.values():
            if len(grouped_reviewers) < 2:
                continue

            ranked = sorted(grouped_reviewers, key=reviewer_sort_key)
            winner = ranked[0]
            conflicts = ranked[1:]
            paper_conflicts.append(
                {
                    "affiliation": winner["affiliation"],
                    "keep_reviewer": serialize_reviewer(winner),
                    "conflict_reviewers": [serialize_reviewer(reviewer) for reviewer in conflicts],
                }
            )

        if paper_conflicts:
            report.append(
                {
                    "paper": paper,
                    "title": paper_data["title"],
                    "conflicts": paper_conflicts,
                }
            )

    return {
        "papers_with_conflicts": report,
        "summary": {
            "paper_count": len(report),
            "conflict_group_count": sum(len(item["conflicts"]) for item in report),
            "conflicted_reviewer_count": sum(
                len(conflict["conflict_reviewers"])
                for item in report
                for conflict in item["conflicts"]
            ),
            "missing_pc_info_emails": sorted(missing_pc_info),
        },
    }


def serialize_reviewer(reviewer):
    return {
        "name": reviewer["name"],
        "email": reviewer["email"],
        "affiliation": reviewer["affiliation"],
        "assignment_role": reviewer["assignment_role"],
        "preference": reviewer["preference"],
    }


def main():
    args = parse_args()

    preferences = load_preferences(args.preferences)
    pc_info = load_pc_info(args.pc_info)
    assignments = load_assignments(args.assignments)
    report = build_conflict_report(assignments, pc_info, preferences)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")

    summary = report["summary"]
    print(f"Wrote {args.output}")
    print(f"Papers with conflicts: {summary['paper_count']}")
    print(f"Conflict groups: {summary['conflict_group_count']}")
    print(f"Conflicted reviewers: {summary['conflicted_reviewer_count']}")
    if summary["missing_pc_info_emails"]:
        print("Missing PC info for:")
        for email in summary["missing_pc_info_emails"]:
            print(f"  - {email}")


if __name__ == "__main__":
    main()
