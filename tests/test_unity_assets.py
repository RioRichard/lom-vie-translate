from __future__ import annotations

import json
import os
import stat
import struct
import zipfile
from pathlib import Path

import pytest

from src.unity_assets import (
    LEAN_CSV_SIG,
    build_patched_assets,
    extract_lean_local_jsons,
    install_patch,
    parse_lean_language_csv,
    parse_serialized_file,
    restore_backup,
)
from tool.patch_game import build_parser
from tool.patch_game import main as patch_game_main


def _align4(n: int) -> int:
    return (n + 3) & ~3


def _pack_str(text: str) -> bytes:
    raw = text.encode("utf-8")
    pad = (-len(raw)) & 3
    return struct.pack("<I", len(raw)) + raw + (b"\x00" * pad)


def _make_lean_csv_object(
    language: str,
    entries: list[tuple[str, str]],
    m_name: str = "",
) -> bytes:
    # MonoBehaviour header: m_GameObject(12) + m_Enabled(4) + m_Script(12) + m_Name + Source(12)
    buf = bytearray()
    buf.extend(struct.pack("<iq", 0, 100))
    buf.extend(struct.pack("<B3x", 1))
    buf.extend(struct.pack("<iq", 1, 200))
    buf.extend(_pack_str(m_name))
    buf.extend(struct.pack("<iq", 2, 300))
    buf.extend(_pack_str(language))
    buf.extend(LEAN_CSV_SIG)
    buf.extend(struct.pack("<I", len(entries)))
    for name, text in entries:
        buf.extend(_pack_str(name))
        buf.extend(_pack_str(text))
    return bytes(buf)


def _build_synthetic_v22_asset(objects_spec: list[tuple[int, int, bytes]]) -> bytes:
    """Build a valid Unity 2020.3.49f1 SerializedFile v22 binary (has_type_tree=0)."""
    meta = bytearray()
    meta.extend(b"2020.3.49f1\x00")
    # platform=19 (StandaloneWindows64), has_type_tree=0, type_count=2
    meta.extend(struct.pack("<iBi", 19, 0, 2))
    # Type 0: GameObject (class_id=1, +16 byte OldTypeHash)
    meta.extend(struct.pack("<iBh", 1, 0, -1))
    meta.extend(b"\x11" * 16)
    # Type 1: MonoBehaviour (class_id=114, +16 ScriptID +16 OldTypeHash)
    meta.extend(struct.pack("<iBh", 114, 0, 0))
    meta.extend(b"\x22" * 16)
    meta.extend(b"\x33" * 16)

    meta.extend(struct.pack("<i", len(objects_spec)))
    table_rel = _align4(len(meta))
    meta.extend(b"\x00" * (table_rel - len(meta)))

    table_pos = 48 + table_rel
    table_bytes_len = len(objects_spec) * 24
    meta.extend(b"\x00" * table_bytes_len)

    # Trailing metadata (e.g. ScriptTypes / Externals) between object table and data_offset
    extra_meta = b"\x01\x00\x00\x00\x01\x00\x00\x00\x0c\x02\x00\x00\x00\x00\x00\x00"
    meta.extend(extra_meta)

    meta_size = len(meta)
    # Align data_offset to 16 bytes
    unaligned_data_off = 48 + meta_size
    data_offset = (unaligned_data_off + 15) & ~15
    header_pad = b"\x00" * (data_offset - unaligned_data_off)

    data_buf = bytearray()
    table_entries: list[tuple[int, int, int, int]] = []
    for idx, (path_id, type_id, obj_bytes) in enumerate(objects_spec):
        if idx > 0:
            pad = (8 - (len(data_buf) % 8)) % 8
            if pad:
                data_buf.extend(b"\x00" * pad)
        byte_start = len(data_buf)
        data_buf.extend(obj_bytes)
        table_entries.append((path_id, byte_start, len(obj_bytes), type_id))

    file_size = data_offset + len(data_buf)
    header = bytearray(48)
    struct.pack_into(">IIIIB3s", header, 0, 0, 0, 22, 0, 0, b"\x00\x00\x00")
    struct.pack_into(">IQQQ", header, 20, meta_size, file_size, data_offset, 0)

    full = bytearray(header)
    full.extend(meta)
    full.extend(header_pad)
    full.extend(data_buf)

    for idx, (path_id, byte_start, byte_size, type_id) in enumerate(table_entries):
        struct.pack_into("<qQII", full, table_pos + idx * 24, path_id, byte_start, byte_size, type_id)

    return bytes(full)


