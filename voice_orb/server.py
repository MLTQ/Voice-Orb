import json
import os
import sys
import contextlib
import gc
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from voice_orb import __version__

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAX_NEW_TOKENS = 384
MIN_MAX_NEW_TOKENS = 64
MAX_MAX_NEW_TOKENS = 1024
PREVIEW_MAX_NEW_TOKENS = 192
DEFAULT_MAX_INPUT_CHARS = 900
DEFAULT_MAX_RSS_MB = 14_000


@dataclass
class PluginState:
    settings: dict[str, Any] = field(default_factory=dict)
    persona_hint: str = ""
    instance_id: str = field(
        default_factory=lambda: f"voice-orb-{os.getpid()}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    )
    startup_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    model_load_count: int = 0
    last_loaded_utc: str | None = None
    loaded_model_ref: str | None = None
    loaded_model: Any | None = None
    torch_module: Any | None = None
    model_class: Any | None = None
    soundfile_module: Any | None = None

    def merged_settings(self) -> dict[str, Any]:
        merged = {
            "enabled": False,
            "model_ref": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
            "cache_dir": "./data/models",
            "output_dir": "./data/output",
            "device": "auto",
            "dtype": "auto",
            "attention_impl": "auto",
            "language": "Auto",
            "default_voice_description": (
                "Warm, articulate, steady, emotionally grounded, "
                "with clear diction and a calm cadence."
            ),
            "allow_persona_drift": True,
            "auto_speak_replies": False,
            "allow_cpu_fallback": False,
            "unload_after_synthesis": False,
            "max_input_chars": DEFAULT_MAX_INPUT_CHARS,
            "max_rss_mb": DEFAULT_MAX_RSS_MB,
            "max_new_tokens": DEFAULT_MAX_NEW_TOKENS,
            "top_p": 0.9,
            "top_k": 50,
            "temperature": 0.7,
            "repetition_penalty": 1.1,
        }
        merged.update(self.settings)
        return merged


STATE = PluginState()


def main() -> int:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue

        response = handle_rpc_line(line)
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    return 0


def handle_rpc_line(line: str) -> dict[str, Any]:
    request_id = "unknown"
    try:
        payload = json.loads(line)
        request_id = str(payload.get("id", "unknown"))
        method = payload.get("method")
        params = payload.get("params") or {}
        result = dispatch(method, params)
        return {"id": request_id, "ok": True, "result": result}
    except Exception as exc:  # pragma: no cover - runtime surface
        return {
            "id": request_id,
            "ok": False,
            "error": {
                "code": "plugin_error",
                "message": str(exc),
            },
        }


def dispatch(method: str, params: dict[str, Any]) -> Any:
    if method == "plugin.handshake":
        return handshake()
    if method == "plugin.configure":
        return configure(params)
    if method == "plugin.handle_event":
        return handle_event(params)
    if method == "plugin.get_prompt_contributions":
        return get_prompt_contributions(params)
    if method == "plugin.invoke_tool":
        return invoke_tool(params)
    raise ValueError(f"unknown method: {method}")


def handshake() -> dict[str, Any]:
    tool_schema = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text to synthesize.",
            },
            "voice_description": {
                "type": "string",
                "description": "Optional VoiceDesign prompt override.",
            },
            "language": {
                "type": "string",
                "description": "Optional language override.",
            },
            "seed": {
                "type": "integer",
                "description": "Optional deterministic seed override.",
            },
        },
        "required": ["text"],
    }
    return {
        "id": "voice-orb",
        "name": "Voice-Orb",
        "version": __version__,
        "capabilities": {
            "tools": ["voice_orb_speak", "voice_orb_preview"],
            "event_hooks": ["persona_evolved", "settings_changed"],
            "prompt_slots": [
                "engaged.instructions",
                "persona_evolution.considerations",
            ],
        },
        "tools": [
            {
                "name": "voice_orb_speak",
                "description": (
                    "Generate speech using Qwen3-TTS VoiceDesign from text "
                    "and a natural-language voice description. "
                    "The generated audio is automatically published to chat — "
                    "do NOT call publish_media_to_chat afterward."
                ),
                "parameters": tool_schema,
                "requires_approval": False,
                "category": "general",
            },
            {
                "name": "voice_orb_preview",
                "description": (
                    "Generate a short preview clip using the current or supplied "
                    "VoiceDesign voice description. "
                    "The generated audio is automatically published to chat — "
                    "do NOT call publish_media_to_chat afterward."
                ),
                "parameters": tool_schema,
                "requires_approval": False,
                "category": "general",
            },
        ],
    }


