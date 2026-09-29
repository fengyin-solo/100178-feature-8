"""压力管道业务规则：状态流转、字段校验、批量录入与筛选口径都收在这里。

数据交换约定：
- 模板列：管道编号、管道名称、管道级别、输送介质、下次检验日（公称直径、敷设方式选填）；
- 逐行校验，非法行与文件内编号重复行单独报错并跳过，合法行当场写入，因此中途失败后
  拿同一份文件重做时，已写入的编号按更新处理，从失败那一行继续即可，不会多出管道；
- 编号已存在于台账中的行按更新处理，同一份数据重复录入结果幂等。
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date
from typing import Any

from app.store import store

MODULE = "pressurepipe"
REQUIRED_FIELDS = ["管道编号", "管道名称", "管道级别"]
# 模板必填列（首行表头必须包含）；公称直径、敷设方式选填，导出文件回传也能识别。
TEMPLATE_COLUMNS = ["管道编号", "管道名称", "管道级别", "输送介质", "下次检验日"]
OPTIONAL_COLUMNS = ["公称直径", "敷设方式"]
LIST_FIELDS = ["管道编号", "管道名称", "管道级别", "公称直径", "输送介质", "敷设方式", "下次检验日", "管道状态"]
STATUS_ORDER = ["待投用", "在用运行", "隔离检修", "已停用"]
ACTION_RULES = {"办理投用": "在用运行", "安排检修": "隔离检修", "停用管道": "已停用"}
NEGATIVE_ACTIONS = ["停用管道"]

CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,31}$")
LEVEL_PATTERN = re.compile(r"^(GC[1-3]|GB[12]|GA[12])$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_row(values: dict[str, str], *, creating: bool) -> list[str]:
    """校验一行模板数据，返回错误原因列表；空列表表示整行合法。"""
    errors: list[str] = []
    code = values.get("管道编号", "")
    if not code:
        errors.append("管道编号为空")
    elif not CODE_PATTERN.match(code):
        errors.append("管道编号格式不合法（3-32位字母、数字、下划线或短横线，且以字母数字开头）")
    level = values.get("管道级别", "")
    if not level:
        errors.append("管道级别为空")
    elif not LEVEL_PATTERN.match(level):
        errors.append("管道级别格式不合法（应为 GA1/GA2/GB1/GB2/GC1/GC2/GC3）")
    medium = values.get("输送介质", "")
    if not medium:
        errors.append("输送介质为空")
    elif len(medium) > 30:
        errors.append("输送介质长度不能超过30个字")
    next_check = values.get("下次检验日", "")
    if not next_check:
        errors.append("下次检验日为空")
    elif not DATE_PATTERN.match(next_check):
        errors.append("下次检验日格式不合法（应为 YYYY-MM-DD）")
    else:
        try:
            date.fromisoformat(next_check)
        except ValueError:
            errors.append("下次检验日不是有效日期（应为 YYYY-MM-DD）")
    name = values.get("管道名称", "")
    if creating and not name:
        errors.append("管道名称为空（新登记管道必须填写）")
    elif name and len(name) > 50:
        errors.append("管道名称长度不能超过50个字")
    return errors


def _present(row: dict[str, Any]) -> dict[str, Any]:
    """列表/导出口径：把内部 status 投影成「管道状态」，保证两处数据一致。"""
    item = {field: row.get(field) for field in LIST_FIELDS[:-1]}
    item["管道状态"] = row.get("status")
    item["id"] = row.get("id")
    return item


class PressurepipeService:
    def _filter_rows(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        level: str | None = None,
        medium: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("管道编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if level:
            rows = [row for row in rows if level in str(row.get("管道级别", ""))]
        if medium:
            rows = [row for row in rows if medium in str(row.get("输送介质", ""))]
        return rows

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        level: str | None = None,
        medium: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._filter_rows(keyword=keyword, status=status, level=level, medium=medium)
        total = len(rows)
        start = max(page - 1, 0) * size
        return [_present(row) for row in rows[start:start + size]], total

    def export_rows(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        level: str | None = None,
        medium: str | None = None,
    ) -> list[dict[str, Any]]:
        """导出口径与列表完全一致：同一套过滤条件，返回全量、不分页。"""
        return [_present(row) for row in self._filter_rows(
            keyword=keyword, status=status, level=level, medium=medium
        )]

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

    def import_rows(self, content: str) -> dict[str, Any]:
        """按模板成批录入：逐行校验、合法行立即写入、问题行跳过并回报。

        返回新增/更新/跳过计数与逐行错误清单。每行独立处理，调用方中断后拿同一文件
        重新调用即为续跑：已落库的编号走更新分支，最终不会出现重复管道。
        """
        reader = csv.reader(io.StringIO(content.lstrip("﻿") if content.startswith("﻿") else content))
        try:
            header = next(reader)
        except StopIteration:
            raise ValueError("文件内容为空，请按模板填写后再导入")
        header = [name.strip() for name in header]
        missing = [name for name in TEMPLATE_COLUMNS if name not in header]
        if missing:
            raise ValueError(f"模板缺少必填列：{'、'.join(missing)}")
        index = {name: header.index(name) for name in header if name}

        rows = store.rows(MODULE)
        existing = {str(row.get("管道编号", "")).strip(): row for row in rows}
        seen_in_file: set[str] = set()

        created = 0
        updated = 0
        skipped = 0
        errors: list[dict[str, Any]] = []

        for line_no, raw in enumerate(reader, start=2):
            # 跳过整行空白（含导出/编辑时留下的空行），不计入错误。
            if not any(str(cell).strip() for cell in raw):
                continue
            values: dict[str, str] = {}
            for name in TEMPLATE_COLUMNS + OPTIONAL_COLUMNS:
                pos = index.get(name)
                values[name] = raw[pos].strip() if pos is not None and pos < len(raw) else ""

            code = values["管道编号"]
            is_duplicate = bool(code) and code in seen_in_file
            row_errors = _validate_row(values, creating=code not in existing)
            if is_duplicate:
                row_errors.append("管道编号在本文件中重复")
            if row_errors:
                skipped += 1
                errors.append({
                    "line": line_no,
                    "管道编号": code,
                    "reasons": row_errors,
                    "raw": values,
                })
                if code:
                    seen_in_file.add(code)
                continue

            seen_in_file.add(code)
            entry = existing.get(code)
            if entry is None:
                entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
                entry["status"] = STATUS_ORDER[0]
                entry["pending"] = True
                entry["abnormal"] = False
                entry["管道编号"] = code
                entry["管道名称"] = values["管道名称"]
                rows.append(entry)
                existing[code] = entry
                created += 1
            else:
                updated += 1

            # 模板字段整行覆盖；选填列留空时保持原值，避免把历史信息误清空。
            entry["管道级别"] = values["管道级别"]
            entry["输送介质"] = values["输送介质"]
            entry["下次检验日"] = values["下次检验日"]
            if values["管道名称"]:
                entry["管道名称"] = values["管道名称"]
            for optional in OPTIONAL_COLUMNS:
                if values[optional]:
                    entry[optional] = values[optional]

        return {
            "total": created + updated + skipped,
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
        }

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"压力管道 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于压力管道可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"压力管道已{action}"
