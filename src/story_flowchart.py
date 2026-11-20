from __future__ import annotations

import json
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, Field, PrivateAttr, field_validator

LEAN_CSV_SIG = (
    b"\x03\x00\x00\x00 = \x00\x02\x00\x00\x00\\n\x00\x00\x04\x00\x00\x00 // \x00\x00\x00\x00"
)
STORY_KEY_PREFIX = "Story/"

CURATED_CHARACTERS: dict[str, dict[str, str]] = {
    "player": {
        "vi_name": "Triệu Hoạt",
        "gender": "male",
        "traits": "Ngoại thất đệ tử Đường Môn, dung mạo xấu xí nhưng nghĩa khí, quật cường.",
    },
    "master": {
        "vi_name": "Đường Trung Linh",
        "gender": "male",
        "traits": "Chưởng môn Đường Môn, uy nghiêm trầm ổn, mang bệnh căn, thương thầm hối hận.",
    },
    "brother1": {
        "vi_name": "Đường Bố Y",
        "gender": "male",
        "traits": "Đại sư huynh Đường Môn (Phi Hiệp), hào hiệp phóng khoáng, trọng nghĩa khí.",
    },
    "brother2": {
        "vi_name": "Đường Tranh",
        "gender": "male",
        "traits": "Nhị sư huynh Đường Môn, tinh thông độc thuật y lý, ngoài lạnh trong nóng, khẩu xà tâm phật.",
    },
    "brother3": {
        "vi_name": "Đường Thăng",
        "gender": "male",
        "traits": "Tam sư huynh Đường Môn, nghiêm nghị chính trực, gánh vác môn quy.",
    },
    "brother4": {
        "vi_name": "Đường Duy Nguyên",
        "gender": "male",
        "traits": "Tứ sư huynh Đường Môn, lanh lợi khôn khéo, buôn bán thực dụng nhưng trọng tình đồng môn.",
    },
    "sister": {
        "vi_name": "Đường Mặc Linh",
        "gender": "female",
        "traits": "Tiểu sư muội Đường Môn, ái nữ chưởng môn, ít nói điềm đạm, thích gấp hạc giấy.",
    },
    "sister1": {
        "vi_name": "Đường Mặc Linh",
        "gender": "female",
        "traits": "Tiểu sư muội Đường Môn, ái nữ chưởng môn, ít nói điềm đạm, thích gấp hạc giấy.",
    },
    "girl1": {
        "vi_name": "Thụy Hạnh",
        "gender": "female",
        "traits": "Hạnh Hoa Tiên, thần bí thâm sâu, am hiểu mệnh số.",
    },
    "girl2": {
        "vi_name": "Diệp Vân Thường",
        "gender": "female",
        "traits": "Điểm Thương Minh Châu, tiểu thư Điểm Thương, dịu dàng đoan trang nhưng đa bệnh.",
    },
    "girl4": {
        "vi_name": "Long Tương",
        "gender": "female",
        "traits": "Đệ tử Cẩm Hương Cung, võ nghệ cao cường, bộc trực hào sảng, thích ăn ngon.",
    },
    "girl5": {
        "vi_name": "Ngu Tiểu Mai",
        "gender": "female",
        "traits": "Nữ đệ tử Phi Thiên Môn (Không Động), tinh nghịch khó đoán, tâm tư sâu kín.",
    },
    "girl6": {
        "vi_name": "Hạ Hầu Lan",
        "gender": "female",
        "traits": "Đoạt Phách U Lan, trưởng lão Đoạt Phách Phái (Không Động), cao ngạo lạnh lùng, sư phụ của Triệu Hoạt.",
    },
    "girl7": {
        "vi_name": "Úc Trúc",
        "gender": "female",
        "traits": "Liệt Cốt Ma (Không Động), tinh quái hoạt bát, giấu nhiều bí mật thân thế.",
    },
    "girl8": {
        "vi_name": "Ngụy Cúc",
        "gender": "female",
        "traits": "Chưởng môn Huyền Công Môn (Không Động), nho nhã điềm tĩnh, thích đọc sách.",
    },
    "girl9": {
        "vi_name": "Thượng Quan Huỳnh",
        "gender": "female",
        "traits": "Thượng Quan thiên kim, thông minh sắc sảo, kiêu kỳ nhưng trượng nghĩa.",
    },
    "special3": {
        "vi_name": "Diệp Vân Chu",
        "gender": "male",
        "traits": "Thương Tùng Kiếm Khách, huynh trưởng Diệp Vân Thường, trầm ổn chính nghĩa.",
    },
    "special999": {
        "vi_name": "Thụy Sanh",
        "gender": "male",
        "traits": "Nhân vật trung tâm giang hồ, phong thái văn nhã nhưng tâm cơ khó lường.",
    },
    "special101": {
        "vi_name": "Nam Cung Viễn",
        "gender": "male",
        "traits": "Gia chủ Nam Cung thế gia, khí độ uy nghi.",
    },
    "special102": {
        "vi_name": "Nam Cung Thâm",
        "gender": "male",
        "traits": "Công tử Nam Cung thế gia, cao ngạo mưu lược.",
    },
    "special103": {
        "vi_name": "Nam Cung Thiển",
        "gender": "male",
        "traits": "Công tử Nam Cung thế gia, phóng đãng ngông cuồng nhưng có nét chân thành.",
    },
    "special104": {
        "vi_name": "Nam Cung Hoành",
        "gender": "male",
        "traits": "Trưởng bối Nam Cung thế gia.",
    },
    "special402": {
        "vi_name": "Ôn phu nhân",
        "gender": "female",
        "traits": "Chưởng môn Thiết Quyền Môn, nghiêm nghị nghĩa khí.",
    },
    "special404": {
        "vi_name": "Đan Hà Tử",
        "gender": "male",
        "traits": "Cao nhân đạo gia, tiêu dao phóng khoáng.",
    },
    "special405": {
        "vi_name": "Thân Đồ Long",
        "gender": "male",
        "traits": "Nhân vật hung hãn giang hồ.",
    },
    "special407": {
        "vi_name": "Thượng Quan Chuẩn",
        "gender": "male",
        "traits": "Gia chủ Thượng Quan thế gia, phụ thân Thượng Quan Huỳnh.",
    },
    "special831": {
        "vi_name": "Mạnh Tiên Dao",
        "gender": "female",
        "traits": "Cao thủ Cẩm Hương Cung.",
    },
    "special832": {
        "vi_name": "Đường Phương",
        "gender": "female",
        "traits": "Người Đường Môn, bản lĩnh quyết đoán.",
    },
    "special834": {
        "vi_name": "Đoạn Trí Tú",
        "gender": "male",
        "traits": "Cao thủ Đại Lý Đoàn thị.",
    },
    "special206": {
        "vi_name": "Phúc Uẩn",
        "gender": "male",
        "traits": "Cao tăng Thiếu Lâm, từ bi trầm tĩnh.",
    },
    "special207": {
        "vi_name": "Kim Ô Thượng Nhân",
        "gender": "male",
        "traits": "Chưởng môn Tung Sơn, dã tâm bành trướng.",
    },
    "special208": {
        "vi_name": "Triều Hòa",
        "gender": "male",
        "traits": "Đệ tử phản đồ / giang hồ hiểm ác.",
    },
    "special2": {
        "vi_name": "Long Uyên",
        "gender": "male",
        "traits": "Tiền võ lâm minh chủ, uy trấn giang hồ.",
    },
    "special4": {
        "vi_name": "Phàn Khiếu Thiên",
        "gender": "male",
        "traits": "Cuồng Khuyển, hào kiệt bộc trực.",
    },
    "special7": {
        "vi_name": "Thạch Công Viễn",
        "gender": "male",
        "traits": "Phi Thạch bang chủ.",
    },
    "special800": {
        "vi_name": "Tống Bi",
        "gender": "male",
        "traits": "Cao thủ giang hồ lão luyện.",
    },
    "special808": {
        "vi_name": "Giải Vô Trần",
        "gender": "male",
        "traits": "Kiếm khách giang hồ.",
    },
    "special811": {
        "vi_name": "Đường Sam",
        "gender": "male",
        "traits": "Người cũ Đường Môn.",
    },
    "narrative": {
        "vi_name": "Dẫn truyện",
        "gender": "neutral",
        "traits": "Lời dẫn chuyện / mô tả cảnh vật và nội tâm.",
    },
}

