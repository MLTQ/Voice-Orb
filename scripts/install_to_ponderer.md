# install_to_ponderer.sh

## Purpose
Installs a development checkout of `Voice-Orb` into a Ponderer workspace by symlinking the repo into `plugins/voice-orb`.

## Components

### `install_to_ponderer.sh`
- **Does**: Creates the target `plugins/` directory if needed, updates a `voice-orb` symlink to point at the current repo, and then runs `install_portable.sh` through that installed path so the venv, dependencies, and model cache are prepared immediately.
- **Interacts with**: `plugin.toml` discovery in Ponderer and `scripts/install_portable.sh`.

## Contracts

| Dependent | Expects | Breaking changes |
|-----------|---------|------------------|
| Ponderer plugin discovery | `plugins/voice-orb/plugin.toml` is reachable after install | Changing the install target name |
| Operators | Existing real directories are never silently overwritten, and install also provisions the runtime environment in place | Removing the non-symlink safety check or the delegated portable install |

## Notes
- For a fully portable package, copying the repo directory into `plugins/voice-orb` also works; this script is mainly for local development.
- `VOICE_ORB_SKIP_MODEL_DOWNLOAD=1` still works here because `install_to_ponderer.sh` delegates to `install_portable.sh`.
