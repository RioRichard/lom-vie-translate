from __future__ import annotations

import json
import re
import shutil
import struct
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.utils import parse_json_entries

LEAN_CSV_SIG = (
    b"\x03\x00\x00\x00 = \x00"
    b"\x02\x00\x00\x00\\n\x00\x00"
    b"\x04\x00\x00\x00 // "
    b"\x00\x00\x00\x00"
)

_ASSET_FILENAME_RE = re.compile(
    r"^(level\d+|sharedassets\d+\.assets|resources\.assets)_0*(\d+)"
)
_CATEGORY_SANITIZE_RE = re.compile(r"[^A-Za-z0-9_]+")
_SKIP_ASSET_SUFFIXES = (".resS", ".bak", ".resource", ".meta", ".txt", ".json")


@dataclass(frozen=True, slots=True)
class SerializedType:
    """Metadata entry for a serialized Unity type in a v22 SerializedFile."""

    class_id: int
    is_stripped: int
    script_type_index: int


@dataclass(frozen=True, slots=True)
class ObjectInfo:
    """Object table entry inside a Unity v22 SerializedFile."""

    path_id: int
    byte_start: int
    byte_size: int
    type_id: int


@dataclass(slots=True)
class SerializedFile:
    """Parsed representation of a Unity 2020.3.49f1 (format v22) SerializedFile."""

    path: Path | None
    version: int
    endian: int
    meta_size: int
    file_size: int
    data_offset: int
    unknown: int
    unity_version: str
    platform: int
    has_type_tree: int
    types: list[SerializedType]
    table_pos: int
    objects: list[ObjectInfo]
    raw_bytes: bytes

    def get_object_bytes(self, obj: ObjectInfo) -> bytes:
        """Return the raw serialized bytes for the given ObjectInfo."""
        start = self.data_offset + obj.byte_start
        end = start + obj.byte_size
        return self.raw_bytes[start:end]


@dataclass(slots=True)
class LeanLanguageCSVData:
    """Parsed LeanLocalization LeanLanguageCSV MonoBehaviour payload."""

    language: str
    prefix_bytes: bytes
    entries: list[tuple[str, str]]


def _align4(value: int) -> int:
    return (value + 3) & ~3


def _pack_aligned_string(text: str) -> bytes:
    encoded = text.encode("utf-8")
    pad_len = (-len(encoded)) & 3
    return struct.pack("<I", len(encoded)) + encoded + (b"\x00" * pad_len)


def _sanitize_category(entries: list[tuple[str, str]]) -> str:
    if not entries:
        return "Misc"
    first_name = entries[0][0]
    raw_prefix = first_name.split("/", 1)[0] if "/" in first_name else first_name
    sanitized = _CATEGORY_SANITIZE_RE.sub("_", raw_prefix).strip("_")
    return sanitized or "Misc"


