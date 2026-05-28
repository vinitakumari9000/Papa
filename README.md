# Papa — Local AI Wallet Orchestration Platform

Papa is an offline-first wallet orchestration platform with a natural-language CLI, safe tool routing, and local LLM integration through Ollama (`qwen2.5:3b` default).

## Highlights

- Local AI command mode (`papa ai`) with strict tool-call JSON parsing
- Safe execution router (registered tools only, no shell execution from LLM)
- AES-GCM encrypted wallet storage (password-based)
- Legacy compatibility preserved (`wallet_gen.py`, `converter.py`, `papa.py`)
- Modern CLI commands: `generate`, `export`, `wallets`, `config`, `doctor`, plus legacy tx commands
- Rotating logs: `logs/ai.log`, `logs/wallet.log`, `logs/export.log`, `logs/errors.log`

## Installation

```bash
chmod +x install.sh
./install.sh
source .venv/bin/activate
```

Installer actions:

- Detect OS (Ubuntu/Debian/CentOS and compatible)
- Create virtualenv + install Python dependencies
- Initialize config/database/log directories
- Install Ollama when possible
- Pull model `qwen2.5:3b`
- Run initial `papa doctor`

## Command Reference

```bash
python papa.py generate --count 25
python papa.py export --format csv --output exports/wallets.csv
python papa.py wallets --limit 20
python papa.py config show
python papa.py doctor
python papa.py ai
```

Legacy compatibility remains:

```bash
python wallet_gen.py --count 1000
python converter.py --format json
```

## AI Mode

Start interactive assistant:

```bash
python papa.py ai
```

Example request:

`generate 25 wallets and export csv`

Expected structured action:

```json
{
  "tool": "generate_wallets",
  "args": {"count": 25, "export": "csv"}
}
```

## Security Model

- Wallet secrets are encrypted at rest with AES-GCM when using `papa generate` (default encrypted mode)
- Plaintext private key export is blocked unless `--unsafe-export` is explicitly provided
- Tool router executes only registered internal handlers
- No arbitrary shell/SQL/filesystem delete operations from AI output

## Configuration

Primary config: `config/config.yaml`

Includes:

- default chain + RPCs
- Ollama host/model
- DB path
- encryption settings
- export defaults
- logging settings

Environment overrides:

- `PAPA_DB_PATH`
- `PAPA_OLLAMA_HOST`
- `PAPA_OLLAMA_MODEL`

## Health Checks

`python papa.py doctor` validates:

- Ollama installation/running/model presence
- Database connectivity
- Config/folder readiness
- Python dependency availability

## Architecture

```text
project/
  ai/
    llm.py
    prompts.py
    parser.py
    router.py
    tools.py
  wallet/
    generator.py
    exporter.py
    storage.py
    encryption.py
  database/
    manager.py
  cli/
    main.py
  setup/
    install.sh
    setup.py
```

## Migration Notes

- Existing `wallets` table schema remains unchanged for compatibility.
- Use `python papa.py generate --migrate-plaintext` to encrypt existing plaintext keys in-place after confirming password.

## Screenshots

- _CLI screenshots placeholder_
- _AI mode walkthrough placeholder_
