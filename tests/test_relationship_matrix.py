from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.config import load_config
from src.relationship_matrix import (
    PairRelationship,
    PronounRule,
    RelationshipMatrix,
    build_matrix_from_flowchart,
)
from src.story_flowchart import (
    CharacterInfo,
    DialogueLineNode,
    RelationshipDelta,
    ScriptNode,
    StoryFlowchart,
)
from src.translator import TranslationEngine
from tool import build_relationship_matrix

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_CONFIG = REPO_ROOT / "config.toml.template"


def _sample_flowchart() -> StoryFlowchart:
    characters = {
        "player": CharacterInfo(
            char_id="player",
            zh_name="赵活",
            vi_name="Triệu Hoạt",
            gender="male",
        ),
        "girl6": CharacterInfo(
            char_id="girl6",
            zh_name="夏侯兰",
            zh_title="夺魄幽兰",
            vi_name="Hạ Hầu Lan",
            gender="female",
        ),
        "brother2": CharacterInfo(
            char_id="brother2",
            zh_name="唐铮",
            vi_name="Đường Tranh",
            gender="male",
        ),
        "npc_elder": CharacterInfo(
            char_id="npc_elder",
            zh_name="掌门长老",
            zh_title="长老",
            gender="male",
        ),
    }

    s1 = ScriptNode(
        script_id="ch_kongdong_01",
        participants=["player", "girl6"],
        relationship_deltas=[
            RelationshipDelta(char_id="girl6", stat_type=1, delta=5, at_line_index=1)
        ],
        lines=[
            DialogueLineNode(
                key="D_K_001",
                line_type="dialogue",
                speaker_id="player",
                listeners_on_stage=["girl6"],
            ),
            DialogueLineNode(
                key="D_K_002",
                line_type="dialogue",
                speaker_id="girl6",
                listeners_on_stage=["player"],
            ),
            DialogueLineNode(
                key="D_K_003",
                line_type="dialogue",
                speaker_id="player",
                listeners_on_stage=["girl6"],
            ),
        ],
    )
    s2 = ScriptNode(
        script_id="ch_tang_01",
        participants=["player", "brother2", "npc_elder"],
        lines=[
            DialogueLineNode(
                key="D_T_001",
                line_type="dialogue",
                speaker_id="player",
                listeners_on_stage=["brother2"],
            ),
            DialogueLineNode(
                key="D_T_002",
                line_type="dialogue",
                speaker_id="player",
                listeners_on_stage=["npc_elder"],
            ),
        ],
    )
    return StoryFlowchart(
        characters=characters,
        scripts={"ch_kongdong_01": s1, "ch_tang_01": s2},
    )


def test_build_matrix_from_flowchart_ranks_pairs_and_curated_rules() -> None:
    flowchart = _sample_flowchart()
    matrix = build_matrix_from_flowchart(
        flowchart,
        glossary_name_map={"Character/npc_elder": "Trưởng lão"},
    )

    assert matrix.characters["npc_elder"]["vi_name"] == "Trưởng lão"
    assert "lover" in matrix.archetypes
    assert "betrayed" in matrix.archetypes

    # Ranking: player->girl6 (2 interactions) precedes player->brother2 (1) and player->npc_elder (1)
    pair_keys = list(matrix.pairs.keys())
    assert pair_keys.index("player->girl6") < pair_keys.index("player->brother2")

    p_g6 = matrix.pairs["player->girl6"]
    assert p_g6.interaction_count == 2
    assert p_g6.scripts_with_deltas == ["ch_kongdong_01"]
    assert p_g6.default.self_pronoun == "đệ tử / vãn bối"
    assert p_g6.default.target_pronoun == "sư phụ / tiền bối"
    assert set(p_g6.stages.keys()) >= {"default", "disciple", "lover", "betrayed", "enemy"}

    # Non-curated NPC pair gets sensible wuxia defaults
    p_npc = matrix.pairs["player->npc_elder"]
    assert p_npc.interaction_count == 1
    assert p_npc.default.self_pronoun
    assert p_npc.default.target_pronoun


