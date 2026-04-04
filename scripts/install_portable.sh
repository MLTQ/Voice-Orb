#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CACHE_ROOT="${REPO_ROOT}/data/models"
DEFAULT_MODEL_REF="Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
DEFAULT_TORCH_CUDA_INDEX_URL="https://download.pytorch.org/whl/cu124"

PYTHON_BIN="${VOICE_ORB_PYTHON_BIN:-}"
if [[ -z "${PYTHON_BIN}" ]]; then
  for candidate in python3.12 python3.11 python3.10 python3; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      PYTHON_BIN="$(command -v "${candidate}")"
      break
    fi
  done
fi

if [[ -z "${PYTHON_BIN}" ]]; then
  echo "A compatible Python interpreter is required (prefer python3.12/python3.11)." >&2
  exit 1
fi

PYTHON_MM="$(${PYTHON_BIN} - <<'PY'
import sys

major, minor = sys.version_info[:2]
if not (major == 3 and 10 <= minor <= 12):
    raise SystemExit(
        f"Voice-Orb requires Python 3.10-3.12 for torch/qwen-tts compatibility; got {major}.{minor}"
    )
print(f"Voice-Orb installer using Python {major}.{minor}: {sys.executable}", file=sys.stderr)
print(f"{major}.{minor}")
PY
)"

DEFAULT_VENV_DIR="${REPO_ROOT}/.venv-py${PYTHON_MM}"
VENV_DIR="${VOICE_ORB_VENV_DIR:-${DEFAULT_VENV_DIR}}"

"${PYTHON_BIN}" -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip setuptools wheel
if [[ -n "${VOICE_ORB_TORCH_INDEX_URL:-}" ]]; then
  python -m pip install --upgrade torch --index-url "${VOICE_ORB_TORCH_INDEX_URL}"
elif command -v nvidia-smi >/dev/null 2>&1; then
  python -m pip install --upgrade torch --index-url "${DEFAULT_TORCH_CUDA_INDEX_URL}"
else
  python -m pip install --upgrade torch
fi
python -m pip install -e "${REPO_ROOT}"
python -m pip install "huggingface_hub>=0.34,<1.0"

TORCH_VERSION="$(python - <<'PY'
import torch
print(torch.__version__)
PY
)"
if [[ -n "${VOICE_ORB_TORCH_INDEX_URL:-}" ]]; then
  python -m pip install --force-reinstall --no-deps "torchaudio==${TORCH_VERSION}" --index-url "${VOICE_ORB_TORCH_INDEX_URL}"
elif command -v nvidia-smi >/dev/null 2>&1; then
  python -m pip install --force-reinstall --no-deps "torchaudio==${TORCH_VERSION}" --index-url "${DEFAULT_TORCH_CUDA_INDEX_URL}"
else
  python -m pip install --force-reinstall --no-deps "torchaudio==${TORCH_VERSION%%+*}"
fi

python - <<'PY'
import torch
import torchaudio

mps_backend = getattr(getattr(torch, "backends", None), "mps", None)
mps_available = bool(mps_backend is not None and mps_backend.is_available())
print(
    "Voice-Orb torch backend:",
    {
        "version": torch.__version__,
        "cuda_available": bool(torch.cuda.is_available()),
        "cuda_version": torch.version.cuda,
        "mps_available": mps_available,
        "torchaudio_version": torchaudio.__version__,
    },
)
PY

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
