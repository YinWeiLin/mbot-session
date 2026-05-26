#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 mbot 智能体协调系统
"""
import sys
import os
import asyncio
import json

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

from agentscope.model import OpenAIChatModel
from agentscope.message import Msg
from config import LLM_CONFIG
from memory_system.memory_manager import MemoryManager
from agents.intention_agent import IntentionAgent
from agents.orchestration_agent import OrchestrationAgent
from agents.lazy_agent_registry import LazyAgentRegistry


async def test_orchestration():
    print("=" * 70)
    print("mbot 智能体协调系统测试")
    print("=" * 70)

    model = OpenAIChatModel(
        model_name=LLM_CONFIG["model_name"],
        api_key=LLM_CONFIG["api_key"],
        stream=False,
        client_kwargs={"base_url": LLM_CONFIG["base_url"]},
        temperature=LLM_CONFIG.get("temperature", 0.7),
        max_tokens=LLM_CONFIG.get("max_tokens", 2000),
    )
    print("✓ 模型加载成功")

    memory = MemoryManager(user_id="test_user", session_id="test_orch")
    print("✓ 记忆管理器初始化成功")

    intention_agent = IntentionAgent(name="IntentionAgent", model=model)
    agent_cache = {}
    lazy_registry = LazyAgentRegistry(model=model, cache=agent_cache, memory_manager=memory)
    orchestrator = OrchestrationAgent(
        name="OrchestrationAgent",
        agent_registry=lazy_registry,
        memory_manager=memory,
    )
    print("✓ 协调器初始化成功\n")

    cases = [
        ("泛问题（无具体意图）", "你好，请问你们是做什么的？"),
        ("产品咨询（有具体意图）", "鲲鹏旗舰班多少钱？"),
        ("购买意向", "我想预约报名，怎么操作？"),
    ]

    for title, query in cases:
        print(f"[{title}]")
        print(f"用户: {query}")

        intention_msg = Msg(name="user", content=query, role="user")
        intention_result = await intention_agent.reply(intention_msg)

        try:
            intention_data = json.loads(intention_result.content)
            print(f"  意图: {[i['type'] for i in intention_data.get('intents', [])]}")
            print(f"  阶段: {intention_data.get('session_stage')}")
        except json.JSONDecodeError as e:
            print(f"  ✗ 意图识别失败: {e}")
            continue

        orch_result = await orchestrator.reply(intention_result)
        try:
            result_data = json.loads(orch_result.content)
            print(f"  执行状态: {result_data.get('status')}")
            for r in result_data.get("results", []):
                print(f"    • {r.get('agent_name')}: {r.get('status')}")
        except json.JSONDecodeError as e:
            print(f"  ✗ 协调执行失败: {e}")

        print()

    print("=" * 70)
    print("✅ 测试完成")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_orchestration())
