import sys
from pathlib import Path

# 將專案根目錄加入 Python 路徑
project_root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(project_root))

from google.adk.agents import LlmAgent, SequentialAgent, BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import FunctionTool
from google.adk.apps import App
from google.adk.runners import ResumabilityConfig
from typing import AsyncGenerator
from src.utils.db import (
    get_all_modules,
    get_files_by_module,
    get_content_by_file_name,
    get_content_by_module,
    get_all_documents,
    bm25_search,
)
from src.utils.agent_patterns import GenericLoop, get_exit_loop_tool, COMPLETION_PHRASE
from src.agents.sub_agents.planner.agent import planner_agent
from src.agents.sub_agents.executor.agent import execution_agent

MODEL = LiteLlm(model="ollama_chat/gpt-oss:20b")

# 工具清單
db_tools = [
    FunctionTool(get_all_modules, require_confirmation=False),
    FunctionTool(get_files_by_module, require_confirmation=False),
    FunctionTool(get_content_by_file_name, require_confirmation=False),
    FunctionTool(get_content_by_module, require_confirmation=False),
    FunctionTool(get_all_documents, require_confirmation=False),
    FunctionTool(bm25_search, require_confirmation=False),
]

# Planning Phase
planning_agent = planner_agent

# Debug Agent
class DebugAgent(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        data = ctx.session.state.get("final_output", "⚠️ 沒找到 final_output！")
        print(f"\n{'='*20} [DEBUG] final_output 内容檢查 {'='*20}\n{data}\n{'='*60}\n")
        yield Event(author=self.name, content={"parts": [{"text": "Debug check complete."}]})

# Execution Phase (Imported from src.agents.sub_agents.executor.agent)
# execution_agent is already imported above

# Orchestrator: Chains Planning -> Debug -> Execution
orchestrator_agent = SequentialAgent(
    name="orchestrator",
    sub_agents=[planning_agent, DebugAgent(name="debug_printer", description="Prints session state"), execution_agent],
    description="Full workflow: Plan -> Execute"
)

# Root App
app = App(
    name="orchestrator",
    root_agent=orchestrator_agent,
    resumability_config=ResumabilityConfig(
        is_resumable=False,
    )
)
