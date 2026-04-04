#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
resolve_python_bin() {
  if [[ -n "${VOICE_ORB_VENV_DIR:-}" && -x "${VOICE_ORB_VENV_DIR}/bin/python" ]]; then
    echo "${VOICE_ORB_VENV_DIR}/bin/python"
    return 0
  fi

  for candidate in \
    "${REPO_ROOT}/.venv-py3.12/bin/python" \
    "${REPO_ROOT}/.venv-py3.11/bin/python" \
    "${REPO_ROOT}/.venv-py3.10/bin/python" \
    "${REPO_ROOT}/.venv/bin/python"
  do
    if [[ -x "${candidate}" ]]; then
      echo "${candidate}"
      return 0
    fi
  done

  return 1
}

PYTHON_BIN="$(resolve_python_bin || true)"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Voice-Orb is not installed. Run ./scripts/install_portable.sh first." >&2
  exit 1
fi

export PYTHONUNBUFFERED=1
export PYTHONNOUSERSITE=1
exec "${PYTHON_BIN}" -m voice_orb.server