def configure(params: dict[str, Any]) -> dict[str, Any]:
    settings = params.get("settings")
    if settings is None:
        settings = {}
    if not isinstance(settings, dict):
        raise ValueError("plugin.configure expects an object settings payload")
    unload_loaded_model()
    STATE.settings = dict(settings)
    return {"configured": True}


def handle_event(params: dict[str, Any]) -> dict[str, Any]:
    event_name = params.get("event")
    if event_name == "persona_evolved" and STATE.merged_settings().get("allow_persona_drift", True):
        description = str(params.get("current_self_description") or "").strip()
        if description:
            STATE.persona_hint = truncate_text(description, 160)
            return {
                "state_changed": True,
                "summary": "Updated voice drift hint from persona evolution.",
            }
    if event_name == "settings_changed":
        return {"state_changed": False, "summary": "Voice-Orb settings reloaded."}
    return {"state_changed": False}


def get_prompt_contributions(params: dict[str, Any]) -> dict[str, Any]:
    slot = params.get("slot")
    contributions: list[dict[str, Any]] = []
    settings = STATE.merged_settings()

    if (
        (slot == "engaged_instructions" or slot == "engaged.instructions")
        and settings.get("auto_speak_replies")
    ):
        text = (
            "If audible speech would help, you may call `voice_orb_speak` "
            "to synthesize your reply using the current voice design."
        )
        text += " Auto-speak is enabled, so speaking finalized replies is allowed when appropriate."
        contributions.append(
            {
                "plugin_id": "voice-orb",
                "slot": "engaged_instructions",
                "kind": "instruction",
                "text": text,
                "priority": 40,
                "max_chars": 260,
            }
        )
    elif slot == "persona_evolution_considerations" or slot == "persona_evolution.considerations":
        if settings.get("allow_persona_drift"):
            contributions.append(
                {
                    "plugin_id": "voice-orb",
                    "slot": "persona_evolution_considerations",
                    "kind": "context",
                    "text": (
                        "Persona changes may justify subtle voice shifts in warmth, "
                        "pace, tension, or confidence. Keep changes gradual."
                    ),
                    "priority": 50,
                    "max_chars": 220,
                }
            )
    return {"contributions": contributions}


def invoke_tool(params: dict[str, Any]) -> dict[str, Any]:
    tool_name = params.get("tool")
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise ValueError("plugin.invoke_tool arguments must be an object")

    if tool_name == "voice_orb_ensure_model":
        return ensure_model_status(arguments)

    if tool_name == "voice_orb_preview":
        arguments = dict(arguments)
        if not arguments.get("text"):
            arguments["text"] = "This is a short voice preview."
        return synthesize(arguments, preview=True)

    if tool_name == "voice_orb_speak":
        return synthesize(arguments, preview=False)

    raise ValueError(f"unknown tool: {tool_name}")


def ensure_model_status(arguments: dict[str, Any]) -> dict[str, Any]:
    preload = coerce_bool(arguments.get("preload"), False)
    configured_model_ref = current_configured_model_ref()
    already_loaded = is_model_loaded_for_ref(configured_model_ref)

    if preload and not already_loaded:
        model = load_model()
        runtime_device, runtime_dtype = resolve_runtime_backend(model)
        return {
            "kind": "json",
            "data": {
                "status": "ok",
                "action": "preloaded",
                "model_ref": STATE.loaded_model_ref,
                "model_loaded": model is not None,
                "runtime_device": runtime_device,
                "runtime_dtype": runtime_dtype,
                **runtime_status_fields(),
            },
        }

    model = STATE.loaded_model
    runtime_device, runtime_dtype = resolve_runtime_backend(model)
    return {
        "kind": "json",
        "data": {
            "status": "ok",
            "action": "status_only",
            "model_ref": STATE.loaded_model_ref,
            "configured_model_ref": configured_model_ref,
            "model_loaded": model is not None,
            "already_loaded": already_loaded,
            "runtime_device": runtime_device,
            "runtime_dtype": runtime_dtype,
            **runtime_status_fields(),
        },
    }


