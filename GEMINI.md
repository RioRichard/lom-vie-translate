# GEMINI.md — Legend of Mortal Vietnamese Translator (`lom-vie-translate`)

## Project Overview

`lom-vie-translate` is a Python 3.12 asynchronous localization tool for translating game text for ***Legend of Mortal*** from **Chinese (Simplified)** (`ChineseSimplified`) to **Vietnamese**, preserving wuxia/historical tone, consistent terminology, and in-game markup/placeholders.

### Key Technologies & Tooling

- **Python**: `3.12` (`requires-python = ">=3.11,<3.14"`, pinned in `.python-version = 3.12`).
- **Environment & Packaging**: Managed strictly via **`uv`** + `pyproject.toml` (`hatchling` build backend, `packages = ["src", "tool"]`, committed `uv.lock`) into the project-local `.venv`.
- **Runtime Dependencies**: `litellm>=1.60.0`, `pydantic>=2.0.0`, `python-dotenv>=1.0.0`, `aiofiles>=24.1.0`, `tqdm>=4.66.0`.
- **Development Dependencies** (`dev` dependency group): `pytest>=8.0.0`, `pytest-asyncio>=0.24.0`, `ruff>=0.8.0`.
- **Installed Console Scripts** (inside `.venv/bin/`):
  - `.venv/bin/lom-translate` -> `src.main:main`
  - `.venv/bin/lom-improve-glossary` -> `tool.improve_glossary:main_cli`
  - `.venv/bin/lom-unpack-game` -> `tool.unpack_game:main_cli`
  - `.venv/bin/lom-patch-game` -> `tool.patch_game:main_cli`
  - `.venv/bin/lom-build-flowchart` -> `tool.build_story_flowchart:main_cli`
  - `.venv/bin/lom-build-matrix` -> `tool.build_relationship_matrix:main_cli`
  - Also runnable via `.venv/bin/python -m src.main`, `.venv/bin/python -m tool.<script>`, or `uv run ...`.
- **Removed Legacy Files**: `build.py`, `GameTextTranslator.spec`, `config.cfg`, and `requirements.txt` have been permanently removed in favor of `uv` + `pyproject.toml` + `config.toml`.

---

## Strict Project Rules (Non-Negotiable)

Every developer and AI agent working in this repository MUST follow these rules without exception:

1. **Strict `.venv` Execution**:
   - ALWAYS run Python, `pytest`, `ruff`, and console scripts via `.venv/bin/...` or `uv run ...`.
   - NEVER invoke system `python`, `python3`, or `pip` directly.
2. **Secrets & Config Hygiene**:
   - API keys live **ONLY** in `.env` (gitignored).
   - `config.toml` stores only environment variable **names** (`api_key_env`), never plaintext secrets, and MUST remain gitignored.
   - Only `config.toml.template` and `.env.template` may be committed to version control.
   - Never log raw API keys (use safe masking via `logger.api_call`).
3. **Test & Lint Gate**:
   - Both `.venv/bin/ruff check .` and `.venv/bin/pytest` MUST pass after every code change.
   - Ruff rules: `target-version = "py312"`, `line-length = 100`, `select = ["E", "F", "I", "UP", "B"]`, `ignore = ["E501"]`.
4. **Documentation Sync**:
   - Any change to CLI flags, TOML/env config schema, `tool/` scripts, or core architecture MUST update **both** `GEMINI.md` and `README.md` in the same change.
5. **Game-Text Integrity**:
   - Always pass explicit `encoding="utf-8"` when reading/writing files and `ensure_ascii=False` when serializing JSON.
   - Preserve all *Legend of Mortal* markup and formatting markers verbatim: `[|]`, `[||]`, `{{0:N0}}`, `{0:N0}`, `{title}`, `{{title}}`, `[{0}]`, `[{{0}}]`, `???`, `？？？`, `……。`, `……！`, etc.
6. **Git Hygiene**:
   - Use Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
   - Never commit `.env`, `config.toml`, `logs/`, local test paths, backup files (`*.bak`), or generated/resource directories (`translated_output/`, `improved_output/`, `translated_output_json/`, `patch_output/`, `Resource/`, `testcase/`, `old_code/`). Keep `uv.lock` committed.

---

## Repository Structure & Module Map

