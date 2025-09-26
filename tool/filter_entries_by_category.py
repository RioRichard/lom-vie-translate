#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import shutil
import argparse
from typing import List

def get_entry_categories(entries: List[dict]) -> set:
    categories = set()
    for entry in entries:
        name = entry.get('Name', '')
        if 'Story/' in name:
            categories.add('Story')
        elif 'LegendInfo/' in name:
            categories.add('LegendInfo')
        else:
            categories.add('Other')
    return categories

def filter_json_by_entry_category(src_folder: str, dst_base_folder: str):
    for filename in os.listdir(src_folder):
        if filename.endswith('.json'):
            src_path = os.path.join(src_folder, filename)
            with open(src_path, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                except Exception as e:
                    print(f"Error reading {filename}: {e}")
                    continue
            entries = data.get('entries', {}).get('Array', [])
            categories = get_entry_categories(entries)
            for category in categories:
                dst_folder = os.path.join(dst_base_folder, category)
                os.makedirs(dst_folder, exist_ok=True)
                dst_path = os.path.join(dst_folder, filename)
                shutil.copy2(src_path, dst_path)
                print(f"Copied {filename} to {dst_folder}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Filter JSON files by entry category.')
    parser.add_argument('--src_folder', type=str, required=True,
                        help='Source folder containing original JSON files.')
    parser.add_argument('--dst_base_folder', type=str, required=True,
                        help='Destination base folder for categorized JSON files.')
    
    args = parser.parse_args()

    filter_json_by_entry_category(args.src_folder, args.dst_base_folder)