def synthesize(arguments: dict[str, Any], preview: bool) -> dict[str, Any]:
    text = str(arguments.get("text") or "").strip()
    if not text:
        raise ValueError("text is required")

    settings = STATE.merged_settings()
    configured_model_ref = current_configured_model_ref()
    already_loaded_before_call = is_model_loaded_for_ref(configured_model_ref)
    text, input_was_truncated = bound_input_text(text, settings)
    rss_before_mb = current_rss_mb()
    max_rss_mb = resolve_max_rss_mb(settings)
    if rss_before_mb is not None and rss_before_mb >= max_rss_mb:
        unload_loaded_model()
        raise RuntimeError(
            f"Voice-Orb refused synthesis because process RSS is already high "
            f"({rss_before_mb:.0f}MB >= budget {max_rss_mb:.0f}MB)."
        )
    soundfile_module = ensure_soundfile()
    voice_description = str(
        arguments.get("voice_description")
        or build_effective_voice_description(settings)
    ).strip()
    language = str(arguments.get("language") or settings.get("language") or "Auto").strip()
    seed_value = arguments.get("seed")

    model = load_model()
    runtime_device, runtime_dtype = resolve_runtime_backend(model)
    should_unload_after_synthesis = bool(settings.get("unload_after_synthesis", False))

    generation_kwargs: dict[str, Any] = {
        "max_new_tokens": resolve_max_new_tokens(settings, preview),
        "top_p": float(settings.get("top_p", 0.9)),
        "top_k": int(settings.get("top_k", 50)),
        "temperature": float(settings.get("temperature", 0.7)),
        "repetition_penalty": float(settings.get("repetition_penalty", 1.1)),
    }
    if seed_value is not None:
        generation_kwargs["seed"] = int(seed_value)

    wavs = None
    sample_rate = None
    output_path = None
    output_name = None
    rss_after_mb = None
    budget_exceeded = False
    try:
        try:
            wavs, sample_rate = generate_voice_design(
                model=model,
                text=text,
                language=language,
                voice_description=voice_description,
                generation_kwargs=generation_kwargs,
            )
        except RuntimeError as exc:
            # Some environments can resolve a partially materialized model (meta tensors).
            # Retry once with an explicit safe fallback load strategy.
            if "meta tensor" not in str(exc).lower():
                raise
            if not should_allow_cpu_fallback(settings):
                raise RuntimeError(
                    "Voice-Orb generation hit a meta-tensor failure. "
                    "CPU fallback is disabled to avoid large host-RAM spikes. "
                    "Try setting device='mps' with dtype='float16' or enable allow_cpu_fallback explicitly."
                ) from exc
            print("Voice-Orb: meta-tensor generation failed; retrying on CPU fallback.", file=sys.stderr)
            unload_loaded_model()
            model = load_model(force_fallback=True)
            runtime_device, runtime_dtype = resolve_runtime_backend(model)
            wavs, sample_rate = generate_voice_design(
                model=model,
                text=text,
                language=language,
                voice_description=voice_description,
                generation_kwargs=generation_kwargs,
            )

        audio = normalize_audio_payload(wavs[0])
        output_dir = ensure_directory(
            resolve_repo_path(str(settings.get("output_dir") or "./data/output"))
        )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        suffix = "preview" if preview else "speak"
        output_name = f"voice_orb_{suffix}_{stamp}.wav"
        output_path = output_dir / output_name
        soundfile_module.write(output_path, audio, sample_rate)
        rss_after_mb = current_rss_mb()
        budget_exceeded = rss_after_mb is not None and rss_after_mb >= max_rss_mb
        return {
            "kind": "json",
            "data": {
                "status": "ok",
                "tool": "voice_orb_preview" if preview else "voice_orb_speak",
                "model_ref": STATE.loaded_model_ref,
                "configured_model_ref": configured_model_ref,
                "sample_rate": sample_rate,
                "voice_description": voice_description,
                "path": str(output_path),
                "runtime_device": runtime_device,
                "runtime_dtype": runtime_dtype,
                "max_new_tokens": generation_kwargs["max_new_tokens"],
                "input_chars": len(text),
                "input_was_truncated": input_was_truncated,
                "already_loaded_before_call": already_loaded_before_call,
                "rss_before_mb": rss_before_mb,
                "rss_after_mb": rss_after_mb,
                "max_rss_mb": max_rss_mb,
                "budget_exceeded": budget_exceeded,
                **runtime_status_fields(),
                "media": [
                    {
                        "filename": output_name,
                        "path": str(output_path),
                        "media_kind": "audio",
                        "mime_type": "audio/wav",
                        "source": "voice-orb",
                    }
                ],
            },
        }
    finally:
        wavs = None
        if should_unload_after_synthesis or budget_exceeded:
            unload_loaded_model()
        else:
            cleanup_inference_memory(model)


