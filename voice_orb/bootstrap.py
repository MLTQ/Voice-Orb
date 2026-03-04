import argparse
import os
import sys

from voice_orb import server

DEFAULT_TOKENIZER_REF = "Qwen/Qwen3-TTS-Tokenizer-12Hz"


def main() -> int:
    parser = argparse.ArgumentParser(description="Voice-Orb bootstrap helper")
    parser.add_argument(
        "--prefetch-hf-assets",
        action="store_true",
        help="Download the configured tokenizer and model into the local Hugging Face cache.",
    )
    parser.add_argument(
        "--download-model",
        action="store_true",
        help="Load and cache the configured model locally.",
    )
    args = parser.parse_args()

    settings = {}
    if model_ref := os.environ.get("VOICE_ORB_MODEL_REF", "").strip():
        settings["model_ref"] = model_ref
    if cache_dir := os.environ.get("VOICE_ORB_CACHE_DIR", "").strip():
        settings["cache_dir"] = cache_dir
    if output_dir := os.environ.get("VOICE_ORB_OUTPUT_DIR", "").strip():
        settings["output_dir"] = output_dir
    if device := os.environ.get("VOICE_ORB_DEVICE", "").strip():
        settings["device"] = device
    if dtype := os.environ.get("VOICE_ORB_DTYPE", "").strip():
        settings["dtype"] = dtype
    if attention := os.environ.get("VOICE_ORB_ATTENTION_IMPL", "").strip():
        settings["attention_impl"] = attention

    if settings:
        server.configure({"settings": settings})

    if args.prefetch_hf_assets:
        prefetch_hf_assets(
            model_ref=settings.get("model_ref"),
            cache_dir=settings.get("cache_dir"),
        )

    if args.download_model:
        server.load_model()

    return 0


def prefetch_hf_assets(model_ref: str | None, cache_dir: str | None) -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError(
            "huggingface_hub is not installed. Run ./scripts/install_portable.sh inside the Voice-Orb repo."
        ) from exc

    effective_model_ref = (model_ref or "").strip() or "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
    effective_cache_dir = cache_dir or "./data/models"
    resolved_cache_dir = server.ensure_directory(
        server.resolve_repo_path(str(effective_cache_dir))
    )
    tokenizer_ref = os.environ.get("VOICE_ORB_TOKENIZER_REF", "").strip() or DEFAULT_TOKENIZER_REF

    print(
        f"Prefetching Voice-Orb tokenizer ({tokenizer_ref}) into {resolved_cache_dir}...",
        file=sys.stderr,
    )
    snapshot_download(repo_id=tokenizer_ref, cache_dir=str(resolved_cache_dir))

    print(
        f"Prefetching Voice-Orb model ({effective_model_ref}) into {resolved_cache_dir}...",
        file=sys.stderr,
    )
    snapshot_download(repo_id=effective_model_ref, cache_dir=str(resolved_cache_dir))


if __name__ == "__main__":
    raise SystemExit(main())
