---
name: requirement-review-output-formatter
description: 将需求评审结果整理为面向用户的 Markdown 报告，并保留 RequirementReviewResult 结构化 JSON。
---

# 需求评审输出格式化

使用本 skill 将前序阶段结果整理为最终评审输出。

最终输出分两层：
- 页面展示层：面向用户阅读的 Markdown 评审报告
- 结构化结果层：用于后续入库或接口解析的 `RequirementReviewResult` JSON

## 前置条件

必须先完成：

- `requirement-evidence-analysis`
- `requirement-quality-scoring`
- `requirement-gate-decision`

如果当前任务要求正式保存评审结果，则本阶段完成后应立即进入
`requirement-review-persistence`，再调用 `persist_requirement_review_result`。

## 输出结构

最终回答必须先输出 Markdown 评审报告，再在末尾输出
`结构化结果（供入库接口使用）` 小节。

Markdown 评审报告必须包含：

- 需求摘要
- 评分与门禁结论
- 是否可进入用例生成
- 主要依据
- 主要风险
- 待澄清项
- 改进建议

`结构化结果（供入库接口使用）` 小节必须包含一个 fenced `json` 代码块。

字段必须包含：

- `requirement_summary`
- `review_score`
- `quality_gate`
- `dimension_scores`
- `key_findings`
- `major_risks`
- `missing_or_ambiguous_items`
- `suggestions_to_improve`
- `assumptions`
- `generation_policy`
- `generation_policy_reason`

## 硬约束

- `review_score` 必须等于五个 `dimension_scores` 之和
- `quality_gate` 必须与分数阈值一致
- `generation_policy` 必须与 `quality_gate` 一致
- 字段值使用用户语言

本 skill 不生成正式测试用例。
