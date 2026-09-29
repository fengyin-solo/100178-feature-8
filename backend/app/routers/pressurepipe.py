"""压力管道接口：维护压力管道，覆盖办理投用、安排检修、停用管道等动作。"""
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.schemas import ActionResult, EntryPayload, ImportPayload, ImportResult, PageResult
from app.services.pressurepipe import LIST_FIELDS, OPTIONAL_COLUMNS, TEMPLATE_COLUMNS
from app.services.pressurepipe import PressurepipeService

router = APIRouter(prefix="/api/pressurepipe", tags=["压力管道"])

service = PressurepipeService()

STATUSES = ["待投用", "在用运行", "隔离检修", "已停用"]
CSV_MEDIA_TYPE = "text/csv; charset=utf-8"


def _csv_response(filename: str, header: list[str], rows: list[dict[str, Any]]) -> Response:
    """生成带 BOM 的 CSV：Excel 直接打开不乱码，文件内容与接口数据一一对应。"""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=header, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return Response(
        content="﻿" + buffer.getvalue(),
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按管道编号检索"),
    status: str | None = Query(default=None, description="待投用、在用运行、隔离检修、已停用"),
    level: str | None = Query(default=None, description="按管道级别检索"),
    medium: str | None = Query(default=None, description="按输送介质检索"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按管道编号、级别、介质与状态过滤压力管道列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword, status=status, level=level, medium=medium, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/template")
def download_template() -> Response:
    """下载批量录入模板：含必填列与选填列表头，另存后可直接填写再导入。"""
    return _csv_response(
        "pressurepipe-template.csv",
        TEMPLATE_COLUMNS + OPTIONAL_COLUMNS,
        [],
    )


@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="按管道编号检索"),
    status: str | None = Query(default=None, description="待投用、在用运行、隔离检修、已停用"),
    level: str | None = Query(default=None, description="按管道级别检索"),
    medium: str | None = Query(default=None, description="按输送介质检索"),
) -> Response:
    """另存压力管道清单：沿用列表当前过滤条件，全量不分页，文件结果与列表一致。"""
    items = service.export_rows(keyword=keyword, status=status, level=level, medium=medium)
    return _csv_response("pressurepipe-export.csv", ["id", *LIST_FIELDS], items)


@router.post("/import", response_model=ImportResult)
def import_entries(payload: ImportPayload) -> ImportResult:
    """按模板成批录入：逐行校验，非法行与编号重复行跳过并逐条回报，合法行写入台账。

    每行即时落库且按编号幂等更新，中断后拿同一份文件重新导入即可从失败行续跑。
    """
    try:
        result = service.import_rows(payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ImportResult(**result)


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