_STAGE_SHOW_RE = re.compile(r'stage\.show\{[^}]*character\s*=\s*characters\.Get\("([^"]+)"\)')
_STAGE_HIDE_RE = re.compile(r'stage\.hide\{[^}]*character\s*=\s*characters\.Get\("([^"]+)"\)')
_PORTRAIT_RE = re.compile(
    r'characters\.(?:LoadCharacterPortrait|GetPortrait)\("([^"]+)"\s*,\s*"([^"]+)"\)'
)
_CUSTOM_NAME_RE = re.compile(r'characters\.SetName\("([^"]+)"\s*,\s*"([^"]+)"\)')
_SAY_DIALOG_RE = re.compile(r"setsaydialog\(saydialogs\.([A-Za-z0-9_]+)\)")
_SET_CHAR_GET_RE = re.compile(r'setcharacter\(characters\.Get\("([^"]+)"\)')
_SET_CHAR_NARRATIVE_RE = re.compile(r"setcharacter\(\s*narrative\s*\)")
_SAY_KEY_RE = re.compile(r'say\(luamanager\.GetStoryText\("([^"]+)"\)\)')
_STAT_CHAR_RE = re.compile(r'statmodifymanager\.Character\("([^"]+)"\s*,\s*(-?\d+)\s*,\s*(-?\d+)\)')
_STAT_FLAG_RE = re.compile(r'statmodifymanager\.AddFlag\("([^"]+)"\s*,\s*(-?\d+)\)')
_NEXT_SCRIPT_RE = re.compile(r'luamanager\.SetNextScript\("([^"]+)"\)')
_ENDGAME_RE = re.compile(r'endgamepanel\.Open\("([^"]+)"\)')
_SWITCH_ASSIGN_RE = re.compile(
    r'^(?:local\s+)?([A-Za-z0-9_]+)\s*=\s*checkpointmanager\.Switch\("([^"]+)"\)'
)
_COND_ASSIGN_RE = re.compile(
    r'^(?:local\s+)?([A-Za-z0-9_]+)\s*=\s*checkpointmanager\.Condition\("([^"]+)"\)'
)
_CHOOSE_ASSIGN_RE = re.compile(
    r'^(?:local\s+)?([A-Za-z0-9_]+)\s*=\s*choose\(([A-Za-z0-9_]+)\)'
)
_OPTION_ASSIGN_RE = re.compile(
    r'^([A-Za-z0-9_]+)\[(\d+)\]\s*=.*?(?:"(?:[a-z]+\+)?(O_[A-Za-z0-9_]+)(?:\+[^"]*)?")'
)
_PLUS_OPTION_RE = re.compile(r'"[a-z]+\+(O_[A-Za-z0-9_]+)\+')
_INDEX_OPTION_RE = re.compile(r"--index:(O_[A-Za-z0-9_]+)")
_IF_RE = re.compile(r"^if\s+(.+?)\s+then\b(.*)$")
_ELSEIF_RE = re.compile(r"^elseif\s+(.+?)\s+then\b(.*)$")
_ELSE_RE = re.compile(r"^else\b")
_END_RE = re.compile(r"^end\b")
_OTHER_BLOCK_RE = re.compile(r"^(?:for|while|function|local\s+function)\b")
_CHOICE_COND_RE = re.compile(r"^([A-Za-z0-9_]+)\s*==\s*(\d+)$")
_CHECKPOINT_ID_RE = re.compile(r"^[A-Z]\d{3,4}(?:_\d+)*$")

