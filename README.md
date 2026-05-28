# Papa — Local AI Wallet Orchestration Platform

Papa is a local-first wallet orchestration platform that combines secure wallet generation/export with an AI command interface powered by Ollama.

## Key Features

- Local Ollama integration (default model: `qwen2.5:3b`)
- Natural-language tool calling with strict JSON action parsing
- Safe tool router (tool registry, validation, dry-run, confirmation checks)
- AES-GCM encrypted private key storage with password-based key derivation
- Legacy plaintext migration to encrypted storage
- Modern CLI with Typer + Rich + prompt_toolkit
- Health diagnostics via `papa doctor`
- One-command setup via `bash install.sh`

## Project Structure

```
project/
├── ai/
│   ├── llm.py
│   ├── prompts.py
│   ├── parser.py
│   ├── router.py
│   └── tools.py
├── wallet/
│   ├── generator.py
│   ├── exporter.py
│   ├── storage.py
│   └── encryption.py
├── database/
├── cli/
│   └── main.py
├── setup/
│   ├── install.sh
│   └── setup.py
└── config/
config/
logs/
```

## Installation

```bash
bash install.sh
```

Installer actions:
- detects Debian/Ubuntu/CentOS/RHEL
- installs system Python prerequisites
- installs Ollama (if missing)
- creates virtualenv and installs requirements
- pulls `qwen2.5:3b`
- initializes config, DB, logs/exports folders
- runs health check

## CLI

```bash
papa ai
papa generate --count 25
papa export --format csv
papa wallets --limit 20
papa config --show
papa doctor
```

## AI Mode

```bash
papa ai "generate 25 wallets and export csv"
```

Expected internal action format:

```json
{"tool":"generate_wallets","args":{"count":25}}
```

Only registered tools are executable. Arbitrary shell execution is blocked.

## Security Model

- AES-GCM encryption for stored private keys
- PBKDF2 password-derived encryption keys
- hidden terminal input for encryption password
- exports are encrypted by default
- plaintext private key export requires `--unsafe-export`

## Health Check (`papa doctor`)

Checks:
- Ollama installed/running
- model availability
- DB path/config/log folders
- core dependencies

## Compatibility

Legacy scripts remain available:

```bash
python wallet_gen.py --count 1000
python converter.py --format json
```

Both route into the new encrypted architecture.

## Future-ready Placeholders

Architecture is prepared for:
- RPC transaction execution
- balance checking
- nonce manager
- multi-chain expansion
- async task queue
- proxy support

## Screenshots

- _TODO: Add CLI screenshots_
- _TODO: Add AI chat mode screenshot_

## Security Warning

Never use `--unsafe-export` on shared or untrusted systems.
