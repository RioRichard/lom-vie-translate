import json
from pathlib import Path
from src.grossary import load_grossary, find_original_matches
from src.config import INPUT_DIR

def load_entries(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    entries = data.get('entries', [])
    if isinstance(entries, dict) and 'Array' in entries:
        entries_list = entries['Array']
    else:
        entries_list = entries
    return entries_list

def map_translation_context(json_path):
    entries = load_entries(json_path)
    name_to_translated, original_to_translated = load_grossary()
    mapped = []
    for entry in entries:
        original_text = entry.get('value') or entry.get('Text', '')
        raw_translated_text = entry.get('TranslatedText') or entry.get('translated') or entry.get('Text', '')
        grossary_matches = find_original_matches(original_text, original_to_translated)
        mapped.append({
            'original_text': original_text,
            'raw_translated_text': raw_translated_text,
            'grossary_matches': grossary_matches
        })
    return mapped

def map_all_files():
    json_dir = Path(INPUT_DIR)
    all_mapped = {}
    for file_path in json_dir.glob('*.json'):
        all_mapped[file_path.name] = map_translation_context(file_path)
    return all_mapped

# Example usage:
# result = map_all_files()
# for fname, entries in result.items():
#     for entry in entries:
#         print(entry)
