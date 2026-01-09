"""
Analyser V2 - Python 層面控制 TODO 流程

支援兩種運行方式：
1. adk web: 透過 CustomAgent 整合 Python 控制邏輯
2. CLI: python agent.py "需求描述"
"""

import sys
import re
import asyncio
from pathlib import Path
from typing import Optional, AsyncGenerator
from dataclasses import dataclass
from contextvars import ContextVar

# 將專案根目錄加入 Python 路徑
project_root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(project_root))

from google.adk.agents import LlmAgent, BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.models.lite_llm import LiteLlm, Message
from google.adk.tools import FunctionTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.apps import App

from src.utils.db import (
    get_all_modules,
    get_files_by_module,
    get_content_by_file_name,
    bm25_search,
)

# =============================================================================
# Helper Classes
# =============================================================================

@dataclass
class TextPart:
    text: str

@dataclass
class SimpleMessage:
    role: str
    parts: list[TextPart]

# =============================================================================
# TodoManager - 管理 TODO 進度
# =============================================================================

@dataclass
class TodoItem:
    """單一 TODO 項目"""
    description: str
    note: str = ""
    processed: bool = False


@dataclass
class AnalysisResult:
    """單一分析結果"""
    file_name: str
    is_target: bool
    reason: str


class TodoManager:
    """管理 TODO 清單的進度與結果收集"""

    def __init__(self):
        self.todo_list: list[TodoItem] = []
        self.current_index: int = 0
        self.results: list[AnalysisResult] = []
        self.user_requirement: str = ""

    def reset(self):
        """重置狀態"""
        self.todo_list = []
        self.current_index = 0
        self.results = []
        self.user_requirement = ""

    def set_requirement(self, requirement: str):
        """設定使用者需求"""
        self.user_requirement = requirement

    def set_todos(self, todos: list[TodoItem]):
        """設定 TODO 清單"""
        self.todo_list = todos
        self.current_index = 0
        self.results = []

    def get_current_todo(self) -> Optional[TodoItem]:
        """取得當前待處理項目"""
        if self.current_index < len(self.todo_list):
            return self.todo_list[self.current_index]
        return None

    def mark_done(self, result: AnalysisResult):
        """標記當前項目完成並記錄結果"""
        if self.current_index < len(self.todo_list):
            self.todo_list[self.current_index].processed = True
        self.results.append(result)
        self.current_index += 1

    def get_all_results(self) -> list[AnalysisResult]:
        """取得所有結果"""
        return self.results

    def get_target_files(self) -> list[str]:
        """取得所有目標文件"""
        return [r.file_name for r in self.results if r.is_target]

    def is_complete(self) -> bool:
        """是否全部處理完成"""
        return self.current_index >= len(self.todo_list)

    def get_progress(self) -> str:
        """取得進度字串"""
        return f"{self.current_index}/{len(self.todo_list)}"


# 全域 ContextVar，用於存儲每個 Request 的 TodoManager
todo_manager_var: ContextVar["TodoManager"] = ContextVar("todo_manager")


# =============================================================================
# Agent Tools - 給 Agent 使用的工具函式
# =============================================================================

def get_current_todo() -> str:
    """取得當前要處理的 TODO 項目"""
    try:
        manager = todo_manager_var.get()
        todo = manager.get_current_todo()
        if todo:
            return f"當前項目：{todo.description}\n備註：{todo.note}\n使用者需求：{manager.user_requirement}"
        return "所有項目已處理完成"
    except LookupError:
        return "錯誤：找不到執行環境 (Context)"
    except Exception as e:
        return f"讀取 TODO 失敗: {str(e)}"


