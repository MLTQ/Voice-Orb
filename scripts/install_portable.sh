#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${REPO_ROOT}/.venv"
CACHE_ROOT="${REPO_ROOT}/data/models"
DEFAULT_MODEL_REF="Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required" >&2
  exit 1
fi

python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e "${REPO_ROOT}"
python -m pip install "huggingface_hub>=0.34,<1.0"

mkdir -p \
  "${CACHE_ROOT}" \
  "${REPO_ROOT}/data/output" \
  "${REPO_ROOT}/data/state"

if [[ "${VOICE_ORB_SKIP_MODEL_DOWNLOAD:-0}" == "1" ]]; then
  echo "Skipping model download because VOICE_ORB_SKIP_MODEL_DOWNLOAD=1"
else
  export VOICE_ORB_MODEL_REF="${VOICE_ORB_MODEL_REF:-${DEFAULT_MODEL_REF}}"
  export HF_HOME="${CACHE_ROOT}"
  export HF_HUB_CACHE="${CACHE_ROOT}"
  export TRANSFORMERS_CACHE="${CACHE_ROOT}"

  echo "Prefetching Voice-Orb Hugging Face assets into ${CACHE_ROOT}..."
  python -m voice_orb.bootstrap --prefetch-hf-assets
  echo "Validating local model load..."
  python -m voice_orb.bootstrap --download-model
fi

echo "Voice-Orb portable environment installed at ${VENV_DIR}"
