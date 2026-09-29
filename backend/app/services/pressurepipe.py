"""压力管道业务规则：状态流转、字段校验、批量导入与筛选口径都收在这里。

批量导入按模板逐行处理：每行独立校验、独立入账，中途中断后可以从失败行续做，
已入账的行不会回滚；入账按管道编号 upsert，同一份数据重复录入不会多出管道。
"""
from __future__ import annotations

import csv
import hashlib
import io
from datetime import datetime
from typing import Any

from app.store import store

MODULE = "pressurepipe"
REQUIRED_FIELDS = ["管道编号", "管道名称", "管道级别"]
STATUS_ORDER = ["待投用", "在用运行", "隔离检修", "已停用"]
ACTION_RULES = {"办理投用": "在用运行", "安排检修": "隔离检修", "停用管道": "已停用"}
NEGATIVE_ACTIONS = ["停用管道"]

# 批量导入模板：管道编号是入账钥匙，管道级别、输送介质、下次检验日是可成批录入的字段
IMPORT_COLUMNS = ["管道编号", "管道级别", "输送介质", "下次检验日"]
EXPORT_COLUMNS = ["管道编号", "管道名称", "管道级别", "公称直径", "输送介质", "敷设方式", "下次检验日", "管道状态"]
IMPORT_LEVELS = {"GA1", "GA2", "GB1", "GB2", "GC1", "GC2", "GC3", "GD1", "GD2"}
DATE_FORMAT = "%Y-%m-%d"


