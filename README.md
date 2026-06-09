# AssignGuard

AssignGuard has a collection of utility tools to process paper submissions made on HotCRP:

- find_assignments_coi.py: checks reviewer assignments for institutional conflicts. Given HotCRP exports for reviewer preferences, paper assignments, and PC member info, the tool finds papers where two or more assigned reviewers share the same affiliation. For each same-affiliation group, it keeps the reviewer with the highest preference score and reports the remaining reviewers as conflicts in a JSON file.
- reassign_papers.py: recommends replacement reviewers for the conflicted reviewers reported by find_assignments_coi.py. It ranks candidates by TPMS score and skips reviewers whose current workload has reached the configured maximum.
- extract_references.py: given PDFs as input, it will create a new PDF containing only pages listing references.
- find_institution_name_issues.py: utility script to help catch problems in the institution information on HotCRP.

## Repository Layout

- `data/`: Input CSV files with synthetic samples.
- `results/`: Generated output files.
- `scripts/`: Python scripts for running the analysis.
- `tests/`: Reserved for automated tests.

## Requirements

- Python 3.9 or newer


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


### find_assignments_coi.py: script for paper assignment conflict resolution
**Using default inputs:**
Run the tool with the default file locations:

```bash
python3 scripts/find_assignments_coi.py
```

This writes a JSON report to `results/example1-affiliation-conflicts.json`.

**Using custom paths:**
You can also provide custom paths:

```bash
python3 scripts/find_assignments_coi.py \
  --preferences path/to/allprefs.csv \
  --assignments path/to/pcassignments.csv \
  --pc-info path/to/pcinfo.csv \
  --output path/to/conflicts.json
```
This writes a JSON report to the path specified in `--output`.

#### Input

The main script expects these CSV files by default:

- `--preferences` (default: `data/example1/icse2027-allprefs.csv`): path to a CSV file containing reviewer preferences per paper. 
- `--assignments` (default: `data/example1/icse2027-pcassignments.csv`): path to a CSV file with containing the paper assignment export from HotCRP.
- `--pc-info` (default: `data/example1/icse2027-pcinfo.csv`): path to a CSV file with PC member profile export from HotCRP.


See [data/README.md](data/README.md) for detailed documentation  on these input files. The current sample (default) files use fake names, fake emails, and dummy paper titles so the repository can be shared publicly. 

#### Output

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

#### Conflict Resolution Rule

If multiple assigned reviewers on the same paper have the same affiliation:

1. The reviewer with the highest preference score is kept.
2. All other reviewers from that affiliation are reported as conflicts.
3. Ties are broken by assignment order in the assignments CSV.

#### Example

With the synthetic sample data included in this repository, the tool reports two institutional conflicts:

- paper `101`: two reviewers from `Northbridge University`
- paper `102`: two reviewers from `Cedar Labs`

#### Notes

- Affiliation matching is case-insensitive and ignores repeated whitespace.
- Reviewer emails are normalized to lowercase before matching.
- Review actions considered by the script are `primaryreview`, `secondaryreview`, `optionalreview`, `review`, and `metareview`.


### reassign_papers.py: script for replacement reviewer recommendations

After generating the conflict report, recommend replacement reviewers with the highest TPMS scores:

```bash
python3 scripts/reassign_papers.py
```

This reads `results/example1-affiliation-conflicts.json` and writes
`results/example1-reassignment-recommendations.json`.

You can also provide custom paths and a workload threshold:

```bash
python3 scripts/reassign_papers.py \
  --conflicts path/to/conflicts.json \
  --preferences path/to/allprefs.csv \
  --assignments path/to/pcassignments.csv \
  --pc-info path/to/pcinfo.csv \
  --max-workload 14 \
  --output path/to/reassignments.json
```

For each conflicted regular reviewer in the input JSON, the script recommends one new reviewer. It only replaces `Main` and `Main_AR` reviewers with PC members whose `tags` include `RegRev`. It skips conflict groups that mix regular reviewers with a `Main_MR` metareviewer, excludes reviewers already assigned to that paper, excludes reviewers whose current workload is already at `--max-workload`, and updates workloads as it makes recommendations so later recommendations in the same run respect the same limit.


### extract_references.py: script to extract reference pages from PDFs.

You can also extract the pages that contain a paper's references section:

```bash
python3 scripts/extract_references.py path/to/paper.pdf
python3 scripts/extract_references.py path/to/folder
```

This writes one output PDF per detected input paper into `out/`, using names like
`paper_references.pdf`.