def save_result(file_name: str, is_target: bool, reason: str) -> str:
    """
    儲存分析結果並標記完成

    Args:
        file_name: 文件名稱
        is_target: 是否為目標文件
        reason: 判斷理由
    """
    try:
        manager = todo_manager_var.get()
        result = AnalysisResult(
            file_name=file_name,
            is_target=is_target,
            reason=reason
        )
        manager.mark_done(result)
        progress = manager.get_progress()
        return f"已儲存結果。進度：{progress}"
    except LookupError:
        return "錯誤：找不到執行環境 (Context)"
    except Exception as e:
        return f"儲存結果失敗: {str(e)}"


def get_all_results() -> list[dict]:
    """取得所有分析結果"""
    try:
        manager = todo_manager_var.get()
        return [
            {
                "file_name": r.file_name,
                "is_target": r.is_target,
                "reason": r.reason
            }
            for r in manager.get_all_results()
        ]
    except LookupError:
        return []


# =============================================================================
# 模型設定
# =============================================================================

# MODEL = LiteLlm(model="ollama_chat/ministral-3:8b")
# MODEL = LiteLlm(model="ollama_chat/qwen3-vl:235b")
MODEL = LiteLlm(model="ollama_chat/gpt-oss:20b")


# =============================================================================
# Sub-Agents 定義
# =============================================================================

# Agent 1: 產生 TODO List
todo_agent = LlmAgent(
    name="todo_agent",
    description="分析需求並產生待辦事項清單",
    instruction="""你是 WMS 需求分析的規劃助手，負責將使用者需求轉換為待辦事項清單。

    ## 任務流程
    1. 使用 get_all_modules() 取得所有模組
    2. 針對可能相關的模組，使用 get_files_by_module(module) 取得文件清單
    3. **強烈建議** 使用 bm25_search(query) 搜尋關鍵字，找出最相關的文件
    4. 根據需求與文件名稱，判斷哪些文件可能需要查閱

    ## 輸出格式
    以點列方式輸出待辦事項，格式必須嚴格遵守：

    TODO
    - [ ] 查閱「文件名稱」| 備註說明
    - [ ] 查閱「文件名稱」| 備註說明
    ...

    範例：
    TODO
    - [ ] 查閱「3.1入庫單維護」| 了解入庫流程欄位定義
    - [ ] 查閱「3.2入庫驗收作業」| 確認驗收邏輯
    """,
    model=MODEL,
    tools=[
        FunctionTool(get_all_modules, require_confirmation=False),
        FunctionTool(get_files_by_module, require_confirmation=False),
        FunctionTool(bm25_search, require_confirmation=False),
    ],
    output_key="todo_list_raw"
)

# Agent 2: 處理單一 TODO 項目
processor_agent = LlmAgent(
    name="processor_agent",
    description="處理單一 TODO 項目，判斷文件是否為目標文件",
    instruction="""你是 WMS 文件分析機器人。你的唯一任務是針對「目前的單一 TODO 項目」進行分析並回報。

    ## 可用工具 (Available Tools)
    - `get_current_todo()`: 取得當前任務
    - `get_content_by_file_name(file_name)`: 讀取文件
    - `save_result(file_name, is_target, reason)`: 儲存結果 (必要!)

    ## 核心規則
    1. **單一焦點**：你現在只能處理 `get_current_todo()` 回傳的那**一個**項目。
    2. **禁止跳題**：別去看清單裡其他還沒輪到的項目。
    3. **必須行動**：不要只在嘴巴上說 (Thought)，最後一定要呼叫工具 (Tool Call)。
    4. **一致性**：`save_result` 的 `file_name` 必須完全等於 `get_current_todo` 的檔名。

    ## 🚫 禁止事項 (CRITICAL)
    - **禁止輸出 Raw JSON**：不要直接回傳 `{"file_name": "..."}` 字串，這會導致系統錯誤 (Tool '' not found)。
    - **禁止空名稱**：呼叫工具時，確認工具名稱正確 (`save_result`)。
    - **禁止假動作**：不要寫 `[Call: save_result]` 這種文字，要真的觸發工具協議。

    現在開始。請先呼叫 `get_current_todo()`。
    """,
    model=MODEL,
    tools=[
        FunctionTool(get_current_todo, require_confirmation=False),
        FunctionTool(get_content_by_file_name, require_confirmation=False),
        FunctionTool(save_result, require_confirmation=False),
    ],
)

