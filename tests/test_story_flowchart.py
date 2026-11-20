from __future__ import annotations

import struct
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.story_flowchart import (
    LEAN_CSV_SIG,
    DialogueLineNode,
    ScriptNode,
    StoryFlowchart,
    extract_story_flowchart_from_mortal_data,
    parse_lua_story_script,
)
from tool import build_story_flowchart, unpack_game


def _pack_aligned_str(text: str) -> bytes:
    raw = text.encode("utf-8")
    pad = (-len(raw)) % 4
    return struct.pack("<I", len(raw)) + raw + (b"\x00" * pad)


def _build_synthetic_unity_v22_file(
    objects: list[tuple[int, int, bytes]],
    *,
    unity_version: str = "2020.3.49f1",
) -> bytes:
    """Build a minimal valid Unity v22 SerializedFile with `(path_id, class_id, obj_bytes)`."""
    unique_classes: list[int] = []
    class_to_tid: dict[int, int] = {}
    for _, cid, _ in objects:
        if cid not in class_to_tid:
            class_to_tid[cid] = len(unique_classes)
            unique_classes.append(cid)

    meta = bytearray()
    meta.extend(unity_version.encode("utf-8") + b"\x00")
    meta.extend(struct.pack("<iBi", 19, 0, len(unique_classes)))
    for cid in unique_classes:
        meta.extend(struct.pack("<iBh", cid, 0, -1))
        if cid == 114 or cid < 0:
            meta.extend(b"\x11" * 16)
        meta.extend(b"\x22" * 16)

    meta.extend(struct.pack("<i", len(objects)))
    while len(meta) % 4 != 0:
        meta.append(0)

    data_buf = bytearray()
    obj_table = bytearray()
    for pid, cid, payload in objects:
        pad = (-len(data_buf)) % 8
        data_buf.extend(b"\x00" * pad)
        byte_start = len(data_buf)
        data_buf.extend(payload)
        obj_table.extend(struct.pack("<qQII", pid, byte_start, len(payload), class_to_tid[cid]))

    meta_total = bytes(meta) + bytes(obj_table)
    # 48-byte v22 header -> align data_offset to 16 bytes
    raw_data_offset = 48 + len(meta_total)
    header_pad = (-raw_data_offset) % 16
    data_offset = raw_data_offset + header_pad
    file_size = data_offset + len(data_buf)

    header = bytearray(48)
    struct.pack_into(">IIII", header, 0, len(meta_total), file_size, 22, data_offset)
    header[16] = 0  # little-endian data
    struct.pack_into(">IQQQ", header, 20, len(meta_total), file_size, data_offset, 0)

    return bytes(header) + meta_total + (b"\x00" * header_pad) + bytes(data_buf)


def _make_text_asset_bytes(name: str, script: str) -> bytes:
    return _pack_aligned_str(name) + _pack_aligned_str(script)


def _make_lean_csv_bytes(language: str, entries: list[tuple[str, str]]) -> bytes:
    buf = bytearray(b"\x00" * 28)
    buf.extend(_pack_aligned_str(language))
    buf.extend(LEAN_CSV_SIG)
    buf.extend(struct.pack("<I", len(entries)))
    for k, v in entries:
        buf.extend(_pack_aligned_str(k))
        buf.extend(_pack_aligned_str(v))
    return bytes(buf)


def _make_checkpoint_monobehaviour_bytes(cp_id: str, title: str, entry_script: str) -> bytes:
    buf = bytearray(b"\x00" * 28)
    buf.extend(_pack_aligned_str(cp_id))
    buf.extend(_pack_aligned_str(cp_id))
    buf.extend(_pack_aligned_str(title))
    buf.extend(_pack_aligned_str(""))
    buf.extend(_pack_aligned_str(entry_script))
    return bytes(buf)


