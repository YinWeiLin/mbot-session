---
name: query-info
description: 当用户需要查询实时信息或进行网络搜索时使用此技能。触发词："查一下XX"、"搜索XX"、"XX最新消息"。使用 InformationQueryAgent（网络搜索来源：DDGS）。课程/价格/师资等知识库内的问题请使用 ask-question（RAG）。
---

# Query Information (网络搜索)

查询**实时网络信息**（DDGS），使用 **InformationQueryAgent**。课程、价格、师资等商家知识类问题由 **ask-question**（RAG）处理。

## When to Use

- 用户问「查一下XX」「XX最新消息」「XX机构怎么样」等需要联网的问题
- 不需要用 RAG 知识库、不需要用户记忆时

## Agent

- **InformationQueryAgent** (`skills/query-info/script/agent.py`)
- 入参为 **model 对象**
- **异步**：`reply()` 为 `async`，需 `await`

## 支持的查询类型

1. **网络搜索**：基于 DDGS（需 `pip install ddgs`），带摘要，过滤低质来源

## 初始化与调用

```python
import asyncio
from agentscope.message import Msg
from agentscope.model import OpenAIChatModel
from config import LLM_CONFIG
from skills.query_info.script.agent import InformationQueryAgent
import json

async def query_info(user_query: str):
    model = OpenAIChatModel(
        model_name=LLM_CONFIG["model_name"],
        api_key=LLM_CONFIG["api_key"],
        client_kwargs={"base_url": LLM_CONFIG["base_url"], "timeout": 60},
        temperature=LLM_CONFIG.get("temperature", 0.7),
        max_tokens=LLM_CONFIG.get("max_tokens", 2000),
    )
    agent = InformationQueryAgent(name="InformationQueryAgent", model=model)
    user_msg = Msg(name="user", content=user_query, role="user")
    result = await agent.reply(user_msg)
    return json.loads(result.content) if isinstance(result.content, str) else result.content

data = asyncio.run(query_info("考德上教育口碑怎么样？"))
# data: {"query_type": "网络搜索", "query_success": bool, "results": {"summary": "...", "sources": [...]}}
```

## 返回格式

- `query_type`: `"网络搜索"`
- `query_success`: 是否成功
- `results`: 含 `summary`、`sources`

## 注意

- 本 Agent **不**处理「课程介绍」「套餐价格」「历史咨询」等；课程/产品问题请用 **ask-question**（RAG），历史咨询请用 **memory-query**。
- 网络搜索依赖：`pip install ddgs`。


## 信息查询总结指南

【要求】
1. 直接回答问题，不要说"根据搜索结果"
2. 保持简洁，2-3句话
3. 如果信息不完整，说明需要更多信息