def test_resolve_pair_across_stages_and_script_stage_map() -> None:
    flowchart = _sample_flowchart()
    matrix = build_matrix_from_flowchart(flowchart)

    # Configure explicit script_stage_map overrides for testing precedence
    p_g6: PairRelationship = matrix.pairs["player->girl6"]
    p_g6.script_stage_map["ch_ending_love"] = "lover"
    p_g6.script_stage_map["ch_ending_love#O_Betray"] = "betrayed"

    # 1. Default stage
    rule_default = matrix.resolve_pair("player", "girl6")
    assert rule_default is not None
    assert rule_default.stage_id == "default"
    assert "đệ tử" in rule_default.self_pronoun

    # 2. script_id match
    rule_lover = matrix.resolve_pair("player", "girl6", script_id="ch_ending_love")
    assert rule_lover is not None
    assert rule_lover.stage_id == "lover"

    # 3. Exact script_id#branch_path precedence over script_id
    rule_betrayed = matrix.resolve_pair(
        "player",
        "girl6",
        script_id="ch_ending_love",
        branch_path="O_Betray",
    )
    assert rule_betrayed is not None
    assert rule_betrayed.stage_id == "betrayed"

    # 4. Branch-path keyword match when script is not in script_stage_map
    rule_enemy_branch = matrix.resolve_pair(
        "player",
        "girl6",
        script_id="ch_random_fight",
        branch_path="route_enemy/Ch_Fight#1",
    )
    assert rule_enemy_branch is not None
    assert rule_enemy_branch.stage_id == "enemy"

    # 5. Variant character ID fallback (girl6_2 -> girl6)
    rule_variant = matrix.resolve_pair("player", "girl6_2")
    assert rule_variant is not None
    assert rule_variant.self_pronoun == rule_default.self_pronoun

    # 6. Unknown pair returns None
    assert matrix.resolve_pair("unknown_a", "unknown_b") is None


def test_relationship_matrix_json_roundtrip_and_cli_with_llm_enrich(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flowchart = _sample_flowchart()
    fc_path = tmp_path / "story_flowchart.json"
    flowchart.to_json_file(fc_path)

    rm_path = tmp_path / "relationship_matrix.json"
    matrix = build_relationship_matrix.main(["-ff", str(fc_path), "-o", str(rm_path)])
    assert rm_path.is_file()
    raw_json = rm_path.read_text(encoding="utf-8")
    assert "\\u" not in raw_json

    reloaded = RelationshipMatrix.from_json_file(rm_path)
    assert reloaded.resolve_pair("player", "girl6") == matrix.resolve_pair("player", "girl6")

    # Test --enrich-with-llm using mocked litellm.acompletion
    json_dir = tmp_path / "LeanLocalJson"
    json_dir.mkdir()
    (json_dir / "level0_story.json").write_text(
        json.dumps(
            {
                "Language": "ChineseSimplified",
                "entries": {"Array": [{"Name": "Story/D_T_002", "Text": "弟子见过长老！"}]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("LOCAL_OPENAI_API_KEYS", raising=False)
    mock_completion = AsyncMock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "self_pronoun": "vãn bối",
                                "target_pronoun": "trưởng lão",
                                "third_person": "ngài",
                                "tone": "kính cẩn trang trọng",
                                "notes": "LLM enriched",
                            },
                            ensure_ascii=False,
                        )
                    )
                )
            ]
        )
    )
    monkeypatch.setattr("src.translator.litellm.acompletion", mock_completion)
    # Ensure load_config picks template config
    cfg = load_config(TEMPLATE_CONFIG, load_env=False)
    assert isinstance(TranslationEngine(cfg), TranslationEngine)

    rm_enriched_path = tmp_path / "rm_enriched.json"
    enriched_matrix = build_relationship_matrix.main(
        [
            "-ff",
            str(fc_path),
            "-o",
            str(rm_enriched_path),
            "--enrich-with-llm",
            "-c",
            str(TEMPLATE_CONFIG),
            "-jd",
            str(json_dir),
            "--max-pairs",
            "5",
        ]
    )
    rule = enriched_matrix.resolve_pair("player", "npc_elder")
    assert isinstance(rule, PronounRule)
    assert rule.self_pronoun == "vãn bối"
    assert rule.target_pronoun == "trưởng lão"
    assert rule.notes == "LLM enriched"
    assert mock_completion.await_count >= 1
