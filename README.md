# Chinese to Vietnamese Text Translator for Legend of Mortal (`lom-vie-translate` v2)

A production-ready, provider-agnostic game localization pipeline for translating and refining game dialogue from Chinese (Simplified) to Vietnamese for *Legend of Mortal*.

Designed for robustness under heavy API concurrency, strict preservation of Unity engine data formats, per-model rate limiting, and intelligent soft validation of formatting tokens.

---

## Key Features

- **Provider-Agnostic LLM Engine**: Integrates natively with any OpenAI-compatible endpoint—local models (Ollama, vLLM, LM Studio, llama.cpp), OpenAI, Google Gemini, and DeepSeek.
- **Per-Model Autonomous Rate Limiting**: Each configured model defines its own retry limit, request-per-minute window (`limit_per_minute`), request delay, and quota backoff.
- **True Per-Call Round-Robin Rotation**: The system rotates to the next available model in the task pool after **each call** (only selecting models that are free and within rate limits). If a model encounters transient errors, the request immediately rotates to the next model rather than repeatedly hammering the failing endpoint.
- **Soft Validation & Auto-Healing**:
  - Automatically heals spacing discrepancies introduced by LLMs around code markers (`[ || ]` $\to$ `[||]`, `{ 0 : N0 }` $\to$ `{0:N0}`, `</ color>` $\to$ `</color>`).
  - Validates preservation of injected linebreak markers (`[|]`, `[||]`), engine interpolation tokens (`{0:N0}`, `{title}`), and Unity rich text tags (`<color>`, `<b>`).
  - Scans for lingering untranslated Chinese characters without aborting the batch.
- **Strict Unity JSON Format Invariance**: Supports both Schema A (`entries.Array`) and Schema B (flat `entries`), preserving all auxiliary engine metadata (`Id`, `Speaker`, `Voice`, `Context`, `Sound`, etc.).
- **High-Performance Glossary Engine**: Ingests both dictionary (`{"term": "dịch"}`) and list formats, using an Aho-Corasick automaton (`pyahocorasick`) for $O(\text{text length})$ term matching with longest-match substring deduplication.
- **Atomic Disk Writes**: All file outputs are written to temporary files and renamed atomically to eliminate data corruption.

---

## Installation

Requires Python 3.10 or newer.

```bash
# Clone the repository
git clone https://github.com/RioRichard/lom-vie-translate.git
cd lom-vie-translate

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the package and dependencies
pip install -e .

# Or install with development dependencies (pytest, ruff, mypy)
pip install -e ".[dev]"
```

---

## Configuration (`config.json`)

All secrets and operational settings live in a single `config.json` file in the project root. This file is **gitignored** to prevent credential leaks.

Copy the template to get started:

```bash
cp config.template.json config.json
```

### Example `config.json`

```json
{
  "models": [
    {
      "id": "my-local-llm",
      "url": "http://localhost:11434/v1",
      "api_key": "not-needed",
      "model_name": "llama3.1:70b",
      "temperature": 0.1,
      "top_p": 0.9,
      "top_k": 40,
      "max_retries": 2,
      "limit_per_minute": 30,
      "rate_limit_delay": 0.5,
      "rate_limit_if_quota_exceeded": 10.0
    },
    {
      "id": "gemini-flash",
      "url": "https://generativelanguage.googleapis.com/v1beta/openai/",
      "api_key": "your-gemini-api-key",
      "model_name": "gemini-2.0-flash",
      "temperature": 0.1,
      "top_p": 0.9,
      "top_k": 40,
      "max_retries": 3,
      "limit_per_minute": 15,
      "rate_limit_delay": 1.0,
      "rate_limit_if_quota_exceeded": 30.0
    },
    {
      "id": "gpt4o-mini",
      "url": "https://api.openai.com/v1",
      "api_key": "sk-your-openai-key",
      "model_name": "gpt-4o-mini",
      "temperature": 0.1,
      "top_p": 0.9,
      "top_k": null,
      "max_retries": 3,
      "limit_per_minute": 60,
      "rate_limit_delay": 0.5,
      "rate_limit_if_quota_exceeded": 20.0
    }
  ],

  "task_assignments": {
    "translate": ["gemini-flash", "my-local-llm"],
    "improve": ["gemini-flash", "my-local-llm"],
    "glossary_improve": ["gpt4o-mini", "my-local-llm"]
  },

  "settings": {
    "max_concurrent": 5,
    "max_concurrent_files": 3,
    "max_global_retries": 3,
    "input_dir": "Resource/LeanLocalJson",
    "output_dir": "translated_output",
    "glossary_dir": "Resource/glossary"
  }
}
```

---

## CLI Usage

The CLI command is `lom-translate` (or `python3 -m lom_translate.cli`).

### 1. Translation Mode

Translates raw Chinese dialogue files to Vietnamese:

```bash
# Basic usage (reads directories and models from config.json):
lom-translate -m translate

# With explicit overrides:
lom-translate \
    -m translate \
    -i /path/to/chinese_jsons \
    -od /path/to/output_dir \
    -gf /path/to/custom_glossary.json \
    -old /path/to/existing_translated_dir
```

### 2. Improvement Mode

Refines previous raw translations using context and glossary rules:

```bash
lom-translate \
    -m improve \
    -i /path/to/chinese_jsons \
    -rd /path/to/raw_translations \
    -od /path/to/improved_output \
    -gf /path/to/custom_glossary.json
```

### CLI Arguments Reference

| Option | Short Alias | Description |
|---|---|---|
| `--mode` | `-m` | Execution mode: `translate` or `improve` (required) |
| `--config` | `-c` | Path to configuration file (default: `config.json`) |
| `--input-dir` | `-id`, `-i` | Input directory containing game JSON files |
| `--output-dir` | `-od` | Base output directory |
| `--raw-dir` | `-rd` | Directory containing raw translations (required for `improve`) |
| `--glossary-file`| `-gf` | Specific glossary JSON or TXT file to load |
| `--old-dir` | `-old` | Directory of existing translations for caching |
| `--old-file` | `-olf` | Single file of existing translations for caching |

---

## Output Structure

The output directory contains three artifacts:

```
translated_output/
├── json/                         # Preserves game JSON schema & extra metadata
│   ├── Story_Chapter1.json
│   └── Combat_Skills.json
├── details/
│   └── translation_details.json  # Comprehensive entry-level audit log
└── pairs/
    └── translation_pairs.txt     # Fast lookup key=value translation cache
```

---

## Tools Roadmap

Utility scripts from the previous release are set aside during core re-initialization and will be integrated directly into the unified `lom-translate` CLI in a future release:

```bash
lom-translate --tool create-glossary --src ... --tgt ...
lom-translate --tool filter-category --src ... --dst ...
lom-translate --tool filter-language --src ... --dst ...
lom-translate --tool convert-details --input ... --output ...
lom-translate --tool improve-glossary --glossary ...
lom-translate --tool map-context --input ...
```

---

## Running Tests & Quality Checks

```bash
# Run pytest test suite with code coverage
pytest tests/ -v --cov=lom_translate --cov-report=term-missing

# Lint and verify code formatting
ruff check lom_translate tests
ruff format --check lom_translate tests

# Static type validation
mypy lom_translate tests
```
