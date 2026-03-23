# Data Folder

This holds synthetic dummy data.
- `icse2027-allprefs.csv`: it has preferences of reviewers extracted from TPMS. Here, the higher the score, the more interested that person is in that paper. A very low negative score means the person has a conflict.
- `data/icse2027-pcassignments.csv`: paper assignments information downloaded from HotCRP. This can be obtained by: 
  - (1) List all submitted papers https://icse2027.hotcrp.com/search?q=&t=s
  - (2) Select all > Download > Review Assignments > PC Assignments 
- `data/icse2027-pcinfo.csv`: profile information of the PC members as exported by HotCRP. This can be obtained by: 
  - (1) List all reviewers https://icse2027.hotcrp.com/users?t=re
  - (2) Select all > Download > PC Info

## Data Format

The tool expects three CSV files with the following formats.

### `icse2027-allprefs.csv`

Reviewer preference scores per paper.

**Header:**

```text
paper,email,preference
```

**Fields:**

- `paper`: Paper identifier. This should match the paper IDs used in the assignments file.
- `email`: Reviewer's email address. Matching is case-insensitive.
- `preference`: Numeric preference score for that reviewer-paper pair. Higher values mean stronger reviewer interest. Blank values are treated as `0`. Very negative values may indicate a reviewer conflict in the original HotCRP export, although this script only uses the score to rank reviewers from the same institution.

### `icse2027-pcassignments.csv`

Paper assignment export from HotCRP.

**Header:**

```text
paper,action,email,title
```

**Fields:**

- `paper`: Paper identifier.
- `action`: Assignment action from HotCRP. The script uses:
  - `clearreview` to capture the paper title
  - `primaryreview`
  - `secondaryreview`
  - `optionalreview`
  - `review`
  - `metareview`
- `email`: Assigned reviewer's email for review-action rows. On `clearreview` rows this may be `#pc`.
- `title`: Paper title. The script reads this from the `clearreview` row for each paper and includes it in the JSON output.

_**Expected pattern:**_

- One `clearreview` row per paper with the title populated.
- Zero or more review assignment rows for the same paper.

### `icse2027-pcinfo.csv`

PC member profile export from HotCRP.

**Header:**

```text
given_name,family_name,email,affiliation,orcid,country,roles,collaborators,follow
```

**Fields used by the script:**

- `given_name`: Reviewer's first name.
- `family_name`: Reviewer's last name.
- `email`: Reviewer's email address. This is the join key to match assignments and preferences.
- `affiliation`: Institution name used to detect same-institution assignments.

**Additional fields:**

- `orcid`
- `country`
- `roles`
- `collaborators`
- `follow`

The current script ignores those additional fields, but they can remain in the export unchanged.

### Matching Rules

- Reviewer emails are normalized to lowercase before matching across files.
- Affiliations are compared case-insensitively and with repeated whitespace collapsed.
- If an assigned reviewer email is missing from `icse2027-pcinfo.csv`, that email is listed in the JSON summary under `missing_pc_info_emails`.