_STORY_SCRIPT_MARKERS = (
    "say(luamanager.GetStoryText",
    "stage.show",
    "luamanager.SetNextScript",
    "endgamepanel.Open",
    "statmodifymanager",
)


def normalize_story_key(key: str) -> str:
    """Normalize a story text key so it always begins with ``Story/`` when non-empty."""
    cleaned = key.strip()
    if not cleaned:
        return ""
    if cleaned.startswith(STORY_KEY_PREFIX):
        return cleaned
    return f"{STORY_KEY_PREFIX}{cleaned}"


class CharacterInfo(BaseModel):
    char_id: str
    zh_name: str
    zh_title: str = ""
    vi_name: str = ""
    aliases: list[str] = Field(default_factory=list)
    gender: str = ""
    traits: str = ""


class RelationshipDelta(BaseModel):
    char_id: str
    stat_type: int
    delta: int
    at_line_index: int


class DialogueLineNode(BaseModel):
    key: str
    line_type: Literal["dialogue", "thought", "narrative", "option"]
    speaker_id: str
    speaker_custom_name: str | None = None
    portrait_mood: str = "normal"
    listeners_on_stage: list[str] = Field(default_factory=list)
    branch_path: str = "main"
    prev_key: str | None = None
    next_key: str | None = None

    @field_validator("key")
    @classmethod
    def _normalize_key(cls, value: str) -> str:
        return normalize_story_key(value)


class ScriptNode(BaseModel):
    script_id: str
    title_zh: str = ""
    participants: list[str] = Field(default_factory=list)
    relationship_deltas: list[RelationshipDelta] = Field(default_factory=list)
    flag_deltas: list[tuple[str, int]] = Field(default_factory=list)
    next_scripts: list[str] = Field(default_factory=list)
    ending_ids: list[str] = Field(default_factory=list)
    option_ids: list[str] = Field(default_factory=list)
    lines: list[DialogueLineNode] = Field(default_factory=list)


class LineContext(BaseModel):
    script: ScriptNode
    line: DialogueLineNode
    prev_lines: list[DialogueLineNode] = Field(default_factory=list)
    next_lines: list[DialogueLineNode] = Field(default_factory=list)


