# voice_note.sh

Quick wrapper for generating Telegram-friendly Qwen3-TTS voice notes from Voice-Orb.

## Basic use

```bash
./scripts/voice_note.sh "Meet me in the garden at dusk."
```

This prints the final `.ogg` path to stdout. In Hermes/Telegram, send that file with:

```text
MEDIA:/absolute/path/from/script_output.ogg
```

## Pipe text in

```bash
printf 'I can send voice notes now.' | ./scripts/voice_note.sh
```

## Override the voice

```bash
./scripts/voice_note.sh \
  --voice "Sultry, breathy, warm, intimate, and natural, with clear diction and soft pacing." \
  "Good evening, Max."
```

## Useful environment overrides

- `VOICE_ORB_DEFAULT_VOICE_DESCRIPTION`
- `VOICE_ORB_DEFAULT_LANGUAGE`
- `VOICE_ORB_MODEL_REF`
- `VOICE_ORB_DEVICE`
- `VOICE_ORB_DTYPE`
- `VOICE_ORB_ATTENTION_IMPL`
- `VOICE_ORB_MAX_NEW_TOKENS`
- `VOICE_ORB_UNLOAD_AFTER_SYNTHESIS`

## Current defaults tuned for this machine

- model: `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign`
- device: `cuda`
- dtype: `bfloat16`
- attention: `eager`
- language: `english`
- max new tokens: auto-estimated from message length, punctuation, and voice style
- unload after synthesis: `true`

## Notes

- Requires `ffmpeg`.
- Uses the local Voice-Orb cache in `data/models/`.
- Writes final voice notes to `data/output/` unless `--output` is supplied.
- If `--max-tokens` is omitted, the helper estimates a budget automatically instead of using a fixed constant.
