"""用户可见中文文案集合。

ChatAgent 的系统 prompt 保持英文（给 LLM 看），但所有面向用户的中文回复与
澄清提示统一放在这里，避免硬编码分散在 sessions / agent / engine 中。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ChatStrings:
    """Frozen bundle of user-facing Chinese strings."""

    fallback_not_understood: str = (
        "我没能正确理解你的意思。你可以直接回复需要做什么，"
        "例如：确认 / 继续 / 提供参数 c_ij:1,2,3;4,5,6。"
    )
    fallback_empty_chat: str = "好的，请告诉我你的需求。"
    session_welcome: str = (
        "文件已收到。我现在开始分析数据并建立优化模型，稍后会给出字段映射和缺失参数说明。"
    )
    business_goal_updated: str = "业务目标已更新：{value}"
    problem_type_updated: str = "问题类型已更新：{value}"
    source_updated: str = "数据源已更新：{value}"
    no_pending_clarification: str = "当前没有需要回答的问题。"

    # Clarification formatting
    data_intelligence_step_prefix: str = "第 1 步"
    modeling_step_prefix: str = "第 2 步"
    ontology_patch_step_prefix: str = "第 2 步"
    ask_select_column: str = "请从下面的列名里选一个，或者直接告诉我列名："
    ask_no_matching_column: str = (
        "数据中似乎没有直接对应的列。请直接告诉我列名；"
        "如果 CSV 里确实没有这一列，也可以直接提供该参数的数值。"
    )
    ask_modeling_parameter_json: str = (
        "请直接回复一个 JSON 数值（例如 `{example}`），或者回复 `default` 让我使用默认值。"
    )
    ask_ontology_patch_approval: str = "请回复“同意”应用补全，或回复修改意见。"

    # Agentic field mapping
    mapping_review_intro: str = "我已读取你的数据，包含 {n_cols} 列：{columns}。我的理解如下："
    mapping_review_item: str = "- `{column}` → {chinese_label}（{role_info}）{reasoning}"
    mapping_review_outro: str = "请确认，或告诉我需要修改的地方。"
    mapping_updated: str = "已更新：{column} → {role_info}。还有其他需要调整的吗？"
    mapping_confirmed: str = "已确认字段映射，继续执行后续流程。"

    def _role_display_name(self, role: str) -> str:
        """Return a user-friendly Chinese name for a canonical role."""
        mapping: dict[str, str] = {
            "fixed_cost": "固定成本",
            "cost": "运输/可变成本",
            "distance": "距离",
            "demand": "需求量",
            "supply": "供应量",
            "capacity": "产能/容量",
            "value": "价值",
            "weight": "重量",
            "processing_time": "处理时间",
            "due_date": "截止日期",
            "holding_cost": "持有成本",
            "ordering_cost": "订货成本",
            "purchase_cost": "采购成本",
            "initial_inventory": "初始库存",
            "customer_key": "客户",
            "facility_key": "工厂/设施",
            "agent_key": "代理",
            "task_key": "任务",
            "source_key": "供应点",
            "sink_key": "需求点",
        }
        return mapping.get(role, role)

    @property
    def _role_name_reverse(self) -> dict[str, str]:
        """Reverse map Chinese role names to canonical roles."""
        mapping: dict[str, str] = {
            "固定成本": "fixed_cost",
            "运输成本": "cost",
            "运输费用": "cost",
            "可变成本": "cost",
            "距离": "distance",
            "需求量": "demand",
            "需求": "demand",
            "供应量": "supply",
            "供应": "supply",
            "产能": "capacity",
            "容量": "capacity",
            "价值": "value",
            "重量": "weight",
            "处理时间": "processing_time",
            "截止日期": "due_date",
            "持有成本": "holding_cost",
            "订货成本": "ordering_cost",
            "采购成本": "purchase_cost",
            "初始库存": "initial_inventory",
            "客户": "customer_key",
            "客户编号": "customer_key",
            "工厂": "facility_key",
            "设施": "facility_key",
            "工厂编号": "facility_key",
            "代理": "agent_key",
            "任务": "task_key",
            "供应点": "source_key",
            "需求点": "sink_key",
        }
        return mapping

    def format_data_intelligence_question(
        self,
        role_name: str,
        symbol: str,
        options_text: str,
        recognized_text: str = "",
    ) -> str:
        """Format data_intelligence clarification question."""
        display = self._role_display_name(role_name)
        lines = [
            f"我已识别字段映射。目前还缺少 **{display}（{role_name} / {symbol}）**。",
        ]
        if recognized_text:
            lines.append(f"当前识别到的字段：\n{recognized_text}")
        lines.append(
            "如果数据中有对应列，请直接告诉我列名；"
            f"如果没有对应列，也可以直接提供 `{symbol}` 的数值。"
        )
        if options_text:
            lines.append(self.ask_select_column)
            lines.append(options_text)
        return "\n".join(lines)

    def format_modeling_question(self, field: str, example: str) -> str:
        """Format modeling clarification question."""
        return (
            f"{self.modeling_step_prefix}：建模需要参数 **{field}**，但当前数据里没有明确提供。\n"
            + self.ask_modeling_parameter_json.format(example=example)
        )

    def format_ontology_patch_question(self, summary: str, confidence: float) -> str:
        """Format ontology_patch approval question."""
        return (
            f"{self.ontology_patch_step_prefix}：当前数据不足以直接建立完整模型。\n"
            f"我建议对模型做如下补全（置信度 {confidence:.2f}）：\n{summary}\n"
            f"{self.ask_ontology_patch_approval}"
        )

    def format_mapping_proposal(self, proposal: dict[str, Any]) -> str:
        """Format a SchemaMappingProposal as a Chinese review message."""
        fields = proposal.get("fields", [])
        columns = [f["column"] for f in fields]
        lines = [self.mapping_review_intro.format(n_cols=len(fields), columns="、".join(columns))]
        for f in fields:
            role = f.get("canonical_role") or f.get("semantic_role") or "未识别"
            symbol = f.get("optimization_symbol") or ""
            label = f.get("chinese_label") or self._role_display_name(role)
            role_info = f"{label} / {role}" + (f" / {symbol}" if symbol else "")
            reasoning = f"：{f.get('reasoning')}" if f.get("reasoning") else ""
            lines.append(
                self.mapping_review_item.format(
                    column=f["column"],
                    chinese_label=label,
                    role_info=role_info,
                    reasoning=reasoning,
                )
            )
        lines.append(self.mapping_review_outro)
        return "\n".join(lines)

    def format_mapping_update(self, column: str, field: dict[str, Any]) -> str:
        """Format a single mapping update confirmation."""
        role = field.get("canonical_role") or field.get("semantic_role") or "未识别"
        symbol = field.get("optimization_symbol") or ""
        label = field.get("chinese_label") or self._role_display_name(role)
        role_info = f"{label} / {role}" + (f" / {symbol}" if symbol else "")
        return self.mapping_updated.format(column=column, role_info=role_info)


CHAT_STRINGS = ChatStrings()
