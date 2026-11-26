from typing import List, Dict

def search_knowledge(query: str, top_k: int = 5) -> List[Dict]:
    """
    旧能力迁移边界：RAG 知识查询工具。
    注意：这里只定义契约，不实现具体的向量检索和重排。
    """
    # 强制要求返回格式：包含内容、来源、得分
    # 这里可以抛出 NotImplementedError 或者返回 mock 数据
    raise NotImplementedError("RAG 检索实现留给独立检索项目，本周仅作为工具契约暴露。")