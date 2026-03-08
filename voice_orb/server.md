# server.py

## Purpose
Implements the `Voice-Orb` stdio JSON-RPC server for Ponderer. It loads Qwen3-TTS VoiceDesign on demand, applies plugin settings, accepts lifecycle events, and exposes the speech-synthesis tools that the runtime plugin host proxies into Ponderer.

## Components

### `PluginState`
- **Does**: Stores persisted settings, a lightweight persona-derived voice hint, and the lazily loaded Qwen model instance.
- **Interacts with**: every RPC method.

### `main` / `handle_rpc_line` / `dispatch`
- **Does**: Run the newline-delimited JSON-RPC loop and route supported methods (`plugin.handshake`, `plugin.configure`, `plugin.handle_event`, `plugin.get_prompt_contributions`, `plugin.invoke_tool`).
- **Interacts with**: Ponderer runtime plugin host.

### `handshake`
- **Does**: Declares plugin metadata, lifecycle/prompt capabilities, and the tool manifests for `voice_orb_speak`, `voice_orb_preview`, and `voice_orb_ensure_model`.
- **Interacts with**: Ponderer tool-proxy registration.

### `synthesize` / `load_model`
- **Does**: Lazily import audio/model dependencies, load the configured Qwen3-TTS VoiceDesign model with explicit device/dtype strategy, detect meta-tensor loads, and generate audio with `generate_voice_design` (including one-shot fallback reload on meta-tensor runtime failures) before writing `.wav` output into the portable plugin output folder. Generation now always runs under torch inference mode, clamps token budgets to a safe range, reports the resolved runtime backend (`runtime_device`/`runtime_dtype`), and by default unloads model weights after each synthesis to prevent RSS ratcheting.
- **Interacts with**: `qwen_tts.Qwen3TTSModel`, `soundfile`, plugin-local `data/`.

## Contracts

| Dependent | Expects | Breaking changes |
|-----------|---------|------------------|
| Ponderer runtime host | One JSON response line per request and the current JSON-RPC method names | Changing transport or method names |
| Ponderer tool loop | Tool names (`voice_orb_speak`, `voice_orb_preview`, `voice_orb_ensure_model`) and parameter schema remain stable | Renaming tool methods or required params |
| Operators | Relative cache/output paths are resolved inside the plugin repo for portability | Switching to machine-global cache paths |

## Notes
- `soundfile`, `torch`, and `qwen-tts` are all imported lazily so the handshake path stays lightweight and less likely to emit startup noise before JSON-RPC begins.
- The model is loaded lazily on first synthesis or `voice_orb_ensure_model`.
- Runtime settings reconfigure now forces a model unload so device/dtype/model changes do not leave old model allocations resident.
- Model unload now drops references directly instead of migrating weights to CPU first, avoiding accidental extra host-RAM spikes during teardown.
- `engaged.instructions` prompt contributions are now emitted only when `auto_speak_replies=true`, so normal chats do not get extra pressure to call TTS tools.
- Auto device mode now resolves to a concrete backend (`cuda:0` -> `mps` -> `cpu`) instead of relying on `device_map="auto"`, and CPU fallback is used automatically if meta tensors are detected.
- The implementation intentionally targets the official `VoiceDesign` mode only for now; `CustomVoice` and cloning can be added later as separate tool paths.
