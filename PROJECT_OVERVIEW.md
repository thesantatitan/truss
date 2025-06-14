# Truss Project Knowledge Base

A high-level map of the current codebase – use this as a quick reference instead of grepping.

---

## 1. Core Concepts & Features

• Durable LLM agents executed as **Temporal workflows**.  
• Retryable **activities** wrap all external I/O (LLM calls, DB, tools).  
• **Postgres** stores all permanent history; **Redis** is used only for real-time streaming.  
• Agent behaviour (model, prompt, tools) defined by **AgentConfig** records in the DB.  
• The backend exposes a (planned) **FastAPI** server for REST endpoints.

---

## 2. Directory Guide

• `truss/data_models.py` – All Pydantic v2 data contracts shared across layers.  
• `truss/core/models/` – SQLAlchemy v2 ORM tables (`base.py` sets declarative base).  
• `truss/core/storage/postgres_storage.py` – Async DB helper used by activities.  
• `truss/activities/`
  – `storage_activities.py` → DB CRUD wrappers (`CreateRun`, `GetRunMemory`, …)  
  – `llm_activities.py`   → LLM streaming, Redis publish, durable write  
  – `tool_activities.py`  → Generic tool router + sample tools  
• `truss/workflows/agent_workflow.py` – Main Temporal workflow orchestrating reasoning loop, tool execution, cancellation & finalization.
• `truss/workflows/__init__.py` – Re-exports workflow class for easy imports.

---

## 3. Activity Names (used by Workflow)

`CreateRun`, `CreateRunStep`, `GetRunMemory`, `FinalizeRun`, `LLMStreamPublish`, `ExecuteTool`.

---

## 4. Important Behavioural Notes

• **Consistency**: The workflow only writes *complete* messages to Postgres; partial LLM deltas live solely in Redis streams.  
• **Cancellation**: External signal `request_cancellation` sets a flag; workflow cleans up and finalizes run status.  
• **Error Handling**: Any uncaught exception triggers `FinalizeRun` with `errored` status.  
• **Parallel Tools**: Tool calls are executed concurrently then persisted as `tool` role messages.

---

## 5. Testing Overview

• `tests/test_agent_workflow_initialization.py` – verifies initial DB writes and successful completion without tools.  
• `tests/test_agent_workflow_tool_execution.py` – covers tool call path and ensures results are persisted.  
• Additional unit tests live alongside their respective modules (e.g., model tests under `tests/`).

---

## 6. Tasks & Roadmap (TaskMaster)

Completed subtasks for Task 7 (Workflow): skeleton, init writes, reasoning loop, parallel tools, cancellation/error handling.  
Pending subtasks: query handler (`get_status`) and final integration tests.

---

Keep this document updated when new modules or directories are introduced. 
