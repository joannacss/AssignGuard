#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

python3 "${REPO_ROOT}/scripts/find_assignments_coi.py" \
  --preferences "${SCRIPT_DIR}/icse2027-allprefs.csv" \
  --assignments "${SCRIPT_DIR}/icse2027-pcassignments.csv" \
  --pc-info "${SCRIPT_DIR}/icse2027-pcinfo.csv" \
  --output "${REPO_ROOT}/results/example2-affiliation-conflicts.json" \
  "$@"
