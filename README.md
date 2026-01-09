# Agentic System: Intelligent Multi-Agent Orchestrator

This project implements a robust, state-aware multi-agent system designed to automatically Plan, Execute, and Verify complex tasks using the Google ADK.

## 🏗️ System Architecture

The system operates as a sequential pipeline managed by an **Orchestrator**, chaining specialized agents for distinct phases of the lifecycle.

```mermaid
graph TD
    User([User Request]) --> Orch[Orchestrator Agent]
    
    subgraph "Phase 1: Planning"
        Orch --> IP[Initial Planner]
        IP --> Draft[Draft Plan]
        Draft --> RefLoop{Refinement Loop}
        RefLoop --> Critic[Critic Agent]
        Critic --> Refiner[Refiner Agent]
        Refiner -->|Refine| RefLoop
        RefLoop -->|Approved| Presenter[Presenter Agent]
        Presenter -->|final_output| TodoList[TODO List]
    end
    
    TodoList --> Debug[Debug Agent]
    
    subgraph "Phase 2: Execution & Verification"
        Debug --> ExecLoop{Execution Loop}
        ExecLoop --> Worker[Executor Worker]
        Worker -->|Execute Task| Judge[Result Judge]
        Judge -->|Update Status| TodoList
        Judge --> Verifier[Execution Verifier]
        Verifier -->|Incomplete| ExecLoop
        Verifier -->|All Done| Summarizer[Summarizer Agent]
    end
    
    subgraph "Phase 3: Response"
        Summarizer -->|final_summary| Clean[Clean Answer Agent]
        Clean -->|clean_output| FinalAns([Final Answer])
    end
```

## 🧩 Key Components

### 1. Orchestrator (`meta_agents/orchestrator`)
The top-level controller that manages the session and queues the `SequentialAgent` pipeline. It ensures data flows seamlessly between agents via the `session.state`.

### 2. Planner (`sub_agents/planner`)
Responsible for breaking down user requests into actionable steps.
- **Initial Planner**: Generates a rough draft.
- **Refinement Loop**: A `GenericLoop` where a Critic reviews the plan and a Refiner improves it until it meets quality standards.
- **Presenter**: Formats the final approved plan into a structured Markdown checklist (`final_output`).

### 3. Executor (`sub_agents/executor`)
Responsible for carrying out the plan with self-correction.
- **Executor Loop**:
    - **Worker**: Picks the first unchecked item `[ ]`, executes it using DB/Tools, and reports results.
    - **Progress Update Agent (Judge)**: Strictly reviews the worker's result. Validates success, updates the checklist to `[x]`, and appends a result summary. If failed, adds a failure reason.
    - **Verifier**: Monitors the list. Exits the loop only when all items are complete.
- **Summarizer**: Synthesizes the execution logs into a detailed final report (`final_summary`).
- **Clean Answer Agent**: Distills the detailed report into a direct, concise answer (`clean_output`) in Traditional Chinese.

## 🔄 State Awareness & Smart Skipping
The system is designed to be state-aware. If you ask a follow-up question in the same session:
1. **Planner** detects an existing approved plan and skips regeneration.
2. **Executor** detects all items are `[x]` (Completed) and instantly skips execution steps.
3. **Responders** (Summarizer/Clean Answer) re-run based on the *new question* and *existing data*, providing immediate answers without redundant work.

## 🛠️ Tech Stack
- **Framework**: Google ADK (Agent Development Kit)
- **Model**: LiteLLM (Ollama/GPT-OSS)
- **State Management**: `InvocationContext.session.state`
- **Pattern**: `GenericLoop` & `SequentialAgent`

## 🚀 Getting Started

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
2. **Run the Server**:
   ```bash
   adk web
   ```
3. **Interact**:
   Open the Web UI or send requests via API.
