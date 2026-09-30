"""场桥调度接口：维护场桥，覆盖分配作业、释放场桥、登记检修等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.rtg import RtgService

router = APIRouter(prefix="/api/rtg", tags=["场桥调度"])

service = RtgService()

LIST_FIELDS = ["场桥编号", "场桥型号", "作业箱区", "跨距参数", "起升高度", "作业司机", "柴油油量", "场桥状态"]
STATUSES = ["在场", "空闲", "作业中", "检修中", "停用"]
YARD_BLOCK_ALIASES = ("yard_block", "yardBlock", "block", "zone", "yard", "work_block", "workBlock", "operation_block", "operationBlock", "作业箱区")
SORT_ALIASES = ("sort_by", "sortBy", "sort_field", "sortField", "sort", "排列字段", "排列方式")
ORDER_ALIASES = ("sort_order", "sortOrder", "order", "order_by", "orderBy", "排列顺序")


def _first_param(request: Request, names: tuple[str, ...]) -> str | None:
    """兼容全角中文参数名与不同前端命名；同名重复参数只取第一份。"""
    for name in names:
        value = request.query_params.get(name)
        if value and value.strip():
            return value.strip()
    return None


def _list_filters(request: Request) -> dict[str, str | None]:
    return {
        "keyword": _first_param(request, ("keyword", "场桥编号")),
        "yard_block": _first_param(request, YARD_BLOCK_ALIASES),
        "status": _first_param(request, ("status", "state", "状态", "场桥状态")),
    }


@router.get("", response_model=PageResult[dict])
def list_entries(
    request: Request,
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按作业箱区与状态过滤场桥调度列表；没有数据时返回空页，不报错。"""
    if size < 1:
        raise HTTPException(status_code=400, detail="每页至少 1 条，请调整分页范围")
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    filters = _list_filters(request)
    items, total = service.list_entries(
        keyword=filters["keyword"],
        yard_block=filters["yard_block"],
        status=filters["status"],
        sort_by=_first_param(request, SORT_ALIASES),
        sort_order=_first_param(request, ORDER_ALIASES),
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/report")
def report_entries(request: Request) -> dict[str, Any]:
    """报表台数与列表使用同一套筛选口径，避免两处数字对不上。"""
    filters = _list_filters(request)
    return service.report(
        keyword=filters["keyword"],
        yard_block=filters["yard_block"],
        status=filters["status"],
    )


@router.get("/export")
def export_entries(request: Request) -> dict[str, Any]:
    """导出场桥调度清单：返回当前过滤条件下的全量数据。"""
    filters = _list_filters(request)
    items, total = service.list_entries(
        keyword=filters["keyword"],
        yard_block=filters["yard_block"],
        status=filters["status"],
        sort_by=_first_param(request, SORT_ALIASES),
        sort_order=_first_param(request, ORDER_ALIASES),
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