def parse_serialized_file(source: bytes | bytearray | memoryview | str | Path) -> SerializedFile:
    """Parse a Unity v22 SerializedFile from bytes or a file path."""
    path: Path | None = None
    if isinstance(source, (str, Path)):
        path = Path(source)
        raw = path.read_bytes()
    else:
        raw = bytes(source)

    if len(raw) < 48:
        raise ValueError(f"SerializedFile too small ({len(raw)} bytes; expected >= 48)")

    _, _, version, _ = struct.unpack_from(">IIII", raw, 0)
    endian = raw[16]
    if version != 22:
        raise ValueError(f"Unsupported SerializedFile version: {version} (expected 22)")
    if endian != 0:
        raise ValueError(f"Unsupported SerializedFile endianness: {endian} (expected 0)")

    meta_size, file_size, data_offset, unknown = struct.unpack_from(">IQQQ", raw, 20)
    if data_offset > len(raw):
        raise ValueError(
            f"Invalid SerializedFile data_offset={data_offset} exceeds file length {len(raw)}"
        )
    if file_size > len(raw):
        raise ValueError(
            f"Invalid SerializedFile file_size={file_size} exceeds file length {len(raw)}"
        )

    try:
        nul_pos = raw.index(0, 48)
    except ValueError as exc:
        raise ValueError("Invalid SerializedFile: unterminated unity_version string") from exc

    unity_version = raw[48:nul_pos].decode("utf-8", errors="replace")
    p = nul_pos + 1
    if p + 9 > len(raw):
        raise ValueError("Invalid SerializedFile: truncated platform/type header")

    platform, has_type_tree, type_count = struct.unpack_from("<iBi", raw, p)
    p += 9
    if type_count < 0:
        raise ValueError(f"Invalid SerializedFile type_count: {type_count}")
    if has_type_tree != 0:
        raise ValueError(
            f"Unsupported SerializedFile has_type_tree={has_type_tree} (expected 0)"
        )

    types: list[SerializedType] = []
    for _ in range(type_count):
        if p + 7 > len(raw):
            raise ValueError("Invalid SerializedFile: truncated SerializedType entry")
        class_id, is_stripped, script_type_idx = struct.unpack_from("<iBh", raw, p)
        p += 7
        if class_id == 114 or class_id < 0:
            p += 16
        p += 16
        if p > len(raw):
            raise ValueError("Invalid SerializedFile: truncated SerializedType hashes")
        types.append(
            SerializedType(
                class_id=class_id,
                is_stripped=is_stripped,
                script_type_index=script_type_idx,
            )
        )

    if p + 4 > len(raw):
        raise ValueError("Invalid SerializedFile: truncated object count")
    obj_count = struct.unpack_from("<i", raw, p)[0]
    p += 4
    if obj_count < 0:
        raise ValueError(f"Invalid SerializedFile obj_count: {obj_count}")

    table_pos = _align4(p)
    table_end = table_pos + obj_count * 24
    if table_end > data_offset:
        raise ValueError(
            f"Invalid SerializedFile: object table end {table_end} exceeds data_offset {data_offset}"
        )

    objects: list[ObjectInfo] = []
    for i in range(obj_count):
        path_id, byte_start, byte_size, type_id = struct.unpack_from(
            "<qQII", raw, table_pos + i * 24
        )
        abs_end = data_offset + byte_start + byte_size
        if abs_end > len(raw):
            raise ValueError(
                f"Object path_id={path_id} range [{data_offset + byte_start}, {abs_end}) "
                f"exceeds file length {len(raw)}"
            )
        objects.append(
            ObjectInfo(
                path_id=path_id,
                byte_start=byte_start,
                byte_size=byte_size,
                type_id=type_id,
            )
        )

    return SerializedFile(
        path=path,
        version=version,
        endian=endian,
        meta_size=meta_size,
        file_size=file_size,
        data_offset=data_offset,
        unknown=unknown,
        unity_version=unity_version,
        platform=platform,
        has_type_tree=has_type_tree,
        types=types,
        table_pos=table_pos,
        objects=objects,
        raw_bytes=raw,
    )


def _extract_preceding_language(obj_bytes: bytes, sig_idx: int) -> str:
    """Extract the 4-byte-aligned Language string immediately preceding LEAN_CSV_SIG."""
    max_words = sig_idx // 4
    for word_offset in range(1, min(max_words, 64) + 1):
        pos = sig_idx - 4 * word_offset
        slen = struct.unpack_from("<I", obj_bytes, pos)[0]
        if 1 <= slen <= 128 and pos + 4 + _align4(slen) == sig_idx:
            pad_bytes = obj_bytes[pos + 4 + slen : sig_idx]
            if any(byte != 0 for byte in pad_bytes):
                continue
            try:
                lang = obj_bytes[pos + 4 : pos + 4 + slen].decode("utf-8")
            except UnicodeDecodeError:
                continue
            if lang and lang.isprintable():
                return lang
    raise ValueError("Found LEAN_CSV_SIG without a valid preceding Language string")


