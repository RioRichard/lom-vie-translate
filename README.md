# Chinese to Vietnamese Text Translator for Lengend of Mortal

A specialized tool for translating game text from Chinese (Simplified) to Vietnamese for Legend of Mortal, with a focus on maintaining consistent game terminology and natural language flow.

## Features

- Translation from Chinese (Simplified) to Vietnamese
- Improvement mode for refining existing translations
- Glossary support for consistent terminology
- Concurrent processing for better performance
- Structured output formats:
  - Individual JSON files maintaining original structure
  - Consolidated translation details
  - Translation pairs in text format

## Project Structure

```
src/
├── config.py          # Configuration and settings
├── file_processor.py  # File handling and processing
├── grossary.py       # Glossary management
├── logger.py         # Logging utilities
├── main.py           # Main entry point
├── prompt_preparer.py # Translation prompt preparation
├── translator.py     # Translation engine interface
└── utils.py         # Utility functions
```

## Setup

1. Create a .env file from the template:
```bash
cp .env.template .env
```

2. Configure your environment variables in .env:
```env
# API Keys (comma-separated)
API_KEYS=your-api-key-1,your-api-key-2,your-api-key-3

# Model Settings
GOOGLE_STUDIO_AI_LLM=gemma-3-27b-it

# Rate Limiting and Concurrency
RATE_LIMIT_DELAY=2
RATE_LIMIT_IF_QUOTA_EXCEEDED=60
MAX_CONCURRENT=5

# Directory Configuration
BASE_DIR=/path/to/your/project
INPUT_DIR=${BASE_DIR}/Resource/LeanLocalJson
OUTPUT_DIR=${BASE_DIR}/translated_output
IMPROVE_DIR=${BASE_DIR}/improved_output
GROSSARY_DIR=${BASE_DIR}/Resource/grossary
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Input File Structure

The tool expects JSON files with the following structure:

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

Or alternatively:

```json
{
    "Language": "ChineseSimplified",
    "entries": [
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
```

Key components:
- `Language`: Must be "ChineseSimplified" (files with other languages will be skipped)
- `entries`: Can be either an object with an "Array" field or a direct array
- Each entry must have:
  - `Name`: Unique identifier/path for the text
  - `Text`: The actual Chinese text to be translated

### Glossary Structure

The glossary files should be JSON files with either of these formats:

```json
[
    {
        "Name": "UI/Button/Confirm",
        "Original": "确认",
        "Translated": "Xác nhận"
    }
]
```

Or:

```json
{
    "UI/Button/Confirm": "Xác nhận"
}
```

The glossary helps maintain consistent translations for frequently used terms.

## Usage

### Translation Mode
```bash
python src/main.py --mode translate --input-dir /path/to/input --output-dir /path/to/output
```

### Improvement Mode
```bash
python src/main.py --mode improve --input-dir /path/to/input --translated-dir /path/to/raw --output-dir /path/to/output
```

## Tool Usage

The `tool/` scripts provide additional utilities for processing JSON files. These scripts now require input and output directories to be specified as command-line arguments.

### 1. `create_grossary.py`

Aggregates original and translated JSON files into a glossary.

```bash
python tool/create_grossary.py --src_folder /path/to/original_jsons --tgt_folder /path/to/translated_jsons --output_json /path/to/output_glossary.json --output_txt /path/to/output_glossary.txt
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

## Output Structure

The tool generates three types of output:

### 1. Individual JSON Files
Maintains the original structure with translated text:
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

### 2. Translation Details (translation_details.json)
Consolidated file containing all translations:
```json
[
    {
        "Name": "Story/Chapter1/Dialog001",
        "Original": "你托人送了信，自己独行下山，加紧脚步往江陵发进。",
        "Translated": "Ngươi phái người đưa thư, tự mình độc hành xuống núi, thúc ngựa lao về Giang Lăng.",
        "Raw": "Ngươi sai người đưa thư, mình độc hành xuống núi, gấp rút bước chân hướng Giang Lăng phát tiến."
    }
]
```
Note: The "Raw" field is only present in improve mode.

### 3. Translation Pairs (translation_pairs.txt)
Simple text file with original=translation pairs:
```text
你托人送了信，自己独行下山，加紧脚步往江陵发进。=Ngươi phái người đưa thư, tự mình độc hành xuống núi, thúc ngựa lao về Giang Lăng.
整装=Chuẩn bị
```

## Notes

- The tool focuses on game text translation and maintains context appropriately
- Special attention is given to short phrases and game terminology
- Concurrent processing is used to optimize performance
- Logging system provides detailed progress and error tracking
