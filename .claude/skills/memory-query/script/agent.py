"""
记忆查询智能体 MemoryQueryAgent
职责：基于用户的长期记忆回答历史相关问题

核心功能：
1. 查询用户偏好（preferences）
2. 查询历史对话记录（chat_history）
3. 使用LLM基于记忆生成自然语言回答

适用场景：
- 用户询问："我之前说过什么偏好？"
- 用户询问："我上次咨询过什么课程？"
"""
from agentscope.agent import AgentBase
from agentscope.message import Msg
from typing import Optional, Union, List, Dict
from utils.llm_resilience import parse_llm_response
import json
import logging
import sys
import os

# Add project root to sys.path
_pr = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
sys.path.insert(0, _pr)
sys.path.insert(0, os.path.join(_pr, 'src'))

logger = logging.getLogger(__name__)


class MemoryQueryAgent(AgentBase):
    """记忆查询智能体 - 基于长期记忆回答用户问题"""

    def __init__(
        self,
        name: str = "MemoryQueryAgent",
        model=None,
        memory_manager=None,
        **kwargs
    ):
        super().__init__()
        self.name = name
        self.model = model
        self.memory_manager = memory_manager
        from utils.skill_loader import SkillLoader
        self.skill_loader = SkillLoader()

    async def reply(self, x: Optional[Union[Msg, List[Msg]]] = None) -> Msg:
        """
        处理记忆查询请求

        Args:
            x: 输入消息，包含用户查询和上下文

        Returns:
            Msg: 基于记忆的回答
        """
        if x is None:
            return Msg(name=self.name, content=json.dumps({}), role="assistant")

        # 解析输入
        if isinstance(x, list):
            input_content = x[-1].content if x else "{}"
        else:
            input_content = x.content

        try:
            input_data = json.loads(input_content) if isinstance(input_content, str) else input_content
        except json.JSONDecodeError:
            input_data = {"context": {"rewritten_query": str(input_content)}}

        # 获取用户查询
        context = input_data.get("context", {})
        user_query = context.get("rewritten_query", "")
        if not user_query:
            # 尝试从 recent_dialogue 获取最后一条用户消息
            recent_dialogue = context.get("recent_dialogue", [])
            if recent_dialogue:
                for msg in reversed(recent_dialogue):
                    if msg.get("role") == "user":
                        user_query = msg.get("content", "")
                        break

        if not user_query:
            return Msg(
                name=self.name,
                content=json.dumps({
                    "status": "error",
                    "message": "无法获取用户查询"
                }),
                role="assistant"
            )

        # 获取长期记忆
        preferences = {}
        chat_summary = ""

        if self.memory_manager:
            # 获取用户偏好
            preferences = self.memory_manager.long_term.get_preference()

            # 获取历史对话摘要（如果有LLM的话）
            try:
                chat_summary = await self.memory_manager.get_long_term_summary_async(max_messages=30)
            except Exception as e:
                logger.warning(f"Failed to get chat summary: {e}")
                chat_summary = ""

        # 格式化偏好
        pref_text = self._format_preferences(preferences)

        # 动态读取 Prompt 指令 (Progressive Disclosure)
        skill_instruction = self.skill_loader.get_skill_content("memory-query")
        if not skill_instruction:
            skill_instruction = "请基于用户的历史记忆回答问题，如无相关记录请诚实说明。"

        # 构建 prompt
        prompt = f"""你是WiLyn教育的智能客服，请基于用户的历史咨询记录回答问题。

【用户问题】
{user_query}

【用户备考偏好】
{pref_text}

【历史对话摘要】
{chat_summary if chat_summary else "（暂无历史对话摘要）"}

【任务说明】
{skill_instruction}
"""

        try:
            # 调用LLM生成回答
            response = await self.model([
                {"role": "system", "content": "你是一个个人记忆助手，帮助用户查询和理解他们的历史记录。"},
                {"role": "user", "content": prompt}
            ])

            # 获取响应文本
            answer = await parse_llm_response(response)

            if not answer:
                answer = "无法基于记忆生成回答"

            logger.info(f"Memory query answered: {user_query[:50]}")

            result = {
                "status": "success",
                "query": user_query,
                "answer": answer,
                "memory_sources": {
                    "has_preferences": any(v for v in preferences.values() if v),
                    "has_chat_summary": bool(chat_summary)
                }
            }

            return Msg(name=self.name, content=json.dumps(result, ensure_ascii=False), role="assistant")

        except Exception as e:
            logger.error(f"Memory query failed: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

            return Msg(
                name=self.name,
                content=json.dumps({
                    "status": "error",
                    "message": f"记忆查询失败: {str(e)}",
                    "query": user_query
                }),
                role="assistant"
            )

    def _format_preferences(self, preferences: Dict) -> str:
        """格式化用户偏好"""
        if not preferences or not any(v for v in preferences.values() if v):
            return "（暂无偏好记录）"

        lines = []
        pref_names = {
            "exam_type": "考试类型",
            "target_position": "目标岗位",
            "study_status": "备考状态",
            "exam_stage": "当前阶段",
            "budget": "预算范围",
            "location": "所在城市",
            "peak_session_stage": "历史最高意向阶段",
        }

        for key, value in preferences.items():
            if value:
                label = pref_names.get(key, key)
                lines.append(f"- {label}: {value}")

        return "\n".join(lines) if lines else "（暂无偏好记录）"
