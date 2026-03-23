# AssignGuard

AssignGuard checks reviewer assignments for institutional conflicts.

Given HotCRP exports for reviewer preferences, paper assignments, and PC member info, the tool finds papers where two or more assigned reviewers share the same affiliation. For each same-affiliation group, it keeps the reviewer with the highest preference score and reports the remaining reviewers as conflicts in a JSON file.

## Repository Layout

- `data/`: Input CSV files. The repository includes synthetic sample data. 
- `results/`: Generated output files.
- `scripts/`: Python scripts for running the analysis.
- `tests/`: Reserved for automated tests.

## Requirements

- Python 3.9 or newer

No third-party dependencies are required for the current script.

## Input Files

The main script expects these CSV files by default:

- `data/icse2027-allprefs.csv`: Reviewer preferences per paper. Higher scores mean stronger interest. Very negative values can represent conflicts.
- `data/icse2027-pcassignments.csv`: Paper assignment export from HotCRP.
- `data/icse2027-pcinfo.csv`: PC member profile export from HotCRP, including affiliation data.

The current sample files use fake names, fake emails, and dummy paper titles so the repository can be shared publicly. See [data/README.md](data/README.md) for detailed documentation  on these input files.

## Setup

Clone the repository and move into it:

```bash
git clone https://github.com/joannacss/AssignGuard
cd AssignGuard
```

Optionally create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## Usage

Run the tool with the default file locations:

```bash
python3 scripts/main.py
```

This writes a JSON report to `results/icse2027-affiliation-conflicts.json`.

You can also provide custom paths:

```bash
python3 scripts/main.py \
  --preferences path/to/allprefs.csv \
  --assignments path/to/pcassignments.csv \
  --pc-info path/to/pcinfo.csv \
  --output path/to/conflicts.json
```

## Output

The generated JSON contains:

- `papers_with_conflicts`: Papers where at least two assigned reviewers share an affiliation.
- `summary.paper_count`: Number of papers with at least one conflict.
- `summary.conflict_group_count`: Number of same-affiliation reviewer groups found.
- `summary.conflicted_reviewer_count`: Number of reviewers marked as conflicts.
- `summary.missing_pc_info_emails`: Assigned reviewer emails that were missing from the PC info file.

For each conflict group, the output includes:

- the shared affiliation
- the reviewer kept on the paper
- the reviewer or reviewers marked as conflicts
- each reviewer's assignment role and preference score

## Conflict Resolution Rule

If multiple assigned reviewers on the same paper have the same affiliation:

1. The reviewer with the highest preference score is kept.
2. All other reviewers from that affiliation are reported as conflicts.
3. Ties are broken by assignment order in the assignments CSV.

## Example

With the synthetic sample data included in this repository, the tool reports two institutional conflicts:

- paper `101`: two reviewers from `Northbridge University`
- paper `102`: two reviewers from `Cedar Labs`

## Notes

- Affiliation matching is case-insensitive and ignores repeated whitespace.
- Reviewer emails are normalized to lowercase before matching.
- Review actions considered by the script are `primaryreview`, `secondaryreview`, `optionalreview`, `review`, and `metareview`.