# Agent 3: 彙總結果
summarize_agent = LlmAgent(
    name="summarize_agent",
    description="彙總所有分析結果，輸出目標文件清單",
    instruction="""你是結果彙總助手，負責整理分析結果。

    ## 任務
    1. 使用 get_all_results() 取得所有分析結果
    2. 篩選出 is_target=True 的文件
    3. 整理成清單輸出

    ## 輸出格式

    ## 目標文件清單

    以下文件與需求相關，需要進一步分析：

    1. 文件名稱 - 原因
    2. 文件名稱 - 原因
    ...

    共 N 個目標文件。
    """,
    model=MODEL,
    tools=[
        FunctionTool(get_all_results, require_confirmation=False),
    ],
    output_key="target_files"
)


# =============================================================================
# TODO List 解析
# =============================================================================

def parse_todo_list(raw_output: str) -> list[TodoItem]:
    """
    解析 todo_agent 的輸出，轉換為 TodoItem 清單

    預期格式：
    - [ ] 查閱「文件名稱」| 備註說明
    """
    todos = []
    pattern = r'-\s*\[\s*\]\s*(.+?)\s*\|\s*(.+?)$'

    # 去除 markdown code block 標記
    lines = raw_output.replace("```json", "").replace("```", "").strip().split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        match = re.match(pattern, line)
        if match:
            description = match.group(1).strip()
            note = match.group(2).strip()
            todos.append(TodoItem(description=description, note=note))

    # 如果嚴格格式解析失敗，嘗試寬鬆解析
    if not todos:
        for line in raw_output.split('\n'):
            if '查閱' in line and '「' in line:
                todos.append(TodoItem(description=line.strip(), note=""))

    return todos


# =============================================================================
# Custom Agent - 整合 Python 控制邏輯
# =============================================================================

