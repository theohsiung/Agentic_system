import sys
from pathlib import Path

# 將專案根目錄加入 Python 路徑
project_root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(project_root))

from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import FunctionTool
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

# 1. Executor Worker: 執行任務
executor_worker = LlmAgent(
    name="executor_worker",
    model=MODEL,
    tools=db_tools,
    instruction="""
    你是一個任務執行者。
    
    ## 輸入資訊
    - 待辦清單: {final_output}
    
    ## 你的任務
    1. 請讀取上方的待辦清單。
    2. 找出**第一個**狀態為未完成 `[ ]` 的項目。
    3. 利用資料庫工具執行該項目要求的動作。
    4. 執行完畢後，請回報你做了什麼，並明確指出完成了哪一個步驟。

    (注意：一次只執行一個步驟)
    """,
    output_key="worker_result"
)

# 2. Progress Update Agent: 嚴格的成果裁判
progress_update_agent = LlmAgent(
    name="progress_update_agent",
    model=MODEL,
    instruction="""
    你是一個嚴格的成果裁判 (Result Judge)。
    
    ## 輸入資訊
    - 當前清單: {final_output}
    - 執行者回報: {worker_result}
    
    ## 你的任務
    1. **審核回報**：判斷執行者是否**成功**完成了當前任務。
       - 成功：執行無誤，且達到預期目標。
       - 失敗：執行報錯、找不到檔案、或其他異常狀況。
    
    2. **更新清單**：
       - **若成功**：
         - 將該項目的狀態從 `[ ]` 改為 `[x]`。
         - **重要**：請在該行後方附加簡短的執行結果摘要 (例如：`- [x] 搜尋資料 -> 找到 5 筆相關文件: a.md, b.md...`)。這將幫助後續總結。
       - **若失敗**：
         - 保持狀態為 `[ ]` (未完成)。
         - 在該項目下方新增一行：`  - ⚠️ 失敗原因：(簡述原因)`，以便讓執行者知道問題所在。
    
    3. **輸出結果**：
       - 請輸出更新後的**完整 Markdown 清單**。
       - 這份清單將直接覆蓋系統紀錄，請務必保持格式正確，不要遺漏任何項目。
    """,
    output_key="final_output" # 關鍵：覆蓋原本的 final_output
)

# 3. Execution Verifier: 檢查是否全部完成
exit_loop_tool = get_exit_loop_tool()

execution_verifier = LlmAgent(
    name="execution_verifier",
    model=MODEL,
    tools=[exit_loop_tool],
    instruction="""
    你是一個驗收員。
    
    ## 輸入資訊
    - 當前清單: {final_output}
    
    ## 你的任務
    檢查清單中是否**所有**項目都已經標記為 `[x]`。
    
    - **情況一：全部完成**
      請呼叫工具 `exit_loop_action()` 結束任務。
      (注意：工具名稱精確為 "exit_loop_action"，不要擅自加前綴)
      
    - **情況二：還有未完成項目**
      請輸出一段簡短的鼓勵話語，讓團隊繼續執行下一個步驟。
    """,
    # 不需要 output_key，它的主要作用是觸發 tool
)

# 4. The Loop (Internal)
execution_loop = GenericLoop(
    name="execution_loop",
    sub_agents=[executor_worker, progress_update_agent, execution_verifier],
    max_iterations=10, 
    description="Iteratively executes tasks and updates the status list."
)

# 5. Summarizer: 最終總結 (詳細版)
summarizer_agent = LlmAgent(
    name="summarizer_agent",
    model=MODEL,
    instruction="""
    你是一個專案總結者。你的功能類似狀態機紀錄，詳細記錄並總結所有操作過程中的產物。
    
    ## 輸入資訊
    - 原始問題: {session.query}
    - 執行結果記錄: 
    {final_output}
    
    ## 你的任務
    請根據「執行結果記錄」中的資訊，回答使用者的「原始問題」。
    
    ## 輸出格式
    - 這是**詳細報告**，請包含執行過程中的重要數據、檔案列表或步驟。
    - 請用清晰、有條理的語言回答。
    """,
    output_key="final_summary"
)

# 6. Clean Answer Agent: 精簡回答 (針對問題)
clean_answer_agent = LlmAgent(
    name="clean_answer_agent",
    model=MODEL,
    instruction="""
    你是一個精簡的回答者。

    ## 輸入資訊
    - 原始問題: {session.query}
    - 詳細總結: {final_summary}

    ## 你的任務
    請根據「詳細總結」，針對「原始問題」給出一個**最直接、最精簡**的回答。
    
    ## 輸出規則
    ## 輸出規則
    - **只回答結論跟簡單原因**。
    - **務必使用繁體中文 (Traditional Chinese)** 回答。
    - **不要**包含執行過程、搜尋步驟或除錯訊息，除非使用者問的是過程。
    - 就像一個專業顧問直接給出答案一樣。
    """,
    output_key="clean_output"
)

# ✨ The Full Executor Agent ✨
execution_agent = SequentialAgent(
    name="execution_agent",
    sub_agents=[execution_loop, summarizer_agent, clean_answer_agent],
    description="Executes the plan and provides a final summary and clean output."
)