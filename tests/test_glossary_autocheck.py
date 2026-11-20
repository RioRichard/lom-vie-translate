from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.glossary import (
    autocheck_and_sync_glossary,
    build_glossary_term_prompt,
    extract_game_glossary_candidates,
)
from src.logger import logger
from src.main import build_parser, main_async
from src.relationship_matrix import RelationshipMatrix
from src.story_flowchart import CharacterInfo, StoryFlowchart
from src.translator import TranslationResult

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_CONFIG = REPO_ROOT / "config.toml.template"


@pytest.fixture(autouse=True)
def _reset_logger_file_handler():
    """Ensure tests calling main_async do not leak FileHandlers across tests."""
    yield
    if logger._file_handler is not None:
        logger.logger.removeHandler(logger._file_handler)
        logger._file_handler.close()
        logger._file_handler = None
        logger._log_file = None


def _make_entry_file(path: Path, entries: list[dict[str, str]], *, array_format: bool = True, language: str = "ChineseSimplified") -> None:
    payload = {
        "Language": language,
        "entries": {"Array": entries} if array_format else entries,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_extract_game_glossary_candidates_all_categories_and_paired_context(tmp_path: Path) -> None:
    input_dir = tmp_path / "LeanLocalJson"
    input_dir.mkdir()

    # English file must be ignored completely
    _make_entry_file(
        input_dir / "english.json",
        [{"Name": "Character/en_only", "Text": "Hero"}],
        language="English",
    )

    # Array format JSON with characters, martial_arts, locations, items_lore, and skip cases
    _make_entry_file(
        input_dir / "level0_part1.json",
        [
            {"Name": "Character/c_custom", "Text": "林青云"},
            {"Name": "CharacterTitle/c_custom", "Text": "青云剑客"},
            {"Name": "CharacterIntro0/c_custom", "Text": "隐居山林的剑客。"},
            {"Name": "CharacterIntro1/c_custom", "Text": "擅长快剑。"},
            {"Name": "CombatCharacter/Name/c_boss", "Text": "血煞魔君"},
            {"Name": "CombatCharacter/Title/c_boss", "Text": "魔教教主"},
            {"Name": "PlayerInfo/Lover/l1", "Text": "心上人"},
            {"Name": "PlayerInfo/Title/t1", "Text": "外姓弟子"},
            {"Name": "EnemyTeam/e1", "Text": "黑衣杀手"},
            # Skipped anonymous / placeholder / non-letter / non-candidate entries
            {"Name": "Character/anon_q1", "Text": "？？？"},
            {"Name": "Character/anon_q2", "Text": "???"},
            {"Name": "Character/anon_mask", "Text": "蒙面人"},
            {"Name": "Character/anon_girl", "Text": "少女"},
            {"Name": "CharacterTitle/ph1", "Text": "{title}"},
            {"Name": "CharacterTitle/ph2", "Text": "{{title}}"},
            {"Name": "Character/empty_char", "Text": "   "},
            {"Name": "Character/num_only", "Text": "12345"},
            {"Name": "Character/punct_only", "Text": "……。"},
            {"Name": "Story/D_001", "Text": "你好。"},
            # Martial arts
            {"Name": "Book/Name/b1", "Text": "玄铁剑谱"},
            {"Name": "Book/Desc/b1", "Text": "记载玄铁剑法的古籍。"},
            {"Name": "CombatSkill/Name/cs1", "Text": "唐门暗器"},
            {"Name": "CombatSkill/Desc/cs1", "Text": "以暗器制敌。"},
            {"Name": "BattleSkill/Name/bs1", "Text": "暴雨梨花针"},
            {"Name": "BattleSkill/Desc/bs1", "Text": "漫天飞针。"},
            {"Name": "BattleSkill/Brother1/bs_b1", "Text": "大师兄绝技"},
            {"Name": "BattleSkill/Desc/brother1", "Text": "大师兄的成名绝学。"},
            {"Name": "PlayerTalent/Name/pt1", "Text": "百毒不侵"},
            {"Name": "PlayerTalent/Desc/pt1", "Text": "免疫多数毒物。"},
        ],
        array_format=True,
    )

    # Direct list format JSON with locations & items_lore
    _make_entry_file(
        input_dir / "level0_part2.json",
        [
            {"Name": "Position/Name/p1", "Text": "唐门"},
            {"Name": "Position/title/p1", "Text": "蜀中名门"},
            {"Name": "Position/desc/p1", "Text": "位于蜀中的古老门派。"},
            {"Name": "MapPosition/Name/mp1", "Text": "后山"},
            {"Name": "MapPosition/Desc/mp1", "Text": "唐门弟子练功之处。"},
            {"Name": "Facility/Name/fac1", "Text": "炼丹房"},
            {"Name": "Facility/Title/fac1", "Text": "制药之所"},
            {"Name": "Facility/Effect/fac1", "Text": "提升炼丹成功率。"},
            {"Name": "Facility/Effect/fac1_lv2", "Text": "额外产出丹药。"},
            {"Name": "Facility/Effect/fac1_placeholder", "Text": "【效果】"},
            {"Name": "Equip/Name/eq1", "Text": "青锋剑"},
            {"Name": "Equip/Desc/eq1", "Text": "锋利无比的佩剑。"},
            {"Name": "Misc/Name/m1", "Text": "金疮药"},
            {"Name": "Misc/Desc/m1", "Text": "疗伤圣药。"},
            {"Name": "_Misc/Name/m2", "Text": "银两"},
            {"Name": "_Misc/Desc/m2", "Text": "通行货币。"},
            {"Name": "Special/Name/sp1", "Text": "玄铁令"},
            {"Name": "Special/Desc/sp1", "Text": "神秘令牌。"},
            {"Name": "Library/Title/lib1", "Text": "江湖轶事"},
            {"Name": "Library/Desc/lib1", "Text": "记录武林秘闻。"},
            {"Name": "Flag/Name/fl1", "Text": "正道声望"},
        ],
        array_format=False,
    )

    flowchart = StoryFlowchart(
        characters={
            "c_custom": CharacterInfo(
                char_id="c_custom",
                zh_name="林青云",
                zh_title="青云剑客",
                gender="male",
                aliases=["青云子"],
            ),
            "fc_only": CharacterInfo(
                char_id="fc_only",
                zh_name="苏清雪",
                zh_title="寒梅仙子",
                gender="female",
                traits="冷若冰霜",
            ),
            "narrative": CharacterInfo(char_id="narrative", zh_name="旁白"),
        }
    )

    candidates = extract_game_glossary_candidates(input_dir, flowchart=flowchart)
    by_name = {c["Name"]: c for c in candidates}

    # English, Story, anonymous, placeholder, empty, pure numbers/punctuation, narrative excluded
    for excluded in (
        "Character/en_only",
        "Character/anon_q1",
        "Character/anon_q2",
        "Character/anon_mask",
        "Character/anon_girl",
        "CharacterTitle/ph1",
        "CharacterTitle/ph2",
        "Character/empty_char",
        "Character/num_only",
        "Character/punct_only",
        "Story/D_001",
        "Character/narrative",
    ):
        assert excluded not in by_name

    # All 4 categories represented
    categories = {c["Category"] for c in candidates}
    assert categories == {"characters", "martial_arts", "locations", "items_lore"}

    # Paired context checks: characters + flowchart enrichment
    assert by_name["Character/c_custom"]["Category"] == "characters"
    assert "Danh hiệu: 青云剑客" in by_name["Character/c_custom"]["Context"]
    assert "Tiểu sử: 隐居山林的剑客。 | 擅长快剑。" in by_name["Character/c_custom"]["Context"]
    assert "Giới tính: male" in by_name["Character/c_custom"]["Context"]
    assert "Biệt danh: 青云子" in by_name["Character/c_custom"]["Context"]

    assert "Nhân vật: 林青云" in by_name["CharacterTitle/c_custom"]["Context"]
    assert by_name["Character/fc_only"]["Original"] == "苏清雪"
    assert "Đặc điểm: 冷若冰霜" in by_name["Character/fc_only"]["Context"]
    assert by_name["CharacterTitle/fc_only"]["Original"] == "寒梅仙子"

    # Paired context checks: martial_arts
    assert by_name["Book/Name/b1"]["Category"] == "martial_arts"
    assert "Mô tả: 记载玄铁剑法的古籍。" in by_name["Book/Name/b1"]["Context"]
    assert "Mô tả: 以暗器制敌。" in by_name["CombatSkill/Name/cs1"]["Context"]
    assert "Mô tả: 漫天飞针。" in by_name["BattleSkill/Name/bs1"]["Context"]
    assert "Mô tả: 大师兄的成名绝学。" in by_name["BattleSkill/Brother1/bs_b1"]["Context"]
    assert "Mô tả: 免疫多数毒物。" in by_name["PlayerTalent/Name/pt1"]["Context"]

    # Paired context checks: locations
    assert by_name["Position/Name/p1"]["Category"] == "locations"
    assert "Hoạt động/Tiêu đề: 蜀中名门" in by_name["Position/Name/p1"]["Context"]
    assert "Mô tả: 位于蜀中的古老门派。" in by_name["Position/Name/p1"]["Context"]
    assert "Địa điểm: 唐门" in by_name["Position/title/p1"]["Context"]
    assert "Mô tả: 唐门弟子练功之处。" in by_name["MapPosition/Name/mp1"]["Context"]
    assert "Hiệu quả: 提升炼丹成功率。 | 额外产出丹药。" in by_name["Facility/Name/fac1"]["Context"]
    assert "【效果】" not in by_name["Facility/Name/fac1"]["Context"]
    assert "Hiệu quả: 提升炼丹成功率。" in by_name["Facility/Title/fac1"]["Context"]

    # Paired context checks: items_lore
    assert by_name["Equip/Name/eq1"]["Category"] == "items_lore"
    assert "Mô tả: 锋利无比的佩剑。" in by_name["Equip/Name/eq1"]["Context"]
    assert "Mô tả: 疗伤圣药。" in by_name["Misc/Name/m1"]["Context"]
    assert "Mô tả: 通行货币。" in by_name["_Misc/Name/m2"]["Context"]
    assert "Mô tả: 神秘令牌。" in by_name["Special/Name/sp1"]["Context"]
    assert "Mô tả: 记录武林秘闻。" in by_name["Library/Title/lib1"]["Context"]
    assert by_name["Flag/Name/fl1"]["Original"] == "正道声望"


async def test_autocheck_in_sync_preservation_zero_llm_calls(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    _make_entry_file(
        input_dir / "data.json",
        [
            {"Name": "Character/c1", "Text": "林青云"},
            {"Name": "Book/Name/b1", "Text": "玄铁剑谱"},
            {"Name": "Position/Name/p1", "Text": "青城山"},
            {"Name": "Equip/Name/e1", "Text": "青锋剑"},
        ],
    )

    glossary_json = tmp_path / "glossary" / "custom.json"
    glossary_json.parent.mkdir(parents=True)
    initial_entries = [
        {"Name": "Character/c1", "Original": "林青云", "Translated": "Lâm Thanh Vân"},
        {"Name": "Book/Name/b1", "Original": "玄铁剑谱", "Translated": "Huyền Thiết Kiếm Phổ"},
        {"Name": "Position/Name/p1", "Original": "青城山", "Translated": "Thanh Thành Sơn"},
        {"Name": "Equip/Name/e1", "Original": "青锋剑", "Translated": "Thanh Phong Kiếm"},
        # Manual/custom term not present in input_dir must be preserved
        {"Name": "Custom/ManualTerm", "Original": "江湖", "Translated": "Giang hồ"},
    ]
    glossary_json.write_text(json.dumps(initial_entries, ensure_ascii=False, indent=2), encoding="utf-8")

    engine = MagicMock()
    engine.translate_text = AsyncMock()

    name_map, orig_map, stats = await autocheck_and_sync_glossary(
        input_dir=input_dir,
        glossary_file_path=glossary_json,
        engine=engine,
    )

    engine.translate_text.assert_not_awaited()
    assert stats["total_candidates"] == 4
    assert stats["in_sync"] == 4
    assert stats["reused"] == 0
    assert stats["outdated_updated"] == 0
    assert stats["new_translated"] == 0
    assert stats["failed"] == 0

    assert name_map["Custom/ManualTerm"] == "Giang hồ"
    assert orig_map["江湖"] == "Giang hồ"
    assert orig_map["林青云"] == "Lâm Thanh Vân"

    txt_path = glossary_json.with_suffix(".txt")
    assert txt_path.is_file()
    txt_content = txt_path.read_text(encoding="utf-8")
    assert "江湖=Giang hồ" in txt_content
    assert "林青云=Lâm Thanh Vân" in txt_content


async def test_autocheck_outdated_term_detection_invalidates_and_retranslates(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    _make_entry_file(
        input_dir / "data.json",
        [
            {"Name": "Character/c1", "Text": "王二"},
            {"Name": "Book/Name/b1", "Text": "新玄铁剑谱"},
            {"Name": "Book/Desc/b1", "Text": "新版玄铁剑法秘籍。"},
        ],
    )

    glossary_json = tmp_path / "glossary.json"
    glossary_json.write_text(
        json.dumps(
            [
                {"Name": "Character/c1", "Original": "王二", "Translated": "Vương Nhị"},
                {"Name": "Book/Name/b1", "Original": "旧剑谱", "Translated": "Kiếm Phổ Cũ"},
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    captured_calls: list[dict] = []

    async def fake_translate(**kwargs):
        captured_calls.append(kwargs)
        return TranslationResult(text="Tân Huyền Thiết Kiếm Phổ", succeeded=True)

    engine = MagicMock()
    engine.translate_text = AsyncMock(side_effect=fake_translate)

    name_map, orig_map, stats = await autocheck_and_sync_glossary(
        input_dir=input_dir,
        glossary_file_path=glossary_json,
        engine=engine,
        task_name="improve_glossary",
    )

    assert engine.translate_text.await_count == 1
    assert captured_calls[0]["text"] == "新玄铁剑谱"
    assert captured_calls[0]["name"] == "Book/Name/b1"
    assert "Mô tả: 新版玄铁剑法秘籍。" in captured_calls[0]["prompt_data"]["prompt"]

    assert stats["in_sync"] == 1
    assert stats["outdated_updated"] == 1
    assert stats["new_translated"] == 0
    assert stats["failed"] == 0

    assert name_map["Book/Name/b1"] == "Tân Huyền Thiết Kiếm Phổ"
    assert orig_map["新玄铁剑谱"] == "Tân Huyền Thiết Kiếm Phổ"
    assert "旧剑谱" not in orig_map

    saved = json.loads(glossary_json.read_text(encoding="utf-8"))
    saved_by_name = {item["Name"]: item for item in saved}
    assert saved_by_name["Book/Name/b1"] == {
        "Name": "Book/Name/b1",
        "Original": "新玄铁剑谱",
        "Translated": "Tân Huyền Thiết Kiếm Phổ",
    }
    txt_content = glossary_json.with_suffix(".txt").read_text(encoding="utf-8")
    assert "旧剑谱=" not in txt_content
    assert "新玄铁剑谱=Tân Huyền Thiết Kiếm Phổ" in txt_content


async def test_autocheck_missing_terms_waves_submatches_and_failure_safety(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    _make_entry_file(
        input_dir / "data.json",
        [
            {"Name": "Character/player", "Text": "赵活"},  # Curated -> deterministic reuse
            {"Name": "Character/hero1", "Text": "龙傲天"},
            {"Name": "CharacterTitle/hero1", "Text": "傲天剑圣"},
            {"Name": "CharacterIntro0/hero1", "Text": "天生剑骨的奇才。"},
            {"Name": "Book/Name/book1", "Text": "龙傲天剑诀"},
            {"Name": "Book/Desc/book1", "Text": "龙傲天自创绝学。"},
            {"Name": "Book/Name/book_dup", "Text": "龙傲天剑诀"},  # Deduplicated to 1 LLM call
            {"Name": "Equip/Name/cursed", "Text": "魔剑"},  # Will fail with succeeded=False
            {"Name": "Equip/Name/broken", "Text": "断刀"},  # Will return empty string
        ],
    )

    glossary_json = tmp_path / "glossary" / "glossary.json"
    call_log: list[tuple[str, str]] = []

    async def fake_translate(**kwargs):
        text = kwargs["text"]
        prompt = kwargs["prompt_data"]["prompt"]
        call_log.append((text, prompt))
        if text == "龙傲天":
            return TranslationResult(text="Long Ngạo Thiên", succeeded=True)
        if text == "傲天剑圣":
            return TranslationResult(text="Ngạo Thiên Kiếm Thánh", succeeded=True)
        if text == "龙傲天剑诀":
            return TranslationResult(text="Long Ngạo Thiên Kiếm Quyết", succeeded=True)
        if text == "魔剑":
            return TranslationResult(text="魔剑", succeeded=False, error="API rate limit")
        if text == "断刀":
            return TranslationResult(text="   ", succeeded=True)
        return TranslationResult(text=text, succeeded=False, error="unexpected")

    engine = MagicMock()
    engine.translate_text = AsyncMock(side_effect=fake_translate)

    name_map, orig_map, stats = await autocheck_and_sync_glossary(
        input_dir=input_dir,
        glossary_file_path=glossary_json,
        engine=engine,
        max_concurrent=1,
    )

    # Curated赵活 reused without LLM call
    assert name_map["Character/player"] == "Triệu Hoạt"
    assert stats["reused"] == 1
    assert stats["new_translated"] == 4  # hero1 + title + book1 + book_dup
    assert stats["failed"] == 2  # cursed + broken

    called_texts = [t for t, _ in call_log]
    assert "赵活" not in called_texts
    # Characters wave translated BEFORE martial_arts wave
    assert called_texts.index("龙傲天") < called_texts.index("龙傲天剑诀")
    # Duplicate 龙傲天剑诀 only triggered 1 LLM call
    assert called_texts.count("龙傲天剑诀") == 1

    book_prompt = next(p for t, p in call_log if t == "龙傲天剑诀")
    assert "Ngữ cảnh đi kèm:\nMô tả: 龙傲天自创绝学。" in book_prompt
    assert "Thuật ngữ thành phần đã chuẩn hóa" in book_prompt
    assert "- 龙傲天=Long Ngạo Thiên" in book_prompt

    assert name_map["Book/Name/book1"] == "Long Ngạo Thiên Kiếm Quyết"
    assert name_map["Book/Name/book_dup"] == "Long Ngạo Thiên Kiếm Quyết"

    # Failed / empty results must NEVER poison glossary maps or disk files
    assert "Equip/Name/cursed" not in name_map
    assert "魔剑" not in orig_map
    assert "Equip/Name/broken" not in name_map
    assert "断刀" not in orig_map

    saved = json.loads(glossary_json.read_text(encoding="utf-8"))
    saved_names = {entry["Name"] for entry in saved}
    assert "Equip/Name/cursed" not in saved_names
    assert "Equip/Name/broken" not in saved_names
    txt_content = glossary_json.with_suffix(".txt").read_text(encoding="utf-8")
    assert "魔剑=" not in txt_content
    assert "断刀=" not in txt_content


def test_build_glossary_term_prompt_formats_optional_sections() -> None:
    prompt = build_glossary_term_prompt(
        original_text="玄铁重剑",
        category="items_lore",
        context="Mô tả: 重剑无锋，大巧不工。",
        glossary_matches=[("玄铁", "Huyền Thiết")],
    )
    assert "items_lore" in prompt
    assert "Ngữ cảnh đi kèm:\nMô tả: 重剑无锋，大巧不工。" in prompt
    assert "- 玄铁=Huyền Thiết" in prompt
    assert "Thuật ngữ cần dịch:\n玄铁重剑" in prompt


async def test_autocheck_syncs_flowchart_and_relationship_matrix_with_anonymous_safeguard(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    _make_entry_file(
        input_dir / "chars.json",
        [
            {"Name": "Character/c_npc", "Text": "无名剑客"},
            {"Name": "Character/anon1", "Text": "？？？"},
            {"Name": "Character/anon2", "Text": "蒙面人"},
        ],
    )

    # Seed dict-style glossary with bogus anonymous mapping to verify safeguard
    glossary_json = tmp_path / "glossary.json"
    glossary_json.write_text(
        json.dumps(
            {
                "？？？": "Kẻ Bí Ẩn Giả Mạo",
                "蒙面人": "Người Đeo Mặt Nạ",
                "唐布衣": "Đường Bố Y",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    flowchart = StoryFlowchart(
        characters={
            "c_npc": CharacterInfo(char_id="c_npc", zh_name="无名剑客", vi_name=""),
            "c_by_orig": CharacterInfo(char_id="c_by_orig", zh_name="唐布衣", vi_name="Đường Cũ"),
            "c_extra": CharacterInfo(char_id="c_extra", zh_name="无名剑客", vi_name=""),
            "anon1": CharacterInfo(char_id="anon1", zh_name="？？？", vi_name=""),
            "anon2": CharacterInfo(char_id="anon2", zh_name="蒙面人", vi_name=""),
        }
    )
    fc_path = tmp_path / "story_flowchart.json"
    flowchart.to_json_file(fc_path)

    matrix = RelationshipMatrix(
        characters={
            "c_npc": {"char_id": "c_npc", "zh_name": "无名剑客", "vi_name": ""},
            "anon1": {"char_id": "anon1", "zh_name": "？？？", "vi_name": ""},
        }
    )
    rm_path = tmp_path / "relationship_matrix.json"
    matrix.to_json_file(rm_path)

    engine = MagicMock()
    engine.translate_text = AsyncMock(
        return_value=TranslationResult(text="Vô Danh Kiếm Khách", succeeded=True)
    )

    _, _, stats = await autocheck_and_sync_glossary(
        input_dir=input_dir,
        glossary_file_path=glossary_json,
        engine=engine,
        flowchart=flowchart,
        flowchart_file=fc_path,
        relationship_matrix=matrix,
        relationship_file=rm_path,
    )

    # Only c_npc (无名剑客) is translated; anonymous characters were skipped by extraction
    engine.translate_text.assert_awaited_once()
    assert stats["flowchart_updated"] == 3  # c_npc, c_by_orig, c_extra
    assert stats["matrix_updated"] >= 3  # updated c_npc + added c_by_orig, c_extra, anon2

    reloaded_fc = StoryFlowchart.from_json_file(fc_path)
    assert reloaded_fc.characters["c_npc"].vi_name == "Vô Danh Kiếm Khách"
    assert reloaded_fc.characters["c_by_orig"].vi_name == "Đường Bố Y"
    assert reloaded_fc.characters["c_extra"].vi_name == "Vô Danh Kiếm Khách"
    # Anonymous characters must NEVER be populated from original_to_translated
    assert reloaded_fc.characters["anon1"].vi_name == ""
    assert reloaded_fc.characters["anon2"].vi_name == ""

    reloaded_rm = RelationshipMatrix.from_json_file(rm_path)
    assert reloaded_rm.characters["c_npc"]["vi_name"] == "Vô Danh Kiếm Khách"
    assert reloaded_rm.characters["c_by_orig"]["vi_name"] == "Đường Bố Y"
    assert reloaded_rm.characters["c_extra"]["vi_name"] == "Vô Danh Kiếm Khách"
    assert reloaded_rm.characters["anon1"]["vi_name"] == ""
    assert reloaded_rm.characters["anon2"]["vi_name"] == ""
    # UTF-8 persisted cleanly without \\u escapes
    assert "\\u" not in fc_path.read_text(encoding="utf-8")
    assert "\\u" not in rm_path.read_text(encoding="utf-8")


async def test_main_async_glossary_mode_auto_preflight_and_no_auto_glossary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LOCAL_OPENAI_API_KEYS", raising=False)
    monkeypatch.setattr("src.config.load_dotenv", lambda *a, **kw: False)

    parser = build_parser()
    parsed = parser.parse_args(["-m", "glossary", "--no-auto-glossary"])
    assert parsed.mode == "glossary"
    assert parsed.no_auto_glossary is True

    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    _make_entry_file(
        input_dir / "items.json",
        [
            {"Name": "Character/c1", "Text": "林风"},
            {"Name": "Equip/Name/sword_1", "Text": "青钢剑"},
            {"Name": "Equip/Desc/sword_1", "Text": "锋利的青钢宝剑。"},
            {"Name": "Story/S1_D1", "Text": "请使用青钢剑！"},
        ],
    )

    flowchart = StoryFlowchart(
        characters={"c1": CharacterInfo(char_id="c1", zh_name="林风", vi_name="")}
    )
    fc_path = tmp_path / "story_flowchart.json"
    flowchart.to_json_file(fc_path)

    matrix = RelationshipMatrix(
        characters={"c1": {"char_id": "c1", "zh_name": "林风", "vi_name": ""}}
    )
    rm_path = tmp_path / "relationship_matrix.json"
    matrix.to_json_file(rm_path)

    captured_prompts: list[str] = []

    async def fake_acompletion(**kwargs):
        prompt = kwargs["messages"][0]["content"]
        captured_prompts.append(prompt)
        if "林风" in prompt and "Thuật ngữ cần dịch:" in prompt:
            out = "Lâm Phong"
        elif "青钢剑" in prompt and "Thuật ngữ cần dịch:" in prompt:
            out = "Thanh Cương Kiếm"
        elif "青钢剑" in prompt:
            out = "Hãy dùng Thanh Cương Kiếm!"
        else:
            out = "Dịch thử"
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=out))]
        )

    mock_completion = AsyncMock(side_effect=fake_acompletion)
    monkeypatch.setattr("src.translator.litellm.acompletion", mock_completion)

    # (a) -m glossary mode: creates non-existent glossary_file, syncs flowchart/matrix, skips output_dir & queue
    glossary_path_a = tmp_path / "glossary_a" / "glossary.json"
    out_dir_a = tmp_path / "out_a_should_not_exist"
    await main_async(
        [
            "-c",
            str(TEMPLATE_CONFIG),
            "-m",
            "glossary",
            "-id",
            str(input_dir),
            "-od",
            str(out_dir_a),
            "-gf",
            str(glossary_path_a),
            "-ff",
            str(fc_path),
            "-rf",
            str(rm_path),
        ]
    )

    assert not out_dir_a.exists()
    assert glossary_path_a.is_file()
    assert glossary_path_a.with_suffix(".txt").is_file()
    saved_a = json.loads(glossary_path_a.read_text(encoding="utf-8"))
    assert {e["Name"]: e["Translated"] for e in saved_a} == {
        "Character/c1": "Lâm Phong",
        "Equip/Name/sword_1": "Thanh Cương Kiếm",
    }
    # Story/S1_D1 must NOT have been translated in glossary mode
    assert mock_completion.await_count == 2
    assert StoryFlowchart.from_json_file(fc_path).characters["c1"].vi_name == "Lâm Phong"
    assert RelationshipMatrix.from_json_file(rm_path).characters["c1"]["vi_name"] == "Lâm Phong"

    # (b) -m translate with auto pre-flight sync (default auto_sync_glossary = true) and non-existent glossary
    captured_prompts.clear()
    mock_completion.reset_mock()
    glossary_path_b = tmp_path / "glossary_b" / "glossary.json"
    out_dir_b = tmp_path / "out_b"

    await main_async(
        [
            "-c",
            str(TEMPLATE_CONFIG),
            "-m",
            "translate",
            "-id",
            str(input_dir),
            "-od",
            str(out_dir_b),
            "-gf",
            str(glossary_path_b),
        ]
    )

    assert glossary_path_b.is_file()
    # 2 glossary LLM calls (林风, 青钢剑) + 2 file entries (Equip/Desc/sword_1, Story/S1_D1);
    # Character/c1 and Equip/Name/sword_1 hit the freshly synced glossary!
    assert mock_completion.await_count == 4
    story_prompt = next(p for p in captured_prompts if "Văn bản cần được dịch:\n请使用青钢剑！" in p)
    assert "- 青钢剑=Thanh Cương Kiếm" in story_prompt

    translated_b = json.loads((out_dir_b / "json" / "items.json").read_text(encoding="utf-8"))
    b_by_name = {e["Name"]: e["Text"] for e in translated_b["entries"]["Array"]}
    assert b_by_name["Character/c1"] == "Lâm Phong"
    assert b_by_name["Equip/Name/sword_1"] == "Thanh Cương Kiếm"
    assert b_by_name["Story/S1_D1"] == "Hãy dùng Thanh Cương Kiếm!"
    assert (out_dir_b / "details" / "translation_details.json").is_file()
    assert (out_dir_b / "pairs" / "translation_pairs.txt").is_file()

    # (c) -m translate --no-auto-glossary: skips pre-flight sync and leaves existing glossary untouched
    captured_prompts.clear()
    mock_completion.reset_mock()
    glossary_path_c = tmp_path / "glossary_c.json"
    initial_c = [{"Name": "Other/1", "Original": "其他", "Translated": "Khác"}]
    glossary_path_c.write_text(json.dumps(initial_c, ensure_ascii=False), encoding="utf-8")
    out_dir_c = tmp_path / "out_c"

    await main_async(
        [
            "-c",
            str(TEMPLATE_CONFIG),
            "-m",
            "translate",
            "--no-auto-glossary",
            "-id",
            str(input_dir),
            "-od",
            str(out_dir_c),
            "-gf",
            str(glossary_path_c),
        ]
    )

    # Glossary file unchanged
    assert json.loads(glossary_path_c.read_text(encoding="utf-8")) == initial_c
    # All 4 entries in items.json translated directly without pre-flight glossary sync
    assert mock_completion.await_count == 4
    assert all("Thuật ngữ cần dịch:" not in p for p in captured_prompts)


async def test_main_async_glossary_fallback_to_translate_task_and_improve_autosync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LOCAL_OPENAI_API_KEYS", raising=False)
    monkeypatch.setattr("src.config.load_dotenv", lambda *a, **kw: False)

    # Custom config with ONLY [tasks.translate] and [tasks.improve] (no [tasks.improve_glossary])
    custom_cfg = tmp_path / "no_glossary_task.toml"
    custom_cfg.write_text(
        """
[run]
mode = "translate"
auto_sync_glossary = true

[providers.local_openai]
api_base = "http://localhost:1234/v1"
timeout = 30.0
default_api_key = "local-no-key"

[providers.local_openai.tiers.local]
max_concurrent = 2
rate_limit_delay = 0.0

[providers.local_openai.models.qwen3-14b]
model_id = "openai/qwen3-14b"

[tasks.translate]
primary = { provider = "local_openai", tier = "local", model = "qwen3-14b" }

[tasks.improve]
primary = { provider = "local_openai", tier = "local", model = "qwen3-14b" }
""".strip(),
        encoding="utf-8",
    )

    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    _make_entry_file(
        input_dir / "skills.json",
        [
            {"Name": "CombatSkill/Name/sk1", "Text": "暗器手法"},
            {"Name": "Story/L1", "Text": "接招吧！"},
        ],
    )

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    _make_entry_file(
        raw_dir / "skills.json",
        [
            {"Name": "CombatSkill/Name/sk1", "Text": "Thủ pháp vũ khí ẩn"},
            {"Name": "Story/L1", "Text": "Đón chiêu đi!"},
        ],
        language="Vietnamese",
    )

    async def fake_acompletion(**kwargs):
        prompt = kwargs["messages"][0]["content"]
        if "Thuật ngữ cần dịch:" in prompt:
            out = "Ám Khí Thủ Pháp"
        else:
            out = "Hãy tiếp chiêu!"
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=out))])

    mock_completion = AsyncMock(side_effect=fake_acompletion)
    monkeypatch.setattr("src.translator.litellm.acompletion", mock_completion)

    # 1. -m glossary falls back to 'translate' task when 'improve_glossary' is not configured
    glossary_path = tmp_path / "glossary.json"
    out_unused = tmp_path / "unused_out"
    await main_async(
        [
            "-c",
            str(custom_cfg),
            "-m",
            "glossary",
            "-id",
            str(input_dir),
            "-od",
            str(out_unused),
            "-gf",
            str(glossary_path),
        ]
    )
    assert not out_unused.exists()
    assert json.loads(glossary_path.read_text(encoding="utf-8")) == [
        {
            "Name": "CombatSkill/Name/sk1",
            "Original": "暗器手法",
            "Translated": "Ám Khí Thủ Pháp",
        }
    ]
    assert mock_completion.await_count == 1

    # 2. -m improve with auto_sync_glossary=true runs pre-flight sync and reuses synced glossary
    mock_completion.reset_mock()
    out_improve = tmp_path / "out_improve"
    glossary_path_2 = tmp_path / "glossary_improve.json"
    await main_async(
        [
            "-c",
            str(custom_cfg),
            "-m",
            "improve",
            "-id",
            str(input_dir),
            "-rd",
            str(raw_dir),
            "-od",
            str(out_improve),
            "-gf",
            str(glossary_path_2),
        ]
    )
    assert glossary_path_2.is_file()
    improved_json = json.loads((out_improve / "json" / "skills.json").read_text(encoding="utf-8"))
    by_name = {e["Name"]: e["Text"] for e in improved_json["entries"]["Array"]}
    assert by_name["CombatSkill/Name/sk1"] == "Ám Khí Thủ Pháp"
    assert by_name["Story/L1"] == "Hãy tiếp chiêu!"
    assert mock_completion.await_count == 2
