"""
RAG知识库智能体 RAGKnowledgeAgent
职责：基于向量数据库的知识检索与问答
"""
from agentscope.agent import AgentBase
from agentscope.message import Msg
from typing import Optional, Union, List, Dict
from utils.llm_resilience import parse_llm_response
import json
import logging
import os
import httpx
from pathlib import Path

import sys
_pr = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
sys.path.insert(0, _pr)
sys.path.insert(0, os.path.join(_pr, 'src'))

_GRPC_MAX_MS = '2147483647'
os.environ['GRPC_KEEPALIVE_TIME_MS'] = _GRPC_MAX_MS
os.environ['GRPC_KEEPALIVE_TIMEOUT_MS'] = '20000'
os.environ['GRPC_KEEPALIVE_PERMIT_WITHOUT_CALLS'] = '0'
os.environ['GRPC_HTTP2_MIN_RECV_PING_INTERVAL_WITHOUT_DATA_MS'] = _GRPC_MAX_MS
os.environ['GRPC_HTTP2_MIN_PING_INTERVAL_WITHOUT_DATA_MS'] = _GRPC_MAX_MS

logger = logging.getLogger(__name__)

try:
    from pymilvus import MilvusClient, DataType
    DEPENDENCIES_AVAILABLE = True
except ImportError as e:
    logger.warning(f"RAG dependencies not available: {e}")
    DEPENDENCIES_AVAILABLE = False


def _get_embedding(text: str, api_url: str, api_key: str, model: str) -> List[float]:
    """调用硅基流动 embedding API 获取向量"""
    response = httpx.post(
        api_url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "input": text, "encoding_format": "float"},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]


