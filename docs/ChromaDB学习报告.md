# ChromaDB 学习报告

## 一、项目概述

本报告基于 ReActAgent 项目，详细介绍 ChromaDB 向量数据库在该项目中的实际应用和存储结构。

## 二、ChromaDB 简介

ChromaDB 是一个轻量级的开源向量数据库，专为 AI 应用设计，提供：
- 向量存储与检索
- 相似度搜索（默认余弦相似度）
- 持久化存储
- 简单易用的 Python API

## 三、在 ReActAgent 中的应用

### 3.1 存储架构

Memory 和 Knowledge **在同一个 ChromaDB 实例中存储，但分属不同的 Collection**：

| 类型 | Collection 名称 | 用途 |
|---|---|---|
| **Memory** | `agent_memory` | Agent 的长期记忆 |
| **Knowledge** | `kb_knowledge` | 通用领域知识 |
| **Knowledge** | `kb_rules` | 规则与约束 |
| **Knowledge** | `kb_cases` | 历史案例 |

### 3.2 共享特性

- 相同的存储目录：`./chroma_data`
- 相同的 Embedding 函数（默认 `HashEmbeddingFunction`）
- 相同的相似度算法（余弦相似度）

## 四、ChromaDB 存储结构详解

### 4.1 目录结构

```
chroma_data/
├── chroma.sqlite3              # 元数据数据库
├── <UUID>/                     # Collection 数据目录（每个 Collection 一个）
│   ├── data_level0.bin         # 向量数据
│   ├── header.bin              # 索引头信息
│   ├── length.bin              # 长度信息
│   └── link_lists.bin          # HNSW 连接链表
└── ...
```

### 4.2 各文件/目录作用

| 文件/目录 | 作用 |
|---|---|
| `chroma.sqlite3` | **元数据数据库**，存储 Collection 信息、文档元数据、索引配置等 |
| UUID 命名的目录 | 每个目录对应一个 Collection 的向量数据存储 |
| `data_level0.bin` | **向量数据**，存储实际的嵌入向量（HNSW 索引的第一层） |
| `header.bin` | 索引头信息，包含索引配置和元数据 |
| `length.bin` | 长度信息文件 |
| `link_lists.bin` | HNSW 索引的连接链表，用于高效近似最近邻搜索 |

### 4.3 存储机制

ChromaDB 使用 **SQLite + 文件系统** 的混合存储方式：
- **元数据**（文档内容、元数据、Collection 配置）存储在 `chroma.sqlite3`
- **向量索引**（HNSW 算法的索引结构）存储在 UUID 目录下的二进制文件中

这种设计保证了向量检索的高效性，同时保持了元数据管理的灵活性。

## 五、代码实现示例

### 5.1 Memory 实现 (memory/memory.py)

```python
class LongTermMemory:
    def __init__(
        self,
        persist_dir: str = CHROMA_PERSIST_DIR,
        collection_name: str = "agent_memory",
        embedding_mode: str = "hash",
    ):
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.embedding_fn = create_embedding_function(embedding_mode)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )
```

### 5.2 Knowledge 实现 (knowledge/store.py)

```python
class KnowledgeStore:
    COLLECTION_NAMES = ["knowledge", "rules", "cases"]
    
    def __init__(
        self,
        persist_dir: str = CHROMA_PERSIST_DIR,
        embedding_mode: str = "hash",
    ):
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.embedding_fn = create_embedding_function(embedding_mode)
        self.collections = {}
        for name in self.COLLECTION_NAMES:
            self.collections[name] = self.client.get_or_create_collection(
                name=f"kb_{name}",
                embedding_function=self.embedding_fn,
                metadata={"hnsw:space": "cosine"},
            )
```

## 六、总结

ChromaDB 在 ReActAgent 项目中扮演了核心存储角色，通过 Collection 的隔离机制实现了 Memory 和 Knowledge 的逻辑分离，同时共享相同的存储基础设施，保证了检索效率和数据一致性。
