#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
from typing import List, Dict

def text_process(text: str) -> str:
    text = text.replace('\n', '\\n').replace('\r', '\\r').strip()
    # Placeholder for any text processing if needed
    return text

def load_entries(json_path: str) -> Dict[str, str]:
	with open(json_path, 'r', encoding='utf-8') as f:
		data = json.load(f)
	entries = data.get('entries', {}).get('Array', [])
	return {entry.get('Name', ''): entry.get('Text', '') for entry in entries if 'Name' in entry and 'Text' in entry}

def create_grossary(original_json_path: str, translated_json_path: str, output_json_path: str, output_txt_path: str):
	original_map = load_entries(original_json_path)
	translated_map = load_entries(translated_json_path)

	glossary: List[Dict[str, str]] = []
	txt_lines: List[str] = []

	for name, original_text in original_map.items():
		translated_text = translated_map.get(name, '')
		glossary.append({
			'Name': name,
			'Original': original_text,
			'Translated': translated_text
		})
		txt_lines.append(f"{original_text}={translated_text}")

	# Write JSON output
	with open(output_json_path, 'w', encoding='utf-8') as f:
		json.dump(glossary, f, ensure_ascii=False, indent=2)

	# Write TXT output
	with open(output_txt_path, 'w', encoding='utf-8') as f:
		f.write('\n'.join(txt_lines))

if __name__ == "__main__":
	# Process all JSON files in the source folder
	src_folder = os.path.join(os.path.dirname(__file__), 'resources/originals/filtered/ChineseSimplified/filtered_by_entry_category/Other')
	tgt_folder = os.path.join(os.path.dirname(__file__), 'resources/translated/filtered/ChineseSimplified/filtered_by_entry_category/Other')
	output_json = os.path.join(os.path.dirname(__file__), 'resources/grossary_map.json')
	output_txt = os.path.join(os.path.dirname(__file__), 'resources/grossary_map.txt')

	all_glossary: List[Dict[str, str]] = []
	all_txt_lines: List[str] = []
	skip_keys = {'Desc', 'desc', 'intro', 'Intro', 'Dialog', 'dialog', 'talking', 'Talking'}

	for filename in os.listdir(src_folder):
		if filename.endswith('.json'):
			original_json = os.path.join(src_folder, filename)
			# Check Language condition
			with open(original_json, 'r', encoding='utf-8') as f:
				data = json.load(f)
			if data.get('Language') != 'ChineseSimplified':
				continue
			translated_json = os.path.join(tgt_folder, filename)
			if os.path.exists(translated_json):
				original_map = load_entries(original_json)
				translated_map = load_entries(translated_json)
				for name, original_text in original_map.items():
					if any(key in name for key in skip_keys):
						continue
					translated_text = translated_map.get(name, '')
					all_glossary.append({
						'Name': name,
						'Original': original_text,
						'Translated': translated_text
					})
					all_txt_lines.append(f"{text_process(original_text)}={text_process(translated_text)}")

	# Write aggregated JSON output
	with open(output_json, 'w', encoding='utf-8') as f:
		json.dump(all_glossary, f, ensure_ascii=False, indent=2)

	# Write aggregated TXT output (remove duplicates)
	unique_txt_lines = list(dict.fromkeys(all_txt_lines))
	with open(output_txt, 'w', encoding='utf-8') as f:
		f.write('\n'.join(unique_txt_lines))