def load_model(force_fallback: bool = False) -> Any:
    settings = STATE.merged_settings()
    model_ref = str(settings.get("model_ref") or "").strip()
    if not model_ref:
        raise ValueError("model_ref is required")
    torch_module, model_class = ensure_qwen_runtime()

    if (
        not force_fallback
        and STATE.loaded_model is not None
        and STATE.loaded_model_ref == model_ref
    ):
        return STATE.loaded_model
    if STATE.loaded_model is not None:
        unload_loaded_model()

    cache_dir = ensure_directory(resolve_repo_path(str(settings.get("cache_dir") or "./data/models")))
    os.environ["HF_HOME"] = str(cache_dir)
    os.environ["HF_HUB_CACHE"] = str(cache_dir)
    os.environ["TRANSFORMERS_CACHE"] = str(cache_dir)

    kwargs = build_model_load_kwargs(settings, torch_module, force_fallback=force_fallback)

    model_source = resolve_model_source(model_ref)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            loaded_model = model_class.from_pretrained(model_source, **kwargs)
    except RuntimeError as exc:
        if "meta tensor" not in str(exc).lower() or force_fallback:
            raise
        if not should_allow_cpu_fallback(settings):
            raise RuntimeError(
                "Voice-Orb model load hit meta tensors and CPU fallback is disabled. "
                "Set dtype='float16' on MPS or enable allow_cpu_fallback explicitly."
            ) from exc
        print("Voice-Orb: meta-tensor load failure; retrying on CPU fallback.", file=sys.stderr)
        return load_model(force_fallback=True)

    if model_has_meta_tensors(loaded_model):
        if force_fallback:
            raise RuntimeError(
                "Voice-Orb model resolved with meta tensors even in fallback mode. "
                "Try CPU + float32, reinstall dependencies, or clear model cache."
            )
        if not should_allow_cpu_fallback(settings):
            raise RuntimeError(
                "Voice-Orb model resolved with meta tensors and CPU fallback is disabled. "
                "Try dtype='float16' on MPS or enable allow_cpu_fallback explicitly."
            )
        print("Voice-Orb: model loaded with meta tensors; retrying on CPU fallback.", file=sys.stderr)
        return load_model(force_fallback=True)

    STATE.loaded_model = loaded_model
    STATE.loaded_model_ref = model_ref
    STATE.model_load_count += 1
    STATE.last_loaded_utc = datetime.now(timezone.utc).isoformat()
    return STATE.loaded_model


def resolve_max_new_tokens(settings: dict[str, Any], preview: bool) -> int:
    raw_max = parse_int(settings.get("max_new_tokens"), DEFAULT_MAX_NEW_TOKENS)
    bounded = max(MIN_MAX_NEW_TOKENS, min(raw_max, MAX_MAX_NEW_TOKENS))
    if preview:
        return min(bounded, PREVIEW_MAX_NEW_TOKENS)
    return bounded


def parse_int(value: Any, default_value: int) -> int:
    try:
        return int(value)
    except Exception:
        return default_value


def parse_float(value: Any, default_value: float) -> float:
    try:
        return float(value)
    except Exception:
        return default_value


def coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def current_rss_mb() -> float | None:
    try:
        output = subprocess.check_output(
            ["ps", "-o", "rss=", "-p", str(os.getpid())],
            text=True,
        ).strip()
        if not output:
            return None
        # `ps rss` reports KiB on macOS and Linux.
        return max(0.0, int(output) / 1024.0)
    except Exception:
        return None