def test_parse_lua_story_script_branch_isolation_and_non_sequential_keys() -> None:
    lua_script = """
    -- Setup stage
    stage.show{character=characters.Get("player"), portrait=characters.GetPortrait("player", "normal")}
    stage.show{character=characters.Get("brother2"), portrait=characters.GetPortrait("brother2", "normal")}

    setsaydialog(saydialogs.character)
    characters.LoadCharacterPortrait("player", "laugh1")
    setcharacter(characters.Get("player"))
    say(luamanager.GetStoryText("D_Test_001"))

    option_01[1] = "O_Test_Opt_1"
    option_01[2] = "talk+O_Test_Opt_2+0+0"
    local choice_opt = choose(option_01)

    if choice_opt == 1 then
        --index:O_Test_Opt_1
        stage.show{character=characters.Get("girl5")}
        setcharacter(characters.Get("girl5"), characters.GetPortrait("girl5", "smile1"))
        say(luamanager.GetStoryText("D_Test_010"))
        statmodifymanager.Character("girl5", 2, 1)
    elseif choice_opt == 2 then
        --index:O_Test_Opt_2
        stage.hide{character=characters.Get("brother2")}
        setcharacter(characters.Get("player"))
        say(luamanager.GetStoryText("D_Test_020"))
        statmodifymanager.Character("brother2", -5, 1)
    else
        setcharacter(characters.Get("brother2"))
        say(luamanager.GetStoryText("D_Test_025"))
    end

    local sw = checkpointmanager.Switch("Ch_Merge_001")
    if sw == 1 then
        setsaydialog(saydialogs.think)
        setcharacter(characters.Get("player"))
        say(luamanager.GetStoryText("T_Test_030"))
        statmodifymanager.AddFlag("F_ROUTE", 1)
        luamanager.SetNextScript("ch_next_a")
        endgamepanel.Open("20031")
    end
    """

    node = parse_lua_story_script("ch_test_01", lua_script)

    assert node.script_id == "ch_test_01"
    assert node.participants == ["player", "brother2", "girl5"]
    assert node.option_ids == ["O_Test_Opt_1", "O_Test_Opt_2"]
    assert node.next_scripts == ["ch_next_a"]
    assert node.ending_ids == ["20031"]
    assert node.flag_deltas == [("F_ROUTE", 1)]
    assert len(node.relationship_deltas) == 2
    assert node.relationship_deltas[0].model_dump() == {
        "char_id": "girl5",
        "stat_type": 1,
        "delta": 2,
        "at_line_index": 2,
    }
    assert node.relationship_deltas[1].model_dump() == {
        "char_id": "brother2",
        "stat_type": 1,
        "delta": -5,
        "at_line_index": 3,
    }

    by_key = {line.key: line for line in node.lines}
    assert list(by_key.keys()) == [
        "Story/D_Test_001",
        "Story/D_Test_010",
        "Story/D_Test_020",
        "Story/D_Test_025",
        "Story/T_Test_030",
    ]

    l1 = by_key["Story/D_Test_001"]
    assert l1.speaker_id == "player"
    assert l1.portrait_mood == "laugh1"
    assert l1.listeners_on_stage == ["brother2"]
    assert l1.branch_path == "main"
    assert l1.prev_key is None
    assert l1.next_key == "Story/D_Test_010"

    # Branch 1 (O_Test_Opt_1): girl5 joins stage
    l10 = by_key["Story/D_Test_010"]
    assert l10.speaker_id == "girl5"
    assert l10.portrait_mood == "smile1"
    assert l10.listeners_on_stage == ["brother2", "player"]
    assert l10.branch_path == "O_Test_Opt_1"
    assert l10.prev_key == "Story/D_Test_001"
    assert l10.next_key == "Story/T_Test_030"

    # Branch 2 (O_Test_Opt_2): isolated from Branch 1! girl5 MUST NOT be on stage,
    # and prev_key MUST link back to D_Test_001 (not D_Test_010!).
    l20 = by_key["Story/D_Test_020"]
    assert l20.speaker_id == "player"
    assert l20.listeners_on_stage == []
    assert l20.branch_path == "O_Test_Opt_2"
    assert l20.prev_key == "Story/D_Test_001"
    assert l20.next_key == "Story/T_Test_030"

    # Else branch: isolated from Branch 2! brother2 is still on stage, girl5 is NOT.
    l25 = by_key["Story/D_Test_025"]
    assert l25.speaker_id == "brother2"
    assert l25.listeners_on_stage == ["player"]
    assert l25.branch_path == "else"
    assert l25.prev_key == "Story/D_Test_001"
    assert l25.next_key == "Story/T_Test_030"

    # Post-merge Switch branch
    l30 = by_key["Story/T_Test_030"]
    assert l30.line_type == "thought"
    assert l30.branch_path == "Ch_Merge_001#1"
    assert l30.prev_key == "Story/D_Test_025"


