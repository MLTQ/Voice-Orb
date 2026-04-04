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

usage() {
  cat <<'EOF'
Usage:
  ./scripts/voice_note.sh "text to speak"
  printf 'text to speak' | ./scripts/voice_note.sh

Options:
  --voice TEXT       Override the default voice description.
  --language NAME    Language name (default: english).
  --max-tokens N     Override max_new_tokens. Default: auto-estimated.
  --output PATH      Final .ogg output path. Defaults into data/output/.
  --keep-wav         Keep the intermediate .wav instead of deleting it.
  --help             Show this help.

Environment overrides:
  VOICE_ORB_MODEL_REF
  VOICE_ORB_DEFAULT_LANGUAGE
  VOICE_ORB_DEFAULT_VOICE_DESCRIPTION
  VOICE_ORB_DEVICE
  VOICE_ORB_DTYPE
  VOICE_ORB_ATTENTION_IMPL
  VOICE_ORB_MAX_NEW_TOKENS
  VOICE_ORB_UNLOAD_AFTER_SYNTHESIS
EOF
}

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg is required" >&2
  exit 1
fi

PYTHON_BIN="$(resolve_python_bin || true)"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Voice-Orb is not installed. Run ./scripts/install_portable.sh first." >&2
  exit 1
fi

VOICE_DESCRIPTION="${VOICE_ORB_DEFAULT_VOICE_DESCRIPTION:-Sultry, breathy, warm, intimate, and natural, with clear diction, soft texture, and an unhurried, conversational cadence.}"
LANGUAGE="${VOICE_ORB_DEFAULT_LANGUAGE:-english}"
MODEL_REF="${VOICE_ORB_MODEL_REF:-Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign}"
DEVICE="${VOICE_ORB_DEVICE:-cuda}"
DTYPE="${VOICE_ORB_DTYPE:-bfloat16}"
ATTENTION_IMPL="${VOICE_ORB_ATTENTION_IMPL:-eager}"
MAX_NEW_TOKENS_OVERRIDE="${VOICE_ORB_MAX_NEW_TOKENS:-auto}"
UNLOAD_AFTER_SYNTHESIS="${VOICE_ORB_UNLOAD_AFTER_SYNTHESIS:-1}"
KEEP_WAV=0
OUTPUT_PATH=""
TEXT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --voice)
      [[ $# -ge 2 ]] || { echo "--voice requires a value" >&2; exit 1; }
      VOICE_DESCRIPTION="$2"
      shift 2
      ;;
    --language)
      [[ $# -ge 2 ]] || { echo "--language requires a value" >&2; exit 1; }
      LANGUAGE="$2"
      shift 2
      ;;
    --max-tokens)
      [[ $# -ge 2 ]] || { echo "--max-tokens requires a value" >&2; exit 1; }
      MAX_NEW_TOKENS_OVERRIDE="$2"
      shift 2
      ;;
    --output)
      [[ $# -ge 2 ]] || { echo "--output requires a path" >&2; exit 1; }
      OUTPUT_PATH="$2"
      shift 2
      ;;
    --keep-wav)
      KEEP_WAV=1
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
    *)
      if [[ -n "${TEXT}" ]]; then
        TEXT+=" "
      fi
      TEXT+="$1"
      shift
      ;;
  esac
done

if [[ $# -gt 0 ]]; then
  REMAINING="$*"
  if [[ -n "${TEXT}" ]]; then
    TEXT+=" "
  fi
  TEXT+="${REMAINING}"
fi

if [[ -z "${TEXT// }" ]] && [[ ! -t 0 ]]; then
  TEXT="$(python3 - <<'PY'
import sys
print(sys.stdin.read().strip())
PY
)"
fi

if [[ -z "${TEXT// }" ]]; then
  echo "No text provided." >&2
  usage >&2
  exit 1
fi

estimate_max_new_tokens() {
  python3 - <<'PY'
import math
import os
import re

text = os.environ["VOICE_NOTE_TEXT_FOR_BUDGET"]
voice = os.environ["VOICE_NOTE_VOICE_FOR_BUDGET"]

char_count = len(text)
word_count = len(re.findall(r"\S+", text))
pause_count = len(re.findall(r"[,:;\-—]", text))
terminal_pause_count = len(re.findall(r"[.!?]", text))
line_breaks = text.count("\n")

style = voice.lower()
style_multiplier = 1.0
if any(token in style for token in ("breathy", "sultry", "intimate", "unhurried", "slow", "soft", "smoky", "close-mic", "close mic")):
    style_multiplier += 0.22
if any(token in style for token in ("calm", "warm", "thoughtful", "conversational")):
    style_multiplier += 0.08

base = 120
estimate = (
    base
    + word_count * 5.0
    + char_count * 0.85
    + pause_count * 10.0
    + terminal_pause_count * 18.0
    + line_breaks * 24.0
) * style_multiplier

bounded = max(192, min(int(math.ceil(estimate)), 1536))
print(bounded)
PY
}

if [[ -z "${MAX_NEW_TOKENS_OVERRIDE// }" || "${MAX_NEW_TOKENS_OVERRIDE}" == "auto" ]]; then
  export VOICE_NOTE_TEXT_FOR_BUDGET="${TEXT}"
  export VOICE_NOTE_VOICE_FOR_BUDGET="${VOICE_DESCRIPTION}"
  MAX_NEW_TOKENS="$(estimate_max_new_tokens)"
else
  MAX_NEW_TOKENS="${MAX_NEW_TOKENS_OVERRIDE}"
fi

if [[ -z "${OUTPUT_PATH}" ]]; then
  STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  OUTPUT_PATH="${REPO_ROOT}/data/output/voice_note_${STAMP}.ogg"
fi

mkdir -p "$(dirname "${OUTPUT_PATH}")" "${REPO_ROOT}/data/models" "${REPO_ROOT}/data/output"
export HF_HOME="${REPO_ROOT}/data/models"
export HF_HUB_CACHE="${REPO_ROOT}/data/models"
export TRANSFORMERS_CACHE="${REPO_ROOT}/data/models"
export HF_HUB_DISABLE_PROGRESS_BARS=1
export TOKENIZERS_PARALLELISM=false
export PYTHONWARNINGS="ignore"
export VOICE_NOTE_TEXT="${TEXT}"
export VOICE_NOTE_VOICE_DESCRIPTION="${VOICE_DESCRIPTION}"
export VOICE_NOTE_LANGUAGE="${LANGUAGE}"
export VOICE_NOTE_MODEL_REF="${MODEL_REF}"
export VOICE_NOTE_DEVICE="${DEVICE}"
export VOICE_NOTE_DTYPE="${DTYPE}"
export VOICE_NOTE_ATTENTION_IMPL="${ATTENTION_IMPL}"
export VOICE_NOTE_MAX_NEW_TOKENS="${MAX_NEW_TOKENS}"
export VOICE_NOTE_UNLOAD_AFTER_SYNTHESIS="${UNLOAD_AFTER_SYNTHESIS}"

PYTHON_LOG="$(mktemp)"
cleanup() {
  rm -f "${PYTHON_LOG}"
}
trap cleanup EXIT

if ! WAV_PATH="$(${PYTHON_BIN} 2>"${PYTHON_LOG}" <<'PY'
import os
from voice_orb import server

server.configure({
    "settings": {
        "model_ref": os.environ["VOICE_NOTE_MODEL_REF"],
        "cache_dir": "./data/models",
        "output_dir": "./data/output",
        "device": os.environ["VOICE_NOTE_DEVICE"],
        "dtype": os.environ["VOICE_NOTE_DTYPE"],
        "attention_impl": os.environ["VOICE_NOTE_ATTENTION_IMPL"],
        "max_new_tokens": int(os.environ["VOICE_NOTE_MAX_NEW_TOKENS"]),
        "unload_after_synthesis": os.environ.get("VOICE_NOTE_UNLOAD_AFTER_SYNTHESIS", "1") not in {"0", "false", "False"},
        "language": os.environ["VOICE_NOTE_LANGUAGE"],
    }
})

result = server.synthesize(
    {
        "text": os.environ["VOICE_NOTE_TEXT"],
        "voice_description": os.environ["VOICE_NOTE_VOICE_DESCRIPTION"],
    },
    preview=False,
)
print(result["data"]["path"])
PY
)"; then
  cat "${PYTHON_LOG}" >&2
  exit 1
fi

ffmpeg -loglevel error -y -i "${WAV_PATH}" -c:a libopus -b:a 48k "${OUTPUT_PATH}"

if [[ "${KEEP_WAV}" != "1" ]]; then
  rm -f "${WAV_PATH}"
fi

printf '%s\n' "${OUTPUT_PATH}"
