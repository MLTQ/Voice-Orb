# run_plugin.sh

## Purpose
Launches the `Voice-Orb` JSON-RPC server from the plugin-local virtual environment.

## Components

### `run_plugin.sh`
- **Does**: Verifies that `.venv` exists, enables unbuffered Python I/O, disables user-site package injection, and executes `python -m voice_orb.server`.
- **Interacts with**: `plugin.toml` and `voice_orb/server.py`.

## Contracts

| Dependent | Expects | Breaking changes |
|-----------|---------|------------------|
| `plugin.toml` | This script is the plugin entrypoint command | Renaming or moving the script |
| Ponderer runtime host | The server uses stdio and writes one JSON response per line | Switching to a different transport |
