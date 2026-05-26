# mbot 商家智能体 Skills（Claude / Cursor 可用）

基于本项目 **agents/** 实际实现的业务 Skills，便于在 Claude 或 Cursor 中按意图调用对应 Agent。

---

## 怎么用、怎么问 Claude

在对话里**用自然语言说出你的需求**，Claude 会根据描述自动选用对应的 Skill（或组合多个）。不需要记命令，直接像和客服说话一样问即可。

下面按 Skill 列出**典型问法**和**会得到什么**。

---

### 1. ask-question（知识库问答）

**怎么问：**
- 「你们有哪些课程？」
- 「鲲鹏班多少钱？」
- 「面试蝶变营适合什么人？」
- 「省考流程是什么？」
- 「肖霞老师是谁？」

**会干啥：** 用 RAG 从商家知识库（`data/documents/`）检索文档，用 LLM 生成答案，并给出参考来源。  
**前置条件：** 已运行过 `python scripts/init_knowledge_base.py`。

---

### 2. query-info（天气 / 网络搜索）

**怎么问：**
- 「长沙明天天气怎么样？」
- 「查一下 XX 最新消息」
- 「搜一下 XX 新闻」

**会干啥：** 天气走 wttr.in；其他用 DDGS 做网络搜索并给摘要。  
**注意：** 课程介绍、套餐价格这类请用「知识库问答」问，不要用「查一下课程」当搜索。

---

### 3. memory-query（查我的历史咨询）

**怎么问：**
- 「我上次问过什么？」
- 「我之前说过什么偏好？」
- 「我的咨询记录有哪些？」

**会干啥：** 从长期记忆（`data/memory/{user_id}.json`）里查你的咨询记录、偏好、对话摘要，用自然语言回答。  
**前置条件：** 需要有 MemoryManager（user_id/session_id），且之前有写入过记忆。

---

### 4. preference（保存 / 改我的偏好）

**怎么问：**
- 「我预算在 1 万以内」
- 「我想要面试课程」
- 「我是应届生」
- 「改成在职备考」

**会干啥：** 识别是「追加」还是「覆盖」，把偏好写入长期记忆；后续咨询和套电策略都会用到。  
**前置条件：** 需要 MemoryManager。

---

### 5. need-stimulation（需求激发 / 套电）

由调度器按会话阶段（CONSIDERING / ACTING）自动插入，不需要手动触发。

---

### 组合问法（一次多件事）

也可以一句话里带多个意图，例如：
- 「你们鲲鹏班多少钱，适合我这种零基础的吗？」  
Claude 会依次用 **ask-question** 查课程价格和适合人群。

---

## 可用 Skills 一览

| Skill | 用途 | 触发示例 | 主要 Agent |
|-------|------|----------|------------|
| **ask-question** | 课程介绍/价格/师资/省考知识问答 | 「XX课程多少钱」「XX老师是谁」「省考怎么报名」 | RAGKnowledgeAgent |
| **query-info** | 天气、网络搜索等实时信息 | 「天气怎么样」「查一下XX」 | InformationQueryAgent |
| **memory-query** | 查询用户自己的历史咨询与偏好 | 「我上次问过什么」「我的咨询记录」 | MemoryQueryAgent |
| **preference** | 保存/追加/覆盖用户偏好 | 「我预算1万」「我是应届生」「改成在职备考」 | PreferenceAgent |
| **need-stimulation** | 需求激发/套电话术生成 | 由调度器自动插入 | NeedStimulationAgent |

---

## 统一约定（与代码一致）

1. **模型传入方式**  
   所有 Agent 使用 **`model=model`**（传入已创建的 `OpenAIChatModel` 实例）。  
   本项目**没有** `model_config_name` 参数。

2. **异步调用**  
   所有子 Agent 的 `reply()` 均为 **async**，调用时需 **await**。

3. **模型创建**  
   ```python
   from agentscope.model import OpenAIChatModel
   from config import LLM_CONFIG
   model = OpenAIChatModel(
       model_name=LLM_CONFIG["model_name"],
       api_key=LLM_CONFIG["api_key"],
       client_kwargs={"base_url": LLM_CONFIG["base_url"], "timeout": 60},
       temperature=LLM_CONFIG.get("temperature", 0.7),
       max_tokens=LLM_CONFIG.get("max_tokens", 2000),
   )
   ```

4. **Skills 独立于 cli.py**  
   Skills 直接导入 **agents/** 与 **memory_system/**，不依赖 `cli.py`。完整交互流程见 `src/mbot.py`。

---

## Agent 与文件对应

| Agent | 文件 | 职责 |
|-------|------|------|
| IntentionAgent | intention_agent.py | 意图识别与智能体调度 |
| RAGKnowledgeAgent | rag_knowledge_agent.py | 知识库检索与问答 |
| InformationQueryAgent | information_query_agent.py | 天气、网络搜索 |
| MemoryQueryAgent | memory_query_agent.py | 基于长期记忆回答历史问题 |
| PreferenceAgent | preference_agent.py | 用户偏好识别（追加/覆盖） |
| NeedStimulationAgent | need_stimulation_agent.py | 需求激发/套电话术生成 |
| OrchestrationAgent | orchestration_agent.py | 协调多 Agent（主流程使用） |

---

## 目录结构

```
.claude/skills/
├── README.md
├── ask-question/SKILL.md
├── query-info/SKILL.md
├── memory-query/SKILL.md
├── preference/SKILL.md
└── need-stimulation/SKILL.md
```

---
