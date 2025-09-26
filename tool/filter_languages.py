#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import shutil

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
    src_folder = os.path.join(os.path.dirname(__file__), 'resources/originals/unfiltered/')
    dst_base_folder = os.path.join(os.path.dirname(__file__), 'resources/originals/filtered')
    filter_json_by_language(src_folder, dst_base_folder)
