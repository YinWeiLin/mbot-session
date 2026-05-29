# wilyn's mbot — 商家智能客服系统

基于 **DeepSeek** 和 **AgentScope 框架**的多智能体商家客服系统，实现意图识别、会话状态机、RAG 知识库问答与套电策略，支持 CLI 调试和 HTTP 生产部署双模式。

## ✨ 核心亮点

### 🎯 智能意图识别
- 基于 LLM 语义理解的多意图识别
- 支持 7 类意图：`product_inquiry`（产品咨询）、`price_inquiry`（价格询问）、`comparison`（产品对比）、`purchase_intent`（购买意向）、`complaint_or_issue`（投诉售后）、`general_chat`（闲聊）、`memory_query`（历史记录查询）
- 同步输出会话阶段（looking / considering / acting），驱动套电策略

### 🔄 会话状态机
- 了解 → 兴趣 → 意向三阶段，阶段只进不退
- 套电策略 Agent 由调度器按阶段和频率强制插入，与 LLM 意图识别解耦
- 历史最高阶段持久化，跨轮次保持一致

### 🧠 两层记忆系统
- **短期记忆**：Python 内存 list，维护多轮对话上下文
- **长期记忆**：JSON 文件持久化，存储用户备考信息（考试类型、备考状态、预算等），挂载 Docker Volume 保证容器重启不丢失

### 📚 RAG 知识库
- Milvus Lite 向量数据库 + SiliconFlow BGE-large-zh-v1.5 Embedding API
- 余弦相似度检索（Top-K=3）
- 以 API 调用替代本地模型加载，解决服务器 OOM 问题

### ⚡ 优先级并行调度
- IntentionAgent → OrchestrationAgent → 子 Agent
- 同优先级 Agent 并行执行（asyncio.gather）
- 低优先级 Agent 可读取前序结果（previous_results），保证话术语义连贯

### 🏗️ 插件化架构
- 所有子 Agent 为独立 Skill 插件（`.claude/skills/`）
- LazyAgentRegistry 动态发现 + 懒加载，新增 Agent 无需修改核心代码

---

## 系统架构

```
用户输入
   ↓
┌──────────────────────────────────────────┐
│  IntentionAgent（意图识别）               │
│  - 识别意图类型 + 关键实体               │
│  - 输出 session_stage（会话阶段）         │
│  - 生成调度计划                          │
└──────────────────────────────────────────┘
   ↓ 阶段推进（只进不退）
┌──────────────────────────────────────────┐
│  OrchestrationAgent（调度器）             │
│  - 按优先级调度子 Agent                  │
│  - 同优先级并行执行                      │
│  - 按阶段和频率插入套电策略              │
└──────────────────────────────────────────┘
   ↓
┌──────── 优先级 1（并行执行）─────────────┐
│  MemoryQueryAgent   RAGKnowledgeAgent    │
│  记忆查询            知识库问答           │
│                                          │
│  EventCollectionAgent  InformationQuery  │
│  需求澄清追问          联网搜索           │
└──────────────────────────────────────────┘
   ↓
┌──────── 优先级最低（串行收尾）───────────┐
│  NeedStimulationAgent                   │
│  套电策略（读取前序回答，生成引导话术）   │
└──────────────────────────────────────────┘
   ↓
结果聚合 → 更新记忆 → 返回回复
```

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，填入 API Key：

```bash
LLM_API_KEY=your-deepseek-api-key
SILICONFLOW_API_KEY=your-siliconflow-api-key
```

### 3. 初始化知识库

```bash
python .claude/skills/ask-question/script/init_knowledge_base.py
```

### 4. 启动（CLI 模式）

```bash
python cli.py
```

### 5. 启动（HTTP 模式）

```bash
uvicorn server.main:app --host 0.0.0.0 --port 8000
```

---

## HTTP 接口

Base URL（线上）：`https://wilyn.com.cn/server/api`