```text
.
├── .python-version           # Pinned Python 3.12
├── pyproject.toml            # uv/hatchling metadata, dependencies, console scripts, pytest & ruff config
├── uv.lock                   # Locked dependency graph (committed)
├── .env.template             # Template for provider/tier API keys & optional LOM_CONFIG_FILE
├── config.toml.template      # Template for [run], [providers.*], and [tasks.*] routing
├── .gitignore                # Ignores .venv, .env, config.toml, logs/, outputs, Resource/
├── GEMINI.md                 # Authoritative engineering rules, architecture & roadmap (this file)
├── README.md                 # User-facing setup, config, CLI, and tool documentation
├── src/
│   ├── __init__.py
│   ├── config.py             # Pydantic v2 config models, tomllib loader, route validation & resolution (zero import side effects)
│   ├── translator.py         # Async LiteLLM TranslationEngine, KeyPool round-robin rotation, per-tier _TierLimiter, fallback/retry loop
│   ├── file_processor.py     # Entry & per-file async processing, context-safe caching, flowchart script ordering + sliding dialogue window
│   ├── prompt_preparer.py    # Per-file prompt builder with raw-translation preprocessing, glossary, flowchart & pronoun-rule injection
│   ├── glossary.py           # Sync/async glossary & old-translation loaders (JSON list, JSON dict, TXT), longest-match term search
│   ├── unity_assets.py       # Unity 2020.3.49f1 (v22) SerializedFile & LeanLanguageCSV parser/repacker (extract, patch, install, restore)
│   ├── story_flowchart.py    # Lua story script parser, character info & StoryFlowchart sliding dialogue context graph
│   ├── relationship_matrix.py# Wuxia Vietnamese xưng hô (PronounRule) resolver across story scripts & relationship stages
│   ├── utils.py              # preprocess_text, postprocess_text, SPECIAL_CHARS, parse_json_entries, shared & context-aware prompt builders
│   ├── logger.py             # TranslationLogger singleton, lazy file logging (enable_file_logging), safe key masking, run summary
│   └── main.py               # CLI entry point (lom-translate), TOML+CLI merge, async producer-consumer file pipeline, output writers
├── tool/
│   ├── __init__.py
│   ├── unpack_game.py                # Zero-UABEA unpacker: extract LeanLocal JSONs + story_flowchart.json + relationship_matrix.json
│   ├── patch_game.py                 # Zero-UABEA patcher: build standalone patch/zip, install with .bak backup, or restore
│   ├── build_story_flowchart.py      # Standalone CLI to build story_flowchart.json from Mortal_Data
│   ├── build_relationship_matrix.py  # Standalone CLI to build relationship_matrix.json from story_flowchart.json
│   ├── create_glossary.py            # Aggregate original + translated JSON folders into JSON & TXT glossaries
│   ├── filter_entries_by_category.py # Categorize JSON files into Story / LegendInfo / Other by entry Name
│   ├── filter_languages.py           # Split JSON files into per-Language subdirectories
│   ├── convert_translation_details.py# Convert legacy dict translation_details.json to list format
│   ├── translation_mapper.py         # Map input entries to raw text and matching glossary terms (stdout)
│   └── improve_glossary.py           # Refine glossary entries via LLM task `improve_glossary` (lom-improve-glossary)
└── tests/                    # pytest + pytest-asyncio automated test suite (config, utils, glossary, engine, pipeline, unity assets, flowchart, matrix, tools)
```

---

## Multi-Provider TOML Configuration (`Provider -> Tier & Model -> Task`)

All runtime behavior is configured in a single `config.toml` (copied from `config.toml.template`), parsed via Python's stdlib `tomllib` and validated by Pydantic v2 in `src/config.py`.

- **Zero import side effects**: Importing `src.config` never calls `load_dotenv()` or reads files from disk.
- **Config lookup order** in `load_config(config_path=None, load_env=True)`:
  1. Explicit `-c` / `--config-file` CLI argument (or `config_path` argument)
  2. `LOM_CONFIG_FILE` environment variable (in `.env` or shell)
  3. Default `./config.toml` (raises a clear `FileNotFoundError` pointing to `config.toml.template` if missing)

### Schema Overview

1. **`[run]`** (`RunConfig`):
   - `mode`: `"translate"` or `"improve"` (default `"translate"`)
   - `input_dir`: default `"Resource/LeanLocalJson"`
   - `output_dir`: default `"translated_output"`
   - `glossary_dir`: default `"Resource/glossary"`
   - `max_concurrent_file_opens`: int `>= 1` (default `100`)
   - `dialogue_window`: int `>= 0` (default `4`, preceding dialogue turns injected for `Story/` lines when a flowchart is loaded)
   - Optional path fields (commented in template, overridable via CLI): `raw_dir`, `json_output_dir`, `details_output_dir`, `pairs_output_dir`, `glossary_file`, `old_dir`, `old_file`, `flowchart_file`, `relationship_file`
