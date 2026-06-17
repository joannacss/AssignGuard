# AssignGuard

AssignGuard has a collection of utility tools to process paper submissions made on HotCRP:

- `find_assignments_coi.py`: checks reviewer assignments for institutional conflicts. Given HotCRP exports for reviewer preferences, paper assignments, and PC member info, the tool finds papers where two or more assigned reviewers share the same affiliation. For each same-affiliation group, it keeps the reviewer with the highest preference score and reports the remaining reviewers as conflicts in a JSON file.
- `reassign_papers.py`: recommends replacement reviewers for the conflicted reviewers reported by find_assignments_coi.py. It keeps the highest-preference reviewer in each conflict group, ranks candidates by TPMS score, matches the replacement to the removed reviewer's assignment type, and skips reviewers whose current workload has reached the configured maximum.
- `extract_references.py`: given PDFs as input, it will create a new PDF containing only pages listing references.
- `find_institution_name_issues.py`: utility script to help catch problems in the institution information on HotCRP.

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


### find_assignments_coi.py: institutional conflict detection

This script detects same-institution reviewer assignments. It uses the HotCRP assignment export to learn which reviewers are assigned to each paper, the HotCRP PC info export to learn each reviewer's affiliation and PC metadata, and the TPMS preferences export to rank reviewers when a conflict is found.

#### Algorithm

1. Load reviewer TPMS preference scores keyed by `(paper, reviewer email)`.
2. Load PC member profiles keyed by normalized lowercase email.
3. Load paper assignments and keep review actions: `primaryreview`, `secondaryreview`, `optionalreview`, `review`, and `metareview`.
4. For each paper, group assigned reviewers by normalized affiliation. Affiliation matching is case-insensitive and collapses repeated whitespace.
5. Ignore reviewers whose affiliation is empty or whose PC profile is missing. Missing PC profile emails are reported in the summary.
6. For each affiliation group with at least two reviewers, rank the reviewers by highest TPMS preference score.
7. Keep the highest-preference reviewer in that group and report all other reviewers in the group as conflicted reviewers.
8. Break ties by the original assignment order in the HotCRP assignment CSV, then by email.

#### Inputs

- `--preferences` (default: `data/example1/icse2027-allprefs.csv`): TPMS preference scores per paper and reviewer.
- `--assignments` (default: `data/example1/icse2027-pcassignments.csv`): HotCRP paper assignment export.
- `--pc-info` (default: `data/example1/icse2027-pcinfo.csv`): HotCRP PC member profile export.
- `--output` (default: `results/example1-affiliation-conflicts.json`): generated conflict report.

See [data/README.md](data/README.md) for detailed documentation on the input files. The current sample files use fake names, fake emails, and dummy paper titles so the repository can be shared publicly.

#### Output

The generated JSON contains:

- `papers_with_conflicts`: papers where at least two assigned reviewers share an affiliation.
- `summary.paper_count`: number of papers with at least one conflict.
- `summary.conflict_group_count`: number of same-affiliation reviewer groups found.
- `summary.conflicted_reviewer_count`: number of reviewers marked as conflicts.
- `summary.missing_pc_info_emails`: assigned reviewer emails missing from the PC info file.

For each conflict group, the output includes the shared affiliation, the reviewer kept on the paper, the reviewer or reviewers marked as conflicts, each reviewer's assignment role, review round, and TPMS preference score.

#### Commands

Run the tool with the default file locations:

```bash
python3 scripts/find_assignments_coi.py
```

This writes a JSON report to `results/example1-affiliation-conflicts.json`.

You can also provide custom paths:

```bash
python3 scripts/find_assignments_coi.py \
  --preferences path/to/allprefs.csv \
  --assignments path/to/pcassignments.csv \
  --pc-info path/to/pcinfo.csv \
  --output path/to/conflicts.json
```
This writes a JSON report to the path specified in `--output`.

#### Example

With the synthetic sample data included in this repository, the tool reports two institutional conflicts:

- paper `101`: two reviewers from `Northbridge University`
- paper `102`: two reviewers from `Cedar Labs`

### reassign_papers.py: replacement reviewer recommendations

This script is the downstream step after `find_assignments_coi.py`. It reads the COI report and recommends replacement reviewers for reviewers who should leave a conflicted assignment group.

#### Algorithm

1. Load the COI JSON report generated by `find_assignments_coi.py`.
2. Load TPMS preferences, current HotCRP assignments, and PC info.
3. Count each reviewer's current workload from the assignment CSV.
4. For each conflict group, combine the reported `keep_reviewer` and `conflict_reviewers`.
5. Re-rank that full conflict group by highest preference score and keep the highest-preference reviewer.
6. For every other reviewer in the group, determine the assignment type from the review round.
7. If the removed reviewer is `Main` or `Main_AR`, only consider replacement candidates whose PC `tags` include `RegRev`.
8. If the removed reviewer is `Main_MR`, only consider replacement candidates marked as `AreaChair` in PC `roles` or `tags`.
9. Exclude candidates already assigned to the same paper.
10. Exclude candidates whose current workload is already at `--max-workload`.
11. Pick the remaining candidate with the highest TPMS score for that paper. Ties prefer lower current workload, then email.
12. After making a recommendation, increment that candidate's workload so later recommendations in the same run respect the workload cap.
13. If no eligible candidate remains, write the case under `unassigned` instead of inventing a replacement.

