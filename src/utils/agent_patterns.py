from google.adk.agents import BaseAgent, LlmAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.tools import ToolContext, FunctionTool
from typing import AsyncGenerator, Optional, List

# Standard completion phrase key, can be imported by users
COMPLETION_PHRASE = "計畫可行，且符合所有限制條件。"

def exit_loop_action(tool_context: ToolContext):
    """
    通用工具：用於結束優化迴圈。
    呼叫此工具會設定 session state 中的 flag，通知 GenericLoop 結束迭代。
    """
    print(f"  [Tool Call] exit_loop triggered by {tool_context.agent_name}")
    # Default key is "loop_complete", but agents can rely on this standard action.
    tool_context.session.state["loop_complete"] = True
    return "Loop termination signal received."

class GenericLoop(BaseAgent):
    """
    A generic Loop Agent that runs a sequence of sub-agents repeatedly.
    It terminates when:
    1. The session state key `exit_key` (default "loop_complete") is set to True.
    2. The `max_iterations` limit is reached.
    """
    max_iterations: int = 3
    exit_key: str = "loop_complete"
    sub_agents: List[LlmAgent] = []
    
    def __init__(self, 
                 sub_agents: List[LlmAgent], 
                 max_iterations: int = 3, 
                 exit_key: str = "loop_complete",
                 name: str = "generic_loop",
                 description: str = "A generic loop agent"):
        super().__init__(name=name, description=description)
        self.sub_agents = sub_agents
        self.max_iterations = max_iterations
        self.exit_key = exit_key

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        # Reset exit flag at start of the loop
        if ctx.session and ctx.session.state:
            ctx.session.state[self.exit_key] = False

        for i in range(self.max_iterations):
            yield Event(author=self.name, content={"parts": [{"text": f"\n🔄 進入迴圈 Round {i+1}...\n"}]})
            
            # Run all sub-agents in order
            for agent in self.sub_agents:
                async for event in agent.run_async(ctx):
                    yield event
            
            # Check for termination flag in session state
            if ctx.session and ctx.session.state.get(self.exit_key):
                yield Event(author=self.name, content={"parts": [{"text": "\n✅ 條件達成，結束迴圈。\n"}]})
                break
        else:
            yield Event(author=self.name, content={"parts": [{"text": "\n⚠️ 達到最大迭代次數，強制結束。\n"}]})

def get_exit_loop_tool() -> FunctionTool:
    """Returns the FunctionTool for exiting the loop (sets 'loop_complete'=True)."""
    return FunctionTool(exit_loop_action, require_confirmation=False)
