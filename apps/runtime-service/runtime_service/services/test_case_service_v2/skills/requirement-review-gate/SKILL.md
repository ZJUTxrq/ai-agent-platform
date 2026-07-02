---
name: requirement-review-gate
description: 在需求分析之后、测试策略和测试用例生成之前激活。负责从测试视角评审需求质量并输出门禁分数，判断当前需求是否足以进入正式用例生成。
---

# 需求评审门禁 Skill

## 激活场景
- `requirement-analysis` 已完成
- 用户要求生成测试用例前，需要先判断需求是否清晰、完整、可验证
- 用户明确要求“需求评审”“需求打分”“达到分数后再生成用例”
- 当前输入来自 PRD、接口说明、用户故事、业务描述、PDF、图片或项目知识库检索结果

## 目标
判断当前需求材料是否足以支撑正式测试用例生成。

本 skill 不负责生成正式测试用例，只负责输出需求质量评分、门禁结论、阻断问题、待澄清项和后续生成建议。

## 必做动作
1. 基于已完成的 `requirement-analysis` 结果和可用证据进行评审。
2. 如果需求事实依赖项目历史文档、接口说明或业务规则，且当前证据不足，可以调用 `query_project_knowledge` 补充依据。
3. 按评分维度给出 0-100 的 `review_score`。
4. 根据分数和阻断问题给出 `review_gate`。
5. 明确列出阻断问题、主要风险和缺失信息。
6. 给出后续是否允许生成用例的 `generation_policy`。

## 评分维度
总分 100 分。

| 维度 | 分值 | 评审重点 |
|---|---:|---|
| 业务目标清晰度 | 20 | 目标用户、业务目标、核心场景是否明确 |
| 功能范围完整度 | 20 | 做什么、不做什么、主流程、关键分支是否清楚 |
| 业务规则完整度 | 20 | 字段规则、状态流转、权限规则、接口约束是否明确 |
| 异常与边界条件 | 15 | 失败场景、边界值、异常状态、重复提交、并发风险是否覆盖 |
| 验收标准可验证性 | 15 | 输出结果、成功条件、失败条件是否能转成可验证预期 |
| 测试依赖与数据准备 | 10 | 账号、测试数据、环境、外部服务、前置条件是否明确 |

## 门禁规则
- `review_score >= 80` 且无阻断问题：`review_gate = pass`
- `60 <= review_score < 80` 或存在重要待澄清项：`review_gate = needs_clarification`
- `review_score < 60` 或存在阻断问题：`review_gate = blocked`

阻断问题包括但不限于：
- 不知道要测试的业务对象或功能范围
- 主流程缺失，无法判断用户如何完成任务
- 关键业务规则、字段约束或状态流转缺失
- 预期结果不可验证
- 需求证据不足，继续生成会导致臆造业务细节

## 生成策略
- `pass`：允许进入 `test-strategy` 和正式测试用例生成。
- `needs_clarification`：只允许生成草稿用例；必须显式标注假设、风险和待确认项。
- `blocked`：不得生成正式测试用例；只输出待澄清问题和补充资料建议。

## 输出格式
默认只输出结构化 JSON 风格内容：

```json
{
  "review_score": 78,
  "review_gate": "needs_clarification",
  "threshold": 80,
  "summary": "需求主体清晰，但异常流程和验收标准不足。",
  "score_breakdown": {
    "business_goal_clarity": 16,
    "functional_scope_completeness": 15,
    "business_rule_completeness": 14,
    "exception_and_boundary_coverage": 10,
    "acceptance_verifiability": 13,
    "test_dependency_readiness": 10
  },
  "blocking_issues": [],
  "major_risks": [
    "缺少失败场景说明",
    "部分字段约束未明确"
  ],
  "missing_information": [
    "接口错误码规则",
    "权限边界说明"
  ],
  "generation_policy": "can_generate_draft_only",
  "generation_advice": "可以生成草稿用例，但必须标注假设和待确认项。"
}
```

## 字段约束
- `review_score` 必须是 0-100 的整数。
- `review_gate` 只能是 `pass`、`needs_clarification`、`blocked`。
- `threshold` 默认是 80，除非用户明确指定其他阈值。
- `score_breakdown` 各项分数不得超过对应维度上限。
- `generation_policy` 只能是：
  - `can_generate_formal_cases`
  - `can_generate_draft_only`
  - `clarification_required`

## 约束
- 不得把需求评审写成测试用例。
- 不得为了让流程继续而虚高评分。
- 知识库只是补充查询来源，不是需求评审或用例生成的硬前置。
- 不得臆造需求中不存在的规则、接口、字段或验收标准。
- 如果现有输入和知识库补充查询后证据仍不足，应降分并列出待澄清项。
- 如果用户要求“分数到了才能生成用例”，必须先输出本门禁结果，再决定是否进入后续阶段。
- 如果 `review_gate = blocked`，不得继续进入正式 `test-case-design`。
