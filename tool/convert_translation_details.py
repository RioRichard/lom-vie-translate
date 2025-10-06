#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import argparse
from pathlib import Path
from typing import List, Dict, Any

def convert_old_to_new_format(old_data: Dict[str, Dict[str, str]]) -> List[Dict[str, str]]:
    """Converts old translation_details.json format to the new list format.

    Args:
        old_data (Dict[str, Dict[str, str]]): The old translation details data.

    Returns:
        List[Dict[str, str]]: The new translation details data in list format.
    """
    new_data: List[Dict[str, str]] = []
    for name, details in old_data.items():
        entry = {
            'Name': name,
            'Original': details.get('original', ''),
            'Translated': details.get('final', '')
        }
        if 'raw' in details:
            entry['Raw'] = details['raw']
        new_data.append(entry)
    return new_data

def main():
    parser = argparse.ArgumentParser(
        description='Convert old translation_details.json to the new list format.'
    )
    parser.add_argument('--input-file', type=str, required=True,
                        help='Path to the old translation_details.json file.')
    parser.add_argument('--output-file', type=str, required=True,
                        help='Path for the new translation_details.json file.')

    args = parser.parse_args()

    input_path = Path(args.input_file)
    output_path = Path(args.output_file)

    if not input_path.exists():
        print(f"Error: Input file not found at {input_path}")
        return

    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            old_data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in input file {input_path}: {e}")
        return
    except Exception as e:
        print(f"Error reading input file {input_path}: {e}")
        return

    if not isinstance(old_data, dict):
        print(f"Error: Input file {input_path} is not in the expected old dictionary format.")
        return

    new_data = convert_old_to_new_format(old_data)

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(new_data, f, ensure_ascii=False, indent=2)
        print(f"Successfully converted {input_path} to {output_path}")
    except Exception as e:
        print(f"Error writing output file {output_path}: {e}")

if __name__ == "__main__":
    main()