def parse_lean_language_csv(obj_bytes: bytes) -> LeanLanguageCSVData | None:
    """Parse a LeanLanguageCSV MonoBehaviour object; return None if signature is absent."""
    sig_idx = obj_bytes.find(LEAN_CSV_SIG)
    if sig_idx == -1:
        return None

    language = _extract_preceding_language(obj_bytes, sig_idx)
    sig_end = sig_idx + len(LEAN_CSV_SIG)
    if sig_end + 4 > len(obj_bytes):
        raise ValueError("Truncated LeanLanguageCSV payload after signature")

    entry_count = struct.unpack_from("<I", obj_bytes, sig_end)[0]
    p = sig_end + 4
    entries: list[tuple[str, str]] = []

    for _ in range(entry_count):
        if p + 4 > len(obj_bytes):
            raise ValueError("Truncated LeanLanguageCSV entry name length")
        name_len = struct.unpack_from("<I", obj_bytes, p)[0]
        p += 4
        name_aligned = _align4(name_len)
        if p + name_aligned > len(obj_bytes):
            raise ValueError("Truncated LeanLanguageCSV entry name bytes")
        name = obj_bytes[p : p + name_len].decode("utf-8")
        p += name_aligned

        if p + 4 > len(obj_bytes):
            raise ValueError("Truncated LeanLanguageCSV entry text length")
        text_len = struct.unpack_from("<I", obj_bytes, p)[0]
        p += 4
        text_aligned = _align4(text_len)
        if p + text_aligned > len(obj_bytes):
            raise ValueError("Truncated LeanLanguageCSV entry text bytes")
        text = obj_bytes[p : p + text_len].decode("utf-8")
        p += text_aligned

        entries.append((name, text))

    if p != len(obj_bytes):
        raise ValueError(
            f"LeanLanguageCSV parse did not consume object exactly: parsed_end={p} != {len(obj_bytes)}"
        )

    return LeanLanguageCSVData(
        language=language,
        prefix_bytes=obj_bytes[:sig_end],
        entries=entries,
    )


def serialize_lean_language_csv(prefix_bytes: bytes, entries: list[tuple[str, str]]) -> bytes:
    """Serialize updated LeanLanguageCSV (Name, Text) pairs preserving prefix_bytes."""
    buf = bytearray(prefix_bytes)
    buf.extend(struct.pack("<I", len(entries)))
    for name, text in entries:
        buf.extend(_pack_aligned_string(name))
        buf.extend(_pack_aligned_string(text))
    return bytes(buf)


def _iter_level_asset_names(mortal_data_dir: Path) -> list[str]:
    """List unique logical level* asset names in mortal_data_dir, skipping .resS and .bak."""
    names: set[str] = set()
    for entry in mortal_data_dir.iterdir():
        if not entry.is_file():
            continue
        name = entry.name
        if name.endswith(".bak"):
            base = name[:-4]
            if base.startswith("level") and not base.endswith(_SKIP_ASSET_SUFFIXES):
                names.add(base)
        elif name.startswith("level") and not name.endswith(_SKIP_ASSET_SUFFIXES):
            names.add(name)
    return sorted(names)


def _resolve_clean_asset_path(mortal_data_dir: Path, asset_name: str) -> Path | None:
    """Return <asset>.bak if present (clean backup), otherwise <asset>, or None."""
    bak_path = mortal_data_dir / f"{asset_name}.bak"
    if bak_path.is_file():
        return bak_path
    asset_path = mortal_data_dir / asset_name
    if asset_path.is_file():
        return asset_path
    return None


def extract_lean_local_jsons(
    mortal_data_dir: str | Path,
    output_dir: str | Path,
    language: str = "ChineseSimplified",
) -> list[Path]:
    """Extract LeanLanguageCSV assets for `language` from level* SerializedFiles into JSON files."""
    mortal_dir = Path(mortal_data_dir)
    if not mortal_dir.is_dir():
        raise FileNotFoundError(f"Mortal_Data directory not found: {mortal_dir}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    written_paths: list[Path] = []
    for entry in sorted(mortal_dir.iterdir(), key=lambda p: p.name):
        if not entry.is_file():
            continue
        if not entry.name.startswith("level") or entry.name.endswith(_SKIP_ASSET_SUFFIXES):
            continue

        sf = parse_serialized_file(entry)
        for obj in sf.objects:
            obj_bytes = sf.get_object_bytes(obj)
            if LEAN_CSV_SIG not in obj_bytes:
                continue
            csv_data = parse_lean_language_csv(obj_bytes)
            if csv_data is None or csv_data.language != language:
                continue

            category = _sanitize_category(csv_data.entries)
            out_name = f"{entry.name}_{obj.path_id:05d}_{category}.json"
            out_path = out_dir / out_name

            payload = {
                "Language": csv_data.language,
                "AssetFile": entry.name,
                "PathId": obj.path_id,
                "entries": {
                    "Array": [
                        {"Name": item_name, "Text": item_text}
                        for item_name, item_text in csv_data.entries
                    ]
                },
            }
            out_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            written_paths.append(out_path)

    return written_paths


def _rebuild_serialized_file(
    sf: SerializedFile,
    updates_by_path_id: dict[int, list[tuple[str, str]]],
) -> tuple[bytes, int, int]:
    """Rebuild a SerializedFile with patched LeanLanguageCSV objects and updated offsets."""
    out = bytearray(sf.raw_bytes[: sf.data_offset])
    data_buf = bytearray()
    patched_objects = 0
    patched_entries = 0
    expected_entries: dict[int, list[tuple[str, str]]] = {}

    for i, obj in enumerate(sf.objects):
        if i > 0:
            pad = (8 - (len(data_buf) % 8)) % 8
            if pad:
                data_buf.extend(b"\x00" * pad)

        new_byte_start = len(data_buf)
        obj_bytes = sf.get_object_bytes(obj)

        if obj.path_id in updates_by_path_id:
            csv_data = parse_lean_language_csv(obj_bytes)
            if csv_data is None:
                raise ValueError(
                    f"Target object path_id={obj.path_id} in {sf.path} is not a LeanLanguageCSV"
                )
            incoming = updates_by_path_id[obj.path_id]
            if len(incoming) == len(csv_data.entries) and [n for n, _ in incoming] == [
                n for n, _ in csv_data.entries
            ]:
                updated_entries = incoming
                patched_entries += sum(
                    1
                    for (_, old_text), (_, new_text) in zip(
                        csv_data.entries, updated_entries, strict=True
                    )
                    if old_text != new_text
                )
            else:
                trans_map = dict(incoming)
                updated_entries = []
                for orig_name, orig_text in csv_data.entries:
                    new_text = trans_map.get(orig_name, orig_text)
                    if new_text != orig_text:
                        patched_entries += 1
                    updated_entries.append((orig_name, new_text))

            new_obj_bytes = serialize_lean_language_csv(csv_data.prefix_bytes, updated_entries)
            expected_entries[obj.path_id] = updated_entries
            patched_objects += 1
        else:
            new_obj_bytes = obj_bytes

        data_buf.extend(new_obj_bytes)
        struct.pack_into(
            "<qQII",
            out,
            sf.table_pos + i * 24,
            obj.path_id,
            new_byte_start,
            len(new_obj_bytes),
            obj.type_id,
        )

    new_file_size = sf.data_offset + len(data_buf)
    struct.pack_into(">IQQ", out, 20, sf.meta_size, new_file_size, sf.data_offset)
    out.extend(data_buf)
    rebuilt = bytes(out)

    # Verify the rebuilt binary parses back cleanly and matches patched entries
    verified_sf = parse_serialized_file(rebuilt)
    if verified_sf.file_size != len(rebuilt):
        raise ValueError(
            f"Rebuilt SerializedFile file_size mismatch: {verified_sf.file_size} != {len(rebuilt)}"
        )
    if len(verified_sf.objects) != len(sf.objects):
        raise ValueError("Rebuilt SerializedFile object count mismatch")

    obj_by_pid = {v_obj.path_id: v_obj for v_obj in verified_sf.objects}
    for pid, expected in expected_entries.items():
        v_csv = parse_lean_language_csv(verified_sf.get_object_bytes(obj_by_pid[pid]))
        if v_csv is None or v_csv.entries != expected:
            raise ValueError(f"Rebuilt LeanLanguageCSV verification failed for path_id={pid}")

    return rebuilt, patched_objects, patched_entries


def _render_patch_scripts(asset_names: list[str]) -> dict[str, str]:
    assets_space = " ".join(asset_names)
    assets_list = "\n".join(f"  - Mortal_Data/{name}" for name in asset_names)

    install_sh = f"""#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
TARGET_DIR="${{1:-}}"

if [[ -z "$TARGET_DIR" ]]; then
  if [[ -d "$SCRIPT_DIR/../Mortal_Data" ]]; then
    TARGET_DIR="$SCRIPT_DIR/../Mortal_Data"
  elif [[ -d "$HOME/.local/share/Steam/steamapps/common/LegendOfMortal/Mortal_Data" ]]; then
    TARGET_DIR="$HOME/.local/share/Steam/steamapps/common/LegendOfMortal/Mortal_Data"
  elif [[ -d "$HOME/.steam/steam/steamapps/common/LegendOfMortal/Mortal_Data" ]]; then
    TARGET_DIR="$HOME/.steam/steam/steamapps/common/LegendOfMortal/Mortal_Data"
  else
    echo "Usage: $0 /path/to/LegendOfMortal/Mortal_Data" >&2
    exit 1
  fi
fi

if [[ -d "$TARGET_DIR/Mortal_Data" ]]; then
  TARGET_DIR="$TARGET_DIR/Mortal_Data"
fi

if [[ ! -d "$TARGET_DIR" ]]; then
  echo "Error: Mortal_Data directory not found: $TARGET_DIR" >&2
  exit 1
fi

for asset in {assets_space}; do
  SRC="$SCRIPT_DIR/Mortal_Data/$asset"
  DST="$TARGET_DIR/$asset"
  BAK="$TARGET_DIR/$asset.bak"
  if [[ -f "$DST" && ! -f "$BAK" ]]; then
    cp -p "$DST" "$BAK"
    echo "Backed up $DST -> $BAK"
  fi
  cp -f "$SRC" "$DST"
  echo "Installed $DST"
done

echo "Vietnamese patch installed successfully."
"""

    uninstall_sh = f"""#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
TARGET_DIR="${{1:-}}"

if [[ -z "$TARGET_DIR" ]]; then
  if [[ -d "$SCRIPT_DIR/../Mortal_Data" ]]; then
    TARGET_DIR="$SCRIPT_DIR/../Mortal_Data"
  elif [[ -d "$HOME/.local/share/Steam/steamapps/common/LegendOfMortal/Mortal_Data" ]]; then
    TARGET_DIR="$HOME/.local/share/Steam/steamapps/common/LegendOfMortal/Mortal_Data"
  elif [[ -d "$HOME/.steam/steam/steamapps/common/LegendOfMortal/Mortal_Data" ]]; then
    TARGET_DIR="$HOME/.steam/steam/steamapps/common/LegendOfMortal/Mortal_Data"
  else
    echo "Usage: $0 /path/to/LegendOfMortal/Mortal_Data" >&2
    exit 1
  fi
fi

if [[ -d "$TARGET_DIR/Mortal_Data" ]]; then
  TARGET_DIR="$TARGET_DIR/Mortal_Data"
fi

if [[ ! -d "$TARGET_DIR" ]]; then
  echo "Error: Mortal_Data directory not found: $TARGET_DIR" >&2
  exit 1
fi

for asset in {assets_space}; do
  DST="$TARGET_DIR/$asset"
  BAK="$TARGET_DIR/$asset.bak"
  if [[ -f "$BAK" ]]; then
    mv -f "$BAK" "$DST"
    echo "Restored $BAK -> $DST"
  else
    echo "No backup found for $asset ($BAK)"
  fi
done

echo "Original assets restored."
"""

    bat_install_lines = "\n".join(
        f"""if exist "%TARGET_DIR%\\{name}" (
    if not exist "%TARGET_DIR%\\{name}.bak" (
        copy /y "%TARGET_DIR%\\{name}" "%TARGET_DIR%\\{name}.bak" >nul
        echo Backed up {name} to {name}.bak
    )
)
copy /y "%SCRIPT_DIR%Mortal_Data\\{name}" "%TARGET_DIR%\\{name}" >nul
echo Installed {name}"""
        for name in asset_names
    )

    install_bat = f"""@echo off
setlocal enabledelayedexpansion
set "SCRIPT_DIR=%~dp0"
set "TARGET_DIR=%~1"

if "%TARGET_DIR%"=="" (
    if exist "%SCRIPT_DIR%..\\Mortal_Data" (
        set "TARGET_DIR=%SCRIPT_DIR%..\\Mortal_Data"
    ) else if exist "%ProgramFiles(x86)%\\Steam\\steamapps\\common\\LegendOfMortal\\Mortal_Data" (
        set "TARGET_DIR=%ProgramFiles(x86)%\\Steam\\steamapps\\common\\LegendOfMortal\\Mortal_Data"
    ) else if exist "%ProgramFiles%\\Steam\\steamapps\\common\\LegendOfMortal\\Mortal_Data" (
        set "TARGET_DIR=%ProgramFiles%\\Steam\\steamapps\\common\\LegendOfMortal\\Mortal_Data"
    ) else (
        echo Usage: install_patch.bat "C:\\Path\\To\\LegendOfMortal\\Mortal_Data"
        exit /b 1
    )
)

if exist "%TARGET_DIR%\\Mortal_Data" (
    set "TARGET_DIR=%TARGET_DIR%\\Mortal_Data"
)

if not exist "%TARGET_DIR%" (
    echo Error: Mortal_Data directory not found: "%TARGET_DIR%"
    exit /b 1
)

{bat_install_lines}

echo Vietnamese patch installed successfully.
endlocal
"""

    bat_uninstall_lines = "\n".join(
        f"""if exist "%TARGET_DIR%\\{name}.bak" (
    move /y "%TARGET_DIR%\\{name}.bak" "%TARGET_DIR%\\{name}" >nul
    echo Restored {name} from {name}.bak
) else (
    echo No backup found for {name}
)"""
        for name in asset_names
    )

    uninstall_bat = f"""@echo off
setlocal enabledelayedexpansion
set "SCRIPT_DIR=%~dp0"
set "TARGET_DIR=%~1"

if "%TARGET_DIR%"=="" (
    if exist "%SCRIPT_DIR%..\\Mortal_Data" (
        set "TARGET_DIR=%SCRIPT_DIR%..\\Mortal_Data"
    ) else if exist "%ProgramFiles(x86)%\\Steam\\steamapps\\common\\LegendOfMortal\\Mortal_Data" (
        set "TARGET_DIR=%ProgramFiles(x86)%\\Steam\\steamapps\\common\\LegendOfMortal\\Mortal_Data"
    ) else if exist "%ProgramFiles%\\Steam\\steamapps\\common\\LegendOfMortal\\Mortal_Data" (
        set "TARGET_DIR=%ProgramFiles%\\Steam\\steamapps\\common\\LegendOfMortal\\Mortal_Data"
    ) else (
        echo Usage: uninstall_patch.bat "C:\\Path\\To\\LegendOfMortal\\Mortal_Data"
        exit /b 1
    )
)

if exist "%TARGET_DIR%\\Mortal_Data" (
    set "TARGET_DIR=%TARGET_DIR%\\Mortal_Data"
)

if not exist "%TARGET_DIR%" (
    echo Error: Mortal_Data directory not found: "%TARGET_DIR%"
    exit /b 1
)

{bat_uninstall_lines}

echo Original assets restored.
endlocal
"""

    readme = f"""Legend of Mortal - Vietnamese Localization Patch
================================================

Included Patched Assets:
{assets_list}

Installation (Linux / Steam Deck):
  chmod +x install_patch.sh uninstall_patch.sh
  ./install_patch.sh "/path/to/LegendOfMortal/Mortal_Data"

Installation (Windows):
  Run install_patch.bat (or drag your Mortal_Data folder onto install_patch.bat,
  or run: install_patch.bat "C:\\Program Files (x86)\\Steam\\steamapps\\common\\LegendOfMortal\\Mortal_Data")

Uninstallation:
  Run ./uninstall_patch.sh (Linux) or uninstall_patch.bat (Windows) to restore
  the automatically created .bak files back to their original state.

Note: In game settings, select Simplified Chinese (简体中文) to display the
Vietnamese localization. Do not delete the .bak backup files if you plan to uninstall.
"""

    return {
        "install_patch.sh": install_sh,
        "uninstall_patch.sh": uninstall_sh,
        "install_patch.bat": install_bat,
        "uninstall_patch.bat": uninstall_bat,
        "README_PATCH.txt": readme,
    }


def _match_translated_jsons(
    mortal_dir: Path,
    json_dir: Path,
) -> tuple[dict[str, dict[int, list[tuple[str, str]]]], int]:
    """Match translated JSON files in json_dir to (asset_name, path_id) targets."""
    updates_by_asset: dict[str, dict[int, list[tuple[str, str]]]] = {}
    matched_count = 0
    unmatched: list[tuple[str | None, list[tuple[str, str]]]] = []

    for json_path in sorted(json_dir.glob("*.json")):
        raw_data = json.loads(json_path.read_text(encoding="utf-8"))
        entries_raw, _ = parse_json_entries(raw_data)
        if not entries_raw:
            continue

        entries: list[tuple[str, str]] = [
            (str(item["Name"]), str(item["Text"]))
            for item in entries_raw
            if isinstance(item, dict) and "Name" in item and "Text" in item
        ]
        if not entries:
            continue

        asset_file = raw_data.get("AssetFile") if isinstance(raw_data, dict) else None
        path_id = raw_data.get("PathId") if isinstance(raw_data, dict) else None
        language_hint = raw_data.get("Language") if isinstance(raw_data, dict) else None

        if (
            isinstance(asset_file, str)
            and asset_file
            and isinstance(path_id, int)
            and not isinstance(path_id, bool)
        ):
            updates_by_asset.setdefault(asset_file, {})[path_id] = entries
            matched_count += 1
            continue

        match = _ASSET_FILENAME_RE.match(json_path.name)
        if match:
            matched_asset = match.group(1)
            matched_pid = int(match.group(2))
            updates_by_asset.setdefault(matched_asset, {})[matched_pid] = entries
            matched_count += 1
            continue

        unmatched.append((language_hint if isinstance(language_hint, str) else None, entries))

    if unmatched:
        # Fallback index by (entry_count, first_entry_name) across clean level* assets
        fallback_index: dict[tuple[int, str], list[tuple[str, int, str]]] = {}
        for asset_name in _iter_level_asset_names(mortal_dir):
            asset_path = _resolve_clean_asset_path(mortal_dir, asset_name)
            if asset_path is None:
                continue
            sf = parse_serialized_file(asset_path)
            for obj in sf.objects:
                obj_bytes = sf.get_object_bytes(obj)
                if LEAN_CSV_SIG not in obj_bytes:
                    continue
                csv_data = parse_lean_language_csv(obj_bytes)
                if csv_data is None or not csv_data.entries:
                    continue
                key = (len(csv_data.entries), csv_data.entries[0][0])
                fallback_index.setdefault(key, []).append(
                    (asset_name, obj.path_id, csv_data.language)
                )

        for lang_hint, entries in unmatched:
            key = (len(entries), entries[0][0])
            candidates = fallback_index.get(key, [])
            target_lang = lang_hint or "ChineseSimplified"
            filtered = [c for c in candidates if c[2] == target_lang] or candidates
            assigned = False
            for asset_name, pid, _ in filtered:
                asset_map = updates_by_asset.setdefault(asset_name, {})
                if pid not in asset_map:
                    asset_map[pid] = entries
                    assigned = True
            if assigned:
                matched_count += 1

    return updates_by_asset, matched_count


def build_patched_assets(
    mortal_data_dir: str | Path,
    translated_json_dir: str | Path,
    output_patch_dir: str | Path,
    create_zip: bool = False,
    zip_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build patched Unity SerializedFile assets and installer scripts without modifying mortal_data_dir."""
    mortal_dir = Path(mortal_data_dir)
    if not mortal_dir.is_dir():
        raise FileNotFoundError(f"Mortal_Data directory not found: {mortal_dir}")

    json_dir = Path(translated_json_dir)
    if not json_dir.is_dir():
        raise FileNotFoundError(f"Translated JSON directory not found: {json_dir}")

    out_patch_dir = Path(output_patch_dir)
    patch_mortal_dir = out_patch_dir / "Mortal_Data"
    patch_mortal_dir.mkdir(parents=True, exist_ok=True)

    updates_by_asset, matched_jsons = _match_translated_jsons(mortal_dir, json_dir)
    if not updates_by_asset:
        raise ValueError(f"No matching translated JSON entries found in {json_dir}")

    patched_assets: list[str] = []
    total_patched_objects = 0
    total_patched_entries = 0

    for asset_name in sorted(updates_by_asset):
        src_asset_path = _resolve_clean_asset_path(mortal_dir, asset_name)
        if src_asset_path is None:
            raise FileNotFoundError(
                f"Source asset '{asset_name}' not found in {mortal_dir}"
            )
        sf = parse_serialized_file(src_asset_path)
        rebuilt_bytes, obj_count, entry_count = _rebuild_serialized_file(
            sf, updates_by_asset[asset_name]
        )
        dst_asset_path = patch_mortal_dir / asset_name
        dst_asset_path.write_bytes(rebuilt_bytes)
        patched_assets.append(asset_name)
        total_patched_objects += obj_count
        total_patched_entries += entry_count

    scripts_map = _render_patch_scripts(patched_assets)
    written_scripts: list[Path] = []
    for filename, content in scripts_map.items():
        script_path = out_patch_dir / filename
        script_path.write_text(content, encoding="utf-8")
        if filename.endswith(".sh"):
            script_path.chmod(0o755)
        written_scripts.append(script_path)

    final_zip_path: Path | None = None
    if create_zip:
        final_zip_path = (
            Path(zip_path) if zip_path is not None else out_patch_dir / "lom_vietnamese_patch.zip"
        )
        final_zip_path.parent.mkdir(parents=True, exist_ok=True)

        files_to_bundle = [
            p
            for p in sorted(out_patch_dir.rglob("*"))
            if p.is_file() and p.resolve() != final_zip_path.resolve()
        ]
        with zipfile.ZipFile(final_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in files_to_bundle:
                zf.write(file_path, arcname=file_path.relative_to(out_patch_dir).as_posix())

    return {
        "patched_assets": patched_assets,
        "patched_objects": total_patched_objects,
        "patched_entries": total_patched_entries,
        "matched_json_files": matched_jsons,
        "output_patch_dir": str(out_patch_dir),
        "mortal_data_output_dir": str(patch_mortal_dir),
        "scripts": [str(p) for p in written_scripts],
        "zip_path": str(final_zip_path) if final_zip_path is not None else None,
    }


def install_patch(
    mortal_data_dir: str | Path,
    translated_json_dir: str | Path | None = None,
    patch_dir: str | Path | None = None,
    backup: bool = True,
) -> dict[str, Any]:
    """Install patched assets into mortal_data_dir, creating .bak backups if missing."""
    mortal_dir = Path(mortal_data_dir)
    if not mortal_dir.is_dir():
        raise FileNotFoundError(f"Mortal_Data directory not found: {mortal_dir}")

    if patch_dir is not None:
        patch_root = Path(patch_dir)
        candidate_dir = patch_root / "Mortal_Data"
        source_mortal_dir = candidate_dir if candidate_dir.is_dir() else patch_root
        if not source_mortal_dir.is_dir():
            raise FileNotFoundError(f"Patch directory not found: {patch_root}")
        return _copy_patched_assets_into_game(mortal_dir, source_mortal_dir, backup=backup)

    if translated_json_dir is not None:
        with tempfile.TemporaryDirectory(prefix="lom_patch_") as tmp_dir:
            build_patched_assets(
                mortal_data_dir=mortal_dir,
                translated_json_dir=translated_json_dir,
                output_patch_dir=tmp_dir,
                create_zip=False,
            )
            return _copy_patched_assets_into_game(
                mortal_dir, Path(tmp_dir) / "Mortal_Data", backup=backup
            )

    raise ValueError("Either translated_json_dir or patch_dir must be provided to install_patch")


def _copy_patched_assets_into_game(
    mortal_dir: Path,
    source_mortal_dir: Path,
    backup: bool,
) -> dict[str, Any]:
    installed_assets: list[str] = []
    backups_created: list[str] = []

    for src_file in sorted(source_mortal_dir.iterdir(), key=lambda p: p.name):
        if not src_file.is_file() or src_file.name.endswith(_SKIP_ASSET_SUFFIXES):
            continue
        dst_file = mortal_dir / src_file.name
        bak_file = mortal_dir / f"{src_file.name}.bak"
        if backup and dst_file.is_file() and not bak_file.exists():
            shutil.copy2(dst_file, bak_file)
            backups_created.append(bak_file.name)
        shutil.copy2(src_file, dst_file)
        installed_assets.append(src_file.name)

    if not installed_assets:
        raise ValueError(f"No patched asset files found in {source_mortal_dir}")

    return {
        "mortal_data_dir": str(mortal_dir),
        "installed_assets": installed_assets,
        "backups_created": backups_created,
    }


def restore_backup(mortal_data_dir: str | Path) -> dict[str, Any]:
    """Restore all <asset>.bak backups in mortal_data_dir back to <asset>."""
    mortal_dir = Path(mortal_data_dir)
    if not mortal_dir.is_dir():
        raise FileNotFoundError(f"Mortal_Data directory not found: {mortal_dir}")

    restored_assets: list[str] = []
    for bak_file in sorted(mortal_dir.glob("*.bak"), key=lambda p: p.name):
        if not bak_file.is_file():
            continue
        target_name = bak_file.name[:-4]
        target_file = mortal_dir / target_name
        shutil.copy2(bak_file, target_file)
        bak_file.unlink()
        restored_assets.append(target_name)

    return {
        "mortal_data_dir": str(mortal_dir),
        "restored_assets": restored_assets,
    }
