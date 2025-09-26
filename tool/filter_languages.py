#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import shutil
import argparse

def filter_json_by_language(src_folder: str, dst_base_folder: str):
    for filename in os.listdir(src_folder):
        if filename.endswith('.json'):
            src_path = os.path.join(src_folder, filename)
            with open(src_path, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                except Exception as e:
                    print(f"Error reading {filename}: {e}")
                    continue
            language = data.get('Language', 'Unknown')
            dst_folder = os.path.join(dst_base_folder, language)
            os.makedirs(dst_folder, exist_ok=True)
            dst_path = os.path.join(dst_folder, filename)
            shutil.copy2(src_path, dst_path)
            print(f"Copied {filename} to {dst_folder}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Filter JSON files by language.')
    parser.add_argument('--src_folder', type=str, required=True,
                        help='Source folder containing original JSON files.')
    parser.add_argument('--dst_base_folder', type=str, required=True,
                        help='Destination base folder for language-filtered JSON files.')
    
    args = parser.parse_args()

    filter_json_by_language(args.src_folder, args.dst_base_folder)
