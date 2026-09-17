# Project Overview

This project (`lom-vie-translate` v2) is a specialized, production-ready tool for translating game dialogue from Chinese (Simplified) to Vietnamese for *Legend of Mortal*. It focuses on strict Unity engine data invariance, robust per-model rate limiting, true round-robin load distribution, soft validation of code tokens, and high-performance glossary matching.

**Key Technologies:** Python 3.10+, OpenAI-compatible API (`openai`), Pydantic v2, Aho-Corasick (`pyahocorasick`), aiofiles, pytest, ruff, mypy.

---

# Architecture & Package Structure

```
lom_translate/
├── __init__.py
├── cli.py          # Command-line interface entry point (lom-translate)
├── client.py       # Isolated LLM client & true round-robin pool rotator
├── config.py       # Zero-side-effect lazy configuration loader
├── glossary.py     # Ingestion & Aho-Corasick O(N) matching
├── logger.py       # Lazy structured logger (creates files only during run)
├── models.py       # Pydantic models for game entries, files & configs
├── pipeline.py     # Concurrent file processor with atomic writes
├── prompt.py       # Contextual prompt generator with O(1) raw mapping
├── text.py         # Injected linebreaks [|], [||] encoding & postprocessing
└── validation.py   # Soft validators: auto-healing & token integrity checks
```

---

# Configuration (`config.json`)

All runtime settings live in `config.json` (gitignored). Copy `config.template.json` to configure:
- **`models`**: Each model defines its own `id`, `url`, `api_key`, `model_name`, `temperature`, `top_p`, `top_k`, `max_retries`, `limit_per_minute`, `rate_limit_delay`, and `rate_limit_if_quota_exceeded`.
- **`task_assignments`**: Maps tasks (`translate`, `improve`) to arrays of model IDs. The engine rotates through models in round-robin order after each call if free and within limits.
- **`settings`**: Operational defaults (`max_concurrent`, `max_concurrent_files`, `input_dir`, `output_dir`, `glossary_dir`).

---

# Development Conventions & Rules

1. **Zero Module-Level Side Effects**: Importing any module in `lom_translate` must never crash, check environment variables, or create log files on disk.
2. **Unity JSON Format Invariance**: Always support Schema A (`entries.Array`) and Schema B (flat `entries`). Reconstructed output must match input schema structure byte-for-byte.
3. **Complete Metadata Preservation**: Never strip auxiliary engine fields (`Id`, `Speaker`, `Voice`, `Context`, etc.). Clone entries via `entry.clone_with_translation()`.
4. **Provider-Agnostic LLM Layer**: Use OpenAI-compatible HTTP clients (`/v1/chat/completions`). Supports local LLMs (Ollama, vLLM, LM Studio) as well as cloud providers.
5. **Per-Call Round-Robin Rotation**: The pool rotates to the next model after every single run (selecting only models that are free and within limits). If a model encounters an error, immediately rotate to the next free model.
6. **Soft Validation & Auto-Healing**:
   - Spacing anomalies injected by LLMs (`[ || ]`, `{ 0 : N0 }`, `</ color >`) are auto-healed without reprompting.
   - Discrepancies in injected linebreaks (`[|]`, `[||]`), engine tokens (`{0:N0}`, `{title}`), or lingering CJK characters are logged as warnings and tracked in run stats.
7. **Atomic Writes**: All JSON outputs are written to temporary files and renamed atomically.
8. **Testing Guardrails**: All code changes must pass:
   ```bash
   pytest tests/ -v --cov=lom_translate --cov-report=term-missing
   ruff check lom_translate tests
   ruff format --check lom_translate tests
   mypy lom_translate tests
   ```

---

# CLI Usage

```bash
# Translation Mode
lom-translate -m translate -i Resource/LeanLocalJson -od translated_output

# Improvement Mode
lom-translate -m improve -i Resource/LeanLocalJson -rd raw_translations -od improved_output
```
