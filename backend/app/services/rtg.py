"""场桥调度业务规则：状态流转、字段校验、筛选口径与排列方式都收在这里。"""
from __future__ import annotations

import unicodedata
from typing import Any

from app.store import store

MODULE = "rtg"
REQUIRED_FIELDS = ["场桥编号", "场桥型号", "作业箱区"]
STATUS_ORDER = ["空闲", "作业中", "检修中", "停用"]
ACTION_RULES = {"分配作业": "作业中", "释放场桥": "空闲", "登记检修": "检修中"}
NEGATIVE_ACTIONS = []

# 停用即不在场：箱区查询默认只列在场场桥。
OFFSITE_STATUS = "停用"
# 允许的排列列：跨距按数值比较，其余按文本；空跨距永远排在末尾，避免翻页时找不到。
SORT_COLUMNS = {"场桥编号": "text", "作业司机": "text", "跨距参数": "number"}
DEFAULT_SORT = "场桥编号"


def normalize_text(value: Any) -> str:
    """全角半角归一：Ａ区与 A区、ＲＴＧ 与 RTG 视为同一写法。"""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    return "".join(text.split()).casefold()


def _span_value(row: dict[str, Any]) -> float | None:
    """跨距参数转数值；空串、None、无法解析都视为未填，而不是丢弃记录。"""
    raw = row.get("跨距参数")
    if raw is None or not str(raw).strip():
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


class RtgService:
    def _filtered_rows(
        self,
        *,
        keyword: str | None = None,
        block: str | None = None,
        status: str | None = None,
        on_site: bool = True,
    ) -> list[dict[str, Any]]:
        """已选条件优先：先按条件筛出集合，排列方式只决定顺序，不能改变集合。"""
        rows = store.rows(MODULE)
        if on_site:
            rows = [row for row in rows if row.get("status") != OFFSITE_STATUS]
        if block and normalize_text(block):
            needle = normalize_text(block)
            rows = [row for row in rows if needle in normalize_text(row.get("作业箱区"))]
        if keyword and normalize_text(keyword):
            needle = normalize_text(keyword)
            rows = [row for row in rows if needle in normalize_text(row.get("场桥编号"))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return rows

    def _sort_rows(
        self,
        rows: list[dict[str, Any]],
        sort_by: str | None,
        sort_order: str = "asc",
    ) -> list[dict[str, Any]]:
        """稳定排列：非法排列列回退默认；空跨距始终排末尾，翻页顺序保持一致。"""
        column = sort_by if sort_by in SORT_COLUMNS else DEFAULT_SORT
        descending = sort_order == "desc"

        if SORT_COLUMNS[column] == "number":
            def key(row: dict[str, Any]) -> tuple[int, float, int]:
                span = _span_value(row)
                # 第二段 0/1：有值在前、空值在后，正序倒序都不改变空值“垫底”的位置。
                if span is None:
                    return (1, 0.0, int(row.get("id", 0)))
                value = -span if descending else span
                return (0, value, int(row.get("id", 0)))

            return sorted(rows, key=key)

        def text_key(row: dict[str, Any]) -> tuple[int, str, int]:
            value = str(row.get(column) or "")
            return (0 if value.strip() else 1, normalize_text(value), int(row.get("id", 0)))

        return sorted(rows, key=text_key, reverse=descending)

    def status_stats(self, rows: list[dict[str, Any]] | None = None) -> dict[str, int]:
        """场桥台数按状态汇总；默认（在场口径）排除停用，台数与列表同源。"""
        if rows is None:
            rows = self._filtered_rows(on_site=True)
        return {name: sum(1 for row in rows if row.get("status") == name) for name in STATUS_ORDER}

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        block: str | None = None,
        status: str | None = None,
        on_site: bool = True,
        sort_by: str | None = DEFAULT_SORT,
        sort_order: str = "asc",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._filtered_rows(keyword=keyword, block=block, status=status, on_site=on_site)
        rows = self._sort_rows(rows, sort_by, sort_order)
        total = len(rows)
        page = max(page, 1)
        start = (page - 1) * size
        return rows[start:start + size], total

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
        # 列表“场桥状态”列与内部状态保持同一口径，列表页与详情页看到的状态才会一致。
        entry["场桥状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"场桥已{action}"