class RAGKnowledgeAgent(AgentBase):
    """RAG知识库智能体"""

    def __init__(
        self,
        name: str = "RAGKnowledgeAgent",
        model=None,
        knowledge_base_path: str = None,
        collection_name: str = "mbot_knowledge",
        top_k: int = 3,
        **kwargs
    ):
        super().__init__()
        self.name = name
        self.model = model

        if knowledge_base_path is None:
            current_dir = Path(__file__).parent.parent
            knowledge_base_path = str(current_dir / "data" / "rag_knowledge")

        self.knowledge_base_path = Path(knowledge_base_path)
        self.collection_name = collection_name
        self.top_k = top_k
        from utils.skill_loader import SkillLoader
        self.skill_loader = SkillLoader()

        if not DEPENDENCIES_AVAILABLE:
            logger.error("pymilvus not installed.")
            self.initialized = False
            return

        from config import RAG_CONFIG
        self._embedding_model = RAG_CONFIG.get("embedding_model", "BAAI/bge-large-zh-v1.5")
        self._embedding_api_url = RAG_CONFIG.get("embedding_api_url", "https://api.siliconflow.cn/v1/embeddings")
        self._embedding_api_key = RAG_CONFIG.get("embedding_api_key", "")
        self.embedding_dim = RAG_CONFIG.get("embedding_dim", 1024)

        milvus_db_path = str(self.knowledge_base_path / "milvus_lite.db")
        logger.info(f"Initializing Milvus Lite at: {milvus_db_path}")

        self.milvus_client = MilvusClient(milvus_db_path, grpc_options={"keepalive_time": _GRPC_MAX_MS, "keepalive_timeout": "20000", "keepalive_permit_without_calls": "0", "http2_min_recv_ping_interval_without_data": _GRPC_MAX_MS, "http2_min_ping_interval_without_data": _GRPC_MAX_MS})

        if self.milvus_client.has_collection(collection_name):
            logger.info(f"Loaded existing collection: {collection_name}")
        else:
            logger.info(f"Creating new collection: {collection_name}")
            self.milvus_client.create_collection(
                collection_name=collection_name,
                dimension=self.embedding_dim,
                metric_type="COSINE",
                auto_id=False,
            )

        self.initialized = True
        self._milvus_db_path = milvus_db_path
        logger.info("RAG Knowledge Agent initialized (SiliconFlow embedding API)")

    def _embed(self, text: str) -> List[float]:
        return _get_embedding(text, self._embedding_api_url, self._embedding_api_key, self._embedding_model)

    def _ensure_connection(self):
        try:
            self.milvus_client.has_collection(self.collection_name)
        except Exception as e:
            logger.warning(f"Milvus connection issue: {e}, reconnecting...")
            try:
                if hasattr(self.milvus_client, 'close'):
                    try:
                        self.milvus_client.close()
                    except:
                        pass
                self.milvus_client = MilvusClient(self._milvus_db_path)
                logger.info("Milvus client reconnected")
            except Exception as reconnect_error:
                logger.error(f"Failed to reconnect Milvus: {reconnect_error}")
                raise

    def add_documents(self, documents: List[Dict[str, str]]) -> Dict:
        if not self.initialized:
            return {"status": "error", "message": "RAG Agent not initialized"}

        try:
            self._ensure_connection()
            stats = self.milvus_client.get_collection_stats(self.collection_name)
            current_count = stats.get("row_count", 0)

            data_to_insert = []
            for i, doc in enumerate(documents):
                doc_id = current_count + i + 1
                content = doc['content']
                metadata = doc.get('metadata', {})
                embedding = self._embed(content)
                data_to_insert.append({
                    "id": doc_id,
                    "vector": embedding,
                    "content": content,
                    "metadata": json.dumps(metadata, ensure_ascii=False)
                })

            self.milvus_client.insert(collection_name=self.collection_name, data=data_to_insert)
            stats = self.milvus_client.get_collection_stats(self.collection_name)
            total_count = stats.get("row_count", len(documents))

            logger.info(f"Added {len(documents)} documents to knowledge base")
            return {"status": "success", "added_count": len(documents), "total_count": total_count}

        except Exception as e:
            logger.error(f"Error adding documents: {e}")
            return {"status": "error", "message": str(e)}

    def search_knowledge(self, query: str, top_k: Optional[int] = None) -> List[Dict]:
        if not self.initialized:
            return []

        try:
            self._ensure_connection()
            k = top_k or self.top_k

            try:
                load_state = self.milvus_client.get_load_state(self.collection_name)
                if load_state.get("state") != "Loaded":
                    self.milvus_client.load_collection(self.collection_name)
            except Exception:
                self.milvus_client.load_collection(self.collection_name)

            query_embedding = self._embed(query)

            results = self.milvus_client.search(
                collection_name=self.collection_name,
                data=[query_embedding],
                limit=k,
                output_fields=["id", "content", "metadata"]
            )

            retrieved_docs = []
            if results and len(results) > 0:
                for hit in results[0]:
                    metadata_str = hit.get("entity", {}).get("metadata", "{}")
                    try:
                        metadata = json.loads(metadata_str)
                    except:
                        metadata = {}
                    retrieved_docs.append({
                        'id': hit.get("entity", {}).get("id", ""),
                        'content': hit.get("entity", {}).get("content", ""),
                        'metadata': metadata,
                        'distance': hit.get("distance", 0.0)
                    })

            logger.info(f"Retrieved {len(retrieved_docs)} documents for query: {query[:50]}")
            return retrieved_docs

        except Exception as e:
            logger.error(f"Error searching knowledge: {e}")
            return []

    async def reply(self, x: Optional[Union[Msg, List[Msg]]] = None) -> Msg:
        if not self.initialized:
            return Msg(
                name=self.name,
                content=json.dumps({"status": "error", "message": "RAG Agent not initialized"}),
                role="assistant"
            )

        if x is None:
            return Msg(name=self.name, content=json.dumps({}), role="assistant")

        if isinstance(x, list):
            content = x[-1].content if x else ""
        else:
            content = x.content

        user_query = content
        if isinstance(content, str) and content.strip().startswith('{'):
            try:
                data = json.loads(content)
                extracted_query = ""
                if "context" in data and isinstance(data["context"], dict):
                    extracted_query = data["context"].get("rewritten_query", "")
                elif "rewritten_query" in data:
                    extracted_query = data.get("rewritten_query", "")
                user_query = extracted_query
            except:
                pass

        retrieved_docs = self.search_knowledge(user_query)
        for _doc in retrieved_docs:
            logger.info(f"RAG hit: score={_doc['distance']:.3f} | {_doc['content'][:60]}")

        if not retrieved_docs:
            result = {
                "status": "no_knowledge",
                "query": user_query,
                "answer": "抱歉，我在知识库中没有找到相关信息。",
                "retrieved_documents": []
            }
            return Msg(name=self.name, content=json.dumps(result, ensure_ascii=False), role="assistant")

        knowledge_context = "\n\n".join([
            f"【知识片段{i+1}】\n{doc['content']}"
            for i, doc in enumerate(retrieved_docs)
        ])

        if self.model:
            skill_instruction = self.skill_loader.get_skill_content("ask-question")
            if not skill_instruction:
                skill_instruction = "请基于知识库中的信息回答用户的问题。"

            prompt = f"""你是WiLyn教育的智能客服，熟悉公务员考试（公考）培训相关知识。请严格基于以下知识库中的信息回答用户的问题。

【用户问题】
{user_query}

【知识库信息】
{knowledge_context}

【任务说明】
{skill_instruction}

【重要约束】
1. 如果参考资料中没有包含回答用户问题所需的信息，请直接回答"抱歉，这个问题我暂时没有相关资料，建议您联系我们的老师进一步咨询。"，不要尝试根据你自己的知识编造答案。
2. 即使问题很基础，如果资料里没写，就说不知道。
3. 以真人客服的语气自然回答，不要说"根据知识库"、"根据资料"、"知识库显示"等暴露内部系统的词语，直接给出答案即可。
4. 语气亲切自然，像真人客服一样对话。
"""

            try:
                messages = [
                    {"role": "system", "content": "你是WiLyn教育的智能客服，熟悉公务员考试培训相关知识。"},
                    {"role": "user", "content": prompt}
                ]
                response = await self.model(messages)
                answer = await parse_llm_response(response)

                if not answer:
                    answer = "无法生成答案"

                answer_str = answer.strip()
                if answer_str.startswith("{") and answer_str.endswith("}"):
                    try:
                        json_obj = json.loads(answer_str)
                        if isinstance(json_obj, dict):
                            answer = json_obj.get("answer") or json_obj.get("content") or answer
                    except:
                        pass

            except Exception as e:
                logger.error(f"Error generating answer with LLM: {e}")
                answer = f"知识库中找到相关信息，但生成答案时出错：{str(e)}"
        else:
            answer = "以下是知识库中的相关信息：\n\n" + knowledge_context

        result = {
            "status": "success",
            "query": user_query,
            "answer": answer,
            "retrieved_documents": [
                {
                    "content": doc['content'][:200] + "..." if len(doc['content']) > 200 else doc['content'],
                    "metadata": doc['metadata']
                }
                for doc in retrieved_docs
            ]
        }

        return Msg(name=self.name, content=json.dumps(result, ensure_ascii=False), role="assistant")

    def get_stats(self) -> Dict:
        if not self.initialized:
            return {"status": "error", "message": "Not initialized"}
        try:
            self._ensure_connection()
            stats = self.milvus_client.get_collection_stats(self.collection_name)
            return {
                "status": "success",
                "collection_name": self.collection_name,
                "total_documents": stats.get("row_count", 0),
                "knowledge_base_path": str(self.knowledge_base_path)
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def close(self):
        if hasattr(self, 'milvus_client'):
            try:
                if hasattr(self.milvus_client, 'close'):
                    self.milvus_client.close()
            except Exception as e:
                logger.warning(f"Error closing Milvus client: {e}")

    def __del__(self):
        self.close()

