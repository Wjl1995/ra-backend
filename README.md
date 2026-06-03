# ReActAgent

> ReActAgent 是一个探索 ReAct Agent 架构、知识库构建与长短期记忆能力的项目。

---

## 项目简介

ReActAgent 旨在构建一个基于 ReAct（Reasoning + Acting）思路的智能代理框架，支持:
- 智能决策与行动流程
- 可扩展的知识库管理
- 长期与短期记忆能力

本仓库适合研究与实验稳定的代理系统、知识检索和记忆管理策略。

## Features

- ReAct agent architecture exploration
- Knowledge base construction and integration
- Short-term and long-term memory capabilities
- Modular structure for experimentation and extension

---

## 目录结构

- `README.md` - 项目说明文档
- `agent/` - ReAct Agent 核心实现
- `knowledge/` - 知识库管理
  - `raw/` - 原始文档存放
  - `parsed/` - 解析后的 Markdown
  - `store.py` - 知识库存储层
  - `processor.py` - 文档处理流水线
  - `parsers/` - 多格式文档解析器
  - `pipelines/` - 入库流水线
- `memory/` - 记忆模块（短期+长期）
- `tools/` - 工具注册中心
- `utils/` - 工具函数
- `docs/` - 设计文档与使用说明
  - `ChromaDB学习报告.md` - ChromaDB 存储结构详解
  - `知识库导入指南.md` - 知识库导入使用指南
- `main.py` - 项目入口
- `quickstart.py` - 快速开始示例
- `config.py` - 全局配置
- `chroma_data/` - ChromaDB 持久化数据

---

## 文档

- [知识库导入指南](docs/知识库导入指南.md) - 如何导入各种格式的文档到知识库
- [ChromaDB学习报告](docs/ChromaDB学习报告.md) - ChromaDB 存储结构详解

---

## 快速开始

1. 克隆仓库

```bash
git clone https://github.com/Wjl1995/ReActAgent.git
cd ReActAgent
```

2. 安装依赖（示例）

```bash
# Python 项目
pip install -r requirements.txt
```

3. 运行示例或测试

```bash
python main.py
```

---

## Usage

Use this repository as a starting point for building and testing ReAct agents with memory capabilities. Typical steps include:

1. Define the agent reasoning and action loop
2. Connect the agent to a knowledge base or retrieval system
3. Implement short-term and long-term memory storage
4. Evaluate on tasks that require reasoning and memory

---

## 贡献指南

欢迎贡献者参与项目建设：

- 提交 issue 讨论新功能和问题
- 创建 pull request 实现改进
- 提供测试用例和文档补充

---

## License

本项目建议使用开源许可证，如 MIT License。

---

## English Version

# ReActAgent

> ReActAgent is a project focused on exploring the ReAct (Reasoning + Acting) agent architecture, knowledge base construction, and memory capabilities.

## Overview

ReActAgent is designed to provide a framework for building intelligent agents that:

- Reason and act in a loop
- Integrate with knowledge bases
- Support short-term and long-term memory

This repository is ideal for research and experimentation in agent systems, knowledge retrieval, and memory management.

## Key Features

- ReAct agent architecture exploration
- Knowledge base construction and integration
- Short-term and long-term memory capabilities
- Modular design for experimentation

## Example Structure

- `README.md` - project documentation
- `src/` - source code for the agent implementation
- `docs/` - design and usage documentation
- `examples/` - sample scenarios and demos

> Adjust the structure description based on the actual repository layout.

## Getting Started

1. Clone the repository

```bash
git clone https://github.com/Wjl1995/ReActAgent.git
cd ReActAgent
```

2. Install dependencies (example)

```bash
# Python project
pip install -r requirements.txt
```

3. Run examples or tests

```bash
python main.py
```

## Usage

Use this repository as a foundation for building and evaluating ReAct-based agents with memory capabilities. Typical workflow:

1. Define the agent reasoning and action loop
2. Connect to a knowledge base or retrieval system
3. Implement short-term and long-term memory storage
4. Test on tasks requiring reasoning and memory

## Contributing

Contributions are welcome:

- Open issues to discuss new ideas and bugs
- Submit pull requests for improvements
- Add tests and documentation

## License

This project is suitable for an open-source license such as MIT License.
