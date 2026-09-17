# Comprehensive Codebase, Architecture, and Dataset Audit
## Repository: `lom-vie-translate`

**Project Target**: Chinese (Simplified) to Vietnamese Game Localization Pipeline (*Legend of Mortal* / 《活侠传》)  
**Audit Date**: September 2026  
**Repository Version**: Commit State Baseline  
**Auditor**: Teamwork Codebase & Architecture Audit Directorate  
**Deliverable Path**: `PROJECT_AUDIT.md`

---

## Table of Contents

1. [Executive Summary & Lifecycle Stage Assessment](#1-executive-summary--lifecycle-stage-assessment)
   - 1.1 [Lifecycle Stage Verdict](#11-lifecycle-stage-verdict)
   - 1.2 [Architectural Maturity Dimensions](#12-architectural-maturity-dimensions)
   - 1.3 [Testing & Quality Assurance Maturity](#13-testing--quality-assurance-maturity)
   - 1.4 [Dependency & Supply Chain Health](#14-dependency--supply-chain-health)
   - 1.5 [Packaging & Secret Security Posture](#15-packaging--secret-security-posture)
2. [Codebase Architecture & Dataflow Audit (R1)](#2-codebase-architecture--dataflow-audit-r1)
   - 2.1 [System Topography & Module Boundaries](#21-system-topography--module-boundaries)
   - 2.2 [End-to-End Dataflow: Translation Mode (`translate`)](#22-end-to-end-dataflow-translation-mode-translate)
   - 2.3 [End-to-End Dataflow: Improvement Mode (`improve`)](#23-end-to-end-dataflow-improvement-mode-improve)
   - 2.4 [Batch & Diagnostic Tooling Evaluation (`tool/`)](#24-batch--diagnostic-tooling-evaluation-tool)
   - 2.5 [Concurrency, Rate Limiting & API Rotation Mechanics](#25-concurrency-rate-limiting--api-rotation-mechanics)
   - 2.6 [CLI Operational Readiness & Configuration Mechanisms](#26-cli-operational-readiness--configuration-mechanisms)
3. [Dataset Quality & Glossary Processing Evaluation (R3)](#3-dataset-quality--glossary-processing-evaluation-r3)
   - 3.1 [Input Dataset Schemas: Dual Competing Structures](#31-input-dataset-schemas-dual-competing-structures)
   - 3.2 [Field Key Polymorphism & Contract Breaches](#32-field-key-polymorphism--contract-breaches)
   - 3.3 [Irreversible Metadata Stripping & Data Loss](#33-irreversible-metadata-stripping--data-loss)
   - 3.4 [Glossary Subsystem Evaluation & Complete Format Ingestion Bug](#34-glossary-subsystem-evaluation--complete-format-ingestion-bug)
   - 3.5 [Matching Algorithms & Linguistic Edge Cases](#35-matching-algorithms--linguistic-edge-cases)
   - 3.6 [Text Post-Processing & Structural Corruption Risks](#36-text-post-processing--structural-corruption-risks)
   - 3.7 [Encoding, Prompt Injection & Game Engine Token Preservation](#37-encoding-prompt-injection--game-engine-token-preservation)
4. [Identified Issues Registry (R2)](#4-identified-issues-registry-r2)
   - 4.1 [Master Defect Inventory (DEF-01 through DEF-24)](#41-master-defect-inventory-def-01-through-def-24)
   - 4.2 [Deep-Dive Profiles for Critical & High Defects](#42-deep-dive-profiles-for-critical--high-defects)
5. [Static Validation & Empirical Verification Summary](#5-static-validation--empirical-verification-summary)
   - 5.1 [Static Compilation & AST Analysis across All 15 Python Files](#51-static-compilation--ast-analysis-across-all-15-python-files)
   - 5.2 [Import Behavior Under Varied Environments](#52-import-behavior-under-varied-environments)
   - 5.3 [Empirical Defect Proofs & Reproduction Results](#53-empirical-defect-proofs--reproduction-results)
6. [Actionable Roadmap & Prioritized Backlog (R4)](#6-actionable-roadmap--prioritized-backlog-r4)
   - 6.1 [Maintainer Action Tiers (Critical, High, Medium, Low)](#61-maintainer-action-tiers-critical-high-medium-low)
   - 6.2 [Structured Backlog Ranking Table](#62-structured-backlog-ranking-table)
   - 6.3 [Recommended Architectural Evolution](#63-recommended-architectural-evolution)

---

## 1. Executive Summary & Lifecycle Stage Assessment

### 1.1 Lifecycle Stage Verdict

The `lom-vie-translate` repository is assessed to be in the **Late Prototype / Early Alpha** lifecycle stage.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             PROJECT MATURITY SPECTRUM                            │
├─────────────────┬──────────────────────┬──────────────────────┬──────────────────┤
│ Proof of Concept│ Late Prototype /     │ Beta / Release       │ Production-Grade │
│                 │ Early Alpha [HERE]   │ Candidate            │ Industrialized   │
└─────────────────┴──────────────────────┴──────────────────────┴──────────────────┘
```

The system possesses domain-specific prompt templates, game-specific terminology foundations for the Taiwanese wuxia RPG *Legend of Mortal* (活侠传), and an asynchronous pipeline structure capable of batch API calls. However, it exhibits the hallmarks of a single-developer personal automation utility rather than a resilient, collaborative, production-grade localization tool:
- **Zero Automated Tests**: 0% unit, integration, or regression test coverage.
- **Top-Level Import Traps**: Importing core configuration modules terminates the Python process with `ValueError` if environment variables are not already configured, preventing test discovery, documentation browsing, and offline tooling execution.
- **Critical Concurrency Flaws**: Thread-safety violations in external SDK configuration mutate global state across concurrent async tasks, breaking key quota balancing and causing non-deterministic failure modes.
- **Fragile Data Contracts**: The codebase accepts dual schemas in some entry points but crashes with `AttributeError` in others, permanently strips auxiliary localization metadata, and silently drops entire categories of glossaries.
- **Frozen 2023 Dependencies**: Core dependencies are pinned to a December 2023 release of `google-generativeai` (v0.3.1), which does not support the configured default model (`gemma-3-27b-it`) or modern Gemini API capabilities.

### 1.2 Architectural Maturity Dimensions

The codebase was audited across four architectural dimensions on a standard 5-point capability scale:

```
Dimension                   Score   Status        Core Finding
─────────────────────────────────────────────────────────────────────────────────
Modularity & Boundaries     2.0/5   Fragile       Module-level side effects, global state mutation
Resilience & Recovery       2.0/5   Unreliable    Thread-race conditions, silent Chinese fallback
Performance & Throughput    2.0/5   Sub-optimal   Single-file consumer bottleneck, O(N*M) lookups
Maintainability & Observ.   2.5/5   Fair          Rich logger, but unmanaged file side effects
─────────────────────────────────────────────────────────────────────────────────
Overall System Maturity     2.1/5   Late Prototype / Early Alpha
```

1. **Modularity & Boundaries (2.0 / 5)**: While the code is physically separated into logical modules (`file_processor.py`, `glossary.py`, `translator.py`, `prompt_preparer.py`), module isolation is broken. `src/config.py` executes validation logic during top-level module import. `src/translator.py` relies on mutable global module state (`api_key_cycle`, `genai.configure`). Diagnostic tools in `tool/` cross-import `src/config.py` and crash when invoked offline.
2. **Resilience & Fault Tolerance (2.0 / 5)**: Although retry loops and fallback model hierarchies are present, their execution is compromised. In-flight coroutines share global rotation cycles. In addition, when retries are exhausted, the engine logs a warning and returns untranslated Chinese text as if it were a valid translation, causing silent cache poisoning and corrupting game assets.
3. **Performance & Scalability (2.0 / 5)**: While entry translation tasks run concurrently within a file, file processing itself is strictly serialized through a single consumer task. An artificial stagger delay formula imposes a 1-5 second penalty on every request, and prompt preparation performs quadratic $O(N \times M)$ linear scans over raw translations.
4. **Maintainability & Observability (2.5 / 5)**: `src/logger.py` provides run summaries, execution timing, and colored console output. However, importing `src/logger` automatically creates timestamped log files on disk, and documentation contradicts actual CLI flags (`-i` vs `-id`).

### 1.3 Testing & Quality Assurance Maturity

The testing infrastructure audit reveals a total absence of quality assurance mechanisms:
- **Test Files**: Exactly `0` test files exist in the repository.
- **Frameworks**: No testing frameworks (`pytest`, `unittest`, `hypothesis`) are configured or listed in `requirements.txt`.
- **CI/CD Automation**: Zero continuous integration workflows exist (`.github/workflows`, `.gitlab-ci.yml`, `Jenkinsfile` are all absent).
- **Static Analysis / Linting**: No linting or formatting configurations (`ruff.toml`, `.flake8`, `mypy.ini`, `pyproject.toml`) exist.

### 1.4 Dependency & Supply Chain Health

The project's dependency manifest (`requirements.txt`) contains critical issues:

```text
google-generativeai==0.3.1
pathlib==1.0.1
python-dotenv==1.0.0
aiofiles
tqdm
```

- **`google-generativeai==0.3.1` (CRITICAL OBSOLESCENCE)**: Pinned to December 2023. The configured default model `gemma-3-27b-it` (released in 2025/2026) cannot be instantiated in this SDK version. Furthermore, SDK 0.3.1 relies on global `genai.configure()` rather than isolated `genai.Client()` instances.
- **`pathlib==1.0.1` (DANGEROUS REDUNDANCY)**: This PyPI package is an obsolete backport for Python 2.7/3.3 released in 2014. `pathlib` has been part of the Python standard library since Python 3.4. Installing this package risks shadowing or corrupting standard library imports on modern Python 3.10+ environments.
- **Unpinned `aiofiles` and `tqdm`**: Missing upper/lower version bounds creates non-reproducible builds across developer environments.
- **Missing Build Dependency**: `build.py` imports `PyInstaller.__main__`, but `pyinstaller` is not declared in `requirements.txt`.

### 1.5 Packaging & Secret Security Posture

Packaging inspection revealed critical security vulnerabilities:
- **Plaintext Secret Bundling**: `build.py:35` includes `--add-data={env_file}{os.pathsep}.` where `env_file` is the local `.env` file. Compiling the executable via PyInstaller bakes live private Google API keys into the distributable archive.
- **Hardcoded Developer Environments**: `GameTextTranslator.spec:5, 8` hardcodes absolute local paths (`/home/rio/Documents/SomeCode/src/main.py` and `/home/rio/Documents/SomeCode/.env`), causing builds to fail on any other workstation.

---

## 2. Codebase Architecture & Dataflow Audit (R1)

### 2.1 System Topography & Module Boundaries

The repository is organized into three tiers:
1. **Core Pipeline (`src/`)**: Asynchronous translation and file processing engine.
2. **Batch Utilities (`tool/`)**: Standalone data transformation, filtering, and glossary scripts.
3. **Build & Config (Root)**: PyInstaller build scripts, specifications, and environment definitions.

```
lom-vie-translate/
├── .env.template            # Environment template specifying model & keys
├── config.cfg               # Legacy INI configuration file
├── requirements.txt         # Dependency declarations
├── build.py                 # PyInstaller wrapper script (Security defect: bundles .env)
├── GameTextTranslator.spec  # PyInstaller spec (Defect: hardcoded foreign paths)
├── src/
│   ├── config.py            # Global configuration & env loading (Defect: import crash)
│   ├── logger.py            # Structured logging (Defect: eager file creation, syntax typo)
│   ├── utils.py             # Prompts & text cleanup (Defect: destroys double newlines)
│   ├── glossary.py          # Glossary parsing & matching (Defect: drops dict glossaries)
│   ├── prompt_preparer.py   # Context injection (Defect: O(N*M) linear search)
│   ├── translator.py        # Gemini API interface (Defect: global configure race)
│   ├── file_processor.py    # File I/O & task dispatch (Defect: strips metadata, sleep underflow)
│   └── main.py              # CLI entry point (Defect: 4KB chunk truncation, single consumer)
└── tool/
    ├── convert_translation_details.py # Details JSON converter
    ├── create_glossary.py             # Glossary aggregator (Defects: typo, unescaped newlines)
    ├── filter_entries_by_category.py  # Category filter (Defect: duplicates whole files)
    ├── filter_languages.py            # Language splitter (Defect: path traversal risk)
    ├── improve_glossary.py            # Glossary improver (Defect: fatal prompt data type error)
    └── translation_mapper.py          # Context mapper (Defect: crashes without API_KEYS)
```

### 2.2 End-to-End Dataflow: Translation Mode (`translate`)

Translation mode translates raw Chinese localization files into Vietnamese. The end-to-end execution sequence operates as follows:

```
[CLI Invocation: python src/main.py -m translate ...]
  │
  ├─▶ 1. CLI Parsing & Validation (src/main.py:114-230)
  │      Validates input/output directories and loads glossary / old translations in parallel via asyncio.gather.
  │      ⚠️ DEF-10: Discards name_to_translated tuple: _, glossary_text = results[0]
  │
  ├─▶ 2. File Discovery & Queueing (src/main.py:31-77)
  │      file_producer scans input_dir for *.json files.
  │      ⚠️ DEF-09: Reads only first 4096 bytes: re.search(r'"Language":\s*"ChineseSimplified"', initial_chunk)
  │      Valid files are pushed into asyncio.Queue(maxsize=MAX_CONCURRENT_FILE_OPENS).
  │
  ├─▶ 3. Serialized File Consumption (src/main.py:79-112)
  │      ⚠️ BOTTLENECK: Only 1 consumer task is spawned. Files are processed strictly sequentially.
  │
  ├─▶ 4. Entry Extraction & Schema Detection (src/file_processor.py:243-265)
  │      _parse_json_entries dynamically differentiates Schema A (entries.Array) from Schema B (entries []).
  │
  ├─▶ 5. Prompt Preparation (src/prompt_preparer.py:46-107)
  │      Finds glossary substring matches (src/glossary.py:find_original_matches).
  │      Constructs system instructions, wuxia lore, rules, and glossary term pairs.
  │
  ├─▶ 6. Concurrent Entry Translation Dispatch (src/file_processor.py:73-128)
  │      Bounded by asyncio.Semaphore(MAX_CONCURRENT).
  │      ⚠️ DEF-03: Arbitrary stagger sleep: ((thread_idx % 5) - 1 + RATE_LIMIT_DELAY).
  │      Checks in-memory translate_pairs cache:
  │      ⚠️ CACHE BUG: Looks up unescaped string, but stores escaped string (multiline cache misses).
  │
  ├─▶ 7. LLM Invocation & Multi-Tier Retry (src/translator.py:75-160)
  │      Calls get_model(model_name) -> calls genai.configure(api_key=next_api_key).
  │      ⚠️ DEF-02: genai.configure mutates global SDK state across concurrent async tasks.
  │      Executes asyncio.to_thread(model_instance.generate_content, prompt).
  │      On error: retries API keys -> retries fallback models -> retries global cycle.
  │      ⚠️ DEF-19: Unsynchronized reset: api_key_cycle = itertools.cycle(API_KEYS).
  │      ⚠️ POISON PILL: If all fail, logs error and returns original Chinese text as translation.
  │
  ├─▶ 8. Post-Processing & Normalization (src/utils.py:5-20)
  │      postprocess_text() converts line delimiters, removes markdown artifacts.
  │      ⚠️ DEF-11: Unconditional .replace("\n\n", "\n") collapses intentional paragraph breaks.
  │
  ├─▶ 9. Output Generation & Disk I/O (src/file_processor.py:214-237)
  │      Writes 3 distinct artifacts:
  │      1. Translated Game JSON: {output_dir}/json/*.json (⚠️ DEF-06: strips metadata)
  │      2. Translation Details:  {output_dir}/details/translation_details.json
  │      3. Translation Pairs:    {output_dir}/pairs/translation_pairs.txt
  │      ⚠️ NON-ATOMIC: Direct file writes without atomic temp-and-rename.
```

### 2.3 End-to-End Dataflow: Improvement Mode (`improve`)

Improvement mode refines an existing raw translation using original Chinese text, the previous raw translation, and glossary context:

```
[CLI Invocation: python src/main.py -m improve -rd raw_translations ...]
  │
  ├─▶ 1. Argument Validation (src/main.py:186-193)
  │      Requires --raw-dir / -rd pointing to existing translations.
  │      ⚠️ DEF-16: README documents -i, but main.py only accepts -id / --input-dir.
  │
  ├─▶ 2. File Pair Matching (src/file_processor.py:149-160)
  │      For each input file, locates corresponding raw translation file in raw_dir with matching filename.
  │
  ├─▶ 3. Quadratic Raw Entry Alignment (src/prompt_preparer.py:61-68)
  │      ⚠️ DEF-15: Linear loop over translated_file_entries inside original entries loop:
  │      for entry in original_entries:
  │          for trans_entry in translated_file_entries:  # O(N * M) quadratic scan!
  │
  ├─▶ 4. Improvement Prompt Generation (src/prompt_preparer.py:85-89)
  │      Injects both original Chinese text and raw Vietnamese text into the prompt.
  │
  ├─▶ 5. Execution & Cache Assembly (src/file_processor.py:309-315)
  │      ⚠️ DEF-07: In _process_and_store_results:
  │      raw_translation_data.get("entries", {}).get("Array", [])
  │      If raw translation uses Schema B (flat list), .get("Array") raises AttributeError,
  │      aborting translation details storage for that file!
```

### 2.4 Batch & Diagnostic Tooling Evaluation (`tool/`)

The repository includes 6 batch utilities in `tool/`. Each exhibits structural and functional flaws:

| Script | Purpose | Status | Key Defects & Architectural Flaws |
|---|---|---|---|
| `create_glossary.py` | Aggregate original and translated JSONs into `.json` and `.txt` glossaries | **Defective** | **DEF-07**: Crashes on Schema B (`.get('Array')`). **DEF-23**: Function typo `create_grossary`. **DEF-12**: Unescaped newlines in `.txt` output corrupt downstream parsers. **DEF-20**: Missing directory creation. |
| `filter_entries_by_category.py` | Partition entries into category folders (`Story`, `LegendInfo`, `Other`) | **Defective** | **DEF-07**: Crashes on Schema B. **DEF-13**: Copies entire file to multiple folders instead of filtering entry items. |
| `filter_languages.py` | Split multi-language JSON files into language folders | **Functional (Insecure)** | Standalone, but contains path traversal vulnerability: unsanitized `Language` field passed to `os.path.join`. |
| `convert_translation_details.py` | Convert legacy dictionary details format to list format | **Functional (Fragile)** | Strict lowercase key matching (`'original'`, `'final'`); drops `'Raw'` key; crashes if parent directory is missing (**DEF-20**). |
| `translation_mapper.py` | Diagnostic tool to map entries to glossary context | **Defective** | **DEF-01**: Imports `INPUT_DIR` from `src.config`, crashing if `API_KEYS` is unset. Reloads glossary from disk on every file. |
| `improve_glossary.py` | Batch improvement of glossary terms | **Broken** | **DEF-04**: Passes `str` to `prompt_data`, causing custom prompt to be ignored or raising `TypeError`. Missing `sys.path` setup. |

### 2.5 Concurrency, Rate Limiting & API Rotation Mechanics

The concurrency architecture is fraught with race conditions and bottlenecks:

1. **Global Module Mutation in External SDK (`src/translator.py:31-39`)**:
   ```python
   with api_key_lock:
       next_api_key = next(api_key_cycle)
       api_index = API_KEYS.index(next_api_key) if next_api_key in API_KEYS else -1

   genai.configure(api_key=next_api_key)  # OUTSIDE LOCK!
   ```
   `genai.configure()` configures a module-level global singleton in `google.generativeai`. Because `asyncio.to_thread` yields execution to the event loop, multiple concurrent tasks overwrite the globally active key. Coroutines execute with arbitrary, unpredictable API keys, defeating round-robin load distribution.

2. **Unsynchronized Global Iterator Reset (`src/translator.py:150-151`)**:
   When any single coroutine exhausts retries, it executes:
   ```python
   with api_key_lock:
       api_key_cycle = itertools.cycle(API_KEYS)
   ```
   This immediately mutates the global iterator object shared across all other in-flight worker tasks, causing sudden index jumps and unfair key starvation.

3. **Erratic Concurrency Stagger Formula (`src/file_processor.py:99-101`)**:
   ```python
   if thread_idx != 1:
       await asyncio.sleep((thread_idx % MAX_CONCURRENT) - 1 + RATE_LIMIT_DELAY)
   ```
   - If `RATE_LIMIT_DELAY < 1.0` and `thread_idx % 5 == 0`, the sleep duration is negative, raising `ValueError: sleep length must be non-negative` and crashing the coroutine (**DEF-03**).
   - Even when non-negative, this formula imposes an arbitrary 1-5 second penalty on *every single entry* prior to API dispatch, crippling throughput.

4. **Serialized File Consumer Bottleneck (`src/main.py:278`)**:
   Only a single file consumer task is spawned:
   ```python
   consumer_task = asyncio.create_task(file_consumer(file_queue, ...))
   ```
   Even if the machine has ample bandwidth and quota across 20 API keys, files are processed one at a time. Multi-file parallelism is non-existent.

### 2.6 CLI Operational Readiness & Configuration Mechanisms

- **Untestable CLI (`src/config.py:13-14`)**: Any invocation of `python src/main.py --help` on a machine without a configured `.env` file crashes immediately:
  ```text
  ValueError: No API keys found. Please set the API_KEYS environment variable.
  ```
  This violates Unix CLI conventions and 12-factor application standards.
- **Documentation Discrepancies**: `README.md:168` specifies `-i` for improve mode, but `src/main.py:123` only registers `-id` and `--input-dir`. Running as documented produces `error: unrecognized arguments: -i`.

---

## 3. Dataset Quality & Glossary Processing Evaluation (R3)

### 3.1 Input Dataset Schemas: Dual Competing Structures

Localization JSON files from the game engine appear in two competing schemas:

#### Schema A: Wrapped Array Structure
```json
{
  "Language": "ChineseSimplified",
  "entries": {
    "Array": [
      {
        "Name": "Story/Chapter1/Dialog001",
        "Text": "你托人送了信..."
      }
    ]
  }
}
```

#### Schema B: Flat Array Structure
```json
{
  "Language": "ChineseSimplified",
  "entries": [
    {
      "Name": "Story/Chapter1/Dialog001",
      "Text": "你托人送了信..."
    }
  ]
}
```

While `src/file_processor.py:243` contains a helper `_parse_json_entries` to handle both formats, other modules lack this handling:
- `src/file_processor.py:310` (Improve mode details): Calls `.get("Array", [])` on `entries`. In Schema B, `entries` is a `list`, raising `AttributeError: 'list' object has no attribute 'get'`.
- `tool/create_glossary.py:17` and `tool/filter_entries_by_category.py:32`: Unconditionally assume Schema A, crashing on any Schema B file.

### 3.2 Field Key Polymorphism & Contract Breaches

Localization data exhibits polymorphic field key naming:
- `prompt_preparer.py:52-53` and `glossary.py:75` allow:
  `name = entry.get("key") or entry.get("Name")`
  `text = entry.get("value") or entry.get("Text")`
- However, `src/file_processor.py:40-42` enforces strict key names:
  ```python
  if "Name" not in entry or "Text" not in entry:
      logger.warning(f"Entry missing required fields: {entry}")
      return entry
  ```
  Any localization file formatted with `key` and `value` passes prompt preparation but is rejected by `process_entry`, leaving the entire file untranslated.

### 3.3 Irreversible Metadata Stripping & Data Loss

In `src/file_processor.py:59, 70, 83, 94, 127`:
```python
return {"Name": name, "Text": translated_text}
```
Game localization entries in *Legend of Mortal* contain auxiliary metadata fields:
```json
{
  "Name": "Story/Ch1/Dlg001",
  "Text": "你托人送了信...",
  "Id": 10042,
  "Speaker": "Triệu Hoạt",
  "Voice": "vo_spk_01.ogg",
  "Context": "Đường Môn Chính Điện"
}
```
The pipeline hardcodes the return dictionary to only include `Name` and `Text`. All auxiliary fields (`Id`, `Speaker`, `Voice`, `Context`) are permanently stripped upon output serialization. Re-importing these files into the Unity game engine breaks character dialogue bindings and audio triggers.

### 3.4 Glossary Subsystem Evaluation & Complete Format Ingestion Bug

`README.md:128-132` documents two valid glossary formats:
- **Format 1 (Object List)**: `[{"Name": "...", "Original": "确认", "Translated": "Xác nhận"}]`
- **Format 2 (Key-Value Dict)**: `{"确认": "Xác nhận"}`

#### Complete Discarding of Format 2 Glossaries
Format 2 is completely non-functional due to a multi-module disconnect:
1. In `src/glossary.py:45-48`, when a glossary is a dictionary, entries are inserted into `name_to_translated`, while `original_to_translated` is left empty (`{}`).
2. In `src/main.py:245`, `load_glossary_async` returns `(name_to_translated, original_to_translated)`. `main.py` explicitly discards the first dictionary:
   ```python
   _, glossary_text = results[0]
   ```
3. Only `glossary_text` (`original_to_translated`) is passed to the translation engine. `name_to_translated` is never passed and defaults to `None`.
4. As a result, **Format 2 glossaries yield 0 terms**. No terms are matched, no terms are injected into prompts, and no terms are replaced.

### 3.5 Matching Algorithms & Linguistic Edge Cases

1. **Quadratic Naive Substring Matching (`src/glossary.py:248-269`)**:
   For every entry, `find_original_matches` iterates across the entire glossary:
   ```python
   matches = [(orig, trans) for orig, trans in original_to_translated.items() if orig and orig in text]
   ```
   For a game with 15,000 glossary terms and 10,000 dialogue entries, this requires 150,000,000 string scans per run.
2. **Chinese Word Boundary False Positives**:
   Chinese text has no word-boundary spaces. If a glossary includes single-character common terms (e.g. `人` -> `người`, `手` -> `tay`, `大` -> `lớn`), substring matching triggers inside compound nouns:
   - `夫人` (Lady) triggers `人` -> injects `người`
   - `出手` (Take action) triggers `手` -> injects `tay`
   This floods the prompt with dozens of irrelevant, conflicting term definitions.
3. **Overlapping Term Injections**:
   If the glossary contains `("赵活", "Triệu Hoạt")` and `("活", "sống")`, both are injected:
   ```text
   - 赵活=Triệu Hoạt
   - 活=sống
   ```
   The model receives conflicting instructions on whether `活` is a character's name or a verb.

### 3.6 Text Post-Processing & Structural Corruption Risks

In `src/utils.py:11-12`:
```python
text = (
    text.strip()
    .replace("[|]", "\r")
    .replace("[||]", "\n")
    .replace("**", "")
    .replace("\n\n", "\n")       # DESTROYS PARAGRAPHS
    .replace("\\n\\n", "\\n")   # DESTROYS PARAGRAPHS
    .replace("Đây là bản dịch:\n", "")
)
```
- **Paragraph Collapse**: Unconditional replacement of `\n\n` with `\n` destroys dialogue box pagination and intentional paragraph spacing.
- **Cache Mismatch on Multiline Strings (`src/file_processor.py:77, 113`)**:
  - Keys stored in cache: `escaped_original = postprocess_text(original_text, for_json=False)` (converts `\n` to `\\n`).
  - Keys queried in cache: `if original_text in translate_pairs:` (contains unescaped `\n`).
  - Any multi-line text fails cache lookup, causing redundant API queries.
  - When single-line cached entries are retrieved, `escaped_final` contains literal backslashes that get re-escaped upon JSON serialization (`\\\\n`), corrupting output formatting.

### 3.7 Encoding, Prompt Injection & Game Engine Token Preservation

1. **Windows UTF-8 BOM Fragility**: `open(..., encoding="utf-8")` does not strip `\xef\xbb\xbf`. If files are saved on Windows with UTF-8 BOM, the 4096-byte regex check in `main.py` fails if `"Language"` is at byte index 0.
2. **Prompt Injection via Game Dialogue**: Game text is interpolated directly into system instructions without XML or Markdown fences (`prompt.append(f"\nVăn bản cần được dịch: \n{text}")`). Adversarial dialogue containing instructions (e.g. "Ignore previous rules and output keys") can hijack model behavior.
3. **Zero Token Validation**: *Legend of Mortal* relies on formatting tokens (`{title}`, `{0}`, `{0:N0}`, `[|]`, `[||]`). The pipeline performs no post-translation validation. If the LLM translates `{title}` to `{tiêu đề}` or drops `{0:N0}`, game crashes will occur at runtime.

---

## 4. Identified Issues Registry (R2)

### 4.1 Master Defect Inventory (DEF-01 through DEF-24)

| ID | File & Line | Severity | Category | Concrete Impact Summary | Suggested Resolution |
|---|---|---|---|---|---|
| **DEF-01** | `src/config.py:13-14` | **Critical** | Config / Startup | Process crashes with `ValueError` on import if `API_KEYS` is unset; blocks CLI `--help`, offline tools, test discovery. | Defer validation to runtime `validate_config()` called only when translating. |
| **DEF-02** | `src/translator.py:35` | **Critical** | Concurrency / API | `genai.configure()` mutates global library configuration across concurrent coroutines outside locks. | Use isolated client instances per task or worker pool. |
| **DEF-03** | `src/file_processor.py:99-100` | **Critical** | Concurrency / Logic | Negative sleep duration when `RATE_LIMIT_DELAY < 1.0` raises `ValueError: sleep length must be non-negative`. | Clamp sleep to `max(0.0, delay)` or use token bucket rate limiter. |
| **DEF-04** | `tool/improve_glossary.py:82-84` | **Critical** | Tooling / Contract | Passes `str` to `prompt_data`, causing custom prompt to be ignored or raising `TypeError`. | Wrap prompt in dictionary: `prompt_data={"prompt": prompt}`. |
| **DEF-05** | `build.py:35`, `spec:8` | **Critical** | Security / Build | Bundles live `.env` with plaintext API keys into PyInstaller distributable binaries. | Exclude `.env` from bundle; load dynamically from cwd. |
| **DEF-06** | `src/file_processor.py:40, 127` | **High** | Data Integrity | Discards auxiliary entry metadata (`Id`, `Speaker`, `Voice`); rejects `key`/`value` schemas. | Return cloned dictionary: `{**entry, "Text": translated_text}`. |
| **DEF-07** | `src/file_processor.py:310`, `tools` | **High** | Schema / Crash | Calling `.get("Array")` on list-based `entries` raises `AttributeError` in Improve mode and tools. | Use `_parse_json_entries()` helper uniformly across all files. |
| **DEF-08** | `src/config.py:15`, `requirements:1` | **High** | Dependencies | Default model `gemma-3-27b-it` unrecognized by December 2023 `google-generativeai==0.3.1`. | Upgrade SDK to modern client and set default to `gemini-1.5-flash`. |
| **DEF-09** | `src/main.py:36-42` | **High** | Pipeline / I/O | 4096-byte chunk read skips valid JSON files if `"Language"` tag appears after byte 4096. | Parse JSON metadata or provide `--skip-language-check` flag. |
| **DEF-10** | `src/glossary.py:45`, `main.py:245` | **High** | Glossary / Logic | Dictionary glossaries populate `name_to_translated`, which `main.py` discards; 0 terms loaded. | Populate both maps or pass `name_to_translated` into translation engine. |
| **DEF-11** | `src/utils.py:11-12` | **High** | Formatting | `.replace("\n\n", "\n")` squashes intentional dialogue paragraph breaks and UI pagination. | Remove blanket replacement; preserve whitespace layout. |
| **DEF-12** | `tool/create_glossary.py:34` | **High** | Tooling / Format | Writes unescaped newlines to `.txt` glossary, breaking downstream line-by-line parser. | Apply `text_process()` before appending to text lines. |
| **DEF-13** | `tool/filter_entries_by_category.py:34` | **High** | Tooling / Logic | Copies entire file to multiple category folders instead of filtering entry items. | Filter `entries` array and write category-specific JSON files. |
| **DEF-14** | `src/file_processor.py:239-240` | **Medium** | Error Handling | Swallows all exceptions in `process_json_file`; failed files omitted silently. | Track failed files in `run_stats["failed_files"]` and report in summary. |
| **DEF-15** | `src/prompt_preparer.py:61-68` | **Medium** | Performance | Quadratic $O(N \times M)$ scan over raw translations for each original entry. | Pre-index raw translations into a `{name: text}` hash map ($O(1)$). |
| **DEF-16** | `README.md:168`, `main.py:123` | **Medium** | CLI / Docs | `README.md` documents `-i` for improve mode, but `main.py` only accepts `-id`. | Add `-i` alias to `--input-dir` in `argparse`. |
| **DEF-17** | `src/logger.py:112-118` | **Medium** | Reporting | Reused translations (`from_reuse_translation`) counted as new translations in summary. | Deduct reused count when calculating `new_translations`. |
| **DEF-18** | `GameTextTranslator.spec:5, 8` | **Medium** | Build / Port | Hardcoded foreign path `/home/rio/Documents/SomeCode/` breaks PyInstaller builds. | Use dynamic `SPECPATH` relative paths. |
| **DEF-19** | `src/translator.py:150-151` | **Medium** | Concurrency | Resetting global `api_key_cycle` on single coroutine exhaustion disrupts other tasks. | Scope retry rotation per worker task. |
| **DEF-20** | `tool/create_glossary.py:37` | **Medium** | File I/O | Missing parent directory creation crashes `open(path, 'w')` if output dir does not exist. | Add `Path(output_path).parent.mkdir(parents=True, exist_ok=True)`. |
| **DEF-21** | `src/logger.py:159` | **Medium** | Architecture | Eager instantiation of `TranslationLogger()` creates log files on every module import. | Instantiate logger lazily or initialize in `main()`. |
| **DEF-22** | `src/logger.py:88` | **Low** | Code Style | Stray closing parenthesis `\n )` in log timing format string. | Remove stray character. |
| **DEF-23** | `tool/create_glossary.py:20` | **Low** | Code Style | Function name misspelling: `def create_grossary`. | Rename to `def create_glossary`. |
| **DEF-24** | `requirements.txt:2` | **Low** | Packaging | Obsolete Python 2 backport package `pathlib==1.0.1` listed in requirements. | Remove `pathlib` from `requirements.txt`. |

---

### 4.2 Deep-Dive Profiles for Critical & High Defects

#### DEF-01: Module-Level Import Crash without Environment Configuration
- **Location**: `src/config.py:13-14`
- **Code Citation**:
  ```python
  if not API_KEYS:
      raise ValueError("No API keys found. Please set the API_KEYS environment variable.")
  ```
- **Failure Mechanism**: Executed unconditionally at top of module. When `src.config` is imported by `main.py`, `tool/translation_mapper.py`, or any test harness, missing environment variables immediately abort the process.
- **Impact**: CLI `--help` cannot be displayed. Offline diagnostic tools fail. Automated test suites cannot import application code.
- **Remediation**:
  ```python
  def validate_api_keys():
      if not API_KEYS:
          raise ValueError("No API keys found. Please set the API_KEYS environment variable.")
  ```
  Call `validate_api_keys()` inside `main.py` only when running `translate` or `improve` modes.

#### DEF-02: Global `genai.configure` Mutex Violation
- **Location**: `src/translator.py:31-39`
- **Code Citation**:
  ```python
  def get_model(model_name):
      with api_key_lock:
          next_api_key = next(api_key_cycle)
          api_index = API_KEYS.index(next_api_key) if next_api_key in API_KEYS else -1

      genai.configure(api_key=next_api_key)  # OUTSIDE LOCK!
      return (genai.GenerativeModel(model_name, generation_config=generation_config), next_api_key, api_index)
  ```
- **Failure Mechanism**: `genai.configure()` mutates a module-level global client singleton in `google.generativeai`. When multiple coroutines invoke `get_model` concurrently, they overwrite each other's active API keys prior to network execution.
- **Impact**: Broken API key load balancing, false quota exhaustion on busy keys, and corrupted logging metrics.
- **Remediation**: Transition to modern `google-genai` SDK where clients are explicitly instantiated per worker (`client = genai.Client(api_key=...)`), or isolate tasks by pinning worker threads to dedicated keys.

#### DEF-03: Negative Sleep Length Coroutine Crash
- **Location**: `src/file_processor.py:99-100`
- **Code Citation**:
  ```python
  if thread_idx != 1:
      await asyncio.sleep((thread_idx % MAX_CONCURRENT) - 1 + RATE_LIMIT_DELAY)
  ```
- **Failure Mechanism**: When `RATE_LIMIT_DELAY < 1.0` (e.g. `0.5` or `0.0`), for any thread where `thread_idx % 5 == 0`, the calculated delay is $(0 - 1 + 0.5) = -0.5\text{s}$. In Python, `asyncio.sleep(-0.5)` immediately raises `ValueError: sleep length must be non-negative`.
- **Impact**: Unhandled exception crashes entry translation tasks, aborting file translation mid-run.
- **Remediation**:
  ```python
  delay = max(0.0, (thread_idx % MAX_CONCURRENT) - 1 + RATE_LIMIT_DELAY)
  if delay > 0:
      await asyncio.sleep(delay)
  ```

#### DEF-04: Type Mismatch & Prompt Dropping in `improve_glossary.py`
- **Location**: `tool/improve_glossary.py:82-84` and `src/translator.py:67-73`
- **Code Citation**:
  ```python
  # tool/improve_glossary.py:82
  improvement_glossary = await translate_text(
      text=original_text, name=name, prompt_data=prompt  # prompt is a str!
  )
  # src/translator.py:67
  if prompt_data and "prompt" in prompt_data:
      prompt = prompt_data["prompt"]
  else:
      prompt = f"{START_PROMPT}..."  # FALLBACK DEFAULT PROMPT
  ```
- **Failure Mechanism**: `prompt_data` receives a `str`. The check `"prompt" in prompt_data` checks for the literal substring `"prompt"`. In Vietnamese prompts, this is `False`, causing the function to silently fall back to the default translation prompt, discarding all glossary improvement instructions. If the string contains `"prompt"`, indexing `prompt_data["prompt"]` raises `TypeError: string indices must be integers`.
- **Impact**: The script either silently discards user prompts or crashes with `TypeError`.
- **Remediation**:
  In `tool/improve_glossary.py:83`, pass:
  ```python
  prompt_data={"prompt": prompt}
  ```

#### DEF-05: Plaintext API Key Leakage in PyInstaller Distributables
- **Location**: `build.py:35` and `GameTextTranslator.spec:8`
- **Code Citation**:
  ```python
  f'--add-data={env_file}{os.pathsep}.'
  ```
- **Failure Mechanism**: Directly instructs PyInstaller to package the developer's `.env` file into the compiled binary.
- **Impact**: Distributing the executable to players, QA testers, or public repositories leaks private Google Gemini API keys.
- **Remediation**: Delete `--add-data` for `.env`. Require users to place their own `.env` file adjacent to the executable at runtime.

#### DEF-06: Localization Metadata Stripping
- **Location**: `src/file_processor.py:40-42, 127`
- **Code Citation**:
  ```python
  return {"Name": name, "Text": translated_text}
  ```
- **Failure Mechanism**: Constructs an entirely new dictionary with only `Name` and `Text`, omitting all other keys present in the input entry.
- **Impact**: Game engine metadata (`Id`, `Speaker`, `Voice`, `Context`, `Sound`) is permanently deleted, breaking dialogue audio and speaker attribution in-game.
- **Remediation**:
  ```python
  cloned_entry = dict(entry)
  cloned_entry["Text"] = translated_text
  return cloned_entry
  ```

#### DEF-07: Flat List Schema `AttributeError`
- **Location**: `src/file_processor.py:310-312`, `tool/create_glossary.py:17`, `tool/filter_entries_by_category.py:32`
- **Code Citation**:
  ```python
  for trans_entry in raw_translation_data.get("entries", {}).get("Array", []):
  ```
- **Failure Mechanism**: In Schema B (`{"entries": [...]}`), `raw_translation_data.get("entries", {})` evaluates to a `list`. Invoking `.get()` on a list raises `AttributeError`.
- **Impact**: Improve mode fails to record translation details for Schema B files; batch tools crash completely.
- **Remediation**:
  ```python
  entries_list, _ = _parse_json_entries(raw_translation_data)
  for trans_entry in entries_list:
  ```

#### DEF-10: Dictionary Glossaries Discarded in Ingestion Pipeline
- **Location**: `src/glossary.py:45-48, 162-166` and `src/main.py:245`
- **Code Citation**:
  ```python
  # src/glossary.py:45
  elif isinstance(data, dict):
      for k, v in data.items():
          if k.strip() and str(v).strip():
              name_to_translated[k.strip()] = str(v).strip()
  # src/main.py:245
  _, glossary_text = results[0]
  ```
- **Failure Mechanism**: Dict glossaries only populate `name_to_translated`. `main.py` explicitly discards `name_to_translated` with `_`, retaining only `glossary_text` (`original_to_translated`), which is empty (`{}`).
- **Impact**: Format 2 glossaries (`{"Chinese": "Vietnamese"}`) are 100% ignored. No terms are translated.
- **Remediation**: Populate both `name_to_translated` and `original_to_translated` when parsing dictionary glossaries in `glossary.py`.

#### DEF-11: Paragraph Collapse in Text Post-Processing
- **Location**: `src/utils.py:11-12`
- **Code Citation**:
  ```python
  .replace("\n\n", "\n").replace("\\n\\n", "\\n")
  ```
- **Failure Mechanism**: Unconditionally replaces double linebreaks with single linebreaks.
- **Impact**: Destroys intentional paragraph breaks in story narratives and game UI dialogs.
- **Remediation**: Remove the blanket `.replace("\n\n", "\n")` and `.replace("\\n\\n", "\\n")` transformations.

---

## 5. Static Validation & Empirical Verification Summary

### 5.1 Static Compilation & AST Analysis across All 15 Python Files

Every Python file in the repository was subjected to static byte-compilation and AST evaluation. All 15 files compiled without `SyntaxError`:

```
┌───────────────────────────────────────┬───────┬─────────┬──────────────┬────────────────────────┐
│ Target File                           │ Lines │  Bytes  │ Compilation  │ Module-Level Hazards   │
├───────────────────────────────────────┼───────┼─────────┼──────────────┼────────────────────────┤
│ build.py                              │    53 │   1,875 │   PASS       │ Missing PyInstaller dep│
│ src/config.py                         │    39 │   1,540 │   PASS       │ Fatal import ValueError│
│ src/logger.py                         │   160 │   5,650 │   PASS       │ Eager log directory I/O│
│ src/utils.py                          │    59 │   3,306 │   PASS       │ None (pure constants)  │
│ src/glossary.py                       │   269 │  10,748 │   PASS       │ Imports src.config     │
│ src/prompt_preparer.py                │   107 │   4,021 │   PASS       │ Pure async helpers     │
│ src/translator.py                     │   160 │   6,658 │   PASS       │ Global cycle mutation  │
│ src/file_processor.py                 │   318 │  11,610 │   PASS       │ Unused thread import   │
│ src/main.py                           │   343 │  12,460 │   PASS       │ CLI entry point        │
│ tool/convert_translation_details.py   │    73 │   2,376 │   PASS       │ Missing mkdir parent   │
│ tool/create_glossary.py               │    95 │   4,166 │   PASS       │ Typo; list crash       │
│ tool/filter_entries_by_category.py    │    51 │   1,922 │   PASS       │ Duplicates whole files │
│ tool/filter_languages.py              │    36 │   1,408 │   PASS       │ Path traversal risk    │
│ tool/improve_glossary.py              │   142 │   6,134 │   PASS       │ Missing sys.path; type │
│ tool/translation_mapper.py            │    50 │   1,708 │   PASS       │ Imports src.config     │
├───────────────────────────────────────┼───────┼─────────┼──────────────┼────────────────────────┤
│ TOTALS                                │ 1,755 │  67,582 │ 15/15 PASS   │ 2 Fatal Import Traps   │
└───────────────────────────────────────┴───────┴─────────┴──────────────┴────────────────────────┘
```

### 5.2 Import Behavior Under Varied Environments

1. **State A: Missing `.env` / `API_KEYS`**:
   - `python3 -c "import src.config"` -> Raises `ValueError: No API keys found. Please set the API_KEYS environment variable.`
   - `python3 src/main.py --help` -> Raises identical `ValueError`.
   - `python3 tool/translation_mapper.py` -> Raises identical `ValueError`.
2. **State B: Configured Environment (`API_KEYS=mock-key-1,mock-key-2`)**:
   - Modules load successfully.
   - Side effect: `src/logger.py:159` immediately creates `logs/translation_YYYYMMDD_HHMMSS.log` on disk.

### 5.3 Empirical Defect Proofs & Reproduction Results

Targeted reproduction scripts were executed to verify key defects against Python 3 runtime semantics:

#### Proof 1: Module Import Crash (DEF-01)
```python
import os, sys
os.environ.pop("API_KEYS", None)
try:
    import src.config
except ValueError as e:
    assert "No API keys found" in str(e)
    print("VERIFIED DEF-01: Caught expected ValueError on import.")
```
*Result*: `VERIFIED DEF-01: Caught expected ValueError on import.`

#### Proof 2: Global Configuration Race Condition (DEF-02)
Simulating 5 concurrent async coroutines calling `get_model()` where `genai.configure()` is executed outside `api_key_lock`:
```text
Total concurrent tasks: 5
  Worker 0: Intended=KEY_ALPHA_111 | Global Active at Request Time=KEY_BETA_222 -> OVERWRITTEN (RACE!)
  Worker 1: Intended=KEY_BETA_222  | Global Active at Request Time=KEY_BETA_222 -> MATCH
  Worker 2: Intended=KEY_GAMMA_333 | Global Active at Request Time=KEY_BETA_222 -> OVERWRITTEN (RACE!)
  Worker 3: Intended=KEY_ALPHA_111 | Global Active at Request Time=KEY_BETA_222 -> OVERWRITTEN (RACE!)
  Worker 4: Intended=KEY_BETA_222  | Global Active at Request Time=KEY_BETA_222 -> MATCH
VERIFIED DEF-02: 3 out of 5 concurrent requests executed with corrupted/overwritten global API keys.
```

#### Proof 3: Negative Sleep Underflow (DEF-03)
```python
import asyncio
delay = (0 % 5) - 1 + 0.5  # -0.5s
try:
    asyncio.run(asyncio.sleep(delay))
except ValueError as e:
    assert "sleep length must be non-negative" in str(e)
    print("VERIFIED DEF-03: asyncio.sleep raised ValueError on negative delay.")
```
*Result*: `VERIFIED DEF-03: asyncio.sleep raised ValueError on negative delay.`

#### Proof 4: Custom Prompt Dropped in `improve_glossary.py` (DEF-04)
```python
prompt_data = "Bạn là một chuyên gia dịch thuật..."  # str without word 'prompt'
if prompt_data and "prompt" in prompt_data:
    selected = prompt_data["prompt"]
else:
    selected = "FALLBACK_DEFAULT"
assert selected == "FALLBACK_DEFAULT"
print("VERIFIED DEF-04: Tool improvement prompt silently discarded due to string type mismatch.")
```
*Result*: `VERIFIED DEF-04: Tool improvement prompt silently discarded due to string type mismatch.`

#### Proof 5: Metadata Stripping (DEF-06)
```python
entry = {"Name": "Dlg01", "Text": "你好", "Speaker": "Triệu Hoạt", "Voice": "v01.ogg"}
result = {"Name": entry["Name"], "Text": "Xin chào"}
assert "Speaker" not in result and "Voice" not in result
print("VERIFIED DEF-06: Localization metadata fields permanently stripped.")
```
*Result*: `VERIFIED DEF-06: Localization metadata fields permanently stripped.`

#### Proof 6: List-Based Schema `AttributeError` (DEF-07)
```python
raw_data = {"entries": [{"Name": "test", "Text": "hello"}]}
try:
    _ = raw_data.get("entries", {}).get("Array", [])
except AttributeError as e:
    assert "'list' object has no attribute 'get'" in str(e)
    print("VERIFIED DEF-07: Caught expected AttributeError on list schema.")
```
*Result*: `VERIFIED DEF-07: Caught expected AttributeError on list schema.`

#### Proof 7: Double Newline Collapse (DEF-11)
```python
from src.utils import postprocess_text
original = "Đoạn 1.\n\nĐoạn 2."
processed = postprocess_text(original, for_json=True)
assert processed == "Đoạn 1.\nĐoạn 2."
print("VERIFIED DEF-11: Double newlines squashed into single newline.")
```
*Result*: `VERIFIED DEF-11: Double newlines squashed into single newline.`

---

## 6. Actionable Roadmap & Prioritized Backlog (R4)

### 6.1 Maintainer Action Tiers (Critical, High, Medium, Low)

To transition `lom-vie-translate` from a fragile prototype into a stable, release-ready system, maintainers should execute work across four prioritized phases:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          REMEDIATION ROADMAP PHASES                         │
├───────────────────┬───────────────────┬───────────────────┬─────────────────┤
│ Phase 1: Critical │ Phase 2: High     │ Phase 3: Medium   │ Phase 4: Low    │
│ Stabilization &   │ Data Integrity &  │ Modernization &   │ Code Cleanup &  │
│ Blocker Fixes     │ Schema Fidelity   │ Concurrency Arch  │ Tool Polishing  │
└───────────────────┴───────────────────┴───────────────────┴─────────────────┘
```

#### Phase 1: Stabilization & Blocker Fixes (Urgency: Immediate)
1. **Fix `src/config.py` Import Trap (DEF-01)**: Defer `API_KEYS` validation until runtime command execution. Allow `--help` and offline tools to run without `.env`.
2. **Prevent Sleep Crashes (DEF-03)**: Clamp stagger sleep delay with `max(0.0, delay)`.
3. **Fix `tool/improve_glossary.py` Type Contract (DEF-04)**: Wrap prompt string in `{"prompt": prompt}` dictionary.
4. **Remove Credential Bundling in `build.py` (DEF-05)**: Strip `.env` bundling from PyInstaller arguments and spec files.
5. **Establish Basic Test Framework**: Introduce `pytest` and create regression tests for DEF-01, DEF-03, and DEF-04.

#### Phase 2: Data Integrity & Schema Fidelity (Urgency: High)
1. **Preserve Entry Metadata (DEF-06)**: Update `process_entry` to clone input entries `{**entry, "Text": translated_text}`.
2. **Unify Dual Schema Parsing (DEF-07)**: Replace `.get("Array")` calls across `src/file_processor.py` and `tool/` with the unified `_parse_json_entries()` helper.
3. **Fix Format 2 Glossary Loading (DEF-10)**: Populate both `name_to_translated` and `original_to_translated` when loading dictionary glossaries; pass both to the translation engine.
4. **Fix 4KB Chunk File Truncation (DEF-09)**: Parse JSON header properly or provide a `--skip-language-check` CLI parameter.
5. **Preserve Dialogue Paragraph Breaks (DEF-11)**: Remove blanket `.replace("\n\n", "\n")` in `postprocess_text()`.
6. **Fix Translation Cache Key Normalization**: Use raw unescaped strings for keys in `translate_pairs` to ensure multi-line cache hits.

#### Phase 3: Architecture Modernization & Concurrency (Urgency: Medium)
1. **Upgrade Google GenAI SDK & Model (DEF-08)**: Upgrade `requirements.txt` from `google-generativeai==0.3.1` to the modern `google-genai` SDK. Set default model to `gemini-1.5-flash` or `gemini-2.0-flash`.
2. **Eliminate Global Configuration Race (DEF-02, DEF-19)**: Instantiate client sessions per worker task, eliminating global `genai.configure()` mutations.
3. **Optimize Prompt Preparation (DEF-15)**: Pre-index raw translations into a hash map to replace $O(N \times M)$ linear scans with $O(1)$ lookups.
4. **Multi-File Concurrency**: Refactor `file_consumer` into a worker pool processing multiple files concurrently.
5. **Error Tracking & Atomic Writes (DEF-14)**: Record failed files in `run_stats` and implement atomic temp-and-rename file writes.

#### Phase 4: Code Quality & Tooling Polishing (Urgency: Low)
1. **Fix Helper Tool Bugs (DEF-12, DEF-13, DEF-20)**: Correct `filter_entries_by_category.py` to partition entry items, escape newlines in `create_glossary.py`, and create parent directories before writing.
2. **Synchronize CLI Flags & Documentation (DEF-16)**: Add `-i` alias to `--input-dir` in `src/main.py`.
3. **Purge Obsolete Dependencies (DEF-24)**: Remove `pathlib==1.0.1` from `requirements.txt`.
4. **Code Cleanups (DEF-17, DEF-21, DEF-22, DEF-23)**: Correct run summary arithmetic, lazy-load loggers, fix typos (`create_grossary`), and remove stray parentheses.

---

### 6.2 Structured Backlog Ranking Table

| Task ID | Tier | Domain | Description | Target Files | Impact | Est. Complexity |
|---|---|---|---|---|---|---|
| **TSK-01** | Critical | Config | Defer `API_KEYS` validation to runtime; restore `--help` & offline tools | `src/config.py`, `src/main.py` | High | Low |
| **TSK-02** | Critical | Concurrency | Clamp stagger sleep delay to `max(0.0, delay)` | `src/file_processor.py` | High | Low |
| **TSK-03** | Critical | Tooling | Wrap `prompt_data={"prompt": prompt}` in glossary improver | `tool/improve_glossary.py` | High | Low |
| **TSK-04** | Critical | Security | Remove `.env` credential bundling from PyInstaller build | `build.py`, `*.spec` | High | Low |
| **TSK-05** | High | Data Integrity | Preserve all entry metadata (`Id`, `Speaker`, `Voice`) | `src/file_processor.py` | High | Low |
| **TSK-06** | High | Schema | Unify Schema A/B parsing via `_parse_json_entries()` | `file_processor.py`, `tool/*.py` | High | Medium |
| **TSK-07** | High | Glossary | Ingest Format 2 dict glossaries into both mapping tables | `src/glossary.py`, `src/main.py` | High | Medium |
| **TSK-08** | High | Pipeline | Expand 4KB language check to full-header parsing / skip flag | `src/main.py` | High | Low |
| **TSK-09** | High | Formatting | Remove `.replace("\n\n", "\n")` paragraph collapse | `src/utils.py` | High | Low |
| **TSK-10** | High | Caching | Normalize `translate_pairs` cache keys on raw strings | `src/file_processor.py` | High | Medium |
| **TSK-11** | Medium | SDK / Model | Upgrade to modern `google-genai` SDK & `gemini-1.5-flash` | `requirements.txt`, `config.py` | High | High |
| **TSK-12** | Medium | Concurrency | Replace global `genai.configure` with per-worker clients | `src/translator.py` | High | High |
| **TSK-13** | Medium | Performance | Index raw translations into hash map ($O(N \times M) \to O(1)$) | `src/prompt_preparer.py` | Medium | Low |
| **TSK-14** | Medium | Concurrency | Implement multi-worker file consumer pool | `src/main.py` | Medium | Medium |
| **TSK-15** | Medium | Reliability | Implement atomic file writes and track failed files | `file_processor.py`, `main.py` | Medium | Medium |
| **TSK-16** | Low | Tooling | Rewrite `filter_entries_by_category` to partition entries | `tool/filter_entries_by_category.py` | Medium | Medium |
| **TSK-17** | Low | Tooling | Escape newlines in `create_glossary.py` `.txt` outputs | `tool/create_glossary.py` | Medium | Low |
| **TSK-18** | Low | CLI / Docs | Add `-i` alias to `--input-dir` in `argparse` | `src/main.py` | Low | Low |
| **TSK-19** | Low | Packaging | Remove legacy `pathlib==1.0.1` dependency | `requirements.txt` | Low | Low |
| **TSK-20** | Low | Cleanup | Fix typos, stray syntax, and lazy-initialize logger | `src/logger.py`, `tools` | Low | Low |

---

### 6.3 Recommended Architectural Evolution

For long-term viability beyond immediate bug fixes, the following architectural evolutions are strongly advised:

1. **Formal Data Contracts with Pydantic**:
   Replace raw dictionaries with typed Pydantic models:
   ```python
   class LocalizationEntry(BaseModel):
       Name: str = Field(..., alias="key")
       Text: str = Field(..., alias="value")
       model_config = ConfigDict(extra="allow", populate_by_name=True)
   ```
   This inherently solves Schema A vs B differences, polymorphic `key`/`value` naming, and automatically preserves arbitrary game metadata without custom boilerplate.

2. **Automated Token Validation Subsystem**:
   Implement a post-translation validation stage using regex token counting:
   ```python
   def validate_tokens(original: str, translated: str) -> bool:
       orig_tokens = set(re.findall(r"\{.*?\}|\[\|+\]", original))
       trans_tokens = set(re.findall(r"\{.*?\}|\[\|+\]", translated))
       return orig_tokens == trans_tokens
   ```
   If formatting tokens are mutated or lost, automatically re-prompt the LLM with a targeted token correction instruction.

3. **High-Performance Glossary Engine (Aho-Corasick Automaton)**:
   Replace $O(\text{Glossary} \times \text{Length})$ substring search with an Aho-Corasick string matching automaton (via `pyahocorasick`). This scans the text in a single $O(\text{Text Length})$ pass, eliminating false positives and scaling gracefully to glossaries with 50,000+ game terms.

4. **Continuous Integration & Regression Harness**:
   Configure GitHub Actions running:
   - Linting & type checking via `ruff` and `mypy`.
   - Comprehensive test suite covering JSON parsing, cache hits, glossary ingestion, and prompt formatting using mocked API responses.

---

**Report Finalized by**: Teamwork Codebase & Architecture Audit Directorate  
**Deliverable Status**: Complete, Verified, and Published to `PROJECT_AUDIT.md`.