class AnalyserAgent(BaseAgent):
    """
    自訂 Agent，整合 Python 層面的 TODO 迴圈控制
    可被 adk web 使用
    """

    def __init__(self):
        super().__init__(
            name="analyser_v2",
            description="需求分析 Agent，使用 Python 控制流程確保每個 TODO 都被處理",
        )

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        """執行分析流程"""

        user_message = ctx.user_content.parts[0].text if ctx.user_content and ctx.user_content.parts else ""

        # 初始化 TodoManager 並設定 ContextVar
        manager = TodoManager()
        token = todo_manager_var.set(manager)
        
        try:
            manager.set_requirement(user_message)

            # Step 1: 產生 TODO List
            yield Event(
                author=self.name,
                content={"parts": [{"text": "📋 正在分析需求，產生待辦清單..."}]},
            )

            todo_result = ""
            async for event in todo_agent.run_async(ctx):
                yield event
                # 收集輸出
                if hasattr(event, 'content') and event.content:
                    if isinstance(event.content, dict) and 'parts' in event.content:
                        for part in event.content['parts']:
                            if isinstance(part, dict) and 'text' in part and part['text']:
                                todo_result += part['text']

            # 從 session state 取得結果
            if ctx.session and ctx.session.state:
                todo_result = ctx.session.state.get("todo_list_raw", todo_result)

            # 解析 TODO List
            todos = parse_todo_list(str(todo_result))
            manager.set_todos(todos)

            yield Event(
                author=self.name,
                content={"parts": [{"text": f"\n📝 找到 {len(todos)} 個待辦項目\n"}]},
            )

            # Step 2: 逐項處理（Python 控制迴圈）
            last_desc = "無 (這是第一個任務)" # 初始化 last_desc
            while not manager.is_complete():
                start_index = manager.current_index
                current = manager.get_current_todo()
                progress = manager.get_progress()

                yield Event(
                    author=self.name,
                    content={"parts": [{"text": f"\n🔍 [{progress}] 處理中: {current.description}\n"}]},
                )

                # 執行 processor_agent (含重試機制)
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        # 注入訊息，強迫模型處理下一個項目 (避免因為 History 認為已完成而停擺)
                        # 加入「上一步」與「這一步」的脈絡，讓模型清楚知道進度
                        
                        prompt_text = f"""
                        系統狀態更新：
                        - 上一步驟已完成：{last_desc}
                        - 當前目標任務：{current.description}

                        請忽略之前的對話歷史中與「上一步」相關的內容，專注於「當前目標任務」。
                        請立即呼叫 `get_current_todo()` 開始處理。
                        """
                        if attempt > 0:
                            prompt_text = f"上一步執行錯誤: 請修正 Function Call 格式並重試。"
                        
                        # 檢查 ctx 是否有名為 messages 的屬性 (InvocationContext 通常有)
                        if hasattr(ctx, "messages"):
                            ctx.messages.append(Message(role="user", content=prompt_text))
                        
                        async for event in processor_agent.run_async(ctx):
                             yield event
                        
                        # 如果跑完沒有 exception，就 break
                        break
                    except Exception as e:
                        if attempt < max_retries - 1:
                            yield Event(
                                author=self.name,
                                content={"parts": [{"text": f"\n⚠️ 執行錯誤，正在重試 (嘗試 {attempt + 1}/{max_retries}): {e}\n"}]},
                            )
                            # 清除可能導致錯誤的最後一條訊息，或者讓模型自行處理
                            if hasattr(ctx, "messages") and ctx.messages:
                                # Remove the last user message if it was added for this attempt
                                if ctx.messages[-1].content == prompt_text:
                                    ctx.messages.pop()
                            continue
                        else:
                            yield Event(
                                author=self.name,
                                content={"parts": [{"text": f"\n❌ 執行失敗，已達最大重試次數: {e}\n"}]},
                            )
                            raise # Re-raise the last exception if all retries fail
                    
                # Watchdog: 檢查進度是否有推進
                if manager.current_index == start_index:
                    yield Event(
                        author=self.name,
                        content={"parts": [{"text": f"\n⚠️ 警告: Agent 未能產生結果，強制跳過此項目。\n"}]},
                    )
                    # 強制標記為失敗並推進
                    result = AnalysisResult(
                        file_name=current.description,
                        is_target=False,
                        reason="Agent 執行失敗或未回傳結果"
                    )
                    manager.mark_done(result)
                else:
                    # 成功推進，更新 last_desc
                    last_desc = current.description

            # Step 3: 彙總結果
            yield Event(
                author=self.name,
                content={"parts": [{"text": "\n📊 彙總分析結果...\n"}]},
            )

            async for event in summarize_agent.run_async(ctx):
                yield event

            # 輸出最終結果
            target_files = manager.get_target_files()
            yield Event(
                author=self.name,
                content={"parts": [{"text": f"\n✅ 完成！目標文件：{target_files}"}]},
            )
            
        finally:
            todo_manager_var.reset(token)


# =============================================================================
# Root Agent & App（給 adk web 使用）
# =============================================================================

root_agent = AnalyserAgent()

app = App(
    name="analyser_v2",
    root_agent=root_agent,
)


# =============================================================================
# CLI 入口
# =============================================================================