def test_parse_lua_line_types_custom_names_and_loop_safety() -> None:
    lua_script = """
    if true then return end
    for i = 1, 3 do
        local x = i
    end
    stage.show{character=characters.Get("player")}
    say(luamanager.GetStoryText("O_Choice_001"))

    characters.SetName("player", "Vô Danh")
    setcharacter(characters.Get("player"))
    say(luamanager.GetStoryText("D_Named_001"))

    setsaydialog(saydialogs.narrative)
    setcharacter(narrative)
    say(luamanager.GetStoryText("N_Scene_001"))

    setsaydialog(saydialogs.think)
    setcharacter(characters.Get("player"))
    say(luamanager.GetStoryText("CustomKey_001"))
    """

    node = parse_lua_story_script("ch_types", lua_script)
    assert [line.line_type for line in node.lines] == [
        "option",
        "dialogue",
        "narrative",
        "thought",
    ]
    assert node.lines[0].speaker_id == "narrative"
    assert node.lines[1].speaker_id == "player"
    assert node.lines[1].speaker_custom_name == "Vô Danh"
    assert node.lines[2].speaker_id == "narrative"
    assert node.lines[3].key == "Story/CustomKey_001"
    assert node.lines[3].branch_path == "main"


def test_story_flowchart_index_get_line_context_and_json_roundtrip(tmp_path: Path) -> None:
    script = parse_lua_story_script(
        "ch_ctx",
        """
        stage.show{character=characters.Get("player")}
        stage.show{character=characters.Get("girl6")}
        setcharacter(characters.Get("player"))
        say(luamanager.GetStoryText("D_Ctx_001"))
        setcharacter(characters.Get("girl6"))
        say(luamanager.GetStoryText("D_Ctx_002"))
        setcharacter(characters.Get("player"))
        say(luamanager.GetStoryText("D_Ctx_003"))
        setcharacter(characters.Get("girl6"))
        say(luamanager.GetStoryText("D_Ctx_004"))
        """,
    )
    flowchart = StoryFlowchart(scripts={"ch_ctx": script})

    # Lookup works both with and without Story/ prefix
    ctx_with = flowchart.get_line_context("Story/D_Ctx_003", window=2, lookahead=1)
    ctx_without = flowchart.get_line_context("D_Ctx_003", window=2, lookahead=1)
    assert ctx_with is not None
    assert ctx_without is not None
    assert ctx_with.line.key == "Story/D_Ctx_003"
    assert [ln.key for ln in ctx_with.prev_lines] == ["Story/D_Ctx_001", "Story/D_Ctx_002"]
    assert [ln.key for ln in ctx_with.next_lines] == ["Story/D_Ctx_004"]
    assert ctx_without.prev_lines == ctx_with.prev_lines

    assert flowchart.get_line_context("Story/DoesNotExist") is None

    # Guard against cycles if hand-crafted
    script_cycle = ScriptNode(
        script_id="cyc",
        lines=[
            DialogueLineNode(
                key="D_A",
                line_type="dialogue",
                speaker_id="player",
                prev_key="Story/D_B",
                next_key="Story/D_B",
            ),
            DialogueLineNode(
                key="D_B",
                line_type="dialogue",
                speaker_id="girl6",
                prev_key="Story/D_A",
                next_key="Story/D_A",
            ),
        ],
    )
    fc_cycle = StoryFlowchart(scripts={"cyc": script_cycle})
    cyc_ctx = fc_cycle.get_line_context("D_A", window=5, lookahead=5)
    assert cyc_ctx is not None
    assert [ln.key for ln in cyc_ctx.prev_lines] == ["Story/D_B"]
    assert [ln.key for ln in cyc_ctx.next_lines] == ["Story/D_B"]

    # JSON roundtrip preserves UTF-8 & rebuilds _index_by_key
    out_file = tmp_path / "flowchart.json"
    flowchart.to_json_file(out_file)
    raw_text = out_file.read_text(encoding="utf-8")
    assert "\\u" not in raw_text

    reloaded = StoryFlowchart.from_json_file(out_file)
    reloaded_ctx = reloaded.get_line_context("D_Ctx_002", window=1, lookahead=2)
    assert reloaded_ctx is not None
    assert [ln.key for ln in reloaded_ctx.prev_lines] == ["Story/D_Ctx_001"]
    assert [ln.key for ln in reloaded_ctx.next_lines] == ["Story/D_Ctx_003", "Story/D_Ctx_004"]


