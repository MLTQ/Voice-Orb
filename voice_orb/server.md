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
- **Does**: Declares plugin metadata, lifecycle/prompt capabilities, and only the LLM-facing tool manifests for `voice_orb_speak` and `voice_orb_preview`. Internal diagnostics like `ensure_model` remain callable for compatibility but are intentionally omitted from handshake to keep the command surface minimal.
- **Interacts with**: Ponderer tool-proxy registration.

### `synthesize` / `load_model`
- **Does**: Lazily import audio/model dependencies, load the configured Qwen3-TTS VoiceDesign model with explicit device/dtype strategy, detect meta-tensor loads, and generate audio with `generate_voice_design` before writing `.wav` output into the portable plugin output folder. Generation runs under torch inference mode, clamps both input text length and token budgets to safe ranges, applies a soft RSS budget guard (`max_rss_mb`) before/after synthesis, reports the resolved runtime backend (`runtime_device`/`runtime_dtype`), and keeps model weights loaded by default to avoid repeated load/unload spikes on memory-constrained backends. Tool results include process/runtime telemetry (`pid`, `instance_id`, `model_load_count`, `last_loaded_at_utc`, `rss_mb`) to diagnose intra-process reload behavior.
- **Interacts with**: `qwen_tts.Qwen3TTSModel`, `soundfile`, plugin-local `data/`.

## Contracts

| Dependent | Expects | Breaking changes |
|-----------|---------|------------------|
| Ponderer runtime host | One JSON response line per request and the current JSON-RPC method names | Changing transport or method names |
| Ponderer tool loop | Tool names (`voice_orb_speak`, `voice_orb_preview`) and parameter schema remain stable | Renaming tool methods or required params |
| Operators | Relative cache/output paths are resolved inside the plugin repo for portability | Switching to machine-global cache paths |

## Notes
- `soundfile`, `torch`, and `qwen-tts` are all imported lazily so the handshake path stays lightweight and less likely to emit startup noise before JSON-RPC begins.
- The model is loaded lazily on first synthesis or `voice_orb_ensure_model`.
- Runtime settings reconfigure now forces a model unload so device/dtype/model changes do not leave old model allocations resident.
- Model unload now drops references directly instead of migrating weights to CPU first, avoiding accidental extra host-RAM spikes during teardown.
- `engaged.instructions` prompt contributions are now emitted only when `auto_speak_replies=true`, so normal chats do not get extra pressure to call TTS tools.
- Auto device mode now resolves to a concrete backend (`cuda:0` -> `mps` -> `cpu`) instead of relying on `device_map="auto"`, and auto dtype now uses `float16` on MPS to reduce unified-memory pressure.
- CPU fallback on meta-tensor failures is now explicit (`allow_cpu_fallback=true`) rather than automatic, preventing surprise host-RAM blowups during retries.
- A soft process-memory budget (`max_rss_mb`) now blocks new synthesis when already over budget and forces unload after any over-budget generation result.
- The implementation intentionally targets the official `VoiceDesign` mode only for now; `CustomVoice` and cloning can be added later as separate tool paths.