2. **`[providers.<provider>]`** (`ProviderConfig`):
   - `api_base`: optional OpenAI-compatible base URL (e.g. `"http://localhost:1234/v1"`)
   - `timeout`: request timeout in seconds (`> 0`, default `120.0`)
   - `default_api_key`: optional fallback key (e.g. `"local-no-key"`) for keyless local servers
3. **`[providers.<provider>.tiers.<tier>]`** (`TierConfig`):
   - `api_key_env`: environment variable name in `.env` holding comma-separated API keys — enables **universal multi-key round-robin rotation across every provider and tier**
   - `max_concurrent`: max simultaneous in-flight requests for this tier (`>= 1`, default `5`)
   - `rate_limit_delay`: minimum seconds between requests on this tier (`>= 0.0`, default `0.0`)
   - `quota_cooldown`: seconds to wait between global retry cycles when all routes fail (`>= 0.0`, default `30.0`)
   - `max_retries`: optional per-route attempt cap (`>= 1`; when omitted, defaults to `max(len(api_keys), 1)`)
   - `model_suffix`: optional string appended to `model_id` (e.g. `":free"` for OpenRouter free tier)
   - `extra_headers`: optional `dict[str, str]` passed to LiteLLM
4. **`[providers.<provider>.models.<model>]`** (`ModelConfig`):
   - `model_id`: LiteLLM model identifier (e.g. `"openai/qwen3-14b"`, `"gemini/gemma-3-27b-it"`, `"openrouter/deepseek/deepseek-chat-v3-0324"`)
   - `temperature`: `0.0..2.0` (default `0.1`)
   - `max_tokens`: `>= 1` (default `1500`)
   - `timeout`: optional per-model timeout override (`> 0`)
   - `allowed_tiers`: optional `list[str]` restricting which tiers may serve this model
   - `tier_model_ids`: optional `dict[str, str]` overriding the full LiteLLM model ID for specific tiers (takes precedence over `model_id + tier.model_suffix`)
   - `extra_params`: optional `dict[str, Any]` forwarded to `litellm.acompletion`
5. **`[tasks.<task>]`** (`TaskConfig`):
   - Core tasks: `translate`, `improve`, `improve_glossary`
   - `primary = { provider = "...", tier = "...", model = "..." }` (`RouteRef`)
   - `fallbacks = [ { provider = "...", tier = "...", model = "..." }, ... ]`
   - `max_global_retries`: number of full-chain retry cycles after the initial pass (`>= 0`, default `3`)
   - Optional task-level overrides: `temperature`, `max_tokens`

### Pre-Configured Providers in `config.toml.template`

| Provider | Base URL / Backend | Tiers (`api_key_env`) | Pre-Configured Models (`model_id`) | Notes |
| --- | --- | --- | --- | --- |
| `local_openai` | `http://localhost:1234/v1` (LM Studio; also `:8080/v1` llama.cpp, `:8000/v1` vLLM) | `local` (`LOCAL_OPENAI_API_KEYS`, `max_concurrent=2`, `rate_limit_delay=0.0`, `quota_cooldown=5.0`, `max_retries=2`) | `qwen3-14b` (`openai/qwen3-14b`) | `timeout=180.0`, `default_api_key="local-no-key"` allows keyless local runs while still supporting multi-key rotation if `LOCAL_OPENAI_API_KEYS` is set |
| `gemini` | Google AI Studio via LiteLLM | `free` (`GEMINI_FREE_API_KEYS`, `max_concurrent=5`, `rate_limit_delay=2.0`, `quota_cooldown=30.0`), `paid` (`GEMINI_PAID_API_KEYS`, `max_concurrent=15`, `rate_limit_delay=0.2`, `quota_cooldown=10.0`) | `gemma-4-26b` (`gemini/gemma-4-26b-a4b-it`), `gemma-3-27b` (`gemini/gemma-3-27b-it`), `gemini-2.5-flash` (`gemini/gemini-2.5-flash`) | `timeout=60.0` |
| `openrouter` | OpenRouter via LiteLLM | `free` (`OPENROUTER_FREE_API_KEYS`, `max_concurrent=3`, `rate_limit_delay=2.0`, `quota_cooldown=30.0`, `model_suffix=":free"`), `paid` (`OPENROUTER_PAID_API_KEYS`, `max_concurrent=10`, `rate_limit_delay=0.2`, `quota_cooldown=10.0`) | `deepseek-v3` (`openrouter/deepseek/deepseek-chat-v3-0324`) | `timeout=90.0`; `free` tier resolves to `...:free` automatically |

Default task routes in `config.toml.template` are configured **local-first** (`local_openai.local.qwen3-14b`) with ordered `gemini` / `openrouter` fallbacks.

