# Chinese to Vietnamese Game Text Translator for Legend of Mortal

A specialized asynchronous Python tool for translating ***Legend of Mortal*** game text from **Chinese (Simplified)** (`ChineseSimplified`) to **Vietnamese**, maintaining wuxia/historical tone, consistent terminology, and in-game formatting markers.

## Features

- **Zero-UABEA Game Unpack & Patch**: Direct Unity 2020.3.49f1 (SerializedFile v22) extraction (`lom-unpack-game`) and patch building/installation/backup restore (`lom-patch-game`) on `Mortal_Data/`.
- **Story Flowchart & Relationship Matrix (*Xưng Hô*) Context**: Extracts Lua story scripts and character relationships to translate `Story/` dialogues in script execution order with a live sliding dialogue window, speaker/mood metadata, and context-safe `{Name}::{Original}` caching.
- **Multi-Provider LLM Engine (`litellm`)**: Supports local OpenAI-compatible servers (LM Studio, llama.cpp, vLLM) and cloud APIs (Google Gemini, OpenRouter) from a single `config.toml`.
- **Universal Multi-Key Rotation & Tiered Fallback**: Every `(provider, tier)` supports comma-separated API keys in `.env` with round-robin rotation, independent concurrency/rate limiting, ordered fallback chains, and global retry cycles.
- **Three CLI Modes + Glossary Refinement**:
  - `translate` mode: Translates Chinese (Simplified) JSON files to Vietnamese (with automatic pre-flight glossary check & sync enabled by default).
  - `improve` mode: Refines existing raw translations against the Chinese originals (with automatic pre-flight glossary check & sync enabled by default).
  - `glossary` mode (`-m glossary`): Built-in glossary auto-check and sync directly from source JSONs (`--input-dir`) without creating translation output directories or requiring `--old-dir` or a pre-translated folder.
  - `improve_glossary` task (`lom-improve-glossary`): Refines existing glossary JSON entries using the configured LLM.
- **Pre-Flight Glossary Auto-Check & Sync**: Automatically extracts structured game terms (`characters`, `martial_arts`, `locations`, `items_lore`) with paired descriptions/biographies, detects outdated `Original` changes, preserves in-sync/manual entries, translates missing terms (characters first so compound items stay consistent), writes `glossary.json` + `glossary.txt`, and syncs character `vi_name` into `story_flowchart.json` and `relationship_matrix.json`. Disable per run with `--no-auto-glossary` or globally via `auto_sync_glossary = false`.
- **3-Tier Caching & Reuse**: Exact glossary lookup -> in-run deduplication (only successful translations cached) -> optional previous-translation reuse (`--old-dir` / `--old-file`) before calling an LLM.
- **Structured Outputs**:
  - Per-file translated JSON files preserving original structure (`entries.Array` or direct `entries` list)
  - Consolidated `translation_details.json`
  - Escaped `translation_pairs.txt`
  - Lazy per-run log files (`logs/translation_<timestamp>.log`)

## Project Structure

```text
.
├── .python-version           # Python 3.12 pin
├── pyproject.toml            # uv / hatchling config, dependencies, console scripts, pytest & ruff
├── uv.lock                   # Locked dependency graph
├── .env.template             # API key & LOM_CONFIG_FILE template
├── config.toml.template      # Multi-provider [run], [providers.*], [tasks.*] template
├── GEMINI.md                 # Engineering rules, deep architecture & roadmap
├── README.md                 # Project documentation (this file)
├── src/
│   ├── config.py             # Pydantic v2 TOML config loader & route resolver
│   ├── translator.py         # Async LiteLLM TranslationEngine, KeyPool & rate limiter
│   ├── file_processor.py     # Entry & per-file async processor, flowchart script ordering & context-safe cache
│   ├── prompt_preparer.py    # Prompt builder with preprocessed raw text, glossary, flowchart & pronoun rules
│   ├── glossary.py           # Glossary/cache loaders, structured extraction & 3-way autocheck_and_sync_glossary
│   ├── unity_assets.py       # Unity 2020.3.49f1 (v22) SerializedFile & LeanLanguageCSV unpack/repack
│   ├── story_flowchart.py    # Lua story script parser, character info, sliding context & glossary vi_name sync
│   ├── relationship_matrix.py# Wuxia Vietnamese xưng hô (PronounRule) resolver & character vi_name sync
│   ├── utils.py              # Text pre/post-processing, JSON entry parser & shared/context-aware prompts
│   ├── logger.py             # Lazy structured logger with safe key masking
│   └── main.py               # Main CLI entry point (lom-translate, -m translate/improve/glossary + pre-flight sync)
├── tool/
│   ├── unpack_game.py                # Zero-UABEA extractor (lom-unpack-game)
│   ├── patch_game.py                 # Zero-UABEA patch builder/installer/restorer (lom-patch-game)
│   ├── build_story_flowchart.py      # Build story_flowchart.json from Mortal_Data (lom-build-flowchart)
│   ├── build_relationship_matrix.py  # Build relationship_matrix.json from flowchart (lom-build-matrix)
│   ├── create_glossary.py            # Aggregate JSON folders into JSON/TXT glossaries
│   ├── filter_entries_by_category.py # Split files by Story / LegendInfo / Other
│   ├── filter_languages.py           # Split files by Language field
│   ├── convert_translation_details.py# Convert legacy dict details JSON to list format
│   ├── translation_mapper.py         # Inspect entry-to-glossary mappings on stdout
│   └── improve_glossary.py           # LLM-powered glossary refiner (lom-improve-glossary)
└── tests/                    # pytest + pytest-asyncio unit test suite
```

