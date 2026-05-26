#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
mbot 商家智能体 - 核心会话逻辑（纯业务，无 IO 依赖, 由CLI和HTTP各自实现自己的IO形式）
"""
from agentscope.message import Msg
from agentscope.model import OpenAIChatModel
from config import LLM_CONFIG, SYSTEM_CONFIG, RESILIENCE_CONFIG
from memory_system.memory_manager import MemoryManager
from utils.circuit_breaker import CircuitBreaker, CircuitOpenError
from utils.llm_resilience import retry_with_backoff
from utils.logger import setup_logger, set_session_id
from agents.intention_agent import IntentionAgent
from agents.orchestration_agent import OrchestrationAgent
from agents.lazy_agent_registry import LazyAgentRegistry
from constants import SessionStage
import json
import logging
import os
import uuid

logger = logging.getLogger(__name__)

AGENT_DISPLAY_NAMES = {
    "event_collection": "事项收集",
    "preference": "偏好管理",
"information_query": "信息查询",
    "rag_knowledge": "知识库查询",
    "memory_query": "记忆查询",
}


class MbotSession:
    """mbot 商家智能体会话 — 纯业务层，不依赖任何 IO 框架"""

    def __init__(self, user_id: str = "default_user", session_id: str = None):
        self.user_id = user_id
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.memory_manager: MemoryManager = None
        self.orchestrator: OrchestrationAgent = None
        self.intention_agent: IntentionAgent = None
        self.model = None
        self._agent_cache = {}
        self.circuit_breaker: CircuitBreaker = None
        self._initialized = False
        self.session_stage: SessionStage = SessionStage.LOOKING

    async def init(self):
        """初始化核心组件，CLI 和 HTTP 均调用此方法"""
        if self._initialized:
            return

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        setup_logger(project_root)
        set_session_id(self.session_id)

        timeout_sec = SYSTEM_CONFIG.get("timeout", 60)
        self.model = OpenAIChatModel(
            model_name=LLM_CONFIG["model_name"],
            api_key=LLM_CONFIG["api_key"],
            stream=False,
            client_kwargs={
                "base_url": LLM_CONFIG["base_url"],
                "timeout": float(timeout_sec),
            },
            temperature=LLM_CONFIG.get("temperature", 0.7),
            max_tokens=LLM_CONFIG.get("max_tokens", 2000),
        )

        self.memory_manager = MemoryManager(
            user_id=self.user_id,
            session_id=self.session_id,
            llm_model=self.model,
        )

        self.intention_agent = IntentionAgent(name="IntentionAgent", model=self.model)

        self._agent_cache = {}
        lazy_registry = LazyAgentRegistry(
            model=self.model,
            cache=self._agent_cache,
            memory_manager=self.memory_manager,
        )

        self.orchestrator = OrchestrationAgent(
            name="OrchestrationAgent",
            agent_registry=lazy_registry,
            memory_manager=self.memory_manager,
        )

        rc = RESILIENCE_CONFIG
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=rc.get("circuit_failure_threshold", 5),
            recovery_timeout_sec=rc.get("circuit_recovery_timeout_sec", 60.0),
            half_open_successes=rc.get("circuit_half_open_successes", 2),
        )

        self._initialized = True
        logger.info(f"MbotSession 初始化完成 user={self.user_id} ssid={self.session_id}")

    async def process_query(self, user_input: str) -> str:
        """处理用户消息，返回回复字符串"""
        if not self._initialized:
            raise RuntimeError("MbotSession.init() must be called before process_query()")
        if self.circuit_breaker:
            try:
                self.circuit_breaker.raise_if_open()
            except CircuitOpenError:
                return "服务暂时不可用，请稍后再试。"

        rc = RESILIENCE_CONFIG
        max_retries = rc.get("max_retries", 3)

        # 1. 构建上下文
        long_term_summary = await self._get_long_term_summary(user_input)
        recent_context = self.memory_manager.short_term.get_recent_context(n_turns=5)
        context_messages = []
        if long_term_summary:
            context_messages.append(Msg(name="system", content=long_term_summary, role="system"))
        for msg in recent_context:
            context_messages.append(Msg(name=msg["role"], content=msg["content"], role=msg["role"]))
        context_messages.append(Msg(name="user", content=user_input, role="user"))

        # 2. 意图识别
        try:
            intention_result = await retry_with_backoff(
                lambda: self.intention_agent.reply(context_messages),
                max_retries=max_retries,
                base_delay_sec=rc.get("retry_base_delay_sec", 1.0),
                max_delay_sec=rc.get("retry_max_delay_sec", 30.0),
            )
            if self.circuit_breaker:
                self.circuit_breaker.record_success()
        except CircuitOpenError:
            raise
        except Exception:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            raise

        # 3. 校验意图结果，并推进会话阶段（只进不退），写回后调度器拿到的永远是历史最高阶段
        try:
            intention_data = json.loads(intention_result.content)
        except json.JSONDecodeError:
            return "无法理解您的需求，请重新描述。"

        try:
            llm_stage = SessionStage[intention_data.get("session_stage", "").upper()]
        except KeyError:
            llm_stage = SessionStage.LOOKING
        logger.info(f"会话阶段: 当前={self.session_stage.name} LLM识别={llm_stage.name}")
        if llm_stage > self.session_stage:
            logger.info(f"会话阶段推进: {self.session_stage.name} → {llm_stage.name}")
            self.session_stage = llm_stage
            peak_str = self.memory_manager.long_term.get_preference("peak_session_stage") or "looking"
            try:
                peak = SessionStage[peak_str.upper()]
            except KeyError:
                peak = SessionStage.LOOKING
            if self.session_stage > peak:
                self.memory_manager.long_term.save_preference("peak_session_stage", self.session_stage.name.lower())

        intention_data["session_stage"] = self.session_stage.name.lower()
        intention_result = Msg(
            name=intention_result.name,
            content=json.dumps(intention_data, ensure_ascii=False),
            role=intention_result.role,
        )

        # 4. 写短期记忆
        self.memory_manager.add_message("user", user_input)

        # 5. 调度智能体
        try:
            orchestration_result = await retry_with_backoff(
                lambda: self.orchestrator.reply(intention_result),
                max_retries=max_retries,
                base_delay_sec=rc.get("retry_base_delay_sec", 1.0),
                max_delay_sec=rc.get("retry_max_delay_sec", 30.0),
            )
            if self.circuit_breaker:
                self.circuit_breaker.record_success()
        except CircuitOpenError:
            raise
        except Exception:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            raise

        # 6. 解析并返回结果
        try:
            result_data = json.loads(orchestration_result.content)
        except json.JSONDecodeError:
            result_data = {"error": "解析结果失败"}

        reply_text = self._collect_reply(result_data)
        self.memory_manager.add_message("assistant", json.dumps(result_data, ensure_ascii=False))

        return reply_text

    def end_session(self):
        """结束会话，持久化记忆"""
        if self.memory_manager:
            self.memory_manager.end_session()

    # ------------------------------------------------------------------ #
    # 以下为内部辅助方法，供 process_query 使用                            #
    # ------------------------------------------------------------------ #

    async def _get_long_term_summary(self, user_input: str = "") -> str:
        """生成长期记忆摘要，注入到 IntentionAgent 上下文"""
        parts = []

        prefs = self.memory_manager.long_term.get_preference()
        if prefs:
            pref_lines = ["【用户背景信息】（来自长期记忆，可用于推断缺失信息）"]
            for k, v in prefs.items():
                if v:
                    pref_lines.append(f"• {k}: {', '.join(v) if isinstance(v, list) else v}")
            if len(pref_lines) > 1:
                parts.extend(pref_lines)

        chat_summary = await self.memory_manager.get_long_term_summary_async(max_messages=50)
        if chat_summary:
            parts.append("\n【历史会话总结】")
            parts.append(chat_summary)

        all_trips = self.memory_manager.long_term.get_trip_history(limit=None)
        if all_trips:
            relevant = [t for t in all_trips if
                        (t.get("origin", "") and t["origin"] in user_input) or
                        (t.get("destination", "") and t["destination"] in user_input)]
            others = [t for t in all_trips if t not in relevant]
            to_show = relevant[:2] + others[:1]
            if to_show:
                parts.append("\n【历史行程】")
                for i, t in enumerate(to_show[:3], 1):
                    mark = "✦ " if t in relevant else ""
                    parts.append(
                        f"{i}. {mark}{t.get('origin','未知')} → {t.get('destination','未知')} "
                        f"({t.get('start_date','')}) - {t.get('purpose','')}"
                    )

        return "\n".join(parts) if parts else ""

    def _collect_reply(self, result_data: dict) -> str:
        """从 Agent 执行结果中提取回复文本"""
        results = result_data.get("results", [])

        if not results:
            if result_data.get("status") == "no_agents":
                return "好的，我已记录下来。您可以继续补充信息。"
            return "未能获取有效结果，请重新描述您的需求。"

        lines = []
        for result in results:
            agent_name = result.get("agent_name", "")
            status = result.get("status", "")
            data = result.get("data", {})

            if status == "error":
                lines.append(f"{AGENT_DISPLAY_NAMES.get(agent_name, agent_name)}执行失败: {data.get('error', '未知错误')}")
                continue

            if status != "success" and not (agent_name == "rag_knowledge" and status == "no_knowledge"):
                continue

            text = self._extract_agent_text(agent_name, data, results)
            lines.append(text if text else f"{AGENT_DISPLAY_NAMES.get(agent_name, agent_name)}已完成")

        return "\n".join(lines) if lines else "已处理您的请求。"

    def _extract_agent_text(self, agent_name: str, data: dict, all_results: list) -> str:
        """从单个 Agent 的 data 中提取纯文本"""
        def nested(d, *keys):
            """从 data 或 data.data 中依次尝试多个 key"""
            inner = d.get("data", {}) if isinstance(d.get("data"), dict) else {}
            for k in keys:
                if isinstance(d.get(k), str) and d[k].strip():
                    return d[k]
                if isinstance(inner.get(k), str) and inner[k].strip():
                    return inner[k]
            return ""

        if agent_name == "rag_knowledge":
            answer = nested(data, "answer", "content")
            if isinstance(answer, dict):
                answer = answer.get("answer", str(answer))
            if isinstance(answer, str) and answer.strip().startswith("{"):
                try:
                    answer = json.loads(answer).get("answer", answer)
                except Exception:
                    pass
            return answer or ""

        if agent_name == "memory_query":
            return nested(data, "answer", "result", "content")

        if agent_name == "information_query":
            qr = data.get("results") or (data.get("data", {}) or {}).get("results") or data
            if not isinstance(qr, dict):
                qr = {}
            text = qr.get("summary") or qr.get("message") or qr.get("error") or ""
            sources = qr.get("sources", [])
            if sources:
                urls = ", ".join((s.get("url", "") if isinstance(s, dict) else str(s)) for s in sources[:3])
                text = f"{text}\n参考来源：{urls}" if text else f"参考来源：{urls}"
            return text

        if agent_name == "preference":
            raw = data.get("preferences") or (data.get("data", {}) or {}).get("preferences")
            prefs_list = raw.get("preferences", []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
            if not prefs_list:
                err = data.get("error", "")
                return f"偏好未保存: {err}" if err else ""
            type_names = {
                "home_location": "常驻地", "transportation_preference": "交通偏好",
                "hotel_brands": "酒店偏好", "airlines": "航空公司偏好",
                "seat_preference": "座位偏好", "meal_preference": "餐食偏好",
                "budget_level": "预算等级",
            }
            lines = ["已更新偏好设置："]
            for p in prefs_list:
                action = "追加" if p.get("action") == "append" else "设置为"
                lines.append(f"  {type_names.get(p.get('type',''), p.get('type',''))} {action} {p.get('value','')}")
            if not any(r.get("agent_name") == "rag_knowledge" for r in all_results):
                lines.append("下次规划时会参考这些偏好。")
            return "\n".join(lines)

        if agent_name == "event_collection":
            follow_up = data.get("follow_up_question") or (data.get("data", {}) or {}).get("follow_up_question")
            return follow_up or ""

        if agent_name == "need_stimulation":
            return data.get("engage_text", "")

        # 通用兜底
        common_keys = ["answer", "content", "result", "message", "summary", "text", "description"]
        return nested(data, *common_keys)