def _create_sample_mortal_dir(tmp_path: Path) -> tuple[Path, bytes, bytes, bytes, bytes]:
    mortal_dir = tmp_path / "Mortal_Data"
    mortal_dir.mkdir(parents=True, exist_ok=True)

    pre_obj = b"\xAA\xBB\xCC\xDD" * 9 + b"\x01\x02\x03"
    eng_csv_obj = _make_lean_csv_object(
        "English",
        [("Story/D_1_001", "Hello there"), ("Story/D_1_002", "Goodbye")],
    )
    zh_csv_obj = _make_lean_csv_object(
        "ChineseSimplified",
        [
            ("Story/D_1_001", "你好，少侠！[|]请留步。"),
            ("Story/D_1_002", "伤害+{{0:N0}}"),
        ],
    )
    post_obj = b"\x11\x22\x33\x44\x55\x66\x77\x88\x99"

    level0_bytes = _build_synthetic_v22_asset(
        [
            (10, 0, pre_obj),
            (20, 1, eng_csv_obj),
            (30, 1, zh_csv_obj),
            (40, 0, post_obj),
        ]
    )
    (mortal_dir / "level0").write_bytes(level0_bytes)
    # Create dummy .resS and .bak files that extract_lean_local_jsons must ignore
    (mortal_dir / "level0.resS").write_bytes(b"\x00" * 64)
    (mortal_dir / "level99.bak").write_bytes(level0_bytes)
    return mortal_dir, level0_bytes, pre_obj, eng_csv_obj, post_obj


def test_parse_serialized_file_and_csv_roundtrip(tmp_path: Path) -> None:
    mortal_dir, level0_bytes, pre_obj, eng_csv_obj, post_obj = _create_sample_mortal_dir(tmp_path)
    sf = parse_serialized_file(mortal_dir / "level0")

    assert sf.version == 22
    assert sf.unity_version == "2020.3.49f1"
    assert sf.has_type_tree == 0
    assert sf.file_size == len(level0_bytes)
    assert [o.path_id for o in sf.objects] == [10, 20, 30, 40]
    assert sf.get_object_bytes(sf.objects[0]) == pre_obj
    assert sf.get_object_bytes(sf.objects[1]) == eng_csv_obj
    assert sf.get_object_bytes(sf.objects[3]) == post_obj

    assert parse_lean_language_csv(pre_obj) is None
    zh_csv = parse_lean_language_csv(sf.get_object_bytes(sf.objects[2]))
    assert zh_csv is not None
    assert zh_csv.language == "ChineseSimplified"
    assert zh_csv.entries == [
        ("Story/D_1_001", "你好，少侠！[|]请留步。"),
        ("Story/D_1_002", "伤害+{{0:N0}}"),
    ]


def test_parse_lean_language_csv_rejects_trailing_bytes() -> None:
    valid_obj = _make_lean_csv_object("ChineseSimplified", [("UI/Ok", "确认")])
    with pytest.raises(ValueError, match="did not consume object"):
        parse_lean_language_csv(valid_obj + b"\x00\x00\x00\x00")


