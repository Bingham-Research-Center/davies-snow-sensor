#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-/home/pi/davies-snow-sensor}"
VENV_PY="${REPO_DIR}/venv/bin/python"
CONFIG_PATH="${REPO_DIR}/config/station_01.yaml"
LOG_DIR="${REPO_DIR}/data/validation"
LOG_FILE="${LOG_DIR}/reference_validation_$(date -u +%Y%m%dT%H%M%SZ).log"
SOAK_SECONDS="${SOAK_SECONDS:-14400}" # default 4 hours

mkdir -p "${LOG_DIR}"

run() {
  echo
  echo ">>> $*" | tee -a "${LOG_FILE}"
  "$@" 2>&1 | tee -a "${LOG_FILE}"
}

section() {
  echo
  echo "==================================================" | tee -a "${LOG_FILE}"
  echo "$1" | tee -a "${LOG_FILE}"
  echo "==================================================" | tee -a "${LOG_FILE}"
}

pause_for_operator() {
  local prompt="$1"
  echo
  read -r -p "${prompt} [press Enter to continue] " _
}

section "Reference Pi Validation Started"
echo "UTC: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"
echo "Repo: ${REPO_DIR}" | tee -a "${LOG_FILE}"
echo "Config: ${CONFIG_PATH}" | tee -a "${LOG_FILE}"
echo "Log: ${LOG_FILE}" | tee -a "${LOG_FILE}"

section "Phase 1: Static Checks"
run test -f "${CONFIG_PATH}"
run "${VENV_PY}" -m pytest -q
run "${VENV_PY}" -m src.sensor.main --config "${CONFIG_PATH}" --test --verbose

section "Phase 2: Hardware Bench Checks (Interactive)"
echo "Run these commands in another terminal or directly here:" | tee -a "${LOG_FILE}"
echo "  sudo ${VENV_PY} ${REPO_DIR}/scripts/test_hardware.py -u --config ${CONFIG_PATH}" | tee -a "${LOG_FILE}"
echo "  sudo ${VENV_PY} ${REPO_DIR}/scripts/test_hardware.py -t --config ${CONFIG_PATH}" | tee -a "${LOG_FILE}"
echo "  sudo ${VENV_PY} ${REPO_DIR}/scripts/test_hardware.py -o --config ${CONFIG_PATH}" | tee -a "${LOG_FILE}"
echo "  sudo ${VENV_PY} ${REPO_DIR}/scripts/test_hardware.py --all --config ${CONFIG_PATH}" | tee -a "${LOG_FILE}"
pause_for_operator "Complete Phase 2 hardware tests and note pass/fail in docs/reference_validation.md."

section "Phase 3: Soak Test"
echo "Starting sensor soak test for ${SOAK_SECONDS}s (~$((SOAK_SECONDS / 3600))h)." | tee -a "${LOG_FILE}"
echo "Use Ctrl+C only if you intentionally abort." | tee -a "${LOG_FILE}"
run timeout "${SOAK_SECONDS}" sudo "${VENV_PY}" -m src.sensor.main --config "${CONFIG_PATH}" --verbose || true
echo "Soak phase ended (timeout/exit)." | tee -a "${LOG_FILE}"

section "Phase 4: Failure-Mode Checks (Operator Driven)"
echo "Perform and observe each scenario while monitoring logs:" | tee -a "${LOG_FILE}"
echo "  1) LoRa receiver ON: confirm transmission_status=success." | tee -a "${LOG_FILE}"
echo "  2) LoRa receiver OFF: confirm transmission_status=local_only and SD writes continue." | tee -a "${LOG_FILE}"
echo "  3) Unmount SSD: confirm warning logs and SD fallback." | tee -a "${LOG_FILE}"
echo "  4) Remount SSD: confirm backup mirror resumes." | tee -a "${LOG_FILE}"
echo "Suggested log follow command:" | tee -a "${LOG_FILE}"
echo "  journalctl -u snow-sensor -f" | tee -a "${LOG_FILE}"
pause_for_operator "Complete Phase 4 checks and record outcomes in docs/reference_validation.md."

section "Phase 5: Service + Diagnostics"
run sudo "${REPO_DIR}/scripts/station_diagnostics.sh"
run sudo systemctl --no-pager --full status snow-firstboot.service || true
run sudo systemctl --no-pager --full status snow-sensor.service || true
run sudo systemctl --no-pager --full status snow-backup-monitor.timer || true

section "Validation Run Complete"
echo "Fill out acceptance gates in docs/reference_validation.md before cloning." | tee -a "${LOG_FILE}"
echo "Log written to ${LOG_FILE}" | tee -a "${LOG_FILE}"
