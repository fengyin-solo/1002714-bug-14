"""场桥调度接口：维护场桥，覆盖分配作业、释放场桥、登记检修等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.rtg import RtgService, STATUS_ORDER

router = APIRouter(prefix="/api/rtg", tags=["场桥调度"])

service = RtgService()

LIST_FIELDS = ["场桥编号", "场桥型号", "作业箱区", "跨距参数", "起升高度", "作业司机", "柴油油量", "场桥状态"]
STATUSES = STATUS_ORDER


@router.get("", response_model=PageResult[dict])
def list_entries(
    block: str | None = Query(default=None, description="按作业箱区检索，全角半角写法自动归一"),
    keyword: str | None = Query(default=None, description="按场桥编号检索，全角半角写法自动归一"),
    status: str | None = Query(default=None, description="空闲、作业中、检修中、停用"),
    sort_by: str = Query(default="场桥编号", description="排列列：场桥编号/作业司机/跨距参数"),
    sort_order: str = Query(default="asc", description="排列方向：asc/desc"),
    on_site: bool = Query(default=True, description="是否只看在场场桥，停用的不在场"),
    page: int = 1,
    size: int = 5,
) -> PageResult[dict]:
    """按作业箱区、场桥编号与状态过滤；全角半角两种写法都能命中。

    排列方式只决定顺序、不改变已选条件圈定的集合；空跨距记录不会因翻页丢失。
    """
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"状态「{status}」不支持，请选择：{'、'.join(STATUS_ORDER)}")
    if sort_order not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail="排列方向仅支持 asc 或 desc")
    items, total = service.list_entries(
        keyword=keyword,
        block=block,
        status=status,
        on_site=on_site,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        size=size,
    )
    # 台数卡片与当前条件下的列表同源，报表数字对得上。
    filtered = service._filtered_rows(keyword=keyword, block=block, status=status, on_site=on_site)
    stats = service.status_stats(filtered)
    return PageResult(items=items, total=total, page=page, size=size, stats=stats)


@router.get("/export")
def export_entries(
    block: str | None = None,
    keyword: str | None = None,
    status: str | None = None,
    on_site: bool = True,
) -> dict[str, Any]:
    """导出场桥调度清单：口径与列表页一致（默认仅在场场桥，含相同箱区/编号/状态条件）。"""
    items, total = service.list_entries(
        block=block,
        keyword=keyword,
        status=status,
        on_site=on_site,
        page=1,
        size=10000,
    )
    return {"module": "rtg", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条场桥明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"场桥 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条场桥，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="场桥已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条场桥执行分配作业、释放场桥、登记检修；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