class StoryFlowchart(BaseModel):
    characters: dict[str, CharacterInfo] = Field(default_factory=dict)
    scripts: dict[str, ScriptNode] = Field(default_factory=dict)

    _index_by_key: dict[str, tuple[str, int]] = PrivateAttr(default_factory=dict)
    _indexed_script_count: int = PrivateAttr(default=-1)

    def model_post_init(self, __context: Any) -> None:
        self.rebuild_index()

    def rebuild_index(self) -> None:
        """Rebuild the O(1) lookup index mapping normalized keys to ``(script_id, line_idx)``."""
        index: dict[str, tuple[str, int]] = {}
        for script_id, script in self.scripts.items():
            for line_idx, line in enumerate(script.lines):
                norm_key = normalize_story_key(line.key)
                if norm_key:
                    index[norm_key] = (script_id, line_idx)
        self._index_by_key = index
        self._indexed_script_count = len(self.scripts)

    def _lookup(self, key: str) -> tuple[str, int] | None:
        if self._indexed_script_count != len(self.scripts):
            self.rebuild_index()
        norm_key = normalize_story_key(key)
        if not norm_key:
            return None
        return self._index_by_key.get(norm_key)

    def get_line_context(
        self,
        key: str,
        window: int = 4,
        lookahead: int = 1,
    ) -> LineContext | None:
        """Return script, line, chronological preceding lines, and following lines in O(1) lookup."""
        location = self._lookup(key)
        if location is None:
            return None

        script_id, line_idx = location
        script = self.scripts[script_id]
        line = script.lines[line_idx]

        prev_lines: list[DialogueLineNode] = []
        visited: set[str] = {line.key}
        cur_prev = line.prev_key
        steps = max(0, window)
        while cur_prev and len(prev_lines) < steps:
            norm_prev = normalize_story_key(cur_prev)
            if norm_prev in visited:
                break
            visited.add(norm_prev)
            prev_loc = self._lookup(norm_prev)
            if prev_loc is None or prev_loc[0] != script_id:
                break
            prev_node = script.lines[prev_loc[1]]
            prev_lines.append(prev_node)
            cur_prev = prev_node.prev_key
        prev_lines.reverse()

        next_lines: list[DialogueLineNode] = []
        visited_next: set[str] = {line.key}
        cur_next = line.next_key
        ahead_steps = max(0, lookahead)
        while cur_next and len(next_lines) < ahead_steps:
            norm_next = normalize_story_key(cur_next)
            if norm_next in visited_next:
                break
            visited_next.add(norm_next)
            next_loc = self._lookup(norm_next)
            if next_loc is None or next_loc[0] != script_id:
                break
            next_node = script.lines[next_loc[1]]
            next_lines.append(next_node)
            cur_next = next_node.next_key

        return LineContext(
            script=script,
            line=line,
            prev_lines=prev_lines,
            next_lines=next_lines,
        )

    def to_json_file(self, path: str | Path, indent: int | None = 2) -> Path:
        """Serialize flowchart to a UTF-8 JSON file with ``ensure_ascii=False``."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.model_dump(mode="json"), ensure_ascii=False, indent=indent)
        target.write_text(payload, encoding="utf-8")
        return target

    @classmethod
    def from_json_file(cls, path: str | Path) -> Self:
        """Load a ``StoryFlowchart`` from a UTF-8 JSON file."""
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.model_validate(raw)


@dataclass
class _BranchSnapshot:
    on_stage: set[str]
    last_key: str | None
    branch_path: str
    speaker: str
    dialog_type: Literal["dialogue", "thought", "narrative"]
    moods: dict[str, str]
    pending_tails: list[str] = field(default_factory=list)


@dataclass
class _IfFrame:
    kind: Literal["if", "other"]
    snapshot: _BranchSnapshot
    branch_tails: list[tuple[set[str], str | None, bool]] = field(default_factory=list)
    has_else: bool = False
    active_segment: str = ""
    current_branch_terminal: bool = False


def _infer_line_type(
    raw_key: str,
    saydialog_type: Literal["dialogue", "thought", "narrative"],
) -> Literal["dialogue", "thought", "narrative", "option"]:
    bare = raw_key.removeprefix(STORY_KEY_PREFIX)
    if bare.startswith("T_"):
        return "thought"
    if bare.startswith("N_"):
        return "narrative"
    if bare.startswith("O_"):
        return "option"
    if bare.startswith("D_"):
        return "dialogue"
    return saydialog_type


def _saydialog_to_type(dialog_name: str) -> Literal["dialogue", "thought", "narrative"]:
    lowered = dialog_name.lower()
    if "think" in lowered or "thought" in lowered:
        return "thought"
    if "narrative" in lowered or "center" in lowered:
        return "narrative"
    return "dialogue"


def _join_branch_path(base_path: str, segment: str) -> str:
    clean_seg = segment.strip("/")
    if not clean_seg:
        return base_path
    if not base_path or base_path == "main":
        return clean_seg
    return f"{base_path}/{clean_seg}"


def _derive_branch_segment(
    cond_expr: str,
    var_sources: dict[str, str],
    choose_tables: dict[str, str],
    option_tables: dict[str, dict[int, str]],
) -> str:
    expr = cond_expr.strip()
    m_eq = _CHOICE_COND_RE.match(expr)
    if m_eq:
        var_name, idx_str = m_eq.group(1), m_eq.group(2)
        idx = int(idx_str)
        if var_name in choose_tables:
            table_name = choose_tables[var_name]
            opt_id = option_tables.get(table_name, {}).get(idx)
            if opt_id:
                return opt_id
            return f"choice:{idx}"
        if var_name in var_sources:
            return f"{var_sources[var_name]}#{idx}"
        return f"{var_name}=={idx}"

    if expr in var_sources:
        return var_sources[expr]

    compact = re.sub(r"[^A-Za-z0-9_.:=-]+", "_", expr).strip("_")
    return compact[:48] or "branch"


def _strip_lua_inline_comment(line: str) -> str:
    """Strip Lua ``-- ...`` comment outside quoted strings (preserving ``--index:`` separately)."""
    in_single = False
    in_double = False
    escaped = False
    i = 0
    while i < len(line):
        ch = line[i]
        if escaped:
            escaped = False
            i += 1
            continue
        if ch == "\\" and (in_single or in_double):
            escaped = True
            i += 1
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "-" and not in_single and not in_double and i + 1 < len(line) and line[i + 1] == "-":
            return line[:i].strip()
        i += 1
    return line.strip()


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def parse_lua_story_script(script_id: str, lua_text: str) -> ScriptNode:
    """Parse a Legend of Mortal Lua story script into a structured ``ScriptNode``."""
    on_stage: set[str] = set()
    char_moods: dict[str, str] = {}
    custom_names: dict[str, str] = {}
    current_dialog_type: Literal["dialogue", "thought", "narrative"] = "dialogue"
    current_speaker: str = "narrative"
    branch_path: str = "main"
    last_key_in_branch: str | None = None

    participants: list[str] = []
    relationship_deltas: list[RelationshipDelta] = []
    flag_deltas: list[tuple[str, int]] = []
    next_scripts: list[str] = []
    ending_ids: list[str] = []
    option_ids: list[str] = []
    lines: list[DialogueLineNode] = []
    line_by_key: dict[str, DialogueLineNode] = {}

    var_sources: dict[str, str] = {}
    choose_tables: dict[str, str] = {}
    option_tables: dict[str, dict[int, str]] = {}
    block_stack: list[_IfFrame] = []
    pending_tails: list[str] = []

    def make_snapshot() -> _BranchSnapshot:
        return _BranchSnapshot(
            on_stage=set(on_stage),
            last_key=last_key_in_branch,
            branch_path=branch_path,
            speaker=current_speaker,
            dialog_type=current_dialog_type,
            moods=dict(char_moods),
            pending_tails=list(pending_tails),
        )

    def restore_snapshot(snap: _BranchSnapshot) -> None:
        nonlocal on_stage, last_key_in_branch, branch_path, current_speaker
        nonlocal current_dialog_type, char_moods, pending_tails
        on_stage = set(snap.on_stage)
        last_key_in_branch = snap.last_key
        branch_path = snap.branch_path
        current_speaker = snap.speaker
        current_dialog_type = snap.dialog_type
        char_moods = dict(snap.moods)
        pending_tails = list(snap.pending_tails)

    for raw_line in lua_text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue

        # Track --index:O_... even though it is a Lua comment
        idx_match = _INDEX_OPTION_RE.search(stripped)
        if idx_match:
            opt_id = idx_match.group(1)
            _append_unique(option_ids, opt_id)
            if block_stack and block_stack[-1].kind == "if":
                frame = block_stack[-1]
                frame.active_segment = opt_id
                branch_path = _join_branch_path(frame.snapshot.branch_path, opt_id)

        code = _strip_lua_inline_comment(stripped)
        if not code:
            continue

        # Variable & option-table tracking
        if m_sw := _SWITCH_ASSIGN_RE.match(code):
            var_sources[m_sw.group(1)] = m_sw.group(2)
        elif m_cd := _COND_ASSIGN_RE.match(code):
            var_sources[m_cd.group(1)] = m_cd.group(2)
        elif m_ch := _CHOOSE_ASSIGN_RE.match(code):
            choose_tables[m_ch.group(1)] = m_ch.group(2)

        if m_opt := _OPTION_ASSIGN_RE.match(code):
            table_name, slot_idx, opt_id = m_opt.group(1), int(m_opt.group(2)), m_opt.group(3)
            option_tables.setdefault(table_name, {})[slot_idx] = opt_id
            _append_unique(option_ids, opt_id)

        for m_plus in _PLUS_OPTION_RE.finditer(code):
            _append_unique(option_ids, m_plus.group(1))

        # Control flow stack (if / elseif / else / end + non-if blocks)
        if m_if := _IF_RE.match(code):
            cond_expr, trailing = m_if.group(1), m_if.group(2).strip()
            # Single-line `if ... then ... end` does not open a persistent block
            if trailing.endswith("end") or re.search(r"\bend\s*$", trailing):
                pass
            else:
                snap = make_snapshot()
                seg = _derive_branch_segment(cond_expr, var_sources, choose_tables, option_tables)
                frame = _IfFrame(kind="if", snapshot=snap, active_segment=seg)
                block_stack.append(frame)
                branch_path = _join_branch_path(snap.branch_path, seg)
                continue

        if m_elif := _ELSEIF_RE.match(code):
            cond_expr = m_elif.group(1)
            for idx in range(len(block_stack) - 1, -1, -1):
                if block_stack[idx].kind == "if":
                    frame = block_stack[idx]
                    frame.branch_tails.append(
                        (set(on_stage), last_key_in_branch, frame.current_branch_terminal)
                    )
                    frame.current_branch_terminal = False
                    restore_snapshot(frame.snapshot)
                    seg = _derive_branch_segment(
                        cond_expr, var_sources, choose_tables, option_tables
                    )
                    frame.active_segment = seg
                    branch_path = _join_branch_path(frame.snapshot.branch_path, seg)
                    break
            continue

        if _ELSE_RE.match(code):
            for idx in range(len(block_stack) - 1, -1, -1):
                if block_stack[idx].kind == "if":
                    frame = block_stack[idx]
                    frame.branch_tails.append(
                        (set(on_stage), last_key_in_branch, frame.current_branch_terminal)
                    )
                    frame.current_branch_terminal = False
                    frame.has_else = True
                    restore_snapshot(frame.snapshot)
                    frame.active_segment = "else"
                    branch_path = _join_branch_path(frame.snapshot.branch_path, "else")
                    break
            continue

        if _OTHER_BLOCK_RE.match(code) and not re.search(r"\bend\s*$", code):
            block_stack.append(_IfFrame(kind="other", snapshot=make_snapshot()))
            continue

        if _END_RE.match(code):
            if block_stack:
                frame = block_stack.pop()
                if frame.kind == "if":
                    frame.branch_tails.append(
                        (set(on_stage), last_key_in_branch, frame.current_branch_terminal)
                    )
                    branch_path = frame.snapshot.branch_path

                    non_terminal = [t for t in frame.branch_tails if not t[2]]
                    active_tails = non_terminal if non_terminal else frame.branch_tails
                    merged_stage: set[str] = set()
                    for b_stage, _, _ in active_tails:
                        merged_stage |= b_stage
                    if not frame.has_else and len(active_tails) == 1:
                        # Single `if ... then ... end` without `else`: keep pre-if characters
                        # unless explicitly hidden? Actually merged_stage already tracks hide/show.
                        pass
                    on_stage = merged_stage

                    tail_keys = [k for _, k, _ in active_tails if k is not None]
                    last_key_in_branch = tail_keys[-1] if tail_keys else frame.snapshot.last_key
                    pending_tails = [
                        k for _, k, is_term in active_tails if not is_term and k is not None
                    ]
            continue

        # Stage & portrait commands
        for m_show in _STAGE_SHOW_RE.finditer(code):
            cid = m_show.group(1)
            on_stage.add(cid)
            _append_unique(participants, cid)

        for m_hide in _STAGE_HIDE_RE.finditer(code):
            cid = m_hide.group(1)
            on_stage.discard(cid)

        for m_port in _PORTRAIT_RE.finditer(code):
            cid, mood = m_port.group(1), m_port.group(2)
            char_moods[cid] = mood

        for m_cname in _CUSTOM_NAME_RE.finditer(code):
            custom_names[m_cname.group(1)] = m_cname.group(2)

        if m_dlg := _SAY_DIALOG_RE.search(code):
            current_dialog_type = _saydialog_to_type(m_dlg.group(1))
            if current_dialog_type == "narrative":
                current_speaker = "narrative"

        if m_setchar := _SET_CHAR_GET_RE.search(code):
            current_speaker = m_setchar.group(1)
            _append_unique(participants, current_speaker)
        elif _SET_CHAR_NARRATIVE_RE.search(code):
            current_speaker = "narrative"

        # Side effects: relationship deltas, flags, next scripts, endings
        for m_rel in _STAT_CHAR_RE.finditer(code):
            cid = m_rel.group(1)
            delta = int(m_rel.group(2))
            stat_type = int(m_rel.group(3))
            _append_unique(participants, cid)
            relationship_deltas.append(
                RelationshipDelta(
                    char_id=cid,
                    stat_type=stat_type,
                    delta=delta,
                    at_line_index=len(lines),
                )
            )

        for m_flag in _STAT_FLAG_RE.finditer(code):
            flag_deltas.append((m_flag.group(1), int(m_flag.group(2))))

        for m_next in _NEXT_SCRIPT_RE.finditer(code):
            _append_unique(next_scripts, m_next.group(1))
            if block_stack and block_stack[-1].kind == "if":
                block_stack[-1].current_branch_terminal = True

        for m_end in _ENDGAME_RE.finditer(code):
            _append_unique(ending_ids, m_end.group(1))
            if block_stack and block_stack[-1].kind == "if":
                block_stack[-1].current_branch_terminal = True

        # Dialogue emission
        if m_say := _SAY_KEY_RE.search(code):
            raw_key = m_say.group(1)
            norm_key = normalize_story_key(raw_key)
            line_type = _infer_line_type(raw_key, current_dialog_type)
            speaker_id = current_speaker or "narrative"
            if line_type == "narrative" and not _SET_CHAR_GET_RE.search(code):
                if current_dialog_type == "narrative" or speaker_id == "":
                    speaker_id = "narrative"

            if speaker_id != "narrative":
                _append_unique(participants, speaker_id)

            listeners = sorted(cid for cid in on_stage if cid != speaker_id)
            mood = char_moods.get(speaker_id, "normal")
            custom_name = custom_names.get(speaker_id)

            node = DialogueLineNode(
                key=norm_key,
                line_type=line_type,
                speaker_id=speaker_id,
                speaker_custom_name=custom_name,
                portrait_mood=mood,
                listeners_on_stage=listeners,
                branch_path=branch_path,
                prev_key=last_key_in_branch,
                next_key=None,
            )

            if last_key_in_branch and last_key_in_branch in line_by_key:
                prev_node = line_by_key[last_key_in_branch]
                if prev_node.next_key is None:
                    prev_node.next_key = norm_key
            for tail_key in pending_tails:
                if tail_key in line_by_key and line_by_key[tail_key].next_key is None:
                    line_by_key[tail_key].next_key = norm_key
            pending_tails.clear()

            lines.append(node)
            line_by_key[norm_key] = node
            last_key_in_branch = norm_key

    return ScriptNode(
        script_id=script_id,
        participants=participants,
        relationship_deltas=relationship_deltas,
        flag_deltas=flag_deltas,
        next_scripts=next_scripts,
        ending_ids=ending_ids,
        option_ids=option_ids,
        lines=lines,
    )


# ---------------------------------------------------------------------------
# Self-contained Unity v22 SerializedFile reader for Mortal_Data extraction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _UnityObjectEntry:
    path_id: int
    abs_start: int
    byte_size: int
    type_id: int
    class_id: int


def _scan_unity_v22_objects(asset_path: Path) -> tuple[bytes, list[_UnityObjectEntry]]:
    """Parse a Unity 2020.3 SerializedFile v22 header and ObjectInfo table."""
    raw = asset_path.read_bytes()
    if len(raw) < 48:
        raise ValueError(f"File too small to be a Unity SerializedFile: {asset_path}")

    _meta_size, _file_size, data_offset, _unknown = struct.unpack_from(">IQQQ", raw, 20)
    pos = raw.index(0, 48) + 1
    _platform, _has_type_tree, type_count = struct.unpack_from("<iBi", raw, pos)
    pos += 9

    type_class_ids: list[int] = []
    for _ in range(type_count):
        class_id, _is_stripped, _script_idx = struct.unpack_from("<iBh", raw, pos)
        pos += 7
        if class_id == 114 or class_id < 0:
            pos += 16
        pos += 16
        type_class_ids.append(class_id)

    obj_count = struct.unpack_from("<i", raw, pos)[0]
    pos += 4
    table_pos = (pos + 3) & ~3

    objects: list[_UnityObjectEntry] = []
    for i in range(obj_count):
        path_id, byte_start, byte_size, type_id = struct.unpack_from(
            "<qQII", raw, table_pos + i * 24
        )
        class_id = type_class_ids[type_id] if 0 <= type_id < len(type_class_ids) else -1
        objects.append(
            _UnityObjectEntry(
                path_id=path_id,
                abs_start=data_offset + byte_start,
                byte_size=byte_size,
                type_id=type_id,
                class_id=class_id,
            )
        )
    return raw, objects


def _read_aligned_utf8(buf: bytes, offset: int) -> tuple[str, int]:
    if offset + 4 > len(buf):
        raise ValueError("Out of bounds reading aligned string length")
    str_len = struct.unpack_from("<I", buf, offset)[0]
    offset += 4
    if offset + str_len > len(buf):
        raise ValueError("Out of bounds reading aligned string payload")
    text = buf[offset : offset + str_len].decode("utf-8", errors="replace")
    offset += (str_len + 3) & ~3
    return text, offset


def _extract_lean_csv_chinese_simplified(level_path: Path) -> dict[str, str]:
    """Extract all ChineseSimplified ``LeanLanguageCSV`` key/value pairs from a level asset."""
    if not level_path.is_file():
        return {}
    raw, objects = _scan_unity_v22_objects(level_path)
    expected_lang_prefix = struct.pack("<I", len("ChineseSimplified")) + b"ChineseSimplified\x00\x00\x00"
    results: dict[str, str] = {}

    for obj in objects:
        if obj.class_id != 114:
            continue
        obj_bytes = raw[obj.abs_start : obj.abs_start + obj.byte_size]
        sig_pos = obj_bytes.find(LEAN_CSV_SIG)
        if sig_pos < len(expected_lang_prefix):
            continue
        if obj_bytes[sig_pos - len(expected_lang_prefix) : sig_pos] != expected_lang_prefix:
            continue

        off = sig_pos + len(LEAN_CSV_SIG)
        if off + 4 > len(obj_bytes):
            continue
        entry_count = struct.unpack_from("<I", obj_bytes, off)[0]
        off += 4
        for _ in range(entry_count):
            key, off = _read_aligned_utf8(obj_bytes, off)
            val, off = _read_aligned_utf8(obj_bytes, off)
            if key:
                results[key] = val
    return results


def _extract_checkpoint_titles(ggm_assets_path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Extract checkpoint titles from ``globalgamemanagers.assets``.

    Returns:
        ``(by_entry_script, by_checkpoint_id)`` mapping IDs to Traditional/Chinese titles.
    """
    if not ggm_assets_path.is_file():
        return {}, {}

    raw, objects = _scan_unity_v22_objects(ggm_assets_path)
    by_entry_script: dict[str, str] = {}
    by_checkpoint_id: dict[str, str] = {}

    for obj in objects:
        if obj.class_id != 114 or obj.byte_size < 44 or obj.byte_size > 1024:
            continue
        buf = raw[obj.abs_start : obj.abs_start + obj.byte_size]
        try:
            m_name, off = _read_aligned_utf8(buf, 28)
            if not _CHECKPOINT_ID_RE.match(m_name):
                continue
            cp_id, off = _read_aligned_utf8(buf, off)
            if cp_id != m_name:
                continue
            cp_title, off = _read_aligned_utf8(buf, off)
            _extra, off = _read_aligned_utf8(buf, off)
            entry_script = ""
            if off + 4 <= len(buf):
                entry_script, _ = _read_aligned_utf8(buf, off)
        except ValueError:
            continue

        clean_title = cp_title.strip()
        if not clean_title:
            continue
        by_checkpoint_id[cp_id] = clean_title
        if entry_script:
            by_entry_script[entry_script] = clean_title

    return by_entry_script, by_checkpoint_id