### POST `/session/start` — 开启会话

```json
// 请求
{ "user_id": "u_001", "message": "你好" }

// 响应
{ "success": true, "data": { "ssid": "12710a0c", "reply": "..." }, "error": null }
```

### POST `/chat` — 继续对话

```json
// 请求
{ "ssid": "12710a0c", "message": "你们的课程多少钱？" }

// 响应
{ "success": true, "data": { "reply": "..." }, "error": null }
```

---

## 子 Agent 说明

| Agent | Skill 目录 | 职责 |
|-------|-----------|------|
| RAGKnowledgeAgent | `ask-question` | 知识库检索问答 |
| MemoryQueryAgent | `memory-query` | 查询用户历史咨询记录 |
| EventCollectionAgent | `event-collection` | 需求澄清，收集备考信息 |
| InformationQueryAgent | `query-info` | 联网搜索实时信息 |
| NeedStimulationAgent | `need-stimulation` | 套电策略，引导留资 |

---

## 项目结构

```
mbot-session/
├── src/
│   ├── agents/
│   │   ├── intention_agent.py        # 意图识别
│   │   ├── orchestration_agent.py    # 调度器
│   │   └── lazy_agent_registry.py    # 插件注册器
│   ├── memory_system/
│   │   ├── memory_manager.py
│   │   ├── short_term_memory.py
│   │   └── long_term_memory.py
│   ├── prompts/                      # LLM Prompt 模板
│   ├── utils/                        # 工具（熔断、重试、日志）
│   └── mbot.py                       # 核心会话逻辑
├── server/
│   ├── main.py                       # FastAPI 入口
│   ├── routers/chat.py               # 接口路由
│   └── session_store.py              # 会话存储
├── .claude/skills/                   # Skill 插件目录
│   ├── ask-question/                 # RAG 知识库
│   ├── memory-query/                 # 记忆查询
│   ├── event-collection/             # 需求澄清
│   ├── query-info/                   # 联网搜索
│   └── need-stimulation/             # 套电策略
├── data/
│   ├── memory/                       # 长期记忆 JSON
│   └── logs/                         # 日志文件
├── cli.py                            # CLI 入口
├── config.py                         # 配置（LLM、RAG、熔断）
├── Dockerfile
├── .github/workflows/deploy.yml      # CI/CD
└── requirements.txt
```

---

## 部署

### Docker

```bash
docker build -t mbot .
docker run -d --name mbot -p 8000:8000 \
  -e LLM_API_KEY=xxx \
  -e SILICONFLOW_API_KEY=xxx \
  -v /data/memory:/app/data/memory \
  mbot
```

### CI/CD（GitHub Actions）

push 到 main 分支自动触发：构建镜像 → 推送 Aliyun ACR → SSH 部署至云服务器。

需在 GitHub Secrets 中配置：`ALIYUN_REGISTRY_USER`、`ALIYUN_REGISTRY_PASSWORD`、`SERVER_HOST`、`SERVER_USER`、`SERVER_SSH_KEY`、`SERVER_PORT`、`LLM_API_KEY`、`SILICONFLOW_API_KEY`

---

## 稳定性保障

| 机制 | 说明 |
|------|------|
| 熔断器 | 连续失败后暂停 LLM 调用，自动半开恢复 |
| 指数退避重试 | 超时/5xx 自动重试，最大 3 次 |
| 健康检查 | CLI 输入 `health` 查看熔断状态 |

配置见 `config.py` 中的 `RESILIENCE_CONFIG`。

---

## 许可证

MIT License


## TODO

- [ ] 数据库：MySQL/PostgreSQL 持久化会话记录与用户数据，替代 JSON 文件存储
- [ ] Redis：缓存用户偏好热数据 + LLM 摘要结果，减少重复计算
- [ ] 性能优化：IntentionAgent 精简 prompt（去 reasoning 字段）、降 max_tokens、流式输出提前截断