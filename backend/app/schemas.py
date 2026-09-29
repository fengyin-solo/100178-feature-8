"""接口出入参模型：列表分页、动作结果与各模块的明细结构。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    """登记或修改一条业务记录时提交的字段集合。"""

    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None


class ImportErrorItem(BaseModel):
    """批量录入中被跳过的一行：行号、编号与逐条错误原因。"""

    line: int
    管道编号: str = ""
    reasons: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class ImportResult(BaseModel):
    """批量录入结果：合法行落库计数 + 问题行清单，便于修完问题行后续跑。"""

    total: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[ImportErrorItem] = Field(default_factory=list)


class ImportPayload(BaseModel):
    """批量录入请求体：直接提交模板 CSV 的文本内容。"""

    content: str



class BoilerEntry(BaseModel):
    """锅炉设备明细结构。"""

    field_0: str | None = None  # 设备编号
    field_1: str | None = None  # 设备名称
    field_2: str | None = None  # 额定蒸发量
    field_3: str | None = None  # 工作压力
    field_4: str | None = None  # 使用场所
    field_5: str | None = None  # 投用日期
    field_6: str | None = None  # 下次检验日
    field_7: str | None = None  # 设备状态

class VesselEntry(BaseModel):
    """压力容器明细结构。"""

    field_0: str | None = None  # 容器编号
    field_1: str | None = None  # 容器名称
    field_2: str | None = None  # 设计压力
    field_3: str | None = None  # 容积规格
    field_4: str | None = None  # 介质类别
    field_5: str | None = None  # 使用场所
    field_6: str | None = None  # 下次检验日
    field_7: str | None = None  # 容器状态

class PressurepipeEntry(BaseModel):
    """压力管道明细结构。"""

    field_0: str | None = None  # 管道编号
    field_1: str | None = None  # 管道名称
    field_2: str | None = None  # 管道级别
    field_3: str | None = None  # 公称直径
    field_4: str | None = None  # 输送介质
    field_5: str | None = None  # 敷设方式
    field_6: str | None = None  # 下次检验日
    field_7: str | None = None  # 管道状态

class CraneEntry(BaseModel):
    """起重机械明细结构。"""

    field_0: str | None = None  # 机械编号
    field_1: str | None = None  # 机械名称
    field_2: str | None = None  # 额定起重量
    field_3: str | None = None  # 跨度规格
    field_4: str | None = None  # 使用场所
    field_5: str | None = None  # 投用日期
    field_6: str | None = None  # 下次检验日
    field_7: str | None = None  # 机械状态

class ElevatorEntry(BaseModel):
    """电梯设备明细结构。"""

    field_0: str | None = None  # 电梯编号
    field_1: str | None = None  # 电梯名称
    field_2: str | None = None  # 载重规格
    field_3: str | None = None  # 层站数量
    field_4: str | None = None  # 使用场所
    field_5: str | None = None  # 投用日期
    field_6: str | None = None  # 下次检验日
    field_7: str | None = None  # 电梯状态

class ForkliftEntry(BaseModel):
    """场内机动车辆明细结构。"""

    field_0: str | None = None  # 车辆编号
    field_1: str | None = None  # 车辆名称
    field_2: str | None = None  # 动力方式
    field_3: str | None = None  # 额定载重
    field_4: str | None = None  # 使用场所
    field_5: str | None = None  # 投用日期
    field_6: str | None = None  # 下次检验日
    field_7: str | None = None  # 车辆状态

class PlanEntry(BaseModel):
    """点检计划明细结构。"""

    field_0: str | None = None  # 计划编号
    field_1: str | None = None  # 点检对象
    field_2: str | None = None  # 点检周期
    field_3: str | None = None  # 点检项目
    field_4: str | None = None  # 计划工期
    field_5: str | None = None  # 编制人员
    field_6: str | None = None  # 审批人员
    field_7: str | None = None  # 计划状态

class SpotcheckEntry(BaseModel):
    """点检记录明细结构。"""

    field_0: str | None = None  # 点检单号
    field_1: str | None = None  # 关联计划
    field_2: str | None = None  # 点检设备
    field_3: str | None = None  # 点检人员
    field_4: str | None = None  # 点检日期
    field_5: str | None = None  # 点检结论
    field_6: str | None = None  # 异常项数
    field_7: str | None = None  # 点检状态

class LubricateEntry(BaseModel):
    """保养记录明细结构。"""

    field_0: str | None = None  # 保养单号
    field_1: str | None = None  # 保养设备
    field_2: str | None = None  # 润滑点位
    field_3: str | None = None  # 油品规格
    field_4: str | None = None  # 加注用量
    field_5: str | None = None  # 保养人员
    field_6: str | None = None  # 保养日期
    field_7: str | None = None  # 保养状态

class InspectEntry(BaseModel):
    """检验任务明细结构。"""

    field_0: str | None = None  # 检验编号
    field_1: str | None = None  # 检验对象
    field_2: str | None = None  # 检验类别
    field_3: str | None = None  # 检验机构
    field_4: str | None = None  # 计划检验日
    field_5: str | None = None  # 检验人员
    field_6: str | None = None  # 检验日期
    field_7: str | None = None  # 检验状态

class ReportEntry(BaseModel):
    """检验报告明细结构。"""

    field_0: str | None = None  # 报告编号
    field_1: str | None = None  # 关联检验
    field_2: str | None = None  # 报告类别
    field_3: str | None = None  # 检验结论
    field_4: str | None = None  # 下次检验日
    field_5: str | None = None  # 出具人员
    field_6: str | None = None  # 出具日期
    field_7: str | None = None  # 报告状态

class HazardEntry(BaseModel):
    """隐患记录明细结构。"""

    field_0: str | None = None  # 隐患编号
    field_1: str | None = None  # 涉及设备
    field_2: str | None = None  # 隐患类型
    field_3: str | None = None  # 隐患描述
    field_4: str | None = None  # 严重等级
    field_5: str | None = None  # 发现日期
    field_6: str | None = None  # 登记人员
    field_7: str | None = None  # 隐患状态

class RectifyEntry(BaseModel):
    """整改单明细结构。"""

    field_0: str | None = None  # 整改单号
    field_1: str | None = None  # 关联隐患
    field_2: str | None = None  # 整改措施
    field_3: str | None = None  # 责任单位
    field_4: str | None = None  # 整改期限
    field_5: str | None = None  # 完成日期
    field_6: str | None = None  # 验收人员
    field_7: str | None = None  # 整改状态

class RegisterEntry(BaseModel):
    """登记记录明细结构。"""

    field_0: str | None = None  # 登记编号
    field_1: str | None = None  # 登记设备
    field_2: str | None = None  # 使用单位
    field_3: str | None = None  # 登记类别
    field_4: str | None = None  # 登记日期
    field_5: str | None = None  # 证件编号
    field_6: str | None = None  # 办理人员
    field_7: str | None = None  # 登记状态

class OperatorEntry(BaseModel):
    """作业人员明细结构。"""

    field_0: str | None = None  # 人员编号
    field_1: str | None = None  # 人员姓名
    field_2: str | None = None  # 所属单位
    field_3: str | None = None  # 作业项目
    field_4: str | None = None  # 证件编号
    field_5: str | None = None  # 有效期至
    field_6: str | None = None  # 复审日期
    field_7: str | None = None  # 人员状态

class SpareEntry(BaseModel):
    """备件器材明细结构。"""

    field_0: str | None = None  # 备件编号
    field_1: str | None = None  # 备件名称
    field_2: str | None = None  # 适用设备
    field_3: str | None = None  # 结存数量
    field_4: str | None = None  # 计量单位
    field_5: str | None = None  # 存放库位
    field_6: str | None = None  # 保管人员
    field_7: str | None = None  # 备件状态

class ContractEntry(BaseModel):
    """维保合同明细结构。"""

    field_0: str | None = None  # 合同编号
    field_1: str | None = None  # 服务单位
    field_2: str | None = None  # 维保设备
    field_3: str | None = None  # 合同金额
    field_4: str | None = None  # 服务期限
    field_5: str | None = None  # 签订人员
    field_6: str | None = None  # 到期日期
    field_7: str | None = None  # 合同状态

class SettleEntry(BaseModel):
    """结算单明细结构。"""

    field_0: str | None = None  # 结算单号
    field_1: str | None = None  # 关联合同
    field_2: str | None = None  # 费用类别
    field_3: str | None = None  # 应付金额
    field_4: str | None = None  # 已付金额
    field_5: str | None = None  # 审核人员
    field_6: str | None = None  # 付款日期
    field_7: str | None = None  # 结算状态
