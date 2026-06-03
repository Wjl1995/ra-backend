"""
ReAct Agent 核心实现

ReAct 框架 = Reasoning + Acting
循环流程: Thought → Action → Observation → ... → Final Answer

使用 Kimi (Moonshot) API，兼容 OpenAI 接口
"""
from __future__ import annotations

import json
from typing import Optional

from openai import OpenAI
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_MAX_TOKENS, LLM_TEMPERATURE, MAX_ITERATIONS
from memory import AgentMemory
from tools import ToolRegistry
from knowledge import KnowledgeStore

console = Console()

# ─── ReAct Prompt 模板 ──────────────────────────────────────

REACT_SYSTEM_PROMPT = """你是一个垂直领域智能助手，使用 ReAct (Reasoning + Acting) 框架来解决问题。

你必须在每一轮按以下格式回复：

**Thought**: 分析当前情况，思考下一步该做什么
**Action**: 调用一个工具（格式见下方）
**Action Input**: 工具的输入参数（JSON 格式）

当你已经收集到足够信息可以回答用户时，使用：

**Thought**: 我现在知道最终答案了
**Final Answer**: 你的完整回答

---

可用工具：
{tools_description}

---

重要规则：
1. 每次只能调用一个工具
2. 必须基于 Observation 的结果进行推理，不要凭空猜测
3. 如果工具调用失败，尝试换一种方式
4. 最多进行 {max_iterations} 轮推理
5. 记得使用 save_memory 保存重要信息，search_memory 查找历史记忆

---

🧠 知识库使用策略（重要！）：

面对用户问题时，请按以下优先级使用知识库工具：

1. **领域知识问题** → 先用 search_knowledge 搜索知识库
   - 涉及领域术语、概念、流程、FAQ 时
   - 不要凭通用知识回答，优先查知识库

2. **合规/规则/流程问题** → 用 lookup_rule 查规则
   - 涉及"能不能做""是否允许""审批流程""SOP"时
   - 必须先查规则再回答，不要猜测

3. **决策/方案/参考问题** → 用 retrieve_case 查案例
   - 涉及"怎么做""有没有参考""类似情况怎么处理"时
   - 参考历史案例给出建议

4. **任务完成后的经验** → 用 save_experience 沉淀
   - 完成了有价值的任务后，主动保存经验
   - 记录场景、做法、结果

---

当前长期记忆（与用户问题相关）：
{long_term_memory}

知识库统计：
{knowledge_stats}
"""