def _infer_gender_from_info(char_id: str, zh_name: str, zh_title: str) -> str:
    if char_id in CURATED_CHARACTERS:
        return CURATED_CHARACTERS[char_id]["gender"]
    if char_id.startswith(("girl", "sister", "trainee_girl", "big_trainee_girl", "aunt", "showgirl")):
        return "female"
    if char_id.startswith(("brother", "boy", "master")):
        return "male"
    if any(tok in zh_title for tok in ("仙子", "姑娘", "小姐", "女侠", "师妹", "千金")):
        return "female"
    if any(tok in zh_name for tok in ("女", "娘", "姑", "妹", "夫人", "仙")):
        return "female"
    return ""


def _resolve_curated_base(char_id: str, zh_name: str) -> dict[str, str] | None:
    if char_id in CURATED_CHARACTERS:
        return CURATED_CHARACTERS[char_id]
    if zh_name in ("？？？", "???", "蒙面人", "少女", "玄衣少年", "斗笠人", "商人", ""):
        return None
    base_id = char_id.split("_", 1)[0]
    if base_id in CURATED_CHARACTERS and base_id not in ("player", "narrative"):
        return CURATED_CHARACTERS[base_id]
    if char_id.startswith("player_"):
        return CURATED_CHARACTERS["player"]
    return None