### `.env` Environment Variables

```env
# Optional: comma-separated keys for authenticated local OpenAI-compatible servers
# Leave unset/empty to use provider default_api_key ("local-no-key")
LOCAL_OPENAI_API_KEYS=

# Google Gemini (comma-separated keys for round-robin rotation per tier)
GEMINI_FREE_API_KEYS=
GEMINI_PAID_API_KEYS=

# OpenRouter (comma-separated keys for round-robin rotation per tier)
OPENROUTER_FREE_API_KEYS=
OPENROUTER_PAID_API_KEYS=

# Optional path override for config.toml
# LOM_CONFIG_FILE=config.toml
```

### Route & Key Resolution Semantics (`AppConfig`)

- **Validation**: `AppConfig`'s `@model_validator(mode="after")` validates every `RouteRef` in every task (provider exists, tier exists, model exists, tier permitted by `allowed_tiers`).
- **Model ID resolution**: `model.tier_model_ids.get(tier) or f"{model.model_id}{tier.model_suffix}"`.
- **Key resolution**:
  - `env_keys = parse_api_keys(tier.api_key_env)` (splits on commas, strips whitespace, drops blanks).
  - If `env_keys` is non-empty -> `api_keys = env_keys`, `uses_default_key = False`.
  - Else if `provider.default_api_key` is set -> `api_keys = [provider.default_api_key]`, `uses_default_key = True`.
  - Else -> `api_keys = []`, `requires_api_key = bool(tier.api_key_env)`. Unconfigured routes with `requires_api_key = True` are cleanly skipped with a warning during execution so fallback routes can proceed.
- **CLI overrides**: Passing any combination of `--provider`, `--tier`, `--model` merges unspecified fields from `task.primary`, validates the resulting `RouteRef`, and places it first ahead of non-duplicate `fallbacks`.

---

## Architecture & Data Flow

### Async Producer-Consumer Pipeline

```text
input_dir/*.json
   │
   ▼  file_producer (bounded by max_concurrent_file_opens)
   │  - Reads first 4096 bytes for fast "Language": "ChineseSimplified" check
   │  - Fast-skips if another "Language" value is found in first 4096 bytes
   │  - Falls back to full-file JSON parse if "Language" appears after byte 4096
   │  - In improve mode, also reads matching raw file from raw_dir
   ▼
asyncio.Queue
   │
   ▼  file_consumer -> process_json_file
   │  - Parses entries via parse_json_entries() (both entries.Array and direct entries list)
   │  - Builds prompt_data via prepare_prompt_data() (preprocessed raw_translation, glossary matches, StoryFlowchart + RelationshipMatrix headers)
   │  - When StoryFlowchart is active, groups mapped Story/ entries by script_id, runs each script in flowchart execution order (multiple scripts concurrently up to max_concurrent), and injects a live sliding dialogue window (prev_lines as Speaker: Original => Translated, next_lines lookahead as Speaker: Original)
   │  - Non-mapped entries run concurrently under the shared semaphore; final output preserves exact original entries_list order
   ▼
process_entry (3-Tier Context-Safe Cache/Reuse + LLM Fallback)
   │  0. Short-circuit empty text or SPECIAL_CHARS verbatim
   │  1. Glossary exact match (by stripped original text via original_to_translated)
   │  2. In-run deduplication: story-contextual entries check per-file contextual_pairs (`{Name}::{Original}`) and never collide on bare `original_text`; non-contextual entries use shared `translation_pairs` (raw unescaped text; ONLY successful translations stored)
   │  3. Old translations cache (--old-dir or --old-file, matched by stripped original text)
   │  4. TranslationEngine.translate_text(...) via litellm.acompletion (uses CONTEXT_AWARE_IMPROVE_RULE_PROMPT when both story_context and raw_translation are set)
   ▼
Outputs
   ├── <json_output_dir>/<filename>.json   (UTF-8, ensure_ascii=False, original structure preserved)
   ├── <details_output_dir>/translation_details.json  (consolidated list of {Name, Original, Raw, Translated}; Raw is null in translate mode)
   ├── <pairs_output_dir>/translation_pairs.txt       (deduplicated orig=trans with literal \r/\n escaping)
   └── logs/translation_<timestamp>.log               (lazily created only when a run starts)
```

### `TranslationEngine` (`src/translator.py`)