def test_extract_build_install_and_restore_end_to_end(tmp_path: Path) -> None:
    mortal_dir, orig_level0_bytes, pre_obj, eng_csv_obj, post_obj = _create_sample_mortal_dir(
        tmp_path
    )
    # Remove level99.bak before testing clean install/restore counts
    (mortal_dir / "level99.bak").unlink()

    extracted_dir = tmp_path / "extracted_json"
    extracted_files = extract_lean_local_jsons(mortal_dir, extracted_dir)
    assert len(extracted_files) == 1
    extracted_file = extracted_files[0]
    assert extracted_file.name == "level0_00030_Story.json"

    extracted_payload = json.loads(extracted_file.read_text(encoding="utf-8"))
    assert extracted_payload == {
        "Language": "ChineseSimplified",
        "AssetFile": "level0",
        "PathId": 30,
        "entries": {
            "Array": [
                {"Name": "Story/D_1_001", "Text": "你好，少侠！[|]请留步。"},
                {"Name": "Story/D_1_002", "Text": "伤害+{{0:N0}}"},
            ]
        },
    }

    # Produce Vietnamese translated JSON (significantly different byte sizes)
    translated_dir = tmp_path / "translated_json"
    translated_dir.mkdir(parents=True, exist_ok=True)
    vi_entries = [
        {"Name": "Story/D_1_001", "Text": "Xin chào thiếu hiệp![|]Xin dừng bước một lát."},
        {"Name": "Story/D_1_002", "Text": "Sát thương +{{0:N0}}"},
    ]
    translated_payload = {
        "Language": "ChineseSimplified",
        "AssetFile": "level0",
        "PathId": 30,
        "entries": {"Array": vi_entries},
    }
    (translated_dir / extracted_file.name).write_text(
        json.dumps(translated_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    patch_out_dir = tmp_path / "patch_out"
    build_res = build_patched_assets(
        mortal_data_dir=mortal_dir,
        translated_json_dir=translated_dir,
        output_patch_dir=patch_out_dir,
        create_zip=True,
    )

    # Original Mortal_Data must remain completely untouched
    assert (mortal_dir / "level0").read_bytes() == orig_level0_bytes
    assert not (mortal_dir / "level0.bak").exists()

    assert build_res["patched_assets"] == ["level0"]
    assert build_res["patched_objects"] == 1
    assert build_res["patched_entries"] == 2

    patched_level0 = patch_out_dir / "Mortal_Data" / "level0"
    assert patched_level0.is_file()

    for script_name in (
        "install_patch.sh",
        "uninstall_patch.sh",
        "install_patch.bat",
        "uninstall_patch.bat",
        "README_PATCH.txt",
    ):
        assert (patch_out_dir / script_name).is_file()

    if os.name != "nt":
        assert (patch_out_dir / "install_patch.sh").stat().st_mode & stat.S_IXUSR
        assert (patch_out_dir / "uninstall_patch.sh").stat().st_mode & stat.S_IXUSR

    zip_file = patch_out_dir / "lom_vietnamese_patch.zip"
    assert zip_file.is_file()
    with zipfile.ZipFile(zip_file, "r") as zf:
        names = set(zf.namelist())
        assert "Mortal_Data/level0" in names
        assert "install_patch.sh" in names
        assert "uninstall_patch.sh" in names
        assert "install_patch.bat" in names
        assert "uninstall_patch.bat" in names
        assert "README_PATCH.txt" in names
        assert "lom_vietnamese_patch.zip" not in names

    # Re-parse patched level0 and verify Vietnamese text & untouched non-CSV objects
    patched_sf = parse_serialized_file(patched_level0)
    assert patched_sf.file_size == patched_level0.stat().st_size
    assert patched_sf.get_object_bytes(patched_sf.objects[0]) == pre_obj
    assert patched_sf.get_object_bytes(patched_sf.objects[1]) == eng_csv_obj
    assert patched_sf.get_object_bytes(patched_sf.objects[3]) == post_obj

    re_csv = parse_lean_language_csv(patched_sf.get_object_bytes(patched_sf.objects[2]))
    assert re_csv is not None
    assert re_csv.language == "ChineseSimplified"
    assert re_csv.entries == [
        ("Story/D_1_001", "Xin chào thiếu hiệp![|]Xin dừng bước một lát."),
        ("Story/D_1_002", "Sát thương +{{0:N0}}"),
    ]

    # Install patch into Mortal_Data (creates .bak)
    install_res = install_patch(mortal_data_dir=mortal_dir, patch_dir=patch_out_dir, backup=True)
    assert install_res["installed_assets"] == ["level0"]
    assert install_res["backups_created"] == ["level0.bak"]
    assert (mortal_dir / "level0.bak").read_bytes() == orig_level0_bytes
    assert (mortal_dir / "level0").read_bytes() == patched_level0.read_bytes()

    # Re-installing must NOT clobber the clean .bak backup
    install_res_2 = install_patch(mortal_data_dir=mortal_dir, patch_dir=patch_out_dir, backup=True)
    assert install_res_2["backups_created"] == []
    assert (mortal_dir / "level0.bak").read_bytes() == orig_level0_bytes

    # Restore backup and verify byte-identical original restoration
    restore_res = restore_backup(mortal_dir)
    assert restore_res["restored_assets"] == ["level0"]
    assert (mortal_dir / "level0").read_bytes() == orig_level0_bytes
    assert not (mortal_dir / "level0.bak").exists()


def test_build_patched_assets_matching_fallbacks_and_bak_source(tmp_path: Path) -> None:
    mortal_dir, orig_level0_bytes, _, _, _ = _create_sample_mortal_dir(tmp_path)
    (mortal_dir / "level99.bak").unlink()

    # Simulate an already-patched level0 with clean original saved in level0.bak
    (mortal_dir / "level0.bak").write_bytes(orig_level0_bytes)
    (mortal_dir / "level0").write_bytes(b"CORRUPTED_OR_OLD_PATCH")

    # 1. Filename regex match (no AssetFile/PathId in JSON)
    json_dir_regex = tmp_path / "json_regex"
    json_dir_regex.mkdir()
    (json_dir_regex / "level0_00030_Story.json").write_text(
        json.dumps(
            {
                "Language": "ChineseSimplified",
                "entries": [
                    {"Name": "Story/D_1_001", "Text": "Bản regex 1"},
                    {"Name": "Story/D_1_002", "Text": "Bản regex 2"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    patch_regex = tmp_path / "patch_regex"
    res1 = build_patched_assets(mortal_dir, json_dir_regex, patch_regex)
    assert res1["patched_assets"] == ["level0"]
    sf1 = parse_serialized_file(patch_regex / "Mortal_Data" / "level0")
    csv1 = parse_lean_language_csv(sf1.get_object_bytes(sf1.objects[2]))
    assert csv1 is not None and csv1.entries == [
        ("Story/D_1_001", "Bản regex 1"),
        ("Story/D_1_002", "Bản regex 2"),
    ]

    # 2. Fallback match by first entry Name + count (arbitrary filename, no AssetFile/PathId)
    json_dir_fallback = tmp_path / "json_fallback"
    json_dir_fallback.mkdir()
    (json_dir_fallback / "custom_dump.json").write_text(
        json.dumps(
            {
                "Language": "ChineseSimplified",
                "entries": {
                    "Array": [
                        {"Name": "Story/D_1_001", "Text": "Bản fallback 1"},
                        {"Name": "Story/D_1_002", "Text": "Bản fallback 2"},
                    ]
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    patch_fallback = tmp_path / "patch_fallback"
    res2 = build_patched_assets(mortal_dir, json_dir_fallback, patch_fallback)
    assert res2["patched_assets"] == ["level0"]
    sf2 = parse_serialized_file(patch_fallback / "Mortal_Data" / "level0")
    csv2 = parse_lean_language_csv(sf2.get_object_bytes(sf2.objects[2]))
    assert csv2 is not None and csv2.entries == [
        ("Story/D_1_001", "Bản fallback 1"),
        ("Story/D_1_002", "Bản fallback 2"),
    ]


def test_patch_game_cli_build_install_restore(tmp_path: Path) -> None:
    mortal_dir, orig_level0_bytes, _, _, _ = _create_sample_mortal_dir(tmp_path)
    (mortal_dir / "level99.bak").unlink()

    extracted_dir = tmp_path / "extracted"
    extract_lean_local_jsons(mortal_dir, extracted_dir)
    json_file = extracted_dir / "level0_00030_Story.json"
    data = json.loads(json_file.read_text(encoding="utf-8"))
    data["entries"]["Array"][0]["Text"] = "Xin chào CLI"
    json_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    parser = build_parser()
    parsed = parser.parse_args(["-md", str(mortal_dir), "--zip"])
    assert parsed.mode == "build"
    assert parsed.mortal_data_dir == str(mortal_dir)
    assert parsed.zip is True

    patch_dir = tmp_path / "cli_patch_out"
    build_res = patch_game_main(
        [
            "--mode",
            "build",
            "-md",
            str(mortal_dir),
            "-jd",
            str(extracted_dir),
            "-opd",
            str(patch_dir),
            "--zip",
        ]
    )
    assert build_res["patched_assets"] == ["level0"]
    assert Path(build_res["zip_path"]).is_file()

    install_res = patch_game_main(
        [
            "--mode",
            "install",
            "-md",
            str(mortal_dir),
            "-pd",
            str(patch_dir),
        ]
    )
    assert install_res["installed_assets"] == ["level0"]
    assert (mortal_dir / "level0.bak").read_bytes() == orig_level0_bytes

    patched_sf = parse_serialized_file(mortal_dir / "level0")
    patched_csv = parse_lean_language_csv(patched_sf.get_object_bytes(patched_sf.objects[2]))
    assert patched_csv is not None
    assert patched_csv.entries[0] == ("Story/D_1_001", "Xin chào CLI")

    restore_res = patch_game_main(["--mode", "restore", "-md", str(mortal_dir)])
    assert restore_res["restored_assets"] == ["level0"]
    assert (mortal_dir / "level0").read_bytes() == orig_level0_bytes


def test_install_from_json_dir_and_invalid_serialized_file(tmp_path: Path) -> None:
    mortal_dir, orig_level0_bytes, _, _, _ = _create_sample_mortal_dir(tmp_path)
    (mortal_dir / "level99.bak").unlink()

    extracted_dir = tmp_path / "extracted_direct"
    extract_lean_local_jsons(mortal_dir, extracted_dir)
    json_file = extracted_dir / "level0_00030_Story.json"
    data = json.loads(json_file.read_text(encoding="utf-8"))
    data["entries"]["Array"][1]["Text"] = "Sát thương trực tiếp +{{0:N0}}"
    json_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    # Install directly via CLI without --patch-dir (builds into temp dir then installs)
    res = patch_game_main(
        ["--mode", "install", "-md", str(mortal_dir), "-jd", str(extracted_dir)]
    )
    assert res["installed_assets"] == ["level0"]
    assert res["backups_created"] == ["level0.bak"]
    assert (mortal_dir / "level0.bak").read_bytes() == orig_level0_bytes

    sf = parse_serialized_file(mortal_dir / "level0")
    csv = parse_lean_language_csv(sf.get_object_bytes(sf.objects[2]))
    assert csv is not None
    assert csv.entries[1] == ("Story/D_1_002", "Sát thương trực tiếp +{{0:N0}}")

    restore_backup(mortal_dir)
    assert (mortal_dir / "level0").read_bytes() == orig_level0_bytes

    # Error handling: truncated and unsupported version headers
    with pytest.raises(ValueError, match="too small"):
        parse_serialized_file(b"\x00" * 10)

    bad_ver = bytearray(orig_level0_bytes)
    struct.pack_into(">I", bad_ver, 8, 21)
    with pytest.raises(ValueError, match="Unsupported SerializedFile version: 21"):
        parse_serialized_file(bytes(bad_ver))