def resolve_max_rss_mb(settings: dict[str, Any]) -> float:
    configured = parse_float(settings.get("max_rss_mb"), DEFAULT_MAX_RSS_MB)
    return max(2_000.0, min(configured, 131_072.0))


def current_configured_model_ref() -> str:
    settings = STATE.merged_settings()
    return str(settings.get("model_ref") or "").strip()


def is_model_loaded_for_ref(model_ref: str) -> bool:
    return (
        STATE.loaded_model is not None
        and STATE.loaded_model_ref is not None
        and STATE.loaded_model_ref == model_ref
    )


def runtime_status_fields() -> dict[str, Any]:
    return {
        "pid": os.getpid(),
        "instance_id": STATE.instance_id,
        "plugin_started_at_utc": STATE.startup_utc,
        "model_load_count": STATE.model_load_count,
        "last_loaded_at_utc": STATE.last_loaded_utc,
        "rss_mb": current_rss_mb(),
    }


def should_allow_cpu_fallback(settings: dict[str, Any]) -> bool:
    return coerce_bool(settings.get("allow_cpu_fallback"), False)


def bound_input_text(text: str, settings: dict[str, Any]) -> tuple[str, bool]:
    limit = parse_int(settings.get("max_input_chars"), DEFAULT_MAX_INPUT_CHARS)
    safe_limit = max(120, min(limit, 12_000))
    if len(text) <= safe_limit:
        return text, False
    return text[:safe_limit].rstrip(), True


def generate_voice_design(
    model: Any,
    text: str,
    language: str,
    voice_description: str,
    generation_kwargs: dict[str, Any],
) -> tuple[Any, Any]:
    torch_module = STATE.torch_module
    inference_mode = getattr(torch_module, "inference_mode", None) if torch_module else None
    if callable(inference_mode):
        with inference_mode():
            return model.generate_voice_design(
                text=text,
                language=language,
                instruct=voice_description,
                **generation_kwargs,
            )
    return model.generate_voice_design(
        text=text,
        language=language,
        instruct=voice_description,
        **generation_kwargs,
    )


def resolve_runtime_backend(model: Any) -> tuple[str, str]:
    for candidate in iter_candidate_modules(model):
        parameters = getattr(candidate, "parameters", None)
        if not callable(parameters):
            continue
        try:
            first_parameter = next(parameters())
            device = getattr(first_parameter, "device", None)
            dtype = getattr(first_parameter, "dtype", None)
            device_name = str(device) if device is not None else "unknown"
            dtype_name = str(dtype) if dtype is not None else "unknown"
            return device_name, dtype_name
        except StopIteration:
            continue
        except Exception:
            continue
    return "unknown", "unknown"


def normalize_audio_payload(audio: Any) -> Any:
    if hasattr(audio, "detach"):
        try:
            tensor = audio.detach()
            if hasattr(tensor, "float"):
                tensor = tensor.float()
            if hasattr(tensor, "cpu"):
                tensor = tensor.cpu()
            if hasattr(tensor, "numpy"):
                return tensor.numpy()
            return tensor
        except Exception:
            return audio
    return audio


def cleanup_inference_memory(model: Any) -> None:
    for candidate in iter_candidate_modules(model):
        for method_name in ("clear_kv_cache", "clear_cache", "reset_cache"):
            method = getattr(candidate, method_name, None)
            if callable(method):
                try:
                    method()
                except Exception:
                    pass
    release_torch_memory()


def unload_loaded_model() -> None:
    model = STATE.loaded_model
    STATE.loaded_model = None
    STATE.loaded_model_ref = None
    if model is None:
        return

    del model
    release_torch_memory()


def release_torch_memory() -> None:
    torch_module = STATE.torch_module
    if torch_module is None:
        gc.collect()
        return

    try:
        if torch_module.cuda.is_available():
            torch_module.cuda.empty_cache()
            if hasattr(torch_module.cuda, "ipc_collect"):
                torch_module.cuda.ipc_collect()
    except Exception:
        pass

    try:
        mps_module = getattr(torch_module, "mps", None)
        if mps_module is not None and hasattr(mps_module, "empty_cache"):
            mps_module.empty_cache()
    except Exception:
        pass

    gc.collect()


