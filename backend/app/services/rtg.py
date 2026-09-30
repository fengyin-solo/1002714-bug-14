"""场桥调度业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.store import store

MODULE = "rtg"
REQUIRED_FIELDS = ["场桥编号", "场桥型号", "作业箱区"]
STATUS_ORDER = ["空闲", "作业中", "检修中", "停用"]
ON_SITE_STATUS = "在场"
ON_SITE_ALIASES = {ON_SITE_STATUS, "onsite", "onsiteyard", "yard"}
ACTION_RULES = {"分配作业": "作业中", "释放场桥": "空闲", "登记检修": "检修中"}
NEGATIVE_ACTIONS = []

SORT_FIELDS: dict[str, str] = {
    "id": "id",
    "rtgid": "id",
    "编号": "id",
    "craneid": "场桥编号",
    "cranenumber": "场桥编号",
    "场桥编号": "场桥编号",
    "model": "场桥型号",
    "场桥型号": "场桥型号",
    "yardblock": "作业箱区",
    "yard": "作业箱区",
    "block": "作业箱区",
    "zone": "作业箱区",
    "workblock": "作业箱区",
    "operationblock": "作业箱区",
    "作业箱区": "作业箱区",
    "span": "跨距参数",
    "spanparameter": "跨距参数",
    "跨距参数": "跨距参数",
    "liftheight": "起升高度",
    "height": "起升高度",
    "起升高度": "起升高度",
    "driver": "作业司机",
    "operator": "作业司机",
    "作业司机": "作业司机",
    "fuel": "柴油油量",
    "diesel": "柴油油量",
    "柴油油量": "柴油油量",
    "status": "场桥状态",
    "state": "场桥状态",
    "场桥状态": "场桥状态",
}
DESCENDING_VALUES = {"desc", "descending", "降序", "倒序"}
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def normalize_text(value: Any) -> str:
    """统一全角/半角、大小写和空白，保证同箱区两种写法能按同一口径匹配。"""
    text = unicodedata.normalize("NFKC", str(value or ""))
    return "".join(text.split()).casefold()


def _is_blank(value: Any) -> bool:
    return value is None or not str(value).strip()


def resolve_sort_field(value: str | None) -> str:
    key = normalize_text(value).replace("_", "").replace("-", "")
    return SORT_FIELDS.get(key, "id")


def resolve_sort_order(value: str | None) -> str:
    key = normalize_text(value).replace("_", "").replace("-", "")
    return "desc" if key in DESCENDING_VALUES else "asc"


def _status_matches(row: dict[str, Any], status: str) -> bool:
    expected = normalize_text(status)
    actual = normalize_text(row.get("status"))
    if expected in ON_SITE_ALIASES:
        return actual != normalize_text("停用")
    return actual == expected


def _filtered_rows(
    rows: list[dict[str, Any]],
    *,
    keyword: str | None = None,
    yard_block: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    result = rows
    if keyword and keyword.strip():
        expected_keyword = normalize_text(keyword)
        result = [
            row for row in result
            if expected_keyword in normalize_text(row.get("场桥编号", ""))
        ]
    if yard_block and yard_block.strip():
        expected_block = normalize_text(yard_block)
        result = [
            row for row in result
            if normalize_text(row.get("作业箱区", "")) == expected_block
        ]
    if status and status.strip():
        result = [row for row in result if _status_matches(row, status)]
    return result


def _comparable(value: Any) -> tuple[int, float, str]:
    if _is_blank(value):
        return (2, 0.0, "")
    text = str(value).strip()
    match = _NUMBER_RE.search(text)
    if match:
        return (0, float(match.group()), normalize_text(text))
    return (1, 0.0, normalize_text(text))


def _sort_rows(
    rows: list[dict[str, Any]],
    *,
    sort_by: str | None = None,
    sort_order: str | None = None,
) -> list[dict[str, Any]]:
    field = resolve_sort_field(sort_by)
    descending = resolve_sort_order(sort_order) == "desc"

    def key(row: dict[str, Any]) -> tuple[int, float, str, int]:
        value = row.get("id") if field == "id" else row.get(field)
        group, number, text = _comparable(value)
        return (group, number, text, int(row.get("id", 0)))

    non_blank = [row for row in rows if not _is_blank(row.get("id") if field == "id" else row.get(field))]
    blank = [row for row in rows if _is_blank(row.get("id") if field == "id" else row.get(field))]
    non_blank = sorted(non_blank, key=key, reverse=descending)
    blank = sorted(blank, key=lambda row: int(row.get("id", 0)), reverse=descending)
    return non_blank + blank


class RtgService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        yard_block: str | None = None,
        status: str | None = None,
        sort_by: str | None = None,
        sort_order: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        page = max(page, 1)
        size = max(size, 1)
        rows = _filtered_rows(
            store.rows(MODULE),
            keyword=keyword,
            yard_block=yard_block,
            status=status,
        )
        rows = _sort_rows(rows, sort_by=sort_by, sort_order=sort_order)
        total = len(rows)
        start = (page - 1) * size
        return rows[start:start + size], total

    def report(
        self,
        *,
        keyword: str | None = None,
        yard_block: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        rows = _filtered_rows(
            store.rows(MODULE),
            keyword=keyword,
            yard_block=yard_block,
            status=status,
        )
        status_counts = {name: 0 for name in STATUS_ORDER}
        for row in rows:
            name = str(row.get("status") or "")
            if name in status_counts:
                status_counts[name] += 1
        return {
            "total": len(rows),
            "on_site_total": sum(1 for row in rows if row.get("status") != "停用"),
            "empty_span_total": sum(1 for row in rows if _is_blank(row.get("跨距参数"))),
            "status_counts": status_counts,
        }

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"场桥 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于场桥调度可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["场桥状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"场桥已{action}"