class PressurepipeService:
    def __init__(self) -> None:
        # 导入批次台账：batch_id -> 批次快照（含断点），只存在内存里
        self._imports: dict[str, dict[str, Any]] = {}

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        name: str | None = None,
        level: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("管道编号", ""))]
        if name:
            rows = [row for row in rows if name in str(row.get("管道名称", ""))]
        if level:
            rows = [row for row in rows if str(row.get("管道级别", "")) == level]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
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

    # ----- 数据交换：模板、导出、批量导入与断点续传 -----

    def import_template(self) -> str:
        """返回导入模板 CSV 文本：一行表头，按列填写即可。"""
        buffer = io.StringIO()
        csv.writer(buffer).writerow(IMPORT_COLUMNS)
        return buffer.getvalue()

    def export_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        name: str | None = None,
        level: str | None = None,
    ) -> str:
        """导出当前过滤条件下的全量清单，与列表口径保持一致。"""
        items, _ = self.list_entries(keyword=keyword, status=status, name=name, level=level, page=1, size=100000)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(EXPORT_COLUMNS)
        for row in items:
            writer.writerow([row.get(column, "") for column in EXPORT_COLUMNS])
        return buffer.getvalue()

    def import_entries(self, content: str, filename: str | None = None) -> dict[str, Any]:
        """按模板成批录入：逐行校验、逐行入账，返回每行的处理结果与断点。

        批次按内容指纹编号：同一份数据重复提交会落到同一批次，从断点继续，
        已入账的行靠 upsert 兜底，不会重复、不会多出管道。
        """
        text = content.lstrip("\ufeff")
        reader = csv.reader(io.StringIO(text))
        parsed = list(reader)
        if not parsed:
            return self._failure("模板内容为空，请下载标准模板填写后再上传")

        header = [cell.strip() for cell in parsed[0]]
        missing = [column for column in IMPORT_COLUMNS if column not in header]
        if missing:
            return self._failure(f"模板缺少必需列：{'、'.join(missing)}；请下载标准模板填写")
        index = {column: header.index(column) for column in IMPORT_COLUMNS}

        data_rows: list[dict[str, str]] = []
        for raw in parsed[1:]:
            if not any(cell.strip() for cell in raw):
                continue
            def cell(column: str) -> str:
                position = index[column]
                return raw[position].strip() if position < len(raw) else ""
            data_rows.append({column: cell(column) for column in IMPORT_COLUMNS})

        batch_id = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        batch = self._imports.get(batch_id)
        if batch is None:
            batch = {
                "batch_id": batch_id,
                "filename": filename or "批量导入",
                "total": len(data_rows),
                "rows": data_rows,
                "checkpoint": 0,
                "done": False,
                "created": 0,
                "updated": 0,
                "skipped": 0,
                "results": [],
                "seen": set(),
                "fatal": None,
            }
            self._imports[batch_id] = batch
        self._run_batch(batch)
        return self._result(batch)

    def resume_import(self, batch_id: str) -> dict[str, Any] | None:
        """从批次断点继续处理未完成的行；批次不存在时返回 None。"""
        batch = self._imports.get(batch_id)
        if batch is None:
            return None
        self._run_batch(batch)
        return self._result(batch)

    def import_status(self, batch_id: str) -> dict[str, Any] | None:
        batch = self._imports.get(batch_id)
        return None if batch is None else self._result(batch)

    def _run_batch(self, batch: dict[str, Any]) -> None:
        """从断点开始逐行处理：每行独立校验、独立入账，失败就停在当前行等续做。"""
        rows = batch["rows"]
        position = batch["checkpoint"]
        while position < len(rows):
            try:
                result = self._process_row(position, rows[position], batch["seen"])
            except Exception as exc:  # noqa: BLE001 - 任何意外都不能丢掉已入账的数据
                batch["fatal"] = f"第 {position + 1} 行处理中断：{exc}；已入账的行不受影响，可从本行继续"
                batch["done"] = False
                return
            batch["results"].append(result)
            if result["ok"]:
                if result["action"] == "created":
                    batch["created"] += 1
                else:
                    batch["updated"] += 1
            else:
                batch["skipped"] += 1
            position += 1
            batch["checkpoint"] = position
        batch["done"] = True
        batch["fatal"] = None

    def _process_row(self, row_index: int, values: dict[str, str], seen: set[str]) -> dict[str, Any]:
        """校验一行并 upsert 进台账；不合法或编号重复的行只报不写。"""
        number = values["管道编号"]
        row_number = row_index + 1
        if not number:
            return {"row": row_number, "管道编号": "", "ok": False, "action": None, "reason": "管道编号为空，跳过"}
        if number in seen:
            return {"row": row_number, "管道编号": number, "ok": False, "action": None, "reason": "管道编号重复，跳过"}

        level = values["管道级别"].upper()
        if not level:
            return {"row": row_number, "管道编号": number, "ok": False, "action": None, "reason": "管道级别为空，跳过"}
        if level not in IMPORT_LEVELS:
            return {"row": row_number, "管道编号": number, "ok": False, "action": None,
                    "reason": f"管道级别「{values['管道级别']}」格式不合法，跳过"}

        medium = values["输送介质"]
        if not medium:
            return {"row": row_number, "管道编号": number, "ok": False, "action": None, "reason": "输送介质为空，跳过"}

        next_date = values["下次检验日"]
        if not next_date:
            return {"row": row_number, "管道编号": number, "ok": False, "action": None, "reason": "下次检验日为空，跳过"}
        try:
            parsed = datetime.strptime(next_date, DATE_FORMAT)
        except ValueError:
            return {"row": row_number, "管道编号": number, "ok": False, "action": None,
                    "reason": f"下次检验日「{next_date}」格式不合法，应为 YYYY-MM-DD，跳过"}
        if parsed.strftime(DATE_FORMAT) != next_date:
            return {"row": row_number, "管道编号": number, "ok": False, "action": None,
                    "reason": f"下次检验日「{next_date}」格式不合法，应为 YYYY-MM-DD，跳过"}

        # 先入账、成功后再记入已见编号：入账中途失败的行不能算已处理，续做时要重试
        action = self._upsert(number, level, medium, next_date)
        seen.add(number)
        return {"row": row_number, "管道编号": number, "ok": True, "action": action, "reason": None}

    def _upsert(self, number: str, level: str, medium: str, next_date: str) -> str:
        """按管道编号入账：已存在则更新三个字段（不动状态），不存在则新建一条。"""
        rows = store.rows(MODULE)
        for row in rows:
            if str(row.get("管道编号", "")) == number:
                row["管道级别"] = level
                row["输送介质"] = medium
                row["下次检验日"] = next_date
                return "updated"
        entry: dict[str, Any] = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "管道编号": number,
            "管道名称": number,
            "管道级别": level,
            "输送介质": medium,
            "下次检验日": next_date,
            "status": STATUS_ORDER[0],
            "pending": True,
            "abnormal": False,
        }
        rows.append(entry)
        return "created"

    def _result(self, batch: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "batch_id": batch["batch_id"],
            "filename": batch["filename"],
            "total": batch["total"],
            "processed": batch["checkpoint"],
            "created": batch["created"],
            "updated": batch["updated"],
            "skipped": batch["skipped"],
            "done": batch["done"],
            "fatal": batch["fatal"],
            "results": batch["results"],
        }

    @staticmethod
    def _failure(message: str) -> dict[str, Any]:
        return {
            "ok": False,
            "message": message,
            "batch_id": None,
            "filename": None,
            "total": 0,
            "processed": 0,
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "done": True,
            "fatal": None,
            "results": [],
        }