async def run_analysis(user_requirement: str, verbose: bool = True) -> dict:
    """
    執行完整的需求分析流程（CLI 模式）

    Args:
        user_requirement: 使用者需求描述
        verbose: 是否輸出進度訊息

    Returns:
        dict: {
            "target_files": ["文件1", "文件2", ...],
            "all_results": [...],
            "summary": "彙總說明"
        }
    """
    # 初始化
    manager = TodoManager()
    token = todo_manager_var.set(manager)
    
    try:
        manager.set_requirement(user_requirement)

        # 建立 Session 和 Runner
        session_service = InMemorySessionService()
        session = await session_service.create_session(
            app_name="analyser_v2",
            user_id="user",
        )

        runner = Runner(
            agent=todo_agent,
            app_name="analyser_v2",
            session_service=session_service,
        )

        # Step 1: 產生 TODO List
        if verbose:
            print("[1/3] 分析需求，產生 TODO List...")

        todo_result = ""
        async for event in runner.run_async(
            user_id="user",
            session_id=session.id,
            new_message=SimpleMessage(role="user", parts=[TextPart(user_requirement)]),
        ):
            if hasattr(event, 'content') and event.content:
                if hasattr(event.content, 'parts'):
                    for part in event.content.parts:
                        if hasattr(part, 'text') and part.text:
                            todo_result += part.text

        # 解析 TODO List
        todos = parse_todo_list(todo_result)

        if verbose:
            print(f"  找到 {len(todos)} 個待辦項目")
            for i, todo in enumerate(todos, 1):
                print(f"    {i}. {todo.description}")

        manager.set_todos(todos)

        # Step 2: 逐項處理（Python 控制迴圈）
        if verbose:
            print("\n[2/3] 逐項分析文件...")

        processor_runner = Runner(
            agent=processor_agent,
            app_name="analyser_v2",
            session_service=session_service,
        )

        while not manager.is_complete():
            start_index = manager.current_index
            current = manager.get_current_todo()
            if verbose:
                print(f"  處理中 [{manager.get_progress()}]: {current.description}")

            proc_session = await session_service.create_session(
                app_name="analyser_v2",
                user_id="user",
            )

            async for event in processor_runner.run_async(
                user_id="user",
                session_id=proc_session.id,
                new_message=SimpleMessage(role="user", parts=[TextPart("請處理當前的 TODO 項目")]),
            ):
                pass
                
            # Watchdog: 檢查進度是否有推進
            if manager.current_index == start_index:
                if verbose:
                    print(f"  ⚠️ 警告: Agent 未能產生結果，強制跳過此項目。")
                
                # 強制標記為失敗並推進
                result = AnalysisResult(
                    file_name=current.description,
                    is_target=False,
                    reason="Agent 執行失敗或未回傳結果"
                )
                manager.mark_done(result)

        if verbose:
            print(f"  完成！共處理 {len(manager.results)} 個項目")

        # Step 3: 彙總結果
        if verbose:
            print("\n[3/3] 彙總分析結果...")

        summarize_runner = Runner(
            agent=summarize_agent,
            app_name="analyser_v2",
            session_service=session_service,
        )

        sum_session = await session_service.create_session(
            app_name="analyser_v2",
            user_id="user",
        )

        summary = ""
        async for event in summarize_runner.run_async(
            user_id="user",
            session_id=sum_session.id,
            new_message=SimpleMessage(role="user", parts=[TextPart("請彙總分析結果")]),
        ):
            if hasattr(event, 'content') and event.content:
                if hasattr(event.content, 'parts'):
                    for part in event.content.parts:
                        if hasattr(part, 'text') and part.text:
                            summary += part.text

        target_files = manager.get_target_files()

        if verbose:
            print(f"\n{'='*50}")
            print(f"目標文件：{target_files}")
            print(f"{'='*50}")

        return {
            "target_files": target_files,
            "all_results": [
                {
                    "file_name": r.file_name,
                    "is_target": r.is_target,
                    "reason": r.reason
                }
                for r in manager.results
            ],
            "summary": summary
        }
    finally:
        todo_manager_var.reset(token)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="WMS 需求分析工具 V2")
    parser.add_argument(
        "requirement",
        nargs="?",
        default="我想要在入庫流程中加入品質檢驗的功能",
        help="使用者需求描述"
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="安靜模式，不輸出進度"
    )

    args = parser.parse_args()

    result = asyncio.run(run_analysis(
        user_requirement=args.requirement,
        verbose=not args.quiet
    ))

    print("\n最終結果：")
    print(f"目標文件：{result['target_files']}")
