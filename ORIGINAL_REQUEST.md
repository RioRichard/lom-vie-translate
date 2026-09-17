# Original User Request

## 2026-09-15T04:31:10Z

Conduct a comprehensive codebase, architecture, and dataset analysis of the `lom-vie-translate` repository to establish the project's current lifecycle stage, identify existing technical debt, bugs, and data issues, evaluate dataset quality and glossary coverage, and map out current feature status and roadmap recommendations for maintainers to resume development.

Working directory: /home/rio/Documents/lom-vie-translate
Integrity mode: development

## Requirements

### R1. Codebase Architecture & Lifecycle Stage Analysis
Evaluate the entire codebase (`src/`, `tool/`, build scripts, and configuration files) to determine the project's current development stage and architectural maturity. Map out end-to-end dataflow for all supported modes (`translate`, `improve`), helper utilities, and concurrency/rate-limiting mechanisms.

### R2. Technical Debt & Defect Identification
Identify all existing bugs, architectural bottlenecks, configuration anomalies, unhandled edge cases, and error recovery vulnerabilities (such as API key rotation, quota handling, and file I/O safety). Document each finding with exact file and line references and severity classifications.

### R3. Dataset Quality & Glossary Processing Evaluation
Examine the schema expectations, data models, and processing logic for localization JSON inputs, glossary formats, and translation output details. Identify discrepancies, potential failure modes, missing validations, or data corruption risks across the translation and improvement pipelines.

### R4. Actionable Roadmap & Prioritized Backlog
Synthesize a concrete, prioritized backlog and implementation roadmap tailored for project maintainers. Organize recommendations into clear tiers (Critical, High, Medium, Low) with actionable guidance on how to continue, stabilize, and expand the project.

### R5. Comprehensive Audit Deliverable
Compile all analysis, findings, registries, and recommendations into a standalone markdown document at `PROJECT_AUDIT.md` located in the repository root.

## Acceptance Criteria

### Audit Report Completeness & Structure
- [ ] `PROJECT_AUDIT.md` exists at the repository root and covers all five core domains: Project Stage Assessment, Architectural Audit, Dataset & Glossary Evaluation, Identified Issues Registry, and Prioritized Roadmap.
- [ ] Every entry in the Identified Issues Registry contains exact file paths, line/symbol references, severity rating (Critical, High, Medium, Low), concrete impact, and suggested fix.
- [ ] The report details the operational readiness and limitations of both primary CLI modes (`translate` and `improve`), batch tools (`tool/`), and configuration mechanisms (`src/config.py`, `.env`).

### Verification & Rigor
- [ ] Static validation and import/dependency checks across all Python files in `src/` and `tool/` are executed and documented.
- [ ] Claimed bugs and schema vulnerabilities are independently verified with objective reproduction checks or test assertions rather than unverified assertions.
- [ ] The roadmap contains a structured summary table ranking maintainer tasks by impact and estimated implementation complexity.

## 2026-09-17T03:13:34Z

Implement an extensible dual-tier validation architecture (Hard and Soft validators) for lom-vie-translate that classifies validation rules, provides corrective diagnostic feedback during re-prompting, prevents infinite retry loops, and maintains game engine data integrity.

Working directory: /home/rio/Documents/lom-vie-translate
Integrity mode: development

## Requirements

### R1. Dual-Tier Validator Categorization
Classify validation rules into Hard and Soft tiers:
- **Hard Validators (mandatory re-prompt on failure)**:
  - Token integrity: Preservation of injected linebreaks (`[|]`, `[||]`), engine interpolation tokens (`{0}`, `{title}`, `{0:N0}`), and bracketed parameters (`[{0}]`).
  - Rich-text tag integrity: Preservation and well-formedness of markup tags (`<color>`, `</color>`, `<b>`, etc.).
  - Output existence: Rejection of empty, whitespace-only, or null outputs.
- **Soft Validators (re-prompt up to threshold, then accept with warnings)**:
  - Lingering CJK characters: Detection of untranslated Chinese characters in Vietnamese output.
  - Verbatim identity: Detection where the model returned source input unchanged without translation.
  - Glossary compliance: Verification that injected glossary terms matched to the entry appear in the translation.
  - Length ratio anomalies: Detection of extreme deviations between source and translated dialogue lengths.

### R2. Corrective Feedback Re-prompting
Construct informative diagnostic feedback when validation fails, passing the specific error reasons (e.g., missing tokens, violated glossary terms, untranslated CJK) into subsequent LLM prompts to guide corrective generation.

### R3. Bounded Retry Budget & Infinite Loop Prevention
Enforce deterministic retry limits:
- Soft validation failures trigger corrective re-prompting up to a configurable maximum count (default: 2); once exhausted, the translation is accepted with logged warnings.
- Hard validation failures trigger re-prompting across the model pool up to the model retry budget; if all retries are exhausted, it safely falls back to the original text.
- Every retry attempt must decrement the remaining retry budget to guarantee zero infinite loops.

### R4. Verification & Automated Test Suite
Provide synthetic test cases and automated tests covering:
- Unit tests for every Hard and Soft validator with valid and failing cases.
- Integration tests simulating LLM outputs: verifying Hard re-prompting, Soft re-prompting up to the default 2-retry limit followed by graceful acceptance, and loop prevention.
- Preservation of existing project quality standards (`pytest`, `ruff`, `mypy`).

## Acceptance Criteria

### Validator Rule Coverage
- [ ] Hard validators strictly flag and reject missing/corrupted engine tokens, broken rich-text tags, and empty/null responses.
- [ ] Soft validators detect verbatim source copies, untranslated CJK characters, ignored glossary mappings, and extreme length anomalies.
- [ ] Auto-healing of benign spacing flaws runs prior to validator evaluations.

### Re-prompting & Loop Prevention
- [ ] Re-prompt queries include concise diagnostic feedback identifying the specific validator failure and corrective instructions.
- [ ] Soft validation failures are accepted with logged warnings after the configured retry threshold (default: 2) is reached.
- [ ] Hard validation failures never allow corrupted engine tokens or unclosed tags into the output, falling back safely if pool retries are exhausted.
- [ ] Total re-prompt attempts per translation entry are strictly bounded with zero possibility of infinite execution loops.

### Automated Verification & Quality
- [ ] Automated tests in `tests/` cover each Hard and Soft validator with synthetic test inputs.
- [ ] Integration tests verify simulated Hard failure re-prompting, Soft failure 2-attempt re-prompting and acceptance, and fallback behavior.
- [ ] Existing test suite passes with zero regressions (`pytest tests/ -v`).
- [ ] Static analysis and formatting checks pass cleanly (`ruff check`, `ruff format --check`, `mypy`).
