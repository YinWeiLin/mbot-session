---
name: memory-query
description: 当用户询问自己的历史咨询记录、过往对话内容或已保存的偏好时使用此技能。触发词："我上次问过什么"、"我之前说过什么偏好"、"我的咨询记录"。使用 MemoryQueryAgent，需传入 MemoryManager（user_id、session_id）以访问长期记忆。
---

# Memory Query (记忆查询)

基于用户**长期记忆**回答「我上次问过什么」「我的备考偏好」等问题，使用 **MemoryQueryAgent**。需传入 **MemoryManager** 以访问 `data/memory/{user_id}.json` 中的咨询记录、偏好与聊天摘要。

## When to Use

- 用户问自己历史咨询过的课程、已保存的备考偏好、或过往对话内容时

## Agent

- **MemoryQueryAgent** (`agents/memory_query_agent.py`)
- 入参：**model**、**memory_manager**（必选，否则无记忆可查）
- **异步**：`reply()` 为 `async`，需 `await`

## 依赖

- **MemoryManager**：`memory_system.memory_manager.MemoryManager(user_id, session_id, storage_path, llm_model)`
- 长期记忆存储：`data/memory/{user_id}.json`

## 初始化与调用

```python
import asyncio
import json
from agentscope.message import Msg
from agentscope.model import OpenAIChatModel
from config import LLM_CONFIG
from memory_system.memory_manager import MemoryManager
from skills.memory_query.script.agent import MemoryQueryAgent

async def memory_query(user_query: str, user_id: str = "default_user", session_id: str = "default"):
    model = OpenAIChatModel(
        model_name=LLM_CONFIG["model_name"],
        api_key=LLM_CONFIG["api_key"],
        client_kwargs={"base_url": LLM_CONFIG["base_url"], "timeout": 60},
        temperature=LLM_CONFIG.get("temperature", 0.7),
        max_tokens=LLM_CONFIG.get("max_tokens", 2000),
    )
    memory_manager = MemoryManager(user_id=user_id, session_id=session_id, llm_model=model)
    agent = MemoryQueryAgent(
        name="MemoryQueryAgent",
        model=model,
        memory_manager=memory_manager,
    )
    user_msg = Msg(
        name="user",
        content=json.dumps({"context": {"rewritten_query": user_query}}),
        role="user",
    )
    result = await agent.reply(user_msg)
    return json.loads(result.content) if isinstance(result.content, str) else result.content

# 使用
data = asyncio.run(memory_query("我上次咨询过什么课程？"))
# data: {"status": "success", "query": "...", "answer": "...", "memory_sources": {"has_preferences", "has_chat_summary"}}
```

## 返回格式

- `status`: `"success"` 或 `"error"`
- `query`: 用户问题
- `answer`: 基于记忆的自然语言回答
- `memory_sources`: `has_preferences`, `has_chat_summary`


## 回答指南

【回答要求】
1. 直接基于上述记忆信息回答问题
2. 如果记忆中没有相关信息，诚实说明"记录中没有相关信息"
3. 回答要自然、准确、有条理
4. 如果有多条记录，可以按时间顺序或分类列举
5. 不要编造不存在的信息

请直接回答用户的问题。