- Powered by `litellm.acompletion(..., num_retries=0)` with `litellm.suppress_debug_info = True` and noisy loggers (`LiteLLM`, `litellm`, `httpx`, `httpcore`) clamped to `WARNING`.
- Maintains lazy per-`(provider_name, tier_name)` state:
  - `KeyPool`: round-robin rotation across all configured keys for that `(provider, tier)`.
  - `_TierLimiter`: `asyncio.Semaphore(max_concurrent)` + monotonic lock enforcing minimum `rate_limit_delay` spacing between requests (never sleeps negative time).
- **Retry & Fallback Loop** (`range(max_global_retries + 1)`):
  1. Iterates ordered `routes` (`primary` then `fallbacks`).
  2. Skips any route where `route.requires_api_key and not route.api_keys`.
  3. Attempts up to `route.max_retries` (or `max(len(route.api_keys), 1)`) calls, rotating to the next key in `KeyPool` on each attempt.
  4. On non-empty response content, runs `postprocess_text(content)` and returns `TranslationResult(text=..., succeeded=True, route_used=route.route_label)`.
  5. If all routes fail in a cycle and cycles remain, sleeps `routes[0].quota_cooldown` seconds before the next global retry cycle.
  6. If every cycle exhausts, logs `critical` and returns `TranslationResult(text=original_text, succeeded=False, error=last_error)`.
- **Cache Integrity Guarantee**: `process_entry` checks `result.succeeded`. Failed translations increment `run_stats["failed"]`, keep the original text in the output JSON, and are **never** written into `translation_pairs` (preventing broken Chinese text from poisoning later cache hits). Multiline strings are stored raw in `translation_pairs` and escaped with `postprocess_text(..., for_json=False)` only when writing `translation_pairs.txt`.

### Data Schemas

- **Input JSON** (`Language == "ChineseSimplified"`):
  - `entries.Array` format: `{"Language": "ChineseSimplified", "entries": {"Array": [{"Name": "...", "Text": "..."}]}}`
  - Direct `entries` list format: `{"Language": "ChineseSimplified", "entries": [{"Name": "...", "Text": "..."}]}`
  - Both formats are supported identically in `translate` mode, `improve` mode, old-translation caching, and `tool/translation_mapper.py` via `src.utils.parse_json_entries`.
- **Glossary Files** (`.json` or `.txt`):
  - JSON list: `[{"Name": "UI/Button/Confirm", "Original": "确认", "Translated": "Xác nhận"}]`
  - JSON dict: `{"确认": "Xác nhận"}` or `{"UI/Button/Confirm": "Xác nhận"}` — populates **both** `name_to_translated` and `original_to_translated`
  - Plain `.txt`: `original=translated` per line — populates **both** `name_to_translated` and `original_to_translated`
- **Output Artifacts**:
  - Per-file JSONs (`<output_dir>/json/` by default): same schema (`entries.Array` or `entries` list) with translated `Text`.
  - `translation_details.json` (`<output_dir>/details/` by default): list of `{"Name", "Original", "Raw", "Translated"}` (`"Raw"` is populated in `improve` mode and `null` in `translate` mode).
  - `translation_pairs.txt` (`<output_dir>/pairs/` by default): `original=translated` with `\r`/`\n` escaped to literal `\r`/`\n`.
  - `logs/translation_<timestamp>.log`: lazily opened via `logger.enable_file_logging()` only after CLI validation succeeds (`--help` and module imports never create `logs/`).

---

## Setup & Runnable Commands

> **Reminder**: Always use `uv` or `.venv/bin/...` — never system `python` or `pip`.

### 1. Environment Setup

```bash
# Create .venv (Python 3.12) and install runtime + dev dependencies
uv sync --group dev

# Create local secret and routing config files (both gitignored)
cp .env.template .env
cp config.toml.template config.toml
```

Verify environment:

```bash
.venv/bin/python --version
.venv/bin/lom-translate --help
```

### 2. Zero-UABEA 3-Step Game Localization Workflow

The repository supports direct extraction from and patching into *Legend of Mortal*'s Unity 2020.3.49f1 (SerializedFile v22) `Mortal_Data/` directory without UABEA:

1. **Step 1 — Unpack game text, story flowchart & relationship matrix** (`Mortal_Data/` is strictly read-only):
   ```bash
   .venv/bin/lom-unpack-game \
       --mortal-data-dir /path/to/LegendOfMortal/Mortal_Data \
       --output-json-dir Resource/LeanLocalJson \
       --flowchart-file Resource/story_flowchart.json \
       --relationship-file Resource/relationship_matrix.json
   ```
2. **Step 2 — Translate or improve with story context & *xưng hô* rules**:
   ```bash
   .venv/bin/lom-translate \
       -c config.toml \
       -m translate \
       -id Resource/LeanLocalJson \
       -od translated_output \
       -ff Resource/story_flowchart.json \
       -rf Resource/relationship_matrix.json \
       -dw 4
   ```
