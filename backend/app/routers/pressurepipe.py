"""压力管道接口：维护压力管道，覆盖办理投用、安排检修、停用管道等动作，
并提供按模板成批导入、断点续传与按当前条件导出清单的数据交换能力。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.schemas import ActionResult, EntryPayload, ImportPayload, PageResult
from app.services.pressurepipe import PressurepipeService

router = APIRouter(prefix="/api/pressurepipe", tags=["压力管道"])

service = PressurepipeService()

LIST_FIELDS = ["管道编号", "管道名称", "管道级别", "公称直径", "输送介质", "敷设方式", "下次检验日", "管道状态"]
STATUSES = ["待投用", "在用运行", "隔离检修", "已停用"]

CSV_MEDIA_TYPE = "text/csv; charset=utf-8"


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按管道编号检索"),
    status: str | None = Query(default=None, description="待投用、在用运行、隔离检修、已停用"),
    管道编号: str | None = Query(default=None, description="按管道编号检索"),
    管道名称: str | None = Query(default=None, description="按管道名称检索"),
    管道级别: str | None = Query(default=None, description="按管道级别过滤"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按管道编号、名称、级别与状态过滤压力管道列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword or 管道编号,
        status=status,
        name=管道名称,
        level=管道级别,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/template")
def download_template() -> Response:
    """下载批量导入模板：CSV 表头为管道编号、管道级别、输送介质、下次检验日。"""
    content = service.import_template()
    return Response(
        content="\ufeff" + content,
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=pressurepipe-template.csv"},
    )


@router.post("/import")
def import_entries(payload: ImportPayload) -> dict:
    """按模板成批导入：逐行校验、逐行入账，格式不合法或编号重复的行单独报出并跳过。

    同一份数据重复提交会命中同一批次断点续做，已入账的行不会重复写入。
    """
    return service.import_entries(payload.content, payload.filename)


@router.post("/import/{batch_id}/resume")
def resume_import(batch_id: str) -> dict:
    """从失败行继续导入：已入账的行不丢，未处理的行接着走。"""
    result = service.resume_import(batch_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"导入批次 {batch_id} 不存在或已过期，请重新上传模板")
    return result


@router.get("/import/{batch_id}")
def import_status(batch_id: str) -> dict:
    """查询导入批次的当前进度与逐行结果。"""
    result = service.import_status(batch_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"导入批次 {batch_id} 不存在或已过期")
    return result


@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="按管道编号检索"),
    status: str | None = Query(default=None, description="待投用、在用运行、隔离检修、已停用"),
    管道编号: str | None = Query(default=None, description="按管道编号检索"),
    管道名称: str | None = Query(default=None, description="按管道名称检索"),
    管道级别: str | None = Query(default=None, description="按管道级别过滤"),
) -> Response:
    """导出压力管道清单：与列表当前过滤条件下的结果一致，返回 CSV 文件。"""
    content = service.export_entries(
        keyword=keyword or 管道编号,
        status=status,
        name=管道名称,
        level=管道级别,
    )
    return Response(
        content="\ufeff" + content,
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=pressurepipe-list.csv"},
    )


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条压力管道明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"压力管道 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条压力管道，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="压力管道已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条压力管道执行办理投用、安排检修、停用管道；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
