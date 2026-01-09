from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import FunctionTool
from google.adk.apps import App
from google.adk.runners import ResumabilityConfig
from src.utils.db import (
    get_all_modules,
    get_files_by_module,
    get_content_by_file_name,
    get_content_by_module,
    get_all_documents,
    bm25_search,
)
from src.utils.agent_patterns import GenericLoop, get_exit_loop_tool, COMPLETION_PHRASE

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

# Agent 1: Proposes an initial plan (規劃者)
initial_planner = LlmAgent(
    name="initial_planner", 
    model=MODEL, 
    tools=db_tools,
    instruction="""
    你是一個任務規劃助理。你的任務是根據使用者的需求，提出一個初步的執行計畫。
    
    ## 執行步驟
    1. **分析需求**：理解使用者的核心目標。
    2. **盤點資源**：利用提供的資料庫工具 (如 `get_all_modules`, `bm25_search`) 來查詢系統中可用的文件或功能。
    3. **制定計畫**：根據搜尋到的資訊，撰寫一份 TODO List。

    ## 注意事項
    - 請盡量具體，引用系統中真實存在的工具。
    - 每個任務應該為最小可執行單位，請避免過度抽象。

    ## 輸出格式
    請依據以下 Markdown 格式輸出你的初步規劃：

    TODO List:
    - [ ] 步驟 1: (具體行動)
    - [ ] 步驟 2: ...
    - [ ] 步驟 N
    """,
    output_key="plan_draft"
)

# Agent 2 (in loop): Critiques the plan (評論者)
critic_agent = LlmAgent(
    name="critic_agent", 
    model=MODEL, 
    tools=db_tools,
    instruction=f"""
    你是一個務實的計畫審查員。你的任務是檢查「初步計畫」是否可行、完整且符合使用者需求。

    ## 輸入資訊
    - 使用者需求: {{session.query}}
    - 當前計畫: {{plan_draft}}

    ## 審查標準
    1. **完整性**：是否漏掉了關鍵步驟？
    2. **可行性**：計畫邏輯是否通順？
    3. **最小可執行單位**：每個任務是否為最小可執行單位？
    4. **務實性**：只要計畫合理且可執行，請優先讓其通過，不要過度糾結細節。

    ## 輸出規則
    - **情況一：計畫可行 (Accept)**
      若計畫在邏輯上沒有重大錯誤，請直接輸出通關密語："{COMPLETION_PHRASE}"
      (注意：不要附加任何其他文字或建議)

    - **情況二：計畫需修正 (Request Changes)**
      只有在發現「重大錯誤」或「關鍵缺漏」時，才列出具體的修改建議。
      (注意：絕對**不要**輸出通關密語)
    """,
    output_key="criticism"
)

# Agent 3 (in loop): Refines the plan or exits (修正者)
# 重點：必須把 exit_loop_action 封裝成的 tool 加入這裡
exit_loop_tool = get_exit_loop_tool()

refiner_agent = LlmAgent(
    name="refiner_agent", 
    model=MODEL, 
    tools=[exit_loop_tool] + db_tools,
    instruction=f"""
    你是一個計畫修正專家。你的任務是根據「審查意見」來修正計畫。

    ## 輸入資訊
    - 原始需求: {{session.query}}
    - 審查意見: {{criticism}}
    - 當前計畫: {{plan_draft}}

    ## 執行邏輯 (最重要 - 關於結束迴圈)
    1. **檢查意見**：
       - 若審查意見包含 "{COMPLETION_PHRASE}"，代表任務完成。
       - 此時，你必須**使用系統提供的 function calling 機制**呼叫 `exit_loop_action()`。
       - ❌ **嚴禁**在回應中直接打出 `{{ "tool_calls": ... }}` 或 `{{ "exit_loop": {{}} }}` 等 JSON 文字。
       - ❌ **嚴禁**輸出 Markdown 程式碼區塊。
       - ✅ 請直接觸發工具執行。

    2. **修正計畫**：
       - 若無通關密語，請根據意見修改計畫。
       - 輸出修正後的 Markdown TODO List。

    """,
    output_key="plan_draft"
)

# ✨ Uses GenericLoop now ✨
refinement_loop_agent = GenericLoop(
    sub_agents=[critic_agent, refiner_agent],
    max_iterations=3,
    exit_key="loop_complete", # default
    name="refinement_loop",
    description="Manages the critique-refine loop"
)

# Agent 4: Presenter (報告者)
presenter_agent = LlmAgent(
    name="presenter_agent",
    model=MODEL,
    instruction="""
    你是一個專業的報告者。你的任務是將最終的計畫以清晰的 Markdown 格式呈現給使用者。

    ## 輸入資訊
    - 最終計畫: {{plan_draft}}

    ## 任務
    請直接輸出最終的 TODO List，不需要添加額外的開場白，但可以稍微美化格式。
    """,
    output_key="final_output"
)

# ✨ The SequentialAgent puts it all together ✨
# NAMING: "planner_agent" now refers to this entire workflow
planner_agent = SequentialAgent(
    name="planner_agent",
    sub_agents=[initial_planner, refinement_loop_agent, presenter_agent],
    description="A workflow that iteratively plans and refines a task based on user requirements."
)

root_agent = planner_agent

app = App(
    name="planner",
    root_agent=root_agent,
    resumability_config=ResumabilityConfig(
        is_resumable=False,
    )
)