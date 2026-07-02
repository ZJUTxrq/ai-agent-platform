---
name: requirement-gate-decision
description: 基于需求质量评分给出 pass、conditional 或 blocked 门禁结论及生成策略。
---

# 需求门禁决策

使用本 skill 根据评分和缺口决定是否允许进入测试用例生成阶段。

## 前置条件

必须先完成：

- `requirement-evidence-analysis`
- `requirement-quality-scoring`

## 门禁规则

- `pass`：评分 >= 85，可以进入测试用例生成
- `conditional`：70 <= 评分 < 85，可以在明确假设后继续生成
- `blocked`：评分 < 70，建议先澄清需求，再生成正式测试用例

## 生成策略

- `allow_generation`：对应 `pass`
- `allow_generation_with_assumptions`：对应 `conditional`
- `block_generation`：对应 `blocked`

## 输出要求

输出门禁中间结论，不要生成正式测试用例。

必须包含：

- `quality_gate`
- `generation_policy`
- `generation_policy_reason`
- `missing_or_ambiguous_items`
- `suggestions_to_improve`
- `assumptions`