## Setup

### Prerequisites

- [`uv`](https://docs.astral.sh/uv/) package manager
- Python `>=3.11,<3.14` (`3.12` pinned via `.python-version`, provisioned automatically by `uv`)

### Installation

Always use `uv` and `.venv/bin/...` (never system `python` or `pip`):

```bash
# 1. Create .venv (Python 3.12) and install runtime + dev dependencies
uv sync --group dev

# 2. Create local configuration files (both are gitignored)
cp .env.template .env
cp config.toml.template config.toml
```

### Configure Secrets (`.env`)

Store API keys **only** in `.env`. Every provider tier supports multiple comma-separated keys for round-robin rotation:

```env
# Optional: comma-separated keys if your local OpenAI-compatible server requires auth.
# Leave blank for keyless local servers (uses default_api_key = "local-no-key").
LOCAL_OPENAI_API_KEYS=

# Google Gemini (comma-separated keys per tier)
GEMINI_FREE_API_KEYS=your-free-key-1,your-free-key-2
GEMINI_PAID_API_KEYS=

# OpenRouter (comma-separated keys per tier)
OPENROUTER_FREE_API_KEYS=
OPENROUTER_PAID_API_KEYS=

# Optional: custom config.toml location
# LOM_CONFIG_FILE=config.toml
```

### Configure Routing & Providers (`config.toml`)

`config.toml` organizes settings into three layers: **`Provider -> Tier & Model -> Task`**, plus `[run]` defaults:

- **`[run]`**: Default `mode` (`"translate"`, `"improve"`, or `"glossary"`), `input_dir`, `output_dir`, `glossary_dir`, `auto_sync_glossary` (`true` by default), `max_concurrent_file_opens`, `dialogue_window` (default `4`), and optional `raw_dir`, `json_output_dir`, `details_output_dir`, `pairs_output_dir`, `glossary_file`, `old_dir`, `old_file`, `flowchart_file`, `relationship_file`.
- **`[providers.<name>]`**: Connection settings (`api_base`, `timeout`, optional `default_api_key`), nested **`tiers.<tier>`** (`api_key_env`, `max_concurrent`, `rate_limit_delay`, `quota_cooldown`, `max_retries`, `model_suffix`, `extra_headers`), and nested **`models.<model>`** (`model_id`, `temperature`, `max_tokens`, `timeout`, `allowed_tiers`, `tier_model_ids`, `extra_params`).
- **`[tasks.<task>]`**: Routing for `translate`, `improve`, and `improve_glossary` — each defines `primary = { provider, tier, model }`, ordered `fallbacks = [...]`, `max_global_retries`, and optional `temperature` / `max_tokens` overrides.

Pre-configured providers in `config.toml.template`:

| Provider | Endpoint / Backend | Tiers | Models |
| --- | --- | --- | --- |
| `local_openai` | `http://localhost:1234/v1` (LM Studio; also supports llama.cpp `:8080/v1`, vLLM `:8000/v1`) | `local` (`LOCAL_OPENAI_API_KEYS` or keyless `default_api_key`) | `qwen3-14b` (`openai/qwen3-14b`) |
| `gemini` | Google AI Studio | `free` (`GEMINI_FREE_API_KEYS`), `paid` (`GEMINI_PAID_API_KEYS`) | `gemma-4-26b` (`gemini/gemma-4-26b-a4b-it`), `gemma-3-27b` (`gemini/gemma-3-27b-it`), `gemini-2.5-flash` (`gemini/gemini-2.5-flash`) |
| `openrouter` | OpenRouter | `free` (`OPENROUTER_FREE_API_KEYS`, auto `:free` suffix), `paid` (`OPENROUTER_PAID_API_KEYS`) | `deepseek-v3` (`openrouter/deepseek/deepseek-chat-v3-0324`) |

> Routes whose tier requires an API key (`api_key_env` set with no `default_api_key`) are automatically skipped if that environment variable is empty, allowing the engine to fall through seamlessly to the next configured route.

## Input & Glossary Formats

### Input JSON Files

Files must have `"Language": "ChineseSimplified"` (other languages are skipped; files whose `"Language"` key appears after byte 4096 are still detected via full-file fallback parsing). Both `entries.Array` and direct `entries` list formats are supported:

```json
{
  "Language": "ChineseSimplified",
  "entries": {
    "Array": [
      {
        "Name": "Story/Chapter1/Dialog001",
        "Text": "你托人送了信，自己独行下山，加紧脚步往江陵发进。"
      },
      {
        "Name": "Story/Chapter1/Action001",
        "Text": "整装"
      }
    ]
  }
}
```

Or direct list format:

```json
{
  "Language": "ChineseSimplified",
  "entries": [
    {
      "Name": "Story/Chapter1/Dialog001",
      "Text": "你托人送了信，自己独行下山，加紧脚步往江陵发进。"
    }
  ]
}
```

### Glossary Files

Glossaries may be loaded from a specific file (`-gf` / `--glossary-file`) or all `*.json` files in `[run].glossary_dir`. When `auto_sync_glossary = true` (default) or `-m glossary` is used, missing target files (such as `-gf Resource/glossary/glossary.json` or `<glossary_dir>/glossary.json` + `.txt`) are created and synchronized automatically from `--input-dir` without needing `--old-dir`. Supported formats:

1. **JSON list** (`Name`, `Original`, `Translated`):
   ```json
   [
     {
       "Name": "UI/Button/Confirm",
       "Original": "确认",
       "Translated": "Xác nhận"
     }
   ]
   ```
2. **JSON dictionary** (populates both exact-Name lookup and source-term matching):
   ```json
   {
     "确认": "Xác nhận",
     "UI/Button/Confirm": "Xác nhận"
   }
   ```
3. **Plain text `.txt`** (`original=translated` per line):
   ```text
   确认=Xác nhận
   整装=Chuẩn bị
   ```

## Usage

Run commands via `.venv/bin/python -m ...`, installed `.venv/bin/lom-*` console scripts, or `uv run ...`. CLI arguments override `[run]` defaults in `config.toml`.

### Zero-UABEA 3-Step Localization Workflow

You can unpack game text directly from *Legend of Mortal*'s `Mortal_Data/` folder, translate with story dialogue context + Vietnamese *xưng hô* rules, and build/install patches without UABEA:

1. **Unpack game text, flowchart, and relationship matrix** (`Mortal_Data/` is read-only):
   ```bash
   .venv/bin/lom-unpack-game \
       --mortal-data-dir /path/to/LegendOfMortal/Mortal_Data \
       --output-json-dir Resource/LeanLocalJson \
       --flowchart-file Resource/story_flowchart.json \
       --relationship-file Resource/relationship_matrix.json
   ```
2. **Check/sync glossary (automatic or standalone) and translate or improve with story context**:
   ```bash
   # Optional standalone glossary check & sync (creates/updates glossary.json + .txt and syncs character vi_name)
   .venv/bin/lom-translate \
       -c config.toml \
       -m glossary \
       -id Resource/LeanLocalJson \
       -gf Resource/glossary/glossary.json \
       -ff Resource/story_flowchart.json \
       -rf Resource/relationship_matrix.json

   # Translate (runs pre-flight glossary auto-check & sync automatically when auto_sync_glossary = true)
   .venv/bin/lom-translate \
       -c config.toml \
       -m translate \
       -id Resource/LeanLocalJson \
       -od translated_output \
       -ff Resource/story_flowchart.json \
       -rf Resource/relationship_matrix.json \
       -dw 4
   ```
3. **Build, install, or restore the game patch**:
   ```bash
   # Build standalone patch folder, install/uninstall scripts, and zip (Mortal_Data stays untouched)
   .venv/bin/lom-patch-game \
       --mode build \
       --mortal-data-dir /path/to/LegendOfMortal/Mortal_Data \
       --json-dir translated_output/json \
       --output-patch-dir patch_output \
       --zip

   # Install directly into Mortal_Data (creates <asset>.bak backups before overwriting)
   .venv/bin/lom-patch-game \
       --mode install \
       --mortal-data-dir /path/to/LegendOfMortal/Mortal_Data \
       --json-dir translated_output/json

   # Or install from an existing built patch folder
   .venv/bin/lom-patch-game \
       --mode install \
       --mortal-data-dir /path/to/LegendOfMortal/Mortal_Data \
       --patch-dir patch_output

   # Restore original .bak backups
   .venv/bin/lom-patch-game \
       --mode restore \
       --mortal-data-dir /path/to/LegendOfMortal/Mortal_Data
   ```

### Glossary Check & Sync Mode (`-m glossary`)

Builds or synchronizes your glossary directly from `ChineseSimplified` JSONs in `--input-dir` (no `--old-dir` or pre-translated folder needed). It extracts `characters`, `martial_arts`, `locations`, and `items_lore` with paired context, detects outdated `Original` text changes, preserves manual entries, translates missing terms, writes `glossary.json` + `glossary.txt` (creating `-gf` automatically if it does not exist yet), and updates character `vi_name` in `story_flowchart.json` and `relationship_matrix.json` without creating `output_dir/(json, details, pairs)`:

```bash
.venv/bin/lom-translate \
    -c config.toml \
    -m glossary \
    -id Resource/LeanLocalJson \
    -gf Resource/glossary/glossary.json \
    -ff Resource/story_flowchart.json \
    -rf Resource/relationship_matrix.json
```

### Translation Mode

Pre-flight glossary auto-check & sync runs automatically before file translation when `auto_sync_glossary = true` in `config.toml` (default). Pass `--no-auto-glossary` to skip pre-flight sync. (`-old` / `--old-dir` is only for optional cache reuse from previous runs, not needed for glossary creation/sync.)

```bash
.venv/bin/python -m src.main \
    -c config.toml \
    -m translate \
    -id /path/to/input_jsons \
    -od /path/to/base_output \
    -jod /path/to/json_output \
    -dod /path/to/details_output \
    -pod /path/to/pairs_output \
    -gf /path/to/your_glossary.json

# Or with the installed console script + route overrides & pre-flight sync skipped:
.venv/bin/lom-translate \
    --mode translate \
    --input-dir /path/to/input_jsons \
    --output-dir /path/to/base_output \
    --no-auto-glossary \
    --provider gemini \
    --tier free \
    --model gemma-3-27b
```

### Improvement Mode

Refines existing raw translations (`-rd` / `--raw-dir`) against original Chinese files (`-id` / `--input-dir`), with automatic pre-flight glossary check & sync enabled by default (disable with `--no-auto-glossary`):

```bash
.venv/bin/python -m src.main \
    -c config.toml \
    -m improve \
    -id /path/to/input_jsons \
    -rd /path/to/raw_translations \
    -od /path/to/base_output \
    -jod /path/to/json_output \
    -dod /path/to/details_output \
    -pod /path/to/pairs_output \
    -gf /path/to/your_glossary.json \
    -olf /path/to/single_old_translation_file.json

# Or using long arguments + console script:
.venv/bin/lom-translate \
    --config-file config.toml \
    --mode improve \
    --input-dir /path/to/input_jsons \
    --raw-dir /path/to/raw_translations \
    --output-dir /path/to/base_output \
    --provider openrouter \
    --tier paid \
    --model deepseek-v3
```

### CLI Options (`lom-translate` / `src.main`)

| Option | Description |
| --- | --- |
| `-c`, `--config-file` | Path to TOML config file (default: `LOM_CONFIG_FILE` or `config.toml`) |
| `-m`, `--mode` | `translate`, `improve`, or `glossary` (overrides `[run].mode`) |
| `-id`, `--input-dir` | Directory containing source JSON files (overrides `[run].input_dir`) |
| `-od`, `--output-dir` | Base output directory (overrides `[run].output_dir`; unused in `glossary` mode) |
| `-rd`, `--raw-dir` | Directory of raw translations (required in `improve` mode if not set in `config.toml`) |
| `-jod`, `--json-output-dir` | Output directory for per-file JSONs (default: `<output_dir>/json`) |
| `-dod`, `--details-output-dir` | Output directory for `translation_details.json` (default: `<output_dir>/details`) |
| `-pod`, `--pairs-output-dir` | Output directory for `translation_pairs.txt` (default: `<output_dir>/pairs`) |
| `-gf`, `--glossary-file` | Path to a specific glossary `.json` or `.txt` file (created/synced automatically when auto-sync is active) |
| `--no-auto-glossary` | Skip automatic pre-flight glossary check and sync before `translate`/`improve` runs |
| `-old`, `--old-dir` | Optional directory of previous translated JSONs for cache reuse (cannot combine with `-olf`; not required for glossary sync) |
| `-olf`, `--old-file` | Optional single previous translation file for cache reuse (cannot combine with `-old`) |
| `-ff`, `--flowchart-file` | Path to `story_flowchart.json` for script-ordered `Story/` context (optional; `vi_name` synced during auto-glossary) |
| `-rf`, `--relationship-file` | Path to `relationship_matrix.json` for character *xưng hô* rules (optional; `vi_name` synced during auto-glossary) |
| `-dw`, `--dialogue-window` | Preceding turns in sliding dialogue context window (integer `>= 0`, default `4`) |
| `--provider` | Override primary provider from `config.toml` (`local_openai`, `gemini`, `openrouter`, ...) |
| `--tier` | Override primary tier from `config.toml` (`local`, `free`, `paid`, ...) |
| `--model` | Override primary model alias from `config.toml` (`qwen3-14b`, `gemma-3-27b`, `deepseek-v3`, ...) |

## Utility Tools (`tool/`)

### 1. `tool/create_glossary.py`

Optional legacy helper that aggregates matching original and already-translated `ChineseSimplified` JSON folders into JSON and deduplicated TXT glossaries. For generating and maintaining glossaries directly from source JSONs without a pre-translated directory, use `.venv/bin/lom-translate -m glossary` (or automatic pre-flight sync).

```bash
.venv/bin/python tool/create_glossary.py \
    --src_folder /path/to/original_jsons \
    --tgt_folder /path/to/translated_jsons \
    --output_json /path/to/output_glossary.json \
    --output_txt /path/to/output_glossary.txt
```

### 2. `tool/filter_entries_by_category.py`

Categorizes JSON files into `Story`, `LegendInfo`, and `Other` folders based on entry `Name` prefixes:

```bash
.venv/bin/python tool/filter_entries_by_category.py \
    --src_folder /path/to/input_jsons \
    --dst_base_folder /path/to/output_categorized_jsons
```

### 3. `tool/filter_languages.py`

Splits JSON files into per-language subdirectories based on their `Language` field:

```bash
.venv/bin/python tool/filter_languages.py \
    --src_folder /path/to/input_jsons \
    --dst_base_folder /path/to/output_language_filtered_jsons
```

### 4. `tool/convert_translation_details.py`

Converts legacy dictionary-format `translation_details.json` files to the current list format (note hyphenated flags `--input-file` / `--output-file`):

```bash
.venv/bin/python tool/convert_translation_details.py \
    --input-file /path/to/old_translation_details.json \
    --output-file /path/to/new_translation_details.json
```

### 5. `tool/translation_mapper.py`

Maps input entries to original text, raw translations, and glossary matches, printing results to stdout:

```bash
.venv/bin/python -m tool.translation_mapper \
    -c config.toml \
    --input-dir /path/to/input_jsons \
    --glossary-file /path/to/your_glossary.json
```

### 6. `tool/improve_glossary.py` (`lom-improve-glossary`)

Calls the configured LLM asynchronously via the `improve_glossary` task in `config.toml` to refine glossary translations and saves an improved glossary JSON (`Name`, `Original`, `RawTranslated`, `Translated`) to `--output-dir`:

```bash
.venv/bin/python -m tool.improve_glossary \
    -gf /path/to/your_glossary.json \
    -od /path/to/output_dir \
    -c config.toml \
    --provider gemini \
    --tier free \
    --model gemma-3-27b

# Or via the installed console script:
.venv/bin/lom-improve-glossary \
    --glossary-file /path/to/your_glossary.json \
    --output-dir /path/to/output_dir
```

### 7. `tool/unpack_game.py` (`lom-unpack-game`)

Extracts `ChineseSimplified` `LeanLanguageCSV` JSON files, `story_flowchart.json`, and `relationship_matrix.json` directly from `Mortal_Data/` without modifying game files:

```bash
.venv/bin/python -m tool.unpack_game \
    --mortal-data-dir /path/to/LegendOfMortal/Mortal_Data \
    --output-json-dir Resource/LeanLocalJson \
    --flowchart-file Resource/story_flowchart.json \
    --relationship-file Resource/relationship_matrix.json
```

### 8. `tool/patch_game.py` (`lom-patch-game`)

Builds standalone Unity asset patches (`patch_output/Mortal_Data/*`, `install_patch.sh`, `uninstall_patch.sh`, `install_patch.bat`, `uninstall_patch.bat`, `README_PATCH.txt`, and optional `lom_vietnamese_patch.zip`), installs patches with `.bak` backups, or restores backups:

```bash
.venv/bin/lom-patch-game --mode build --mortal-data-dir /path/to/Mortal_Data --json-dir translated_output/json --output-patch-dir patch_output --zip
.venv/bin/lom-patch-game --mode install --mortal-data-dir /path/to/Mortal_Data --patch-dir patch_output
.venv/bin/lom-patch-game --mode restore --mortal-data-dir /path/to/Mortal_Data
```

### 9. `tool/build_story_flowchart.py` & `tool/build_relationship_matrix.py`

Standalone tools (`lom-build-flowchart`, `lom-build-matrix`) to regenerate `story_flowchart.json` from `Mortal_Data/` or build/enrich `relationship_matrix.json` from a flowchart. Run `--help` to view all options:

```bash
.venv/bin/lom-build-flowchart --help
.venv/bin/lom-build-matrix --help
```

## Output Structure

1. **Per-File Translated JSONs** (`<output_dir>/json/`):
   Preserves the exact input structure (`entries.Array` or direct `entries` list), written as UTF-8 (`ensure_ascii=False, indent=2`):
   ```json
   {
     "Language": "ChineseSimplified",
     "entries": {
       "Array": [
         {
           "Name": "Story/Chapter1/Dialog001",
           "Text": "Ngươi phái người đưa thư, tự mình độc hành xuống núi, thúc ngựa lao về Giang Lăng."
         }
       ]
     }
   }
   ```
2. **Consolidated Translation Details** (`<output_dir>/details/translation_details.json`):
   ```json
   [
     {
       "Name": "Story/Chapter1/Dialog001",
       "Original": "你托人送了信，自己独行下山，加紧脚步往江陵发进。",
       "Raw": "Ngươi sai người đưa thư, mình độc hành xuống núi, gấp rút bước chân hướng Giang Lăng phát tiến.",
       "Translated": "Ngươi phái người đưa thư, tự mình độc hành xuống núi, thúc ngựa lao về Giang Lăng."
     }
   ]
   ```
   *(The `"Raw"` key is always present: populated in `improve` mode and `null` in `translate` mode.)*
3. **Translation Pairs** (`<output_dir>/pairs/translation_pairs.txt`):
   Deduplicated `original=translated` pairs with `\r` and `\n` escaped to literal `\r` / `\n`:
   ```text
   你托人送了信，自己独行下山，加紧脚步往江陵发进。=Ngươi phái người đưa thư, tự mình độc hành xuống núi, thúc ngựa lao về Giang Lăng.
   整装=Chuẩn bị
   ```
4. **Logs** (`logs/translation_<timestamp>.log`):
   Created lazily only when a translation/improvement run starts (running `--help` or importing modules does not create `logs/`). API keys are masked automatically in log output.

## Development & Quality Checks

Run lint and tests strictly inside `.venv`:

```bash
.venv/bin/ruff check .
.venv/bin/pytest -v
```

Key engineering rules (see `GEMINI.md` for the full specification and improvement roadmap):
- Always execute Python/tools via `.venv/bin/...` or `uv run` (never system `python` or `pip`).
- Keep `.env`, `config.toml`, `logs/`, `patch_output/`, `*.bak`, and generated outputs out of git; commit only `config.toml.template` and `.env.template`.
- Always use explicit `encoding="utf-8"` and `ensure_ascii=False`, and preserve all *Legend of Mortal* game markers (`[|]`, `[||]`, `{{0:N0}}`, `{title}`, `[{0}]`, `???`, etc.).
- Keep `GEMINI.md` and `README.md` synchronized whenever CLI flags, config schema, tools, or architecture change.
