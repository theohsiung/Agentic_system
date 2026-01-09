import sys
from pathlib import Path

# 將專案根目錄加入 Python 路徑
project_root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(project_root))

from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import FunctionTool
from google.adk.apps import App
from google.adk.runners import ResumabilityConfig, Runner
from src.utils.db import get_all_modules, get_files_by_module, get_content_by_file_name


todo_agent = LlmAgent(
    name="todo_agent",
    description="todo_agent",
    instruction="""你是 WMS 需求分析的規劃助手，負責將使用者需求轉換為待辦事項清單。

    ## 任務流程
    1. 使用 get_all_modules() 取得所有模組
    2. 針對可能相關的模組，使用 get_files_by_module(module) 取得文件清單
    3. 根據需求與文件名稱，判斷哪些文件可能需要查閱

    ## 輸出格式
    以點列方式輸出待辦事項，格式如下：

    TODO
    - [ ] 項目描述 | 備註說明
    - [ ] 項目描述 | 備註說明
    ...

    範例：
    TODO
    - [ ] 查閱「3.1入庫單維護」| 了解入庫流程欄位定義
    - [ ] 查閱「3.2入庫驗收作業」| 確認驗收邏輯
    - [ ] 查閱「4.1揀貨單維護」| 可能涉及揀貨流程調整
    """,
    model=LiteLlm(model="ollama_chat/ministral-3:8b"),
    tools=[
        FunctionTool(get_all_modules, require_confirmation=False),
        FunctionTool(get_files_by_module, require_confirmation=False),
    ],
    output_key="TODO_list"
)

aimming_agent = LlmAgent(
    name="aimming_agent",
    description="aimming_agent",
    instruction="""你是 WMS 文件查閱助手，負責執行 TODO list 中的查閱任務並篩選重點文件。

    ## 輸入
    你會收到前一個 agent 產生的 TODO list {TODO_list}，格式如下：
    TODO
    - [ ] 查閱「文件名稱」| 備註說明
    ...

    ## 任務流程
    1. 解析 TODO list，提取每個待查閱的文件名稱
    2. 對每個文件使用 get_content_by_file_name(file_name) 讀取內容
    - 注意：file_name 只需要文件名稱，不含「」符號
    - 例如：get_content_by_file_name("3.1入庫單維護")
    3. 閱讀文件內容，根據備註說明的目的判斷該文件是否為重點文件
    4. 重點文件的判斷標準：
    - 文件內容直接涉及使用者需求的功能
    - 文件描述的流程或欄位與需求修改相關
    - 文件包含需要調整的業務邏輯

    ## 輸出格式
    請輸出篩選後的重點文件清單：
    list: ["文件名稱", ...]

    ## 注意事項
    - 必須實際讀取每個文件內容才能判斷相關性
    - 如果 get_content_by_file_name 回傳 None，表示文件不存在，請記錄並跳過
    - 優先標記與需求最相關的文件
    """,
    model=LiteLlm(model="ollama_chat/ministral-3:8b"),
    tools=[
        FunctionTool(get_content_by_file_name, require_confirmation=False),
        FunctionTool(get_files_by_module, require_confirmation=False),
    ],
    output_key="aimming_list"
)

# 使用 SequentialAgent 串接兩個 agent
# todo_agent 的 output="TODO_list" 會自動傳遞給 aimming_agent
root_agent = SequentialAgent(
    name="root_agent",
    description="需求分析規劃流程，找出物標文件，回傳目標文件的list",
    sub_agents=[todo_agent, aimming_agent],
)

app = App(
    name="analyser",
    root_agent=root_agent,
    resumability_config=ResumabilityConfig(
        is_resumable=False,
    )
)