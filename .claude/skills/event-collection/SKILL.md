---
name: event-collection
description: 在 LOOKING 阶段由调度器自动插入的内部辅助技能。从用户输入中提取备考相关结构化信息（考试类型、目标岗位、备考状态、预算等），并生成一个自然口语化的追问。有追问时调度器短路本轮其他 Agent，只输出追问。
---

# Need Clarification（需求澄清）

在 **LOOKING 阶段**每轮自动运行，提取用户备考信息并生成追问，直到关键字段收集完毕。

## 触发条件

- 由 `OrchestrationAgent` 在 `session_stage == LOOKING` 时强制插入，优先级最高
- 有 `follow_up_question` 时短路其他 Agent，本轮只输出追问
- `follow_up_question` 为 null 时正常走后续调度（RAG 等）

## 提取字段

| 字段 | 含义 | 示例 |
|------|------|------|
| exam_type | 考试类型 | 省考 / 国考 / 选调生 |
| target_position | 目标岗位 | 省市岗 / 县乡岗 / 执法岗 |
| study_status | 备考状态 | 应届生 / 在职备考 |
| exam_stage | 当前阶段 | 备考笔试 / 已过笔试备考面试 |
| budget | 预算范围 | 1万以内 / 2万左右 |
| location | 所在城市 | 长沙 / 湖南 |

## 追问优先级

`exam_stage → exam_type → study_status → budget`（每次只追问一个）

## 返回格式

```json
{
    "exam_type": "省考",
    "target_position": null,
    "study_status": "应届生",
    "exam_stage": null,
    "budget": null,
    "location": "长沙",
    "extracted_count": 3,
    "follow_up_question": "请问您目前是备考笔试还是准备面试呢？"
}
```