def test_extract_story_flowchart_from_synthetic_mortal_data(tmp_path: Path) -> None:
    mortal_dir = tmp_path / "Mortal_Data"
    mortal_dir.mkdir()

    # resources.assets: duplicate script name (old unlocalized vs new GetStoryText) + fungus JSON
    old_lua = 'setcharacter(characters.Get("player"))\nsay("旧文本")'
    new_lua = (
        'stage.show{character=characters.Get("player")}\n'
        'stage.show{character=characters.Get("girl6")}\n'
        'setcharacter(characters.Get("girl6"))\n'
        'say(luamanager.GetStoryText("D_S9101_01_001"))\n'
    )
    fungus_json = '{\n  "player_name": {"ChineseTraditional": "巨八"},\n}'

    res_bytes = _build_synthetic_unity_v22_file(
        [
            (1, 49, _make_text_asset_bytes("S9101_01", new_lua)),
            (2, 49, _make_text_asset_bytes("S9101_01", old_lua)),
            (3, 49, _make_text_asset_bytes("fungus_character_name", fungus_json)),
            (4, 49, _make_text_asset_bytes("inspect", "if a == 1 then return end")),
        ]
    )
    (mortal_dir / "resources.assets").write_bytes(res_bytes)

    # level0: Korean CSV (must be ignored) + ChineseSimplified Character/CombatCharacter CSVs
    lvl0_bytes = _build_synthetic_unity_v22_file(
        [
            (10, 114, _make_lean_csv_bytes("Korean", [("Character/girl6", "한국어")])),
            (
                11,
                114,
                _make_lean_csv_bytes(
                    "ChineseSimplified",
                    [
                        ("Character/player", "赵活"),
                        ("Character/girl6", "夏侯兰"),
                        ("CharacterTitle/girl6", "夺魄幽兰"),
                        ("CombatCharacter/Name/special99", "神秘剑客"),
                        ("CombatCharacter/Title/special99", "剑圣"),
                    ],
                ),
            ),
        ]
    )
    (mortal_dir / "level0").write_bytes(lvl0_bytes)

    # globalgamemanagers.assets: checkpoint title for S9101 -> S9101_01
    ggm_bytes = _build_synthetic_unity_v22_file(
        [
            (100, 114, _make_checkpoint_monobehaviour_bytes("S9101", "支線「睡過頭」", "S9101_01")),
        ]
    )
    (mortal_dir / "globalgamemanagers.assets").write_bytes(ggm_bytes)

    flowchart = extract_story_flowchart_from_mortal_data(mortal_dir)

    assert "S9101_01" in flowchart.scripts
    script = flowchart.scripts["S9101_01"]
    assert script.title_zh == "支線「睡過頭」"
    assert [ln.key for ln in script.lines] == ["Story/D_S9101_01_001"]

    assert flowchart.characters["player"].vi_name == "Triệu Hoạt"
    assert "巨八" in flowchart.characters["player"].aliases
    assert flowchart.characters["girl6"].zh_name == "夏侯兰"
    assert flowchart.characters["girl6"].zh_title == "夺魄幽兰"
    assert flowchart.characters["girl6"].vi_name == "Hạ Hầu Lan"
    assert flowchart.characters["special99"].zh_name == "神秘剑客"
    assert flowchart.characters["special99"].zh_title == "剑圣"

    # Verify build_story_flowchart CLI and unpack_game CLI
    fc_out = tmp_path / "out_fc.json"
    build_story_flowchart.main(["-md", str(mortal_dir), "-o", str(fc_out)])
    assert fc_out.is_file()

    # unpack_game with --skip-json
    fc_unpack = tmp_path / "unpack_fc.json"
    rm_unpack = tmp_path / "unpack_rm.json"
    summary = unpack_game.main(
        [
            "-md",
            str(mortal_dir),
            "-ff",
            str(fc_unpack),
            "-rf",
            str(rm_unpack),
            "--skip-json",
        ]
    )
    assert fc_unpack.is_file()
    assert rm_unpack.is_file()
    assert summary["json_files"] == []

    # Verify unpack_game invokes src.unity_assets.extract_lean_local_jsons when --skip-json is not set
    fake_extract = MagicMock(return_value=[tmp_path / "level0_00011_Character.json"])
    import sys
    from types import SimpleNamespace

    fake_unity_mod = SimpleNamespace(extract_lean_local_jsons=fake_extract)
    old_mod = sys.modules.get("src.unity_assets")
    sys.modules["src.unity_assets"] = fake_unity_mod  # type: ignore[assignment]
    try:
        summary_full = unpack_game.main(
            [
                "-md",
                str(mortal_dir),
                "-od",
                str(tmp_path / "json_out"),
                "-ff",
                str(tmp_path / "fc2.json"),
                "-rf",
                str(tmp_path / "rm2.json"),
            ]
        )
    finally:
        if old_mod is None:
            sys.modules.pop("src.unity_assets", None)
        else:
            sys.modules["src.unity_assets"] = old_mod

    fake_extract.assert_called_once_with(mortal_dir, str(tmp_path / "json_out"), language="ChineseSimplified")
    assert len(summary_full["json_files"]) == 1

    # Guard missing dir
    with pytest.raises(SystemExit):
        build_story_flowchart.main(["-md", str(tmp_path / "missing")])
