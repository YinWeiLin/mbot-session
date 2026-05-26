---
name: need-stimulation
description: 需求激发策略，在用户进入认真考虑或准备行动阶段时触发，生成引导话术。由调度器按会话阶段和频率策略插入，不由 IntentionAgent 直接调度。
---

# Need Stimulation（需求激发）

根据当前会话阶段生成话术，引导用户留资或预约。

## When to Use

由 OrchestrationAgent._should_engage() 控制触发时机：
- `considering` 阶段：每隔 2 轮触发，生成 soft_nudge 话术
- `acting` 阶段：每轮触发，生成 direct_ask 话术
- `looking` 阶段：不触发

## 返回格式

```json
{
  "engage_text": "话术文案",
  "engage_type": "soft_nudge | direct_ask",
  "urgency": "low | medium | high"
}
```
