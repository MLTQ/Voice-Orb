# install_portable.sh

## Purpose
Creates a self-contained Python virtual environment inside the plugin repo and installs `Voice-Orb` plus its dependencies there.

## Components

### `install_portable.sh`
- **Does**: Creates `.venv`, upgrades packaging tools, installs `torch` first (allowing explicit `VOICE_ORB_TORCH_INDEX_URL` override or CUDA auto-selection when `nvidia-smi` exists), installs the project in editable mode, re-pins `huggingface_hub` into the `transformers`-compatible `<1.0` range, prints detected torch backend capabilities (`cuda`/`mps`) for install-time verification, creates portable `data/` directories used for model cache, output, and plugin state, uses `voice_orb.bootstrap` to explicitly pre-download both the Qwen tokenizer and configured model into the plugin-local Hugging Face cache, and then validates that the model can be loaded.
- **Interacts with**: `pyproject.toml`, `scripts/run_plugin.sh`.

## Contracts

| Dependent | Expects | Breaking changes |
|-----------|---------|------------------|
| `scripts/run_plugin.sh` | `.venv/bin/python` exists after install | Changing the venv location |
| Operators | Running this script is enough to prepare a fresh portable checkout, including a local tokenizer/model cache under `data/models` | Removing editable install, data-dir creation, explicit Hugging Face prefetch, or install-time verification |

## Notes
- Set `VOICE_ORB_SKIP_MODEL_DOWNLOAD=1` if you need to skip the model prefetch step during development or offline setup.
- `VOICE_ORB_MODEL_REF` and `VOICE_ORB_TOKENIZER_REF` can override which Hugging Face repos are prefetched during install.
- Set `VOICE_ORB_TORCH_INDEX_URL` to force a specific PyTorch wheel channel (for example, CUDA builds) when auto-detection is not enough.
- The installer no longer upgrades or depends on an external `huggingface-cli` binary; it reuses the in-environment `huggingface_hub` Python package directly and explicitly re-pins it into a `transformers`-compatible version range.
