# ReAct Agent 学习报告

**日期**: 2026-06-01
**项目**: ReAct 框架个人学习

---

## 一、项目概述

基于 ReAct (Reasoning + Acting) 框架的智能 Agent，支持：
- Thought → Action → Observation 循环推理
- 短期/长期双重记忆系统
- 可扩展的工具注册机制
- Kimi (Moonshot) API 集成

---

## 二、核心架构

### 2.1 ReAct 循环
```
用户问题 → Thought(推理) → Action(行动) → Observation(观察) → ... → Final Answer
```

### 2.2 记忆系统
| 类型 | 实现方式 | 用途 |
|------|---------|------|
| 短期记忆 | 滑动窗口 (最近10轮) | 当前对话上下文 |
| 长期记忆 | ChromaDB 向量库 | 跨会话持久化知识 |

### 2.3 内置工具
- `calculator` - 数学计算
- `get_current_time` - 获取时间
- `json_format` - JSON 格式化
- `save_memory` - 保存长期记忆
- `search_memory` - 搜索长期记忆

---

## 三、技术要点

### 3.1 Embedding 对比
| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|---------|
| 哈希 Embedding | 零依赖、快 | 语义理解弱 | 开发测试 |
| text-embedding-v3 | 语义理解强 | 需要 API | 生产环境 |

### 3.2 ChromaDB 选型
选择原因：
- 轻量级，无需单独部署
- Python API 友好
- 专为 LLM 应用设计
- 本地持久化简单

替代方案：FAISS、Pinecone、Weaviate、Milvus、pgvector

---

## 四、调试工具

### 4.1 交互模式指令
- `/memory` - 查看长期记忆
- `/reset` - 重置短期记忆
- `/quit` - 退出

### 4.2 记忆调试脚本
```bash
python scripts/debug_memory.py list
python scripts/debug_memory.py search "xxx"
python scripts/debug_memory.py add "xxx" --tag learning
```

---

## 五、配置说明

```bash
# .env 配置
KIMI_API_KEY=sk-xxx
KIMI_MODEL=kimi-k2.5
EMBEDDING_MODE=hash  # 或 openai
EMBEDDING_MODEL=text-embedding-v3
```

---

## 六、收获总结

1. ✅ 理解了 ReAct 框架的推理循环机制
2. ✅ 掌握了长短期记忆的设计思路
3. ✅ 了解了向量数据库的选型考量
4. ✅ 学会了如何调试和管理记忆数据
5. ✅ 完成了环境配置和问题修复

---

*报告生成时间: 2026-06-01*