3. **Step 3 — Build standalone patch / zip, install, or restore backups**:
   ```bash
   # Build standalone patch folder + install/uninstall scripts + zip (Mortal_Data stays read-only)
   .venv/bin/lom-patch-game \
       --mode build \
       --mortal-data-dir /path/to/LegendOfMortal/Mortal_Data \
       --json-dir translated_output/json \
       --output-patch-dir patch_output \
       --zip

   # Install patch directly into Mortal_Data (creates <asset>.bak backups first)
   .venv/bin/lom-patch-game \
       --mode install \
       --mortal-data-dir /path/to/LegendOfMortal/Mortal_Data \
       --json-dir translated_output/json

   # Or install from an already-built patch directory
   .venv/bin/lom-patch-game \
       --mode install \
       --mortal-data-dir /path/to/LegendOfMortal/Mortal_Data \
       --patch-dir patch_output

   # Restore original .bak backups inside Mortal_Data
   .venv/bin/lom-patch-game \
       --mode restore \
       --mortal-data-dir /path/to/LegendOfMortal/Mortal_Data
   ```

### 3. Main CLI (`translate` & `improve` Modes)

Can be invoked via `.venv/bin/python -m src.main`, `.venv/bin/lom-translate`, or `uv run lom-translate`. Any omitted path/mode option falls back to `[run]` in `config.toml`.

#### Translation Mode

```bash
.venv/bin/python -m src.main \
    -c config.toml \
    -m translate \
    -id /path/to/input_jsons \
    -od /path/to/base_output \
    -jod /path/to/json_output \
    -dod /path/to/details_output \
    -pod /path/to/pairs_output \
    -gf /path/to/your_glossary.json \
    -old /path/to/old_translations

# Equivalent console script with runtime route override (e.g. switch to Gemini free tier):
.venv/bin/lom-translate \
    --mode translate \
    --input-dir /path/to/input_jsons \
    --output-dir /path/to/base_output \
    --provider gemini \
    --tier free \
    --model gemma-3-27b
```

#### Improvement Mode

Refines an existing raw translation directory (`-rd` / `--raw-dir`) against the Chinese source (`-id` / `--input-dir`) using task `improve`:

```bash
.venv/bin/python -m src.main \
    -c config.toml \
    -m improve \
    -id /path/to/input_jsons \
    -rd /path/to/raw_translations \
    -od /path/to/base_output \
    -gf /path/to/your_glossary.json \
    -olf /path/to/single_old_translation_file.json \
    --provider openrouter \
    --tier paid \
    --model deepseek-v3
```

#### Full CLI Flag Reference (`src.main` / `lom-translate`)

| Short | Long | Description |
| --- | --- | --- |
| `-c` | `--config-file` | Path to TOML config file (default: `LOM_CONFIG_FILE` env var or `config.toml`) |
| `-m` | `--mode` | Execution mode: `translate` or `improve` (default: `[run].mode`) |
| `-id` | `--input-dir` | Input directory of source JSON files (default: `[run].input_dir`) |
| `-od` | `--output-dir` | Base output directory (default: `[run].output_dir`) |
| `-rd` | `--raw-dir` | Raw translations directory (required in `improve` mode unless set in `[run].raw_dir`) |
| `-jod` | `--json-output-dir` | Per-file JSON output directory (default: `<output_dir>/json`) |
| `-dod` | `--details-output-dir` | `translation_details.json` output directory (default: `<output_dir>/details`) |
| `-pod` | `--pairs-output-dir` | `translation_pairs.txt` output directory (default: `<output_dir>/pairs`) |
| `-gf` | `--glossary-file` | Specific glossary `.json` or `.txt` file (default: all `*.json` in `[run].glossary_dir`) |
| `-old` | `--old-dir` | Directory of previously translated JSONs for cache reuse (mutually exclusive with `-olf`) |
| `-olf` | `--old-file` | Single previous JSON/details file for cache reuse (mutually exclusive with `-old`) |
| `-ff` | `--flowchart-file` | Path to `story_flowchart.json` for story dialogue ordering & context (optional, overrides `[run].flowchart_file`) |
| `-rf` | `--relationship-file` | Path to `relationship_matrix.json` for character *xưng hô* rules (optional, overrides `[run].relationship_file`) |
| `-dw` | `--dialogue-window` | Preceding dialogue turns in sliding context window (integer `>= 0`, overrides `[run].dialogue_window`, default `4`) |
| — | `--provider` | Override primary provider route from `config.toml` |
| — | `--tier` | Override primary route tier from `config.toml` |
| — | `--model` | Override primary route model alias from `config.toml` |

### 4. Utility Scripts (`tool/`)

#### 1. `tool/create_glossary.py`
Aggregates matching `ChineseSimplified` original and translated JSON folders into both a JSON glossary and a deduplicated TXT glossary (skipping dialogue/description keys).

```bash
.venv/bin/python tool/create_glossary.py \
    --src_folder /path/to/original_jsons \
    --tgt_folder /path/to/translated_jsons \
    --output_json /path/to/output_glossary.json \
    --output_txt /path/to/output_glossary.txt
```

#### 2. `tool/filter_entries_by_category.py`
Copies JSON files into `Story`, `LegendInfo`, and `Other` subdirectories based on entry `Name` prefixes.

```bash
.venv/bin/python tool/filter_entries_by_category.py \
    --src_folder /path/to/input_jsons \
    --dst_base_folder /path/to/output_categorized_jsons
```

#### 3. `tool/filter_languages.py`
Copies JSON files into per-`Language` subdirectories (e.g., `ChineseSimplified`, `English`, `Unknown`).

```bash
.venv/bin/python tool/filter_languages.py \
    --src_folder /path/to/input_jsons \
    --dst_base_folder /path/to/output_language_filtered_jsons
```

#### 4. `tool/convert_translation_details.py`
Converts legacy dictionary-format `translation_details.json` files to the current list format. **Note: flags use hyphens (`--input-file`, `--output-file`), not underscores.**

```bash
.venv/bin/python tool/convert_translation_details.py \
    --input-file /path/to/old_translation_details.json \
    --output-file /path/to/new_translation_details.json
```

#### 5. `tool/translation_mapper.py`
Maps input JSON entries to their original text, raw translation text, and matched glossary terms, printing results to stdout. When `--input-dir` is provided directly, `config.toml` is not required; otherwise paths load from `config.toml`.

```bash
.venv/bin/python -m tool.translation_mapper \
    -c config.toml \
    --input-dir /path/to/input_jsons \
    --glossary-file /path/to/your_glossary.json
```

#### 6. `tool/improve_glossary.py` (`lom-improve-glossary`)
Calls the configured LLM asynchronously via the `improve_glossary` task in `config.toml` to refine every entry in an existing glossary JSON (using the shared `build_translation_prompt` builder) and writes an improved glossary JSON (`Name`, `Original`, `RawTranslated`, `Translated`) to `--output-dir`.

```bash
.venv/bin/python -m tool.improve_glossary \
    -gf /path/to/your_glossary.json \
    -od /path/to/output_dir \
    -c config.toml \
    --provider local_openai \
    --tier local \
    --model qwen3-14b

# Or via the installed console script:
.venv/bin/lom-improve-glossary \
    --glossary-file /path/to/your_glossary.json \
    --output-dir /path/to/output_dir
```

#### 7. `tool/unpack_game.py` (`lom-unpack-game`)
Extracts `ChineseSimplified` `LeanLanguageCSV` JSON files, `story_flowchart.json`, and `relationship_matrix.json` directly from `Mortal_Data/` (read-only).

```bash
.venv/bin/python -m tool.unpack_game \
    --mortal-data-dir /path/to/LegendOfMortal/Mortal_Data \
    --output-json-dir Resource/LeanLocalJson \
    --flowchart-file Resource/story_flowchart.json \
    --relationship-file Resource/relationship_matrix.json
```

#### 8. `tool/patch_game.py` (`lom-patch-game`)
Builds standalone Unity asset patches (with `install_patch.sh`, `uninstall_patch.sh`, `install_patch.bat`, `uninstall_patch.bat`, `README_PATCH.txt`, and optional `lom_vietnamese_patch.zip`), installs patches with `.bak` backups, or restores `.bak` backups.

```bash
.venv/bin/python -m tool.patch_game --help
```

Flags: `--mode` (`build` | `install` | `restore`, default `build`), `--mortal-data-dir` / `-md` (required), `--json-dir` / `-jd` (default `translated_output/json`), `--output-patch-dir` / `-opd` (default `patch_output`), `--patch-dir` / `-pd`, `--zip`.

#### 9. `tool/build_story_flowchart.py` (`lom-build-flowchart`) & `tool/build_relationship_matrix.py` (`lom-build-matrix`)
Standalone CLIs for regenerating `story_flowchart.json` from `Mortal_Data/` and building/enriching `relationship_matrix.json` from a flowchart. Run `--help` for options:

```bash
.venv/bin/lom-build-flowchart --help
.venv/bin/lom-build-matrix --help
```

