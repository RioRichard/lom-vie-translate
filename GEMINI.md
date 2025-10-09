# Project Overview

This project is a specialized tool for translating game text from Chinese (Simplified) to Vietnamese. It focuses on maintaining consistent game terminology and natural language flow, offering features like glossary support, concurrent processing, and structured output formats.

**Key Technologies:** Python

# Building and Running

## Setup

1.  **Create `.env` file:** Copy the template and configure your API keys and other settings.
    ```bash
    cp .env.template .env
    ```
    Edit `.env` with your specific configurations. Example:
    ```env
    # API Keys (comma-separated)
    API_KEYS=your-api-key-1,your-api-key-2,your-api-key-3

    # Model Settings
    GOOGLE_STUDIO_AI_LLM=gemma-3-27b-it

    # Rate Limiting and Concurrency
    RATE_LIMIT_DELAY=2
    RATE_LIMIT_IF_QUOTA_EXCEEDED=60
    MAX_CONCURRENT=5

    # Directory Configuration (paths are relative to project root)
    INPUT_DIR=Resource/LeanLocalJson
    OUTPUT_DIR=translated_output
    IMPROVE_DIR=improved_output
    GLOSSARY_DIR=Resource/glossary
    ```

2.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Usage

### Translation Mode

Translates Chinese (Simplified) game text to Vietnamese.

```bash
python src/main.py \
    --mode translate \
    --input-dir /path/to/input_jsons \
    --output-dir /path/to/base_output \
    --json-output-dir /path/to/json_output (optional, defaults to --output-dir/json) \
    --details-output-dir /path/to/details_output (optional, defaults to --output-dir/details) \
    --pairs-output-dir /path/to/pairs_output (optional, defaults to --output-dir/pairs) \
    --glossary-file /path/to/your_glossary.json (optional)
```

### Improvement Mode

Refines existing translations.

```bash
python src/main.py \
    --mode improve \
    --input-dir /path/to/input_jsons \
    --translated-dir /path/to/raw_translations \
    --output-dir /path/to/base_output \
    --json-output-dir /path/to/json_output (optional, defaults to --output-dir/json) \
    --details-output-dir /path/to/details_output (optional, defaults to --output-dir/details) \
    --pairs-output-dir /path/to/pairs_output (optional, defaults to --output-dir/pairs) \
    --glossary-file /path/to/your_glossary.json (optional)
```

## Tool Usage

The `tool/` scripts provide additional utilities for processing JSON files. These scripts now require input and output directories to be specified as command-line arguments.

### 1. `create_glossary.py`

Aggregates original and translated JSON files into a glossary.

```bash
python tool/create_glossary.py --src_folder /path/to/original_jsons --tgt_folder /path/to/translated_jsons --output_json /path/to/output_glossary.json --output_txt /path/to/output_glossary.txt
```

### 2. `filter_entries_by_category.py`

Filters JSON entries into categories (e.g., 'Story', 'LegendInfo', 'Other') based on their 'Name' field.

```bash
python tool/filter_entries_by_category.py --src_folder /path/to/input_jsons --dst_base_folder /path/to/output_categorized_jsons
```

### 3. `filter_languages.py`

Filters JSON files into language-specific folders based on their 'Language' field.

```bash
python tool/filter_languages.py --src_folder /path/to/input_jsons --dst_base_folder /path/to/output_language_filtered_jsons
```

### 4. `convert_translation_details.py`

Converts old `translation_details.json` files (dictionary format) to the new list format.

```bash
python tool/convert_translation_details.py --input_file /path/to/old_translation_details.json --output_file /path/to/new_translation_details.json
```

### 5. `translation_mapper.py`

Maps translation entries to their context, including glossary matches. This script prints the mapped data to standard output.

```bash
python tool/translation_mapper.py
```

# Development Conventions

*   **Language:** Python
*   **Configuration:** Uses a `.env` file for environment-specific settings and `src/config.py` for application configuration.
*   **Logging:** Includes a dedicated `src/logger.py` for structured logging.
*   **Modularity:** The project is structured into distinct modules for file processing, glossary management, prompt preparation, and translation engine interfacing.