#### Inputs

- `--conflicts` (default: `results/example1-affiliation-conflicts.json`): JSON output from `find_assignments_coi.py`.
- `--preferences` (default: `data/example1/icse2027-allprefs.csv`): TPMS preference scores per paper and reviewer.
- `--assignments` (default: `data/example1/icse2027-pcassignments.csv`): HotCRP paper assignment export used to compute current workload and exclude already assigned reviewers.
- `--pc-info` (default: `data/example1/icse2027-pcinfo.csv`): HotCRP PC member profile export used to check `RegRev` and `AreaChair` eligibility.
- `--max-workload` (default: `14`): maximum number of assigned reviews a reviewer can have before being excluded.
- `--output` (default: `results/example1-reassignment-recommendations.json`): generated reassignment report.

#### Output

The generated JSON contains:

- `reassignments`: successful replacement recommendations grouped by paper.
- `unassigned`: conflicted reviewers for whom no eligible replacement was found.
- `skipped`: reviewers whose round is unsupported by the reassignment algorithm.
- `summary.paper_count`: number of papers with at least one recommendation.
- `summary.replacement_count`: number of successful replacement recommendations.
- `summary.unassigned_count`: number of needed replacements without an eligible candidate.
- `summary.skipped_count`: number of unsupported replacement cases.
- `summary.max_workload`: workload threshold used for the run.

Each recommendation includes the reviewer to replace, that reviewer's current workload, and the recommended new reviewer with TPMS score and current workload before assignment.

#### Commands

After generating the conflict report, recommend replacement reviewers with the highest eligible TPMS scores:

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

### find_institution_name_issues.py: institution-name quality checks

This script helps clean the HotCRP PC info export before conflict detection. It looks for institution names that are likely acronyms or typo variants of other institution names in the same file.

#### Algorithm

1. Load reviewer names, emails, and affiliations from the PC info CSV.
2. Normalize affiliations by trimming whitespace, collapsing repeated whitespace, and case-folding.
3. Build an affiliation index grouped by normalized affiliation.
4. Choose a canonical display name for each normalized affiliation using frequency first, then longer display name, then lexicographic order.
5. Detect acronym-like affiliations by removing whitespace and punctuation, then checking for short all-uppercase values.
6. For each acronym-like affiliation, compare it with initialisms generated from multi-token institution names.
7. Report acronym entries with suggested long-form matches when available.
8. Detect typo variants by comparing normalized affiliations with the same number of tokens.
9. Only flag typo candidates when exactly one token differs, the differing token is at least five characters, the full-name similarity is at least `0.88`, and token edit distance is at most `2`.
10. For typo pairs, choose the canonical spelling by reviewer count, display-name length, and display-name order.

#### Inputs

- `--pc-info` (default: `data/example1/icse2027-pcinfo.csv`): HotCRP PC member profile export.
- `--output` (default: `results/institution-name-issues.json`): generated institution issue report.

#### Output

The generated JSON contains:

- `summary.reviewer_count`: number of PC rows scanned.
- `summary.distinct_affiliation_count`: number of normalized non-empty affiliations.
- `summary.suspicious_entry_count`: number of findings.
- `summary.acronym_count`: number of acronym-like findings.
- `summary.typo_count`: number of likely typo findings.
- `findings`: individual suspicious rows with reviewer name, email, issue type, original affiliation, suggested affiliation, and candidate matches.

#### Commands

Run with the default example1 PC info:

```bash
python3 scripts/find_institution_name_issues.py
```

Or provide custom paths:

```bash
python3 scripts/find_institution_name_issues.py \
  --pc-info path/to/pcinfo.csv \
  --output path/to/institution-name-issues.json
```

### extract_references.py: reference-page extraction

This script extracts the pages containing a references section from one PDF or from every PDF under a folder.

#### Algorithm

1. Resolve the input as either a single PDF file or a folder to scan recursively for PDFs.
2. Use `pypdf` to extract text from every page.
3. Normalize page text into non-empty whitespace-collapsed lines.
4. Find the first page whose top lines contain an exact references heading: `References`, `Bibliography`, `Works Cited`, or `Literature Cited`.
5. Continue including pages until the end of the document or until a later page starts with a strong stop heading such as `Appendix`, `Appendices`, `Supplementary Material`, or author biography headings.
6. Write the detected inclusive page range to a new PDF in `out/`.
7. Skip PDFs where no references heading is detected.

The script also includes a simple reference-page scoring helper based on bibliography patterns, years, `et al.`, and `doi`, but the current extraction boundary uses heading detection.

#### Inputs

- Positional `source`: path to a PDF file or folder.

#### Output

For each detected input PDF, the script writes `out/<paper_stem>_references.pdf` and prints the extracted page range. If a PDF has no detected references section, it prints a skip message.

#### Commands

Extract the pages that contain a paper's references section:

```bash
python3 scripts/extract_references.py path/to/paper.pdf
python3 scripts/extract_references.py path/to/folder
```

This writes one output PDF per detected input paper into `out/`, using names like
`paper_references.pdf`.
