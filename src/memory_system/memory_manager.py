from .short_term_memory import ShortTermMemory
from .long_term_memory import LongTermMemory
from prompts.memory.index import get_long_term_summary_prompt
from utils.llm_resilience import parse_llm_response
import logging

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    记忆管理器：统一管理两层记忆
    - 短期记忆：最近对话（会话级）
    - 长期记忆：用户偏好和历史（跨会话）
    """

    def __init__(self, user_id: str, session_id: str, storage_path: str = "data/memory", llm_model=None):
        """
        初始化记忆管理器

        Args:
            user_id: 用户ID
            session_id: 会话ID
            storage_path: 长期记忆存储路径
            llm_model: LLM模型实例 - 用于总结长期记忆
        """
        self.user_id = user_id
        self.session_id = session_id
        self.llm_model = llm_model

        # 初始化两层记忆
        self.short_term = ShortTermMemory(max_turns=10)
        self.long_term = LongTermMemory(user_id, storage_path)

        # 长期摘要本地缓存：避免每轮重复 LLM 调用
        self._summary_cache: str = ""
        self._summary_cache_msg_count: int = -1

        logger.info(f"记忆管理器初始化完成，用户: {user_id}，会话: {session_id}")

    # ========== 短期记忆操作 ==========

    def add_message(self, role: str, content: str, metadata: dict = None):
        """
        添加消息到短期记忆和长期记忆

        Args:
            role: 角色 (user/assistant)
            content: 消息内容
            metadata: 元数据
        """
        # 添加到短期记忆（当前会话）
        self.short_term.add_message(role, content, metadata)

        # 同时添加到长期记忆（跨会话持久化）
        self.long_term.add_chat_message(role, content, self.session_id)

    # ========== 长期记忆操作 ==========
    # 注意：大部分方法直接使用 self.short_term 和 self.long_term 即可，无需封装

    # ========== 会话管理 ==========

    def end_session(self):
        """结束会话"""
        self.short_term.clear()
        logger.info(f"会话结束: {self.session_id}")

    async def get_long_term_summary_async(self, max_messages: int = 50) -> str:
        """
        使用LLM总结长期聊天历史 - 异步版本 

        Args:
            max_messages: 最多总结的消息数量

        Returns:
            总结后的文本
        """
        if not self.llm_model:
            return ""

        # 获取长期聊天历史（排除当前会话）
        all_history = self.long_term.get_chat_history(limit=max_messages)
        history_from_other_sessions = [
            msg for msg in all_history
            if msg.get("session_id") != self.session_id
        ]

        if not history_from_other_sessions:
            return ""

        # 消息条数没变，直接返回缓存，跳过 LLM 调用
        if len(history_from_other_sessions) == self._summary_cache_msg_count:
            logger.info("长期记忆摘要命中缓存，跳过 LLM 总结")
            return self._summary_cache

        history_str = self._format_history_msg_text(history_from_other_sessions[-max_messages:])

        # 使用LLM总结
        summarization_prompt = get_long_term_summary_prompt(history_str)

        try:
            # 调用模型（异步调用）
            response = await self.llm_model([{"role": "user", "content": summarization_prompt}])
            summary = await parse_llm_response(response)

            logger.info(f"长期记忆摘要生成完成（{len(summary)} 字）")
            self._summary_cache = summary.strip()
            self._summary_cache_msg_count = len(history_from_other_sessions)
            return self._summary_cache

        except Exception as e:
            logger.error(f"生成长期记忆摘要失败: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return ""

    def _format_history_msg_text(self, messages: list[dict]) -> str:
        history_text = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            timestamp = msg.get("timestamp", "")
            history_text.append(f"[{timestamp}] {role}: {content}")
        return "\n".join(history_text) if history_text else "（无聊天记录）"

    def get_long_term_summary(self, max_messages: int = 50) -> str:
        """
        使用LLM总结长期聊天历史（同步版本）

        Args:
            max_messages: 最多总结的消息数量

        Returns:
            总结后的文本
        """
        import asyncio

        # 检查是否在事件循环中
        try:
            loop = asyncio.get_running_loop()
            # 已经在事件循环中，不能使用 asyncio.run
            logger.warning("在异步上下文中调用了同步方法 get_long_term_summary，请改用 get_long_term_summary_async")
            return ""
        except RuntimeError:
            # 没有运行的事件循环，可以使用 asyncio.run
            return asyncio.run(self.get_long_term_summary_async(max_messages))
