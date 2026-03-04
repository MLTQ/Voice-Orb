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
- **Does**: Lazily import audio/model dependencies, load the configured Qwen3-TTS VoiceDesign model, generate audio with `generate_voice_design`, and write `.wav` output into the portable plugin output folder.
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
- The implementation intentionally targets the official `VoiceDesign` mode only for now; `CustomVoice` and cloning can be added later as separate tool paths.