### 5. Quality Gates (Lint & Tests)

```bash
.venv/bin/ruff check .
.venv/bin/pytest -v
```

---

## Current Features & Phased Improvement Roadmap

### Phase 0 — Core Modernization & Multi-Provider Engine *(Completed)*
- Migrated environment to `uv` + `pyproject.toml` + `.venv` (Python 3.12); removed `build.py`, `GameTextTranslator.spec`, `config.cfg`, and `requirements.txt`.
- Replaced legacy `google.generativeai` SDK with `litellm`-based `TranslationEngine` supporting local OpenAI-compatible servers (`local_openai`: LM Studio, llama.cpp, vLLM) and cloud providers (`gemini`, `openrouter`), with **universal per-`(provider, tier)` multi-key round-robin rotation**, per-tier concurrency/rate limiting, ordered route fallbacks, and global retry cycles.
- Introduced validated Pydantic v2 TOML configuration (`Provider -> Tier & Model -> Task`) with CLI route overrides (`--provider`, `--tier`, `--model`) and zero import-time side effects.
- Fixed critical bugs:
  - Multiline cache corruption (store raw strings in `translation_pairs`, escape only when writing `translation_pairs.txt`).
  - Failed-translation cache pollution (track `succeeded` explicitly; failed entries increment `failed` count and never enter `translation_pairs`).
  - Direct-list `entries` crash in `improve` mode (`parse_json_entries` + O(1) `raw_by_name` lookup).
  - JSON `dict`-format glossary missing `original_to_translated` entries.
  - `Language` header fast-check missing `"Language"` keys beyond byte 4096 (added full-file JSON fallback scan).
  - `tool/improve_glossary.py` prompt corruption, raw-string `prompt_data` mismatch, and manual delay loop.
  - Lazy file logging (`--help` / imports no longer create `logs/`), safe API key masking, and duplicate rule numbering in `improve` prompts.
- Added automated `pytest` + `pytest-asyncio` unit test suite, `ruff` linting, and synchronized `GEMINI.md` / `README.md`.

### Phase 1 — Translation QA & Reliability *(Planned)*
- **Automated Placeholder & Leftover-CJK Validator**: Validate translated outputs against source markers (`[|]`, `[||]`, `{{0:N0}}`, `{title}`, `[{0}]`, etc.) and unexpected remaining Chinese characters, triggering targeted auto-retry with corrective feedback on violations.
- **Failed-Entries Report & Targeted Retry**: Export failed entries to `failed_entries.json` with error metadata and add a `--retry-failed` CLI workflow to reprocess only failures.
- **Crash-Safe Incremental Checkpoint / Resume**: Periodically flush completed entries/files so interrupted long runs resume cleanly without re-calling the LLM.

### Phase 2 — Translation Quality & Throughput *(Partially Implemented)*
- **Zero-UABEA Unity Asset Unpack & Repack** *(Completed)*: Direct Unity 2020.3.49f1 (v22) `LeanLanguageCSV` extraction (`lom-unpack-game`) and patch building/installation/restore (`lom-patch-game`).
- **Sliding-Window Dialogue Context & Relationship Matrix (`Story/`)** *(Completed)*: Lua script flowchart extraction (`story_flowchart.py`), wuxia Vietnamese *xưng hô* rules (`relationship_matrix.py`), script-ordered execution with live `prev_lines` (`Original => Translated`) + `next_lines` lookahead, context-safe `{Name}::{Original}` caching, and `CONTEXT_AWARE_IMPROVE_RULE_PROMPT`.
- **Multi-Entry Batching**: Batch short UI/item/skill strings into structured multi-item prompts to cut API overhead and improve throughput.
- **Category-Aware Task Routing**: Route different entry categories (`Story/` vs `UI` / `LegendInfo`) to distinct `[tasks.*]` profiles (e.g., stronger literary model for `Story/`, faster model for short UI labels).
- **Fast Glossary Matching**: Replace linear substring scan in `find_original_matches` with an Aho-Corasick automaton or compiled regex matcher for large glossaries.

### Phase 3 — Workflow & Developer Experience *(Planned)*
- **Dry-Run Preview (`--dry-run`)**: Estimate cache hit rates, token volume, active routes, and projected cost without making LLM calls.
- **Human Proofreading Diff Export**: Export side-by-side HTML/CSV diffs (`Original`, `Raw`, `Translated`, glossary highlights) for community editors.
- **Optional Local Git `pre-commit` Hook**: Provide an opt-in local `pre-commit` configuration running `.venv/bin/ruff check .` and `.venv/bin/pytest` (no GitHub Actions CI required).
