"""
需求澄清智能体 NeedClarificationAgent
职责：在 LOOKING 阶段主动收集用户关键备考信息，每次只追问一个最关键的缺失字段

核心功能：
- 从用户输入中提取备考相关结构化信息
- 识别缺失的关键字段，生成一个自然口语化的追问
- 信息齐全时 follow_up_question 为 null，调度器据此决定是否跳过 RAG
"""
from agentscope.agent import AgentBase
from agentscope.message import Msg
from typing import Optional, Union, List
from utils.llm_resilience import parse_llm_response
import json
import logging
import sys
import os

_pr = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
sys.path.insert(0, _pr)
sys.path.insert(0, os.path.join(_pr, 'src'))

logger = logging.getLogger(__name__)


class EventCollectionAgent(AgentBase):
    """需求澄清智能体（复用 event-collection skill 槽位）"""

    def __init__(self, name: str = "EventCollectionAgent", model=None, **kwargs):
        super().__init__()
        self.name = name
        self.model = model

    async def reply(self, x: Optional[Union[Msg, List[Msg]]] = None) -> Msg:
        if x is None:
            return Msg(name=self.name, content=json.dumps({}), role="assistant")

        content = x.content if not isinstance(x, list) else x[-1].content

        user_query = content
        known_info = {}
        if isinstance(content, str):
            try:
                data = json.loads(content)
                context = data.get("context", {})
                user_query = context.get("rewritten_query", "") or str(data)
                known_info = context.get("user_preferences", {})
            except json.JSONDecodeError:
                pass

        # 把已知偏好格式化给 LLM，避免重复追问
        field_labels = {
            "exam_type": "考试类型",
            "target_position": "目标岗位",
            "study_status": "备考状态",
            "exam_stage": "当前阶段",
            "budget": "预算范围",
            "location": "所在城市",
        }
        known_parts = [
            f"• {label}: {known_info[k]}"
            for k, label in field_labels.items()
            if known_info.get(k)
        ]
        known_section = ("【已知用户信息】\n" + "\n".join(known_parts) + "\n\n") if known_parts else ""

        prompt = f"""你是WiLyn教育的智能客服，负责了解用户备考需求以便推荐合适的课程。

{known_section}【用户输入】
{user_query}

【提取任务】
请从用户输入中尽可能提取以下字段（未提及的设为 null）：
1. exam_type - 考试类型（省考 / 国考 / 选调生 / 事业单位 / 其他）
2. target_position - 目标岗位（省市岗 / 县乡岗 / 执法岗 / 烟草岗 / 公安岗 / 其他）
3. study_status - 备考状态（应届生 / 在职备考 / 全职备考 / 二战及以上）
4. exam_stage - 当前阶段（备考笔试 / 已过笔试备考面试 / 待定）
5. budget - 预算范围（如"1万以内" / "2万左右" / "不限"）
6. location - 所在城市/省份

【追问规则】
- 只在以下关键字段缺失时生成 follow_up_question，优先级依次为：
  exam_stage → exam_type → study_status → budget
- 每次只追问一个，问题要自然口语化，不超过 20 字
- 已知字段不追问
- 若关键字段都已知，follow_up_question 设为 null

【输出格式】(严格JSON，无其他文字)
{{
    "exam_type": null,
    "target_position": null,
    "study_status": null,
    "exam_stage": null,
    "budget": null,
    "location": null,
    "extracted_count": 0,
    "follow_up_question": "请问您目前是备考笔试还是准备面试呢？"
}}
"""

        try:
            response = await self.model([{"role": "user", "content": prompt}])
            text = await parse_llm_response(response)

            text = text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            start_idx = text.find("{")
            end_idx = text.rfind("}")
            if start_idx != -1 and end_idx != -1:
                result = json.loads(text[start_idx:end_idx + 1])
            else:
                raise ValueError("No JSON found in response")

        except Exception as e:
            logger.error(f"Need clarification failed: {e}")
            result = {
                "exam_type": None, "target_position": None,
                "study_status": None, "exam_stage": None,
                "budget": None, "location": None,
                "extracted_count": 0, "follow_up_question": None,
                "error": str(e),
            }

        logger.info(f"需求澄清: extracted={result.get('extracted_count', 0)}, follow_up={result.get('follow_up_question')}")
        return Msg(name=self.name, content=json.dumps(result, ensure_ascii=False), role="assistant")
