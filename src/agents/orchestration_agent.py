"""
协调器智能体 OrchestrationAgent
职责：根据意图识别结果，协调调度多个子智能体完成任务

核心功能：
1. 接收 IntentionAgent 的调度决策
2. 按照优先级顺序执行子智能体
3. 管理智能体之间的消息传递
4. 聚合多个智能体的结果
5. 与两层记忆系统集成

执行模式：
- 同优先级并行（asyncio.gather）：Priority 1 的信息收集类智能体同时执行
- 跨优先级串行：Priority 2 的行程规划智能体等待 Priority 1 全部完成后执行
"""
from agentscope.agent import AgentBase
from agentscope.message import Msg
from typing import Optional, Union, List, Dict, Any
from constants import SessionStage
import json
import logging
import asyncio

logger = logging.getLogger(__name__)


class OrchestrationAgent(AgentBase):
    """协调器智能体 - 调度和协调多个子智能体"""

    def __init__(
        self,
        name: str = "OrchestrationAgent",
        agent_registry: Dict[str, AgentBase] = None,
        memory_manager = None,
    ):
        """
        初始化协调器

        Args:
            name: 智能体名称
            agent_registry: 子智能体注册表 {agent_name: agent_instance}
            memory_manager: 记忆管理器
        """
        super().__init__()
        self.name = name
        self.agent_registry = agent_registry or {}
        self.memory_manager = memory_manager
        self.turn_count: int = 0  # 当前会话已处理轮次，用于控制 need_stimulation 的触发频率

    def register_agent(self, agent_name: str, agent: AgentBase):
        """注册子智能体"""
        self.agent_registry[agent_name] = agent
        logger.info(f"已注册智能体: {agent_name}")

    def unregister_agent(self, agent_name: str):
        """注销子智能体"""
        if agent_name in self.agent_registry:
            del self.agent_registry[agent_name]
            logger.info(f"已注销智能体: {agent_name}")

    async def reply(self, x: Optional[Union[Msg, List[Msg]]] = None) -> Msg:
        """
        协调执行流程

        Args:
            x: 输入消息，应包含 IntentionAgent 的输出

        Returns:
            Msg: 执行结果
        """
        if x is None:
            return Msg(
                name=self.name,
                content=json.dumps({"error": "No input provided"}),
                role="assistant"
            )

        self.turn_count += 1

        # 解析输入
        if isinstance(x, list):
            intention_output = x[-1].content if x else "{}"
        else:
            intention_output = x.content

        # 解析意图识别结果
        try:
            intention_data = json.loads(intention_output) if isinstance(intention_output, str) else intention_output
        except json.JSONDecodeError as e:
            logger.error(f"解析意图识别结果失败: {e}")
            return Msg(
                name=self.name,
                content=json.dumps({"error": "Invalid intention format"}),
                role="assistant"
            )

        # 获取智能体调度计划
        agent_schedule = intention_data.get("agent_schedule", [])
        if not agent_schedule:
            return Msg(
                name=self.name,
                content=json.dumps({
                    "status": "no_agents",
                    "message": "没有需要调度的智能体"
                }),
                role="assistant"
            )

        # 按优先级排序，need_stimulation 由调度器按策略插入 判断当前会话阶段
        if self._should_engage(intention_data):
            agent_schedule.append({
                "agent_name": "need_stimulation",
                "priority": 999,
                "reason": "需求激发策略触发",
                "expected_output": "engage_text"
            })

        try:
            stage = SessionStage[intention_data.get("session_stage", "looking").upper()]
        except KeyError:
            stage = SessionStage.LOOKING

        # 判断是否有具体意图（有则走 RAG，无则跳过 RAG 只追问）
        EXPLICIT_INTENTS = {"price_inquiry", "product_inquiry", "comparison", "purchase_intent"}
        intents = intention_data.get("intents", [])
        has_explicit_intent = any(
            i.get("type") in EXPLICIT_INTENTS for i in intents if isinstance(i, dict)
        )

        # 需求澄清：LOOKING / CONSIDERING 阶段运行，ACTING 阶段跳过
        context = self._prepare_context(intention_data)
        clarif_result = None
        if stage in (SessionStage.LOOKING, SessionStage.CONSIDERING):
            context = self._prepare_context(intention_data)
            clarif_result = await self._execute_agent(
                "event_collection", context, "需求澄清", "follow_up_question", []
            )
            if clarif_result.get("status") != "error":
                clarif_data = clarif_result.get("data", {})
                # 提取到的字段写入用户偏好
                if self.memory_manager:
                    for field in ("exam_type", "target_position", "study_status", "exam_stage", "budget", "location"):
                        val = clarif_data.get(field)
                        if val:
                            self.memory_manager.long_term.save_preference(field, val)
                follow_up = clarif_data.get("follow_up_question")
                if follow_up and not has_explicit_intent:
                    # 无具体意图 + 有追问 → 只输出追问，跳过所有其他 Agent
                    logger.info(f"无具体意图，需求澄清短路: {follow_up}")
                    wrapped = {"agent_name": "event_collection", "priority": 0, "result": clarif_result}
                    final_result = self._aggregate_results([wrapped], intention_data)
                    return Msg(
                        name=self.name,
                        content=json.dumps(final_result, ensure_ascii=False),
                        role="assistant"
                    )
                # 有具体意图 + 有追问 → 继续走 RAG，追问会在 _aggregate_results 后附上
                # 无追问（信息齐了）→ 继续走 RAG，不追问

        sorted_schedule = sorted(agent_schedule, key=lambda x: x.get("priority", 999))

        logger.info(f"开始协调调度 {len(sorted_schedule)} 个智能体")

        # 并行执行智能体（按优先级分组）
        results = []
        current_priority = None
        parallel_tasks = []

        for task in sorted_schedule:
            priority = task.get("priority", 0)

            # 如果优先级变化，先执行当前批次
            if current_priority is not None and priority != current_priority:
                # 并行执行当前优先级的所有任务
                if parallel_tasks:
                    batch_results = await self._execute_parallel_agents(parallel_tasks, context, results)
                    results.extend(batch_results)
                    parallel_tasks = []

            current_priority = priority
            parallel_tasks.append(task)

        # 执行最后一批
        if parallel_tasks:
            batch_results = await self._execute_parallel_agents(parallel_tasks, context, results)
            results.extend(batch_results)

        # 聚合结果；若有澄清追问（有具体意图时），追加到 results 末尾
        if clarif_result and clarif_result.get("status") != "error":
            follow_up = clarif_result.get("data", {}).get("follow_up_question")
            if follow_up:
                results.append({
                    "agent_name": "event_collection",
                    "priority": 998,
                    "result": clarif_result,
                })
        final_result = self._aggregate_results(results, intention_data)

        # 更新记忆
        if self.memory_manager:
            self._update_memory(results)

        return Msg(
            name=self.name,
            content=json.dumps(final_result, ensure_ascii=False),
            role="assistant"
        )

    def _prepare_context(self, intention_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        准备上下文信息，供子智能体使用

        Args:
            intention_data: 意图识别结果

        Returns:
            上下文字典
        """
        context = {
            "reasoning": intention_data.get("reasoning", ""),
            "intents": intention_data.get("intents", []),
            "key_entities": intention_data.get("key_entities", {}),
            "rewritten_query": intention_data.get("rewritten_query", ""),
            "session_stage": intention_data.get("session_stage", "looking"),
        }

        # 从记忆系统获取上下文
        if self.memory_manager:
            # 短期记忆：最近对话
            recent_context = self.memory_manager.short_term.get_recent_context(3)
            context["recent_dialogue"] = recent_context

            # 长期记忆：用户偏好
            preferences = self.memory_manager.long_term.get_preference()
            context["user_preferences"] = preferences

        return context

    async def _execute_parallel_agents(
        self,
        tasks: List[Dict],
        context: Dict[str, Any],
        previous_results: List[Dict]
    ) -> List[Dict]:
        """
        并行执行多个智能体

        Args:
            tasks: 任务列表，每个任务包含 agent_name, priority, reason, expected_output
            context: 上下文信息
            previous_results: 前序智能体的结果

        Returns:
            执行结果列表
        """
        if not tasks:
            return []

        # 如果只有一个任务，直接执行
        if len(tasks) == 1:
            task = tasks[0]
            result = await self._execute_agent(
                agent_name=task.get("agent_name"),
                context=context,
                reason=task.get("reason", ""),
                expected_output=task.get("expected_output", ""),
                previous_results=previous_results
            )
            return [{
                "agent_name": task.get("agent_name"),
                "priority": task.get("priority", 0),
                "result": result
            }]

        # 多个任务并行执行
        logger.info(f"Executing {len(tasks)} agents in parallel")

        # 创建并行任务
        parallel_coroutines = []
        for task in tasks:
            agent_name = task.get("agent_name")
            priority = task.get("priority", 0)
            reason = task.get("reason", "")
            expected_output = task.get("expected_output", "")

            logger.info(f"并行执行智能体: {agent_name} (优先级={priority})")

            # 创建协程
            coroutine = self._execute_agent(
                agent_name=agent_name,
                context=context,
                reason=reason,
                expected_output=expected_output,
                previous_results=previous_results
            )
            parallel_coroutines.append((agent_name, priority, coroutine))

        # 使用 asyncio.gather 并行执行
        execution_results = await asyncio.gather(
            *[coro for _, _, coro in parallel_coroutines],
            return_exceptions=True
        )

        # 整理结果
        results = []
        for (agent_name, priority, _), exec_result in zip(parallel_coroutines, execution_results):
            if isinstance(exec_result, Exception):
                logger.error(f"Parallel agent execution failed: {agent_name}, error: {exec_result}")
                result = {
                    "status": "error",
                    "agent_name": agent_name,
                    "data": {"error": str(exec_result)},
                    "message": f"并行执行失败: {str(exec_result)}"
                }
            else:
                result = exec_result

            results.append({
                "agent_name": agent_name,
                "priority": priority,
                "result": result
            })

        return results

    async def _execute_agent(
        self,
        agent_name: str,
        context: Dict[str, Any],
        reason: str,
        expected_output: str,
        previous_results: List[Dict]
    ) -> Dict[str, Any]:
        """
        执行单个智能体

        Args:
            agent_name: 智能体名称
            context: 上下文信息
            reason: 调用原因
            expected_output: 期望输出
            previous_results: 前序智能体的结果

        Returns:
            执行结果
        """
        # 检查智能体是否注册
        if agent_name not in self.agent_registry:
            logger.warning(f"Agent not registered: {agent_name}")
            return {
                "status": "error",
                "message": f"智能体未注册: {agent_name}"
            }

        agent = self.agent_registry[agent_name]

        # 构建输入消息
        input_msg = Msg(
            name="Orchestrator",
            content=json.dumps({
                "context": context,
                "reason": reason,
                "expected_output": expected_output,
                "previous_results": previous_results
            }, ensure_ascii=False),
            role="user"
        )

        try:
            # 调用智能体
            response = await agent.reply(input_msg)

            # 解析响应
            if isinstance(response.content, str):
                try:
                    result = json.loads(response.content)
                except json.JSONDecodeError:
                    result = {"output": response.content}
            else:
                result = response.content

            # 检查 result 中是否有 error 字段
            # 如果有，说明智能体内部执行失败了
            if isinstance(result, dict) and "error" in result:
                error_msg = result.get("error", "未知错误")
                return {
                    "status": "error",
                    "agent_name": agent_name,
                    "data": result,
                    "message": error_msg
                }

            return {
                "status": "success",
                "agent_name": agent_name,
                "data": result
            }

        except Exception as e:
            logger.error(f"智能体执行异常: {agent_name}，错误: {e}")
            # 返回友好的错误信息，但不中断流程
            return {
                "status": "error",
                "agent_name": agent_name,
                "data": {"error": str(e)},
                "message": f"智能体执行失败: {str(e)}"
            }

    def _aggregate_results(
        self,
        results: List[Dict],
        intention_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        聚合多个智能体的结果

        Args:
            results: 所有智能体的执行结果
            intention_data: 原始意图识别结果

        Returns:
            聚合后的最终结果
        """
        aggregated = {
            "status": "completed",
            "session_stage": intention_data.get("session_stage", "looking"),
            "intention": {
                "intents": intention_data.get("intents", []),
                "key_entities": intention_data.get("key_entities", {})
            },
            "agents_executed": len(results),
            "results": []
        }

        # 收集每个智能体的结果
        for result in results:
            aggregated["results"].append({
                "agent_name": result["agent_name"],
                "priority": result["priority"],
                "status": result["result"].get("status", "unknown"),
                "data": result["result"].get("data", {})
            })

        # 检查是否有错误
        errors = [r for r in results if r["result"].get("status") == "error"]
        if errors:
            aggregated["status"] = "partial_failure"
            aggregated["errors"] = len(errors)

        return aggregated

    def _update_memory(self, results: List[Dict]):
        if not self.memory_manager:
            return

        # 提取并保存信息到长期记忆
        for result in results:
            agent_name = result["agent_name"]
            data = result["result"].get("data", {})

            # 如果是偏好智能体，保存偏好信息到长期记忆
            if agent_name == "preference" and isinstance(data, dict):
                preferences_data = data.get("preferences", {})

                # 新格式：preferences 是列表，包含 {type, value, action}
                if isinstance(preferences_data, list):
                    for pref_item in preferences_data:
                        if not isinstance(pref_item, dict):
                            continue

                        pref_type = pref_item.get("type")
                        pref_value = pref_item.get("value")
                        pref_action = pref_item.get("action", "replace")  # 默认覆盖

                        if not pref_type or not pref_value:
                            continue

                        # 根据 action 决定操作
                        if pref_action == "append":
                            # 追加模式：获取现有值并追加
                            current_prefs = self.memory_manager.long_term.get_preference()
                            existing_value = current_prefs.get(pref_type)

                            # 如果现有值是列表，追加
                            if isinstance(existing_value, list):
                                if pref_value not in existing_value:
                                    existing_value.append(pref_value)
                                self.memory_manager.long_term.save_preference(pref_type, existing_value)
                                logger.info(f"Appended to {pref_type}: {pref_value}, total: {existing_value}")
                            else:
                                # 如果现有值不是列表，创建新列表
                                new_list = [existing_value, pref_value] if existing_value else [pref_value]
                                self.memory_manager.long_term.save_preference(pref_type, new_list)
                                logger.info(f"Created list for {pref_type}: {new_list}")
                        else:
                            # 覆盖模式：直接保存新值
                            self.memory_manager.long_term.save_preference(pref_type, pref_value)
                            logger.info(f"Replaced {pref_type}: {pref_value}")

                # 旧格式兼容：preferences 是字典
                elif isinstance(preferences_data, dict):
                    for pref_type, value in preferences_data.items():
                        if value and pref_type != "has_preferences" and pref_type != "error":
                            self.memory_manager.long_term.save_preference(pref_type, value)
                            logger.info(f"Updated {pref_type}: {value} (legacy format)")

        logger.info("记忆系统已更新")

    def _should_engage(self, intention_data: dict) -> bool:
        try:
            stage = SessionStage[intention_data.get("session_stage", "looking").upper()]
        except KeyError:
            return False
        if stage == SessionStage.ACTING:
            return True
        if stage == SessionStage.CONSIDERING:
            return self.turn_count % 2 == 0
        return False
