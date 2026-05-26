"""
需求激发智能体
职责：根据会话阶段生成引导话术，不负责判断是否触发（由调度器保证）
"""
from agentscope.agent import AgentBase
from agentscope.message import Msg
from utils.llm_resilience import parse_llm_response
from typing import Optional, Union, List
import json
import logging
import sys
import os

_pr = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
sys.path.insert(0, _pr)
sys.path.insert(0, os.path.join(_pr, "src"))

logger = logging.getLogger(__name__)


class NeedStimulationAgent(AgentBase):
    """需求激发智能体"""

    def __init__(self, name: str = "NeedStimulationAgent", model=None, **kwargs):
        super().__init__()
        self.name = name
        self.model = model

    async def reply(self, x: Optional[Union[Msg, List[Msg]]] = None) -> Msg:
        if x is None:
            return Msg(name=self.name, content=json.dumps({"engage_text": "", "engage_type": "skip", "urgency": "low"}, ensure_ascii=False), role="assistant")

        content = x.content if not isinstance(x, list) else x[-1].content
        try:
            data = json.loads(content) if isinstance(content, str) else content
        except json.JSONDecodeError:
            data = {}

        context = data.get("context", {})
        session_stage = context.get("session_stage", "looking")
        previous_results = data.get("previous_results", [])

        # 从前序结果里提取主回答
        main_answer = ""
        for r in previous_results:
            if not isinstance(r, dict):
                continue
            if r.get("agent_name") == "rag_knowledge":
                main_answer = (r.get("data", {}) or {}).get("answer", "")
                break

        if session_stage == "acting":
            engage_type = "direct_ask"
            urgency = "high"
        else:
            engage_type = "soft_nudge"
            urgency = "medium"

        prompt = f"""你是一名专业的商家销售顾问，正在与客户对话。

【当前对话阶段】{session_stage}（considering=认真考虑，acting=准备行动）

【本轮主回答】
{main_answer or "（无）"}

【任务】
根据以上信息，生成一句自然的引导话术，附加在主回答之后。

要求：
- {"直接邀请用户留下联系方式或预约，语气坚定但不强硬" if engage_type == "direct_ask" else "轻描淡写地提示用户可以进一步咨询，不要强迫"}
- 语气自然，像真人顾问，不要像广告
- 不超过 30 字

【输出格式】（严格 JSON）
{{
    "engage_text": "话术文案",
    "engage_type": "{engage_type}",
    "urgency": "{urgency}"
}}
"""

        try:
            response = await self.model([{"role": "user", "content": prompt}])
            text = await parse_llm_response(response)
            text = text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                result = json.loads(text[start:end + 1])
            else:
                raise ValueError("No JSON found")
        except Exception as e:
            logger.error(f"NeedStimulationAgent failed: {e}")
            fallback = "感兴趣的话欢迎留下联系方式，我们顾问会进一步介绍。" if engage_type == "soft_nudge" else "您方便留个电话吗？我们安排专人跟进。"
            result = {"engage_text": fallback, "engage_type": engage_type, "urgency": urgency}

        return Msg(name=self.name, content=json.dumps(result, ensure_ascii=False), role="assistant")