def _build_characters_catalog(
    level0_strings: dict[str, str],
    fungus_raw: str | None,
) -> dict[str, CharacterInfo]:
    characters: dict[str, CharacterInfo] = {}

    def ensure_char(char_id: str) -> CharacterInfo:
        if char_id not in characters:
            characters[char_id] = CharacterInfo(char_id=char_id, zh_name="")
        return characters[char_id]

    for key, val in level0_strings.items():
        if key.startswith("Character/"):
            cid = key.removeprefix("Character/")
            info = ensure_char(cid)
            if val:
                info.zh_name = val
        elif key.startswith("CharacterTitle/"):
            cid = key.removeprefix("CharacterTitle/")
            info = ensure_char(cid)
            if val and not info.zh_title:
                info.zh_title = val
        elif key.startswith("CombatCharacter/Name/"):
            cid = key.removeprefix("CombatCharacter/Name/")
            info = ensure_char(cid)
            if val and not info.zh_name:
                info.zh_name = val
        elif key.startswith("CombatCharacter/Title/"):
            cid = key.removeprefix("CombatCharacter/Title/")
            info = ensure_char(cid)
            if val and not info.zh_title:
                info.zh_title = val
        elif key.startswith("CharacterIntro0/"):
            cid = key.removeprefix("CharacterIntro0/")
            info = ensure_char(cid)
            if val and not info.traits:
                info.traits = val.replace("\r\n", " ").replace("\n", " ").strip()

    if fungus_raw:
        # Relaxed JSON parse (source asset contains a trailing comma before closing brace)
        cleaned = re.sub(r",\s*([}\]])", r"\1", fungus_raw)
        try:
            fungus_data = json.loads(cleaned)
        except json.JSONDecodeError:
            fungus_data = {}
        if isinstance(fungus_data, dict):
            for raw_key, payload in fungus_data.items():
                if not isinstance(payload, dict):
                    continue
                base_id = raw_key.removesuffix("_name")
                zh_val = str(payload.get("ChineseTraditional") or "").strip()
                if not zh_val:
                    continue
                parts = [p.strip() for p in zh_val.split(",") if p.strip()]
                target_ids = [base_id]
                if base_id == "sister" and "sister1" in characters:
                    target_ids.append("sister1")
                for tid in target_ids:
                    info = ensure_char(tid)
                    for alias in parts:
                        if alias not in info.aliases and alias != info.zh_name and alias != info.zh_title:
                            info.aliases.append(alias)
                    if not info.zh_name and parts:
                        info.zh_name = parts[0]
                    if len(parts) > 1 and not info.zh_title:
                        info.zh_title = parts[1]

    # Always seed curated core characters (e.g., narrative, sister, etc.)
    for cid, curated in CURATED_CHARACTERS.items():
        info = ensure_char(cid)
        if not info.vi_name:
            info.vi_name = curated["vi_name"]
        if not info.gender:
            info.gender = curated["gender"]
        if not info.traits:
            info.traits = curated["traits"]

    for cid, info in characters.items():
        curated = _resolve_curated_base(cid, info.zh_name)
        if curated:
            if not info.vi_name:
                info.vi_name = curated["vi_name"]
            if not info.gender:
                info.gender = curated["gender"]
            if not info.traits:
                info.traits = curated["traits"]
        if not info.gender:
            info.gender = _infer_gender_from_info(cid, info.zh_name, info.zh_title)

    return characters


