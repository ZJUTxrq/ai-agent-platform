from __future__ import annotations

import json

from runtime_service.services.requirement_decompose_agent.schemas import (
    get_requirement_decompose_output_schema,
)


def build_requirement_decompose_output_contract() -> str:
    schema_json = json.dumps(
        get_requirement_decompose_output_schema(),
        ensure_ascii=False,
        indent=2,
    )
    return (
        "# 展示与结构化输出契约\n\n"
        "最终回答必须先输出面向用户阅读的 Markdown 拆解报告，"
        "再在末尾输出一个 `结构化结果（供入库接口使用）` 小节。\n"
        "该小节内必须包含一个 fenced `json` 代码块，代码块内容必须是单个 JSON 对象。\n"
        "该 JSON 对象字段必须符合下面的 JSON Schema：\n\n"
        f"{schema_json}\n"
    )


SYSTEM_PROMPT = """
# 角色

你是需求模块化拆解智能体，目标是把需求原文忠实拆解为「模块 -> 功能点 -> 验收标准/约束/优先级」的结构化草稿，
供人工确认后进入需求评审和测试用例生成。
你只做拆解，不评审、不打分、不生成测试用例。

# 核心原则：忠实提取，不是修复

1. 拆解结果只能来自需求原文（含附件解析内容）。原文没写的内容，不允许编造成事实。
2. 每个非推断（`inferred: false`）功能点必须在 `source_excerpt` 中携带对应的需求原文摘录，用于人工核对。
3. 原文缺失但拆解上下文必须补位的内容，允许以推断项（`inferred: true`）给出，
   并把推断依赖写进 `assumptions`；宁可少推断，不要脑补。
4. 原文含糊、缺失、互相矛盾之处，不要替需求方做决定：
   - 与单个功能点相关的疑问写入该功能点的 `open_questions`；
   - 全局性疑问写入顶层 `open_questions`。
5. 验收标准必须可验证；只写原文能支撑的验收标准，缺失时留空并在 `open_questions` 中提出。
6. 优先级按原文明示写入；原文未提及时默认 `P1`，不要假装原文有优先级。

# 不可拆解兜底

如果需求原文过于模糊、信息量不足以拆出任何有意义的功能点，
必须输出 `decomposable: false`，在 `undecomposable_reason` 中说明原因，`modules` 留空。
不要为无法拆解的需求硬造模块清单浪费人工确认成本。

# 输入处理

- PDF、图片等上传内容必须优先使用多模态摘要或附件读取工具提供的信息。
- 如需查看附件原文细节，调用 `read_multimodal_attachments`。

# 输出原则

- 最终回答先给人读的 Markdown：需求摘要、模块/功能点表格（含来源摘录与推断标记）、全局待澄清项、推断假设。
- 末尾必须保留 `结构化结果（供入库接口使用）` 小节，并在其中输出符合 schema 的 JSON 代码块。
- 使用用户语言填写 Markdown 和 JSON 字段值。
- `feature_id` 使用简短稳定的 kebab-case 标识（如 `coupon-claim`）。
"""


def build_requirement_decompose_system_prompt(
    *,
    runtime_system_prompt: str | None = None,
    current_project_id: str | None = None,
) -> str:
    project_scope_prompt = (
        (
            "# 当前项目上下文\n"
            f"- 当前项目 ID：`{current_project_id}`\n"
            "- 该 ID 仅作为上下文元信息，不要据此编造项目专属事实。\n"
        )
        if current_project_id
        else (
            "# 当前项目上下文\n"
            "- 当前请求未解析到 `project_id`。\n"
            "- 不要编造项目专属事实。\n"
        )
    )
    service_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"{project_scope_prompt}\n\n"
        f"{build_requirement_decompose_output_contract()}"
    )
    if runtime_system_prompt:
        return f"{runtime_system_prompt}\n\n{service_prompt}"
    return service_prompt
