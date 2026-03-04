# bootstrap.py

## Purpose
Provides a small non-RPC entrypoint for install-time setup tasks such as pre-downloading the configured Qwen model into the plugin-local cache.

## Components

### `main`
- **Does**: Reads optional `VOICE_ORB_*` environment overrides, applies them to the shared `server` settings, can explicitly prefetch the tokenizer/model snapshots into the local Hugging Face cache, and can optionally call `load_model()` to validate that the configured model can be loaded.
- **Interacts with**: `voice_orb/server.py` and `scripts/install_portable.sh`.

### `prefetch_hf_assets`
- **Does**: Uses `huggingface_hub.snapshot_download` to fetch the Qwen tokenizer plus the selected VoiceDesign model into the plugin-local cache without relying on an external CLI binary.
- **Interacts with**: Hugging Face cache environment variables set by `install_portable.sh`.

## Contracts

| Dependent | Expects | Breaking changes |
|-----------|---------|------------------|
| `scripts/install_portable.sh` | `python -m voice_orb.bootstrap --prefetch-hf-assets` downloads tokenizer/model snapshots and `--download-model` verifies local load | Renaming CLI flags or removing bootstrap module |

## Notes
- This is intentionally separate from the stdio JSON-RPC server so install-time model bootstrap never writes protocol data to stdout.