def extract_story_flowchart_from_mortal_data(mortal_data_dir: str | Path) -> StoryFlowchart:
    """Extract the complete story flowchart and character catalog from ``Mortal_Data``."""
    data_dir = Path(mortal_data_dir)
    resources_path = data_dir / "resources.assets"
    if not resources_path.is_file():
        raise FileNotFoundError(f"resources.assets not found in {data_dir}")

    res_raw, res_objects = _scan_unity_v22_objects(resources_path)

    raw_scripts: dict[str, str] = {}
    fungus_character_raw: str | None = None

    for obj in res_objects:
        if obj.class_id != 49:
            continue
        obj_bytes = res_raw[obj.abs_start : obj.abs_start + obj.byte_size]
        try:
            asset_name, off = _read_aligned_utf8(obj_bytes, 0)
            script_text, _ = _read_aligned_utf8(obj_bytes, off)
        except ValueError:
            continue

        if asset_name == "fungus_character_name":
            fungus_character_raw = script_text
            continue

        if not any(marker in script_text for marker in _STORY_SCRIPT_MARKERS):
            continue

        # Multiple TextAssets can share a name (older unlocalized vs localized with GetStoryText);
        # always prefer the localized script containing luamanager.GetStoryText.
        existing = raw_scripts.get(asset_name)
        if existing is None or (
            "luamanager.GetStoryText" in script_text
            and "luamanager.GetStoryText" not in existing
        ):
            raw_scripts[asset_name] = script_text

    level0_strings = _extract_lean_csv_chinese_simplified(data_dir / "level0")
    characters = _build_characters_catalog(level0_strings, fungus_character_raw)

    by_entry_script, by_checkpoint_id = _extract_checkpoint_titles(
        data_dir / "globalgamemanagers.assets"
    )

    scripts: dict[str, ScriptNode] = {}
    for script_id in sorted(raw_scripts):
        node = parse_lua_story_script(script_id, raw_scripts[script_id])
        title_zh = by_entry_script.get(script_id, "")
        if not title_zh and "_" in script_id:
            prefix = script_id.split("_", 1)[0]
            if prefix in by_checkpoint_id:
                title_zh = by_checkpoint_id[prefix]
        if title_zh:
            node.title_zh = title_zh

        for cid in node.participants:
            if cid not in characters:
                characters[cid] = CharacterInfo(
                    char_id=cid,
                    zh_name="",
                    gender=_infer_gender_from_info(cid, "", ""),
                )
        scripts[script_id] = node

    return StoryFlowchart(characters=characters, scripts=scripts)
