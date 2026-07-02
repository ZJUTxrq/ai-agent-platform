---
name: requirement-review-persistence
description: 当需求评审结论已经定稿且需要正式落库时激活。负责调用唯一持久化工具，把评审结果和当前附件解析结果写入 interaction-data-service。
---

# 需求评审持久化

使用本 skill 的前提是：

- 已完成 `requirement-evidence-analysis`
- 已完成 `requirement-quality-scoring`
- 已完成 `requirement-gate-decision`
- 已完成 `requirement-review-output-formatter`

## 唯一允许的工具

1. 只调用 `persist_requirement_review_result`
2. 不要调用测试用例生成或测试用例落库工具
3. 不要在没有工具成功返回时声称“已保存”

## 调用要求

传入的结构化字段必须与最终评审 JSON 一致，至少包含：

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

## 工具结果解释

- `status=persisted`：说明评审结果已入库，并返回项目、批次、文档数量和结果 ID
- `status=skipped_remote_not_configured`：远端未配置，本次未正式入库
- `status=failed_missing_project_id` / `failed_invalid_project_id`：当前运行上下文缺少合法项目 ID
- `status=failed_remote_request`：远端调用失败，应如实反馈失败原因

## 输出要求

工具成功后，只能基于工具返回内容说明：

- 是否已保存
- 保存到了哪个 `project_id`
- 当前 `batch_id`
- 持久化了多少份文档
- 评审结果的 `persisted_result_id`