def ensure_qwen_runtime() -> tuple[Any, Any]:
    if STATE.torch_module is not None and STATE.model_class is not None:
        return STATE.torch_module, STATE.model_class

    try:
        with contextlib.redirect_stdout(sys.stderr):
            import torch as torch_module
    except ImportError as exc:  # pragma: no cover - optional until installed
        raise RuntimeError(
            "torch is not installed. Run ./scripts/install_portable.sh inside the Voice-Orb repo."
        ) from exc

    try:
        with contextlib.redirect_stdout(sys.stderr):
            from qwen_tts import Qwen3TTSModel as model_class
    except ImportError as exc:  # pragma: no cover - optional until installed
        raise RuntimeError(
            "qwen-tts is not installed. Run ./scripts/install_portable.sh inside the Voice-Orb repo."
        ) from exc

    STATE.torch_module = torch_module
    STATE.model_class = model_class
    return torch_module, model_class


def build_model_load_kwargs(
    settings: dict[str, Any], torch_module: Any, force_fallback: bool
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}

    if force_fallback:
        kwargs["device_map"] = {"": "cpu"}
        kwargs["dtype"] = torch_module.float32
        kwargs["attn_implementation"] = "eager"
        kwargs["low_cpu_mem_usage"] = False
        return kwargs

    device_target = resolve_effective_device(settings, torch_module)
    kwargs["device_map"] = {"": device_target}
    kwargs["low_cpu_mem_usage"] = False

    dtype_name = str(settings.get("dtype") or "auto").strip().lower()
    if dtype_name != "auto":
        dtype_map = {
            "bfloat16": torch_module.bfloat16,
            "float16": torch_module.float16,
            "float32": torch_module.float32,
        }
        kwargs["dtype"] = dtype_map.get(dtype_name, torch_module.float32)
    elif device_target == "cpu":
        kwargs["dtype"] = torch_module.float32
    elif device_target == "mps":
        kwargs["dtype"] = torch_module.float16

    attention_impl = str(settings.get("attention_impl") or "auto").strip()
    if attention_impl and attention_impl != "auto":
        kwargs["attn_implementation"] = attention_impl

    return kwargs


def resolve_effective_device(settings: dict[str, Any], torch_module: Any) -> str:
    configured = str(settings.get("device") or "auto").strip().lower()
    if configured and configured != "auto":
        if configured == "cuda":
            return "cuda:0"
        return configured

    if torch_module.cuda.is_available():
        return "cuda:0"

    mps_backend = getattr(getattr(torch_module, "backends", None), "mps", None)
    if mps_backend is not None and mps_backend.is_available():
        return "mps"

    return "cpu"


def model_has_meta_tensors(model: Any) -> bool:
    for candidate in iter_candidate_modules(model):
        parameters = getattr(candidate, "parameters", None)
        if not callable(parameters):
            continue
        try:
            for parameter in parameters():
                device = getattr(parameter, "device", None)
                if getattr(device, "type", None) == "meta":
                    return True
        except Exception:
            continue
    return False


def iter_candidate_modules(model: Any) -> list[Any]:
    candidates: list[Any] = [model]
    for attribute in ("model", "tts_model", "inner_model"):
        nested = getattr(model, attribute, None)
        if nested is not None:
            candidates.append(nested)
    return candidates


def ensure_soundfile() -> Any:
    if STATE.soundfile_module is not None:
        return STATE.soundfile_module

    try:
        with contextlib.redirect_stdout(sys.stderr):
            import soundfile as soundfile_module
    except ImportError as exc:  # pragma: no cover - optional until installed
        raise RuntimeError(
            "soundfile is not installed. Run ./scripts/install_portable.sh inside the Voice-Orb repo."
        ) from exc

    STATE.soundfile_module = soundfile_module
    return soundfile_module


def build_effective_voice_description(settings: dict[str, Any]) -> str:
    base = str(settings.get("default_voice_description") or "").strip()
    if not STATE.persona_hint or not settings.get("allow_persona_drift"):
        return base
    if not base:
        return STATE.persona_hint
    return f"{base} Subtle current persona influence: {STATE.persona_hint}."


def resolve_model_source(model_ref: str) -> str:
    candidate = resolve_repo_path(model_ref)
    if candidate.exists():
        return str(candidate)
    return model_ref


def resolve_repo_path(raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return REPO_ROOT / candidate


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


if __name__ == "__main__":
    raise SystemExit(main())