class ReActAgent:
    """基于 ReAct 框架的 Agent"""

    def __init__(
        self,
        api_key: str = LLM_API_KEY,
        base_url: str = LLM_BASE_URL,
        model: str = LLM_MODEL,
        max_iterations: int = MAX_ITERATIONS,
        memory: Optional[AgentMemory] = None,
        tool_registry: Optional[ToolRegistry] = None,
        knowledge_store: Optional[KnowledgeStore] = None,
    ):
        if not api_key or api_key == "your_kimi_api_key_here":
            raise ValueError(
                "请先配置 Kimi API Key！\n"
                "1. 复制 .env.example 为 .env\n"
                "2. 填入你的 API Key"
            )

        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.max_iterations = max_iterations

        # 初始化记忆系统
        self.memory = memory or AgentMemory()

        # 初始化知识库
        self.knowledge_store = knowledge_store or KnowledgeStore()

        # 初始化工具注册中心（注入 memory + knowledge）
        self.tools = tool_registry or ToolRegistry.create_default(
            memory=self.memory,
            knowledge_store=self.knowledge_store,
        )

    def _build_system_prompt(self, user_query: str) -> str:
        tools_desc = []
        for tool in self.tools.all_tools():
            params_desc = ", ".join(
                f"{k}: {v['description']}"
                for k, v in tool.parameters.get("properties", {}).items()
            )
            tools_desc.append(f"- {tool.name}({params_desc}): {tool.description}")

        long_term = self.memory.recall(user_query)

        # 知识库统计
        stats = self.knowledge_store.stats()
        stats_lines = []
        for name, info in stats.items():
            stats_lines.append(f"  {name}: {info['count']} 条")
        knowledge_stats = "\n".join(stats_lines) if stats_lines else "  （知识库为空）"

        return REACT_SYSTEM_PROMPT.format(
            tools_description="\n".join(tools_desc),
            max_iterations=self.max_iterations,
            long_term_memory=long_term,
            knowledge_stats=knowledge_stats,
        )

    def _parse_action(self, text: str) -> tuple[Optional[str], Optional[str]]:
        """从 LLM 回复中解析 Action 和 Action Input"""
        action = None
        action_input = None

        lines = text.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("**Action**:") or line.startswith("Action:"):
                action = line.split(":", 1)[1].strip().strip("*")
            elif line.startswith("**Action Input**:") or line.startswith("Action Input:"):
                raw = line.split(":", 1)[1].strip().strip("*")
                try:
                    action_input = json.loads(raw)
                except json.JSONDecodeError:
                    # 尝试简单包装
                    action_input = {"input": raw}

        return action, action_input

    def _parse_final_answer(self, text: str) -> Optional[str]:
        """检查是否包含 Final Answer"""
        for line in text.strip().split("\n"):
            line = line.strip()
            if line.startswith("**Final Answer**:") or line.startswith("Final Answer:"):
                return line.split(":", 1)[1].strip().strip("*")
        return None

    def _execute_tool(self, action: str, action_input: dict) -> str:
        """执行工具调用"""
        tool = self.tools.get(action)
        if not tool:
            return f"错误: 未找到工具 '{action}'，可用工具: {[t.name for t in self.tools.all_tools()]}"
        return tool.run(**action_input) if isinstance(action_input, dict) else tool.run()

    def run(self, query: str, verbose: bool = True) -> str:
        """
        执行 ReAct 循环

        流程: User Query → Thought → Action → Observation → ... → Final Answer
        """
        # 保存用户消息到短期记忆
        self.memory.add_user_message(query)

        # 构建初始消息
        system_prompt = self._build_system_prompt(query)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ]

        if verbose:
            console.print(Panel(query, title="🧑 用户", style="blue"))

        # ReAct 主循环
        for iteration in range(1, self.max_iterations + 1):
            if verbose:
                console.print(f"\n[dim]── 第 {iteration} 轮推理 ──[/dim]")

            # 调用 LLM
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=LLM_MAX_TOKENS,
                temperature=LLM_TEMPERATURE,
            )
            assistant_text = response.choices[0].message.content

            if verbose:
                console.print(Markdown(assistant_text))

            # 检查是否已给出最终答案
            final_answer = self._parse_final_answer(assistant_text)
            if final_answer:
                if verbose:
                    console.print(Panel(final_answer, title="🤖 最终回答", style="green"))
                self.memory.add_assistant_message(final_answer)
                return final_answer

            # 解析 Action
            action, action_input = self._parse_action(assistant_text)
            if not action:
                # LLM 没有给出 Action，直接返回
                if verbose:
                    console.print(Panel(assistant_text, title="🤖 回答", style="green"))
                self.memory.add_assistant_message(assistant_text)
                return assistant_text

            # 执行工具
            observation = self._execute_tool(action, action_input)
            if verbose:
                console.print(Panel(observation, title=f"🔧 Observation ({action})", style="yellow"))

            # 将当前轮次加入消息历史
            messages.append({"role": "assistant", "content": assistant_text})
            messages.append({"role": "user", "content": f"Observation: {observation}"})

        # 达到最大轮次
        timeout_msg = f"已达到最大推理轮次 ({self.max_iterations})，以下是目前得到的信息。"
        if verbose:
            console.print(Panel(timeout_msg, title="⚠️ 超时", style="red"))
        self.memory.add_assistant_message(timeout_msg)
        return timeout_msg

    def chat(self, verbose: bool = True) -> None:
        """交互式对话模式"""
        console.print(Panel(
            "ReAct Agent 已启动！\n"
            "输入问题开始对话\n"
            "/quit - 退出 | /reset - 重置对话 | /memory - 查看长期记忆 | /kb - 查看知识库统计",
            title="🚀 ReAct Agent + Knowledge",
            style="bold green",
        ))

        while True:
            try:
                user_input = console.input("[bold blue]你>[/bold blue] ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n👋 再见！")
                break

            if not user_input:
                continue
            if user_input == "/quit":
                console.print("👋 再见！")
                break
            if user_input == "/reset":
                self.memory.reset_conversation()
                console.print("🔄 对话已重置，长期记忆保留")
                continue
            if user_input == "/memory":
                count = self.memory.long_term.count()
                console.print(f"📊 长期记忆条数: {count}")
                if count > 0:
                    results = self.memory.long_term.search("所有记忆", top_k=min(count, 10))
                    for i, r in enumerate(results, 1):
                        console.print(f"  {i}. {r['text']} (tag: {r['metadata'].get('tag', 'N/A')})")
                continue
            if user_input == "/kb":
                stats = self.knowledge_store.stats()
                console.print("📊 知识库统计:")
                for name, info in stats.items():
                    console.print(f"  {name}: {info['count']} 条")
                continue

            self.run(user_input, verbose=verbose)
