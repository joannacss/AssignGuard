#!/usr/bin/env bash
set -euo pipefail
#3086
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CONFLICTS_OUTPUT="${REPO_ROOT}/results/example3-affiliation-conflicts.json"
REASSIGNMENTS_OUTPUT="${REPO_ROOT}/results/example3-reassignment-recommendations.json"
MAX_WORKLOAD="${MAX_WORKLOAD:-14}"

python3 "${REPO_ROOT}/scripts/find_assignments_coi.py" \
  --preferences "${SCRIPT_DIR}/icse2027-allprefs.csv" \
  --assignments "${SCRIPT_DIR}/icse2027-pcassignments.csv" \
  --pc-info "${SCRIPT_DIR}/icse2027-pcinfo.csv" \
  --output "${CONFLICTS_OUTPUT}"

python3 "${REPO_ROOT}/scripts/reassign_papers.py" \
  --conflicts "${CONFLICTS_OUTPUT}" \
  --preferences "${SCRIPT_DIR}/icse2027-allprefs.csv" \
  --assignments "${SCRIPT_DIR}/icse2027-pcassignments.csv" \
  --pc-info "${SCRIPT_DIR}/icse2027-pcinfo.csv" \
  --max-workload "${MAX_WORKLOAD}" \
  --output "${REASSIGNMENTS_OUTPUT}"
