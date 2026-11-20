from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, Field

from src.story_flowchart import CharacterInfo, StoryFlowchart


class PronounRule(BaseModel):
    stage_id: str = "default"
    self_pronoun: str
    target_pronoun: str
    third_person: str = ""
    tone: str = ""
    notes: str = ""


class PairRelationship(BaseModel):
    speaker_id: str
    listener_id: str
    interaction_count: int = 0
    scripts_with_deltas: list[str] = Field(default_factory=list)
    default: PronounRule
    stages: dict[str, PronounRule] = Field(default_factory=dict)
    script_stage_map: dict[str, str] = Field(default_factory=dict)


class RelationshipMatrix(BaseModel):
    characters: dict[str, dict[str, Any]] = Field(default_factory=dict)
    archetypes: dict[str, PronounRule] = Field(default_factory=dict)
    pairs: dict[str, PairRelationship] = Field(default_factory=dict)

    def resolve_pair(
        self,
        speaker_id: str,
        listener_id: str,
        script_id: str | None = None,
        branch_path: str | None = None,
    ) -> PronounRule | None:
        """Resolve the active ``PronounRule`` for ``(speaker_id -> listener_id)`` in context."""
        pair = self.pairs.get(f"{speaker_id}->{listener_id}")
        if pair is None:
            base_speaker = speaker_id.split("_", 1)[0]
            base_listener = listener_id.split("_", 1)[0]
            pair = (
                self.pairs.get(f"{base_speaker}->{listener_id}")
                or self.pairs.get(f"{speaker_id}->{base_listener}")
                or self.pairs.get(f"{base_speaker}->{base_listener}")
            )
        if pair is None:
            return None

        stage_id: str | None = None
        if script_id and branch_path and branch_path != "main":
            stage_id = pair.script_stage_map.get(f"{script_id}#{branch_path}")
        if stage_id is None and script_id:
            stage_id = pair.script_stage_map.get(script_id)

        if stage_id is None and branch_path and branch_path != "main":
            lowered_branch = branch_path.lower()
            for candidate_stage in pair.stages:
                if candidate_stage.lower() in lowered_branch:
                    stage_id = candidate_stage
                    break

        if stage_id and stage_id in pair.stages:
            return pair.stages[stage_id]
        if stage_id and stage_id in self.archetypes:
            return self.archetypes[stage_id]
        return pair.default

    def to_json_file(self, path: str | Path, indent: int | None = 2) -> Path:
        """Serialize matrix to a UTF-8 JSON file with ``ensure_ascii=False``."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.model_dump(mode="json"), ensure_ascii=False, indent=indent)
        target.write_text(payload, encoding="utf-8")
        return target

    @classmethod
    def from_json_file(cls, path: str | Path) -> Self:
        """Load a ``RelationshipMatrix`` from a UTF-8 JSON file."""
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.model_validate(raw)


DEFAULT_ARCHETYPES: dict[str, PronounRule] = {
    "default": PronounRule(
        stage_id="default",
        self_pronoun="tại hạ / ta",
        target_pronoun="các hạ / ngươi",
        third_person="hắn / nàng",
        tone="kiếm hiệp trung lập, lịch sự hoặc giữ khoảng cách tùy bối cảnh",
        notes="Quy tắc chung khi chưa có quan hệ đặc biệt.",
    ),
    "disciple": PronounRule(
        stage_id="disciple",
        self_pronoun="đệ tử / vãn bối",
        target_pronoun="sư phụ / tiền bối",
        third_person="ngài / tiền bối",
        tone="cung kính, lễ phép",
        notes="Vãn bối hoặc đệ tử thưa với sư phụ, trưởng bối.",
    ),
    "master": PronounRule(
        stage_id="master",
        self_pronoun="vi sư / ta",
        target_pronoun="đồ nhi / ngươi",
        third_person="hắn / đồ nhi",
        tone="uy nghiêm, bề trên, đôi lúc nghiêm khắc",
        notes="Sư phụ hoặc chưởng môn nói với đệ tử.",
    ),
    "friend": PronounRule(
        stage_id="friend",
        self_pronoun="ta / huynh / đệ",
        target_pronoun="huynh / đệ / muội / cô nương",
        third_person="huynh ấy / nàng ấy",
        tone="thân thiết, nghĩa khí giang hồ",
        notes="Bằng hữu tri kỷ hoặc đồng môn thân thiết.",
    ),
    "lover": PronounRule(
        stage_id="lover",
        self_pronoun="ta / huynh / thiếp",
        target_pronoun="nàng / chàng / muội / huynh",
        third_person="nàng / chàng",
        tone="tình cảm sâu đậm, dịu dàng hoặc e ấp",
        notes="Giai đoạn kết duyên, tỏ tình hoặc phu thê.",
    ),
    "enemy": PronounRule(
        stage_id="enemy",
        self_pronoun="ta / lão tử",
        target_pronoun="ngươi / nhà ngươi",
        third_person="hắn / ả / tên đó",
        tone="thù địch, căng thẳng, khinh miệt hoặc gay gắt",
        notes="Đối đầu trực tiếp hoặc sinh tử chi chiến.",
    ),
    "betrayed": PronounRule(
        stage_id="betrayed",
        self_pronoun="ta",
        target_pronoun="ngươi",
        third_person="kẻ đó / ngươi",
        tone="lạnh lùng, đau đớn, cắt đứt tình nghĩa",
        notes="Sau khi phản bội hoặc rạn nứt không thể hàn gắn.",
    ),
}


def _rule(
    stage_id: str,
    self_p: str,
    target_p: str,
    third_p: str,
    tone: str,
    notes: str = "",
) -> PronounRule:
    return PronounRule(
        stage_id=stage_id,
        self_pronoun=self_p,
        target_pronoun=target_p,
        third_person=third_p,
        tone=tone,
        notes=notes,
    )


def _curated_pair_specs() -> dict[tuple[str, str], tuple[PronounRule, dict[str, PronounRule]]]:
    """Curated wuxia Vietnamese pronoun rules and multi-stage overrides for key pairs."""
    specs: dict[tuple[str, str], tuple[PronounRule, dict[str, PronounRule]]] = {}

    def add_pair(
        spk: str,
        lst: str,
        default_rule: PronounRule,
        stages: dict[str, PronounRule] | None = None,
    ) -> None:
        stage_map = dict(stages or {})
        stage_map.setdefault("default", default_rule)
        specs[(spk, lst)] = (default_rule, stage_map)

    # player <-> master (Đường Trung Linh)
    add_pair(
        "player",
        "master",
        _rule("default", "đệ tử", "chưởng môn / sư phụ", "chưởng môn", "cung kính, khiêm nhường"),
        {
            "disciple": _rule("disciple", "đệ tử", "sư phụ", "ngài", "kính trọng tuyệt đối"),
            "betrayed": _rule("betrayed", "ta", "ngươi / Đường chưởng môn", "ông ta", "lạnh nhạt xa cách"),
        },
    )
    add_pair(
        "master",
        "player",
        _rule("default", "ta", "ngươi", "hắn", "nghiêm nghị, trầm ổn"),
        {
            "master": _rule("master", "vi sư / ta", "ngươi / Triệu Hoạt", "hắn", "khích lệ nhưng điềm tĩnh"),
            "enemy": _rule("enemy", "ta", "ngươi", "nghịch đồ", "lạnh lùng uy áp"),
            "betrayed": _rule("betrayed", "ta", "ngươi", "kẻ phản bội", "đau đáu thất vọng"),
        },
    )

    # player <-> brother1 (Đường Bố Y)
    add_pair(
        "player",
        "brother1",
        _rule("default", "đệ", "đại sư huynh", "đại sư huynh", "kính trọng, thân thiết"),
        {
            "friend": _rule("friend", "đệ", "đại sư huynh", "huynh ấy", "gần gũi tin tưởng"),
            "betrayed": _rule("betrayed", "ta", "ngươi", "hắn", "cay đắng thất vọng"),
            "enemy": _rule("enemy", "ta", "ngươi", "hắn", "quyết liệt đối đầu"),
        },
    )
    add_pair(
        "brother1",
        "player",
        _rule("default", "huynh / ta", "sư đệ / tiểu Hoạt", "sư đệ", "hào sảng, che chở"),
        {
            "friend": _rule("friend", "huynh", "sư đệ / tiểu Hoạt", "đệ ấy", "ân cần phóng khoáng"),
            "betrayed": _rule("betrayed", "ta", "ngươi", "hắn", "lạnh lẽo xa cách"),
            "enemy": _rule("enemy", "ta", "ngươi", "hắn", "kiếm bạt nỗ trương"),
        },
    )

    # player <-> brother2 (Đường Tranh)
    add_pair(
        "player",
        "brother2",
        _rule("default", "đệ", "nhị sư huynh", "nhị sư huynh", "dè dặt, nhẫn nhịn nhưng kính nể"),
        {
            "friend": _rule("friend", "đệ", "nhị sư huynh", "nhị sư huynh", "hiểu lòng, bớt e dè"),
            "enemy": _rule("enemy", "ta", "ngươi", "hắn", "căng thẳng đối nghịch"),
            "betrayed": _rule("betrayed", "ta", "ngươi", "hắn", "lạnh lùng cắt đứt"),
        },
    )
    add_pair(
        "brother2",
        "player",
        _rule("default", "ta", "ngươi / sư đệ", "hắn", "lạnh lùng, mỉa mai nhưng ngầm bảo vệ"),
        {
            "friend": _rule("friend", "ta / huynh", "sư đệ / ngươi", "hắn", "khẩu xà tâm phật, tin cậy"),
            "enemy": _rule("enemy", "ta", "ngươi", "tên xấu xí kia", "châm chọc gay gắt"),
            "betrayed": _rule("betrayed", "ta", "ngươi", "hắn", "tuyệt tình, cay độc"),
        },
    )

    # player <-> brother3 (Đường Thăng)
    add_pair(
        "player",
        "brother3",
        _rule("default", "đệ", "tam sư huynh", "tam sư huynh", "ngay ngắn, tôn trọng"),
        {
            "friend": _rule("friend", "đệ", "tam sư huynh", "huynh ấy", "chân thành kề vai sát cánh"),
            "betrayed": _rule("betrayed", "ta", "ngươi", "hắn", "xa cách nặng nề"),
        },
    )
    add_pair(
        "brother3",
        "player",
        _rule("default", "ta", "sư đệ / ngươi", "sư đệ", "nghiêm chỉnh, trách nhiệm"),
        {
            "friend": _rule("friend", "huynh / ta", "sư đệ / Triệu sư đệ", "đệ ấy", "ôn hòa, tin tưởng"),
            "master": _rule("master", "ta", "sư đệ / ngươi", "hắn", "cương vị quyền chưởng môn"),
            "betrayed": _rule("betrayed", "ta", "ngươi", "hắn", "nghiêm khắc lạnh nhạt"),
        },
    )

    # player <-> brother4 (Đường Duy Nguyên)
    add_pair(
        "player",
        "brother4",
        _rule("default", "đệ", "tứ sư huynh", "tứ sư huynh", "suồng sã, thân thuộc"),
        {
            "friend": _rule("friend", "đệ", "tứ sư huynh", "huynh ấy", "cười đùa thân tình"),
            "enemy": _rule("enemy", "ta", "ngươi", "hắn", "lật mặt đối nghịch"),
        },
    )
    add_pair(
        "brother4",
        "player",
        _rule("default", "huynh / ta", "sư đệ / Triệu sư đệ", "sư đệ", "lanh lợi, nửa đùa nửa thật"),
        {
            "friend": _rule("friend", "huynh", "tiểu Hoạt / sư đệ", "hắn", "hết lòng giúp đỡ"),
            "enemy": _rule("enemy", "ta", "ngươi", "hắn", "tính toán lạnh nhạt"),
        },
    )

    # player <-> sister1 / sister (Đường Mặc Linh)
    for sis_id in ("sister1", "sister"):
        add_pair(
            "player",
            sis_id,
            _rule("default", "sư huynh / ta", "tiểu sư muội", "tiểu sư muội", "dịu dàng, trân trọng"),
            {
                "friend": _rule("friend", "sư huynh", "tiểu sư muội / Mặc Linh", "muội ấy", "ấm áp thân cận"),
                "lover": _rule("lover", "huynh / ta", "muội / Mặc Linh / nàng", "nàng", "thâm tình sâu nặng"),
                "betrayed": _rule("betrayed", "ta", "muội / cô nương", "nàng ta", "đau xót xa cách"),
                "enemy": _rule("enemy", "ta", "ngươi", "nàng ta", "bi thương đối đầu"),
            },
        )
        add_pair(
            sis_id,
            "player",
            _rule("default", "muội", "sư huynh", "sư huynh", "ít lời, điềm đạm, thân quen"),
            {
                "friend": _rule("friend", "muội", "sư huynh", "huynh ấy", "nhẹ nhàng ỷ lại"),
                "lover": _rule("lover", "muội / thiếp", "sư huynh / chàng", "chàng", "dịu dàng gắn bó"),
                "betrayed": _rule("betrayed", "ta", "ngươi", "hắn", "lạnh lẽo vô cảm"),
                "enemy": _rule("enemy", "ta", "ngươi", "hắn", "cắt đứt ân tình"),
            },
        )

    # player <-> girl1 (Thụy Hạnh)
    add_pair(
        "player",
        "girl1",
        _rule("default", "tại hạ / ta", "cô nương / Thụy cô nương", "nàng", "tò mò, giữ lễ"),
        {
            "friend": _rule("friend", "ta", "Thụy cô nương", "nàng", "thẳng thắn tin tưởng"),
            "lover": _rule("lover", "ta", "nàng / Thụy Hạnh", "nàng", "tình ý sâu sắc"),
            "enemy": _rule("enemy", "ta", "ngươi", "ả", "cảnh giác gay gắt"),
        },
    )
    add_pair(
        "girl1",
        "player",
        _rule("default", "ta", "công tử / ngươi", "hắn", "bí ẩn, thong dong"),
        {
            "friend": _rule("friend", "ta", "Triệu công tử", "chàng", "ưu ái ngầm"),
            "lover": _rule("lover", "thiếp / ta", "chàng / Triệu lang", "chàng", "trìu mến dịu dàng"),
            "enemy": _rule("enemy", "ta", "ngươi", "hắn", "lạnh lùng vô tình"),
        },
    )

    # player <-> girl2 (Diệp Vân Thường)
    add_pair(
        "player",
        "girl2",
        _rule("default", "tại hạ / ta", "Diệp cô nương / cô nương", "nàng", "lễ độ, ân cần"),
        {
            "friend": _rule("friend", "ta / huynh", "Vân Thường / Diệp cô nương", "nàng", "chăm sóc chân thành"),
            "lover": _rule("lover", "huynh / ta", "Vân Thường / muội / nàng", "nàng", "yêu thương nâng niu"),
            "enemy": _rule("enemy", "ta", "ngươi", "nàng ta", "lạnh nhạt"),
        },
    )
    add_pair(
        "girl2",
        "player",
        _rule("default", "tiểu nữ / muội", "Triệu công tử / đại ca", "công tử", "nhã nhặn, dịu dàng"),
        {
            "friend": _rule("friend", "muội", "Triệu đại ca / Triệu công tử", "huynh ấy", "tin cậy thân thương"),
            "lover": _rule("lover", "muội / thiếp", "Triệu đại ca / chàng", "chàng", "ngọt ngào gắn bó"),
            "enemy": _rule("enemy", "ta", "ngươi", "hắn", "tổn thương xa lánh"),
        },
    )

    # player <-> girl4 (Long Tương)
    add_pair(
        "player",
        "girl4",
        _rule("default", "tại hạ / ta", "Long cô nương / cô nương", "nàng", "khách sáo xen kính nể"),
        {
            "friend": _rule("friend", "ta", "Long cô nương / Tương tỷ", "nàng", "thoải mái thân tình"),
            "lover": _rule("lover", "ta", "nàng / Long Tương", "nàng", "chân thành nồng ấm"),
            "enemy": _rule("enemy", "ta", "ngươi", "nàng", "kiêng dè đối đầu"),
        },
    )
    add_pair(
        "girl4",
        "player",
        _rule("default", "ta / cô nương", "ngươi / Triệu Hoạt", "hắn", "bộc trực, phóng khoáng"),
        {
            "friend": _rule("friend", "ta", "Triệu Hoạt / ngươi", "hắn", "hào sảng coi trọng"),
            "lover": _rule("lover", "ta / thiếp", "ngươi / chàng", "chàng", "thẳng thắn mà dịu dàng"),
            "enemy": _rule("enemy", "ta", "ngươi", "hắn", "lẫm liệt thị uy"),
        },
    )

    # player <-> girl5 (Ngu Tiểu Mai)
    add_pair(
        "player",
        "girl5",
        _rule("default", "ta / tại hạ", "Ngu cô nương / cô nương", "nàng", "vừa đề phòng vừa thân quen"),
        {
            "friend": _rule("friend", "ta / huynh", "Tiểu Mai / muội", "nàng", "chiều chuộng dung túng"),
            "lover": _rule("lover", "huynh / ta", "Tiểu Mai / muội / nàng", "nàng", "yêu thương sâu đậm"),
            "betrayed": _rule("betrayed", "ta", "ngươi", "ả", "đau đớn oán hận"),
            "enemy": _rule("enemy", "ta", "ngươi", "nàng ta", "cảnh giác tuyệt đối"),
        },
    )
    add_pair(
        "girl5",
        "player",
        _rule("default", "muội / ta", "Triệu sư huynh / ngươi", "huynh ấy", "tinh nghịch, lém lỉnh"),
        {
            "friend": _rule("friend", "muội", "Triệu sư huynh / ca ca", "huynh ấy", "quấn quýt tinh quái"),
            "lover": _rule("lover", "muội / thiếp", "ca ca / chàng", "chàng", "nũng nịu si tình"),
            "betrayed": _rule("betrayed", "ta", "ngươi", "hắn", "lạnh lẽo tàn nhẫn"),
            "enemy": _rule("enemy", "ta", "ngươi", "hắn", "châm chọc tàn độc"),
        },
    )

    # player <-> girl6 (Hạ Hầu Lan — Sư phụ ở Không Động!)
    add_pair(
        "player",
        "girl6",
        _rule("default", "đệ tử / vãn bối", "sư phụ / tiền bối", "sư phụ", "tôn kính, lễ phép"),
        {
            "disciple": _rule("disciple", "đệ tử", "sư phụ", "sư phụ", "cung kính hết mực"),
            "friend": _rule("friend", "đệ tử", "sư phụ", "nàng", "gần gũi thấu hiểu"),
            "lover": _rule("lover", "đệ tử / ta", "sư phụ / nàng", "nàng", "sư đồ luyến, vừa kính vừa yêu"),
            "betrayed": _rule("betrayed", "ta", "ngươi", "nàng ta", "đau thương đoạn tuyệt"),
            "enemy": _rule("enemy", "ta", "ngươi", "nàng ta", "sinh tử đối đầu"),
        },
    )
    add_pair(
        "girl6",
        "player",
        _rule("default", "vi sư / ta", "ngươi / đồ nhi", "hắn", "cao ngạo, lạnh lùng"),
        {
            "master": _rule("master", "vi sư", "đồ nhi / ngươi", "hắn", "nghiêm khắc nhưng bao bọc"),
            "lover": _rule("lover", "ta / vi sư", "ngươi / chàng", "chàng", "ngoài lạnh trong nóng, chung tình"),
            "betrayed": _rule("betrayed", "ta", "ngươi", "kẻ phụ bạc", "oán hận tột độ"),
            "enemy": _rule("enemy", "ta", "ngươi", "hắn", "sát khí bức người"),
        },
    )

    # player <-> girl7 (Úc Trúc)
    add_pair(
        "player",
        "girl7",
        _rule("default", "tại hạ / ta", "Úc cô nương / cô nương", "nàng", "hơi dè chừng vì tinh quái"),
        {
            "friend": _rule("friend", "ta", "Úc cô nương / Úc Trúc", "nàng", "thoải mái tin tưởng"),
            "lover": _rule("lover", "ta", "nàng / Úc Trúc", "nàng", "chân thành nâng niu"),
            "betrayed": _rule("betrayed", "ta", "ngươi", "nàng ta", "lạnh nhạt thất vọng"),
            "enemy": _rule("enemy", "ta", "ngươi", "nàng ta", "đề phòng đối địch"),
        },
    )
    add_pair(
        "girl7",
        "player",
        _rule("default", "ta", "ngươi / Triệu Hoạt", "hắn", "tinh quái, hoạt bát"),
        {
            "friend": _rule("friend", "ta", "Triệu Hoạt / ngươi", "hắn", "vui vẻ thân thiết"),
            "lover": _rule("lover", "ta / thiếp", "ngươi / chàng", "chàng", "tình cảm chân thành"),
            "betrayed": _rule("betrayed", "ta", "ngươi", "hắn", "oán hận lạnh lùng"),
            "enemy": _rule("enemy", "ta", "ngươi", "hắn", "hung hãn đối đầu"),
        },
    )

    # player <-> girl8 (Ngụy Cúc)
    add_pair(
        "player",
        "girl8",
        _rule("default", "tại hạ / ta", "Ngụy chưởng môn / Ngụy cô nương", "nàng", "kính trọng, lễ nhã"),
        {
            "friend": _rule("friend", "ta", "Ngụy cô nương / A Cúc", "nàng", "tri kỷ đồng điệu"),
            "lover": _rule("lover", "ta", "nàng / Ngụy Cúc", "nàng", "tao nhã, tình thâm"),
            "enemy": _rule("enemy", "ta", "ngươi", "nàng ta", "xa cách nghiêm nghị"),
        },
    )
    add_pair(
        "girl8",
        "player",
        _rule("default", "ta", "Triệu công tử / Triệu thiếu hiệp", "công tử", "điềm đạm, nho nhã"),
        {
            "friend": _rule("friend", "ta", "Triệu Hoạt / Triệu công tử", "hắn", "ôn hòa thân cận"),
            "lover": _rule("lover", "thiếp / ta", "chàng / Triệu lang", "chàng", "dịu dàng thục nữ"),
            "enemy": _rule("enemy", "ta", "ngươi", "hắn", "nghiêm khắc lạnh nhạt"),
        },
    )

    # player <-> girl9 (Thượng Quan Huỳnh)
    add_pair(
        "player",
        "girl9",
        _rule("default", "tại hạ / ta", "Thượng Quan cô nương / tiểu thư", "nàng", "lễ độ, hơi nể nang"),
        {
            "friend": _rule("friend", "ta", "Thượng Quan cô nương / Huỳnh nhi", "nàng", "thẳng thắn thân tình"),
            "lover": _rule("lover", "ta", "nàng / Huỳnh nhi", "nàng", "ân cần gắn bó"),
            "enemy": _rule("enemy", "ta", "ngươi", "nàng ta", "lạnh nhạt đối đầu"),
        },
    )
    add_pair(
        "girl9",
        "player",
        _rule("default", "bổn tiểu thư / ta", "ngươi / Triệu Hoạt", "hắn", "kiêu kỳ, sắc sảo"),
        {
            "friend": _rule("friend", "ta", "Triệu Hoạt / ngươi", "hắn", "trọng nghĩa, bớt kiêu"),
            "lover": _rule("lover", "ta / thiếp", "ngươi / chàng", "chàng", "mạnh miệng mềm lòng"),
            "enemy": _rule("enemy", "ta", "ngươi", "hắn", "khinh thường lạnh lùng"),
        },
    )

    # player <-> special3 (Diệp Vân Chu), special999 (Thụy Sanh), Nam Cung family
    add_pair(
        "player",
        "special3",
        _rule("default", "tại hạ", "Diệp huynh / Diệp đại hiệp", "Diệp huynh", "kính trọng, nghĩa khí"),
        {
            "friend": _rule("friend", "ta / đệ", "Diệp đại ca / Diệp huynh", "huynh ấy", "tin tưởng như huynh đệ"),
            "enemy": _rule("enemy", "ta", "ngươi", "hắn", "đối địch"),
        },
    )
    add_pair(
        "special3",
        "player",
        _rule("default", "tại hạ / ta", "Triệu huynh / Triệu thiếu hiệp", "Triệu huynh", "ôn hòa, trọng nghĩa"),
        {
            "friend": _rule("friend", "huynh / ta", "Triệu hiền đệ / Triệu huynh", "hắn", "thân tình trân trọng"),
            "enemy": _rule("enemy", "ta", "ngươi", "hắn", "lạnh lùng nghiêm nghị"),
        },
    )
    add_pair(
        "player",
        "special999",
        _rule("default", "tại hạ / ta", "Thụy công tử / công tử", "hắn", "khiêm nhường nhưng cảnh giác"),
        {
            "friend": _rule("friend", "ta", "Thụy huynh", "hắn", "tương kính"),
            "enemy": _rule("enemy", "ta", "ngươi", "hắn", "quyết liệt sinh tử"),
        },
    )
    add_pair(
        "special999",
        "player",
        _rule("default", "tại hạ / ta", "Triệu huynh / ngươi", "hắn", "lịch thiệp, sâu không lường"),
        {
            "friend": _rule("friend", "ta", "Triệu huynh", "hắn", "tao nhã thân thiện"),
            "enemy": _rule("enemy", "ta", "ngươi", "hắn", "lạnh lùng uy áp"),
        },
    )
    add_pair(
        "player",
        "special102",
        _rule("default", "tại hạ", "Nam Cung công tử", "hắn", "khách sáo đề phòng"),
        {"enemy": _rule("enemy", "ta", "ngươi", "hắn", "châm biếm đối nghịch")},
    )
    add_pair(
        "special102",
        "player",
        _rule("default", "ta / bổn công tử", "ngươi", "hắn", "ngạo mạn khinh thường"),
        {"enemy": _rule("enemy", "ta", "ngươi", "tên xấu xí", "tàn nhẫn ngạo mạn")},
    )
    add_pair(
        "player",
        "special103",
        _rule("default", "tại hạ / ta", "Nam Cung công tử / ngươi", "hắn", "bất đắc dĩ giao thiệp"),
        {"friend": _rule("friend", "ta", "Nam Cung huynh", "hắn", "nửa đùa nửa thật")},
    )
    add_pair(
        "special103",
        "player",
        _rule("default", "ta", "ngươi / Triệu huynh", "hắn", "phóng đãng ngông nghênh"),
        {"friend": _rule("friend", "ta", "Triệu huynh", "hắn", "chân thành kiểu công tử bột")},
    )

    # Key Đường Môn & Diệp family inter-character pairs
    add_pair(
        "brother1",
        "brother2",
        _rule("default", "huynh / ta", "nhị sư đệ / sư đệ", "sư đệ", "thân tình mà thẳng thắn"),
    )
    add_pair(
        "brother2",
        "brother1",
        _rule("default", "đệ / ta", "đại sư huynh", "đại sư huynh", "khẩu xà tâm phật nhưng kính trọng"),
    )
    add_pair(
        "brother2",
        "sister1",
        _rule("default", "nhị sư huynh / ta", "tiểu sư muội", "tiểu sư muội", "ôn tồn cưng chiều ngầm"),
    )
    add_pair(
        "sister1",
        "brother2",
        _rule("default", "muội", "nhị sư huynh", "nhị sư huynh", "lễ phép thân quen"),
    )
    add_pair(
        "master",
        "sister1",
        _rule("default", "cha / ta", "Mặc Linh / con", "con gái", "từ phụ trầm lặng thương con"),
    )
    add_pair(
        "sister1",
        "master",
        _rule("default", "con / nhi nữ", "cha / phụ thân", "phụ thân", "hiếu thuận điềm đạm"),
    )
    add_pair(
        "special3",
        "girl2",
        _rule("default", "ca / huynh", "Vân Thường / muội", "muội ấy", "huynh trưởng thương em hết mực"),
    )
    add_pair(
        "girl2",
        "special3",
        _rule("default", "muội", "ca ca / huynh", "ca ca", "lễ phép ỷ lại"),
    )

    return specs


def _default_rule_for_pair(
    speaker_id: str,
    listener_id: str,
    characters: dict[str, CharacterInfo],
) -> PronounRule:
    spk_info = characters.get(speaker_id)
    lst_info = characters.get(listener_id)

    if listener_id == "master" or (lst_info and "掌门" in lst_info.zh_title):
        return _rule("default", "vãn bối / tại hạ", "tiền bối / chưởng môn", "tiền bối", "cung kính")
    if speaker_id == "master" or (spk_info and "掌门" in spk_info.zh_title):
        return _rule("default", "ta / bản tọa", "ngươi / các hạ", "hắn", "uy nghiêm bề trên")
    if speaker_id.startswith("trainee") and listener_id in (
        "player",
        "brother1",
        "brother2",
        "brother3",
        "brother4",
    ):
        return _rule("default", "đệ tử", "sư huynh", "sư huynh", "lễ phép đồng môn")
    if speaker_id.startswith("trainee") and listener_id == "sister1":
        return _rule("default", "đệ tử / sư huynh", "tiểu sư muội", "tiểu sư muội", "kính nể")
    if listener_id.startswith("trainee") and speaker_id in (
        "player",
        "brother1",
        "brother2",
        "brother3",
        "brother4",
    ):
        return _rule("default", "ta / sư huynh", "sư đệ / ngươi", "hắn", "thẳng thắn đồng môn")
    if lst_info and lst_info.gender == "female":
        return _rule("default", "tại hạ / ta", "cô nương", "nàng", "kiếm hiệp lịch sự")
    if spk_info and spk_info.gender == "female":
        return _rule("default", "tiểu nữ / ta", "công tử / các hạ", "hắn", "kiếm hiệp lịch sự")
    return _rule("default", "tại hạ / ta", "các hạ / ngươi", "hắn", "kiếm hiệp trung lập")


def build_matrix_from_flowchart(
    flowchart: StoryFlowchart,
    glossary_name_map: dict[str, str] | None = None,
) -> RelationshipMatrix:
    """Build a ``RelationshipMatrix`` ranked by interaction frequency from ``StoryFlowchart``."""
    char_summaries: dict[str, dict[str, Any]] = {}
    for cid, cinfo in flowchart.characters.items():
        vi_name = cinfo.vi_name
        if glossary_name_map:
            vi_name = (
                glossary_name_map.get(f"Character/{cid}")
                or glossary_name_map.get(cinfo.zh_name)
                or vi_name
            )
        char_summaries[cid] = {
            "char_id": cid,
            "zh_name": cinfo.zh_name,
            "zh_title": cinfo.zh_title,
            "vi_name": vi_name,
            "gender": cinfo.gender,
            "traits": cinfo.traits,
        }

    interaction_counts: dict[tuple[str, str], int] = defaultdict(int)
    pair_scripts_with_deltas: dict[tuple[str, str], set[str]] = defaultdict(set)

    for script_id, script in flowchart.scripts.items():
        delta_chars = {d.char_id for d in script.relationship_deltas}
        for line in script.lines:
            speaker = line.speaker_id
            if not speaker or speaker == "narrative":
                continue
            for listener in line.listeners_on_stage:
                if not listener or listener == "narrative" or listener == speaker:
                    continue
                pair_key = (speaker, listener)
                interaction_counts[pair_key] += 1
                if listener in delta_chars or speaker in delta_chars:
                    pair_scripts_with_deltas[pair_key].add(script_id)

    curated_specs = _curated_pair_specs()
    all_pair_keys = set(interaction_counts.keys()) | set(curated_specs.keys())

    # Sort descending by interaction count, then deterministically by (speaker_id, listener_id)
    sorted_keys = sorted(
        all_pair_keys,
        key=lambda k: (-interaction_counts.get(k, 0), k[0], k[1]),
    )

    pairs: dict[str, PairRelationship] = {}
    for spk, lst in sorted_keys:
        if (spk, lst) in curated_specs:
            default_rule, stages = curated_specs[(spk, lst)]
        else:
            default_rule = _default_rule_for_pair(spk, lst, flowchart.characters)
            stages = {"default": default_rule}

        pairs[f"{spk}->{lst}"] = PairRelationship(
            speaker_id=spk,
            listener_id=lst,
            interaction_count=interaction_counts.get((spk, lst), 0),
            scripts_with_deltas=sorted(pair_scripts_with_deltas.get((spk, lst), set())),
            default=default_rule,
            stages=stages,
            script_stage_map={},
        )

    return RelationshipMatrix(
        characters=char_summaries,
        archetypes=dict(DEFAULT_ARCHETYPES),
        pairs=pairs,
    )
