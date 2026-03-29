![Architecture diagram](./assets/architecture.png)

# Architecture

This document describes how the system is structured: the agents, tools, shared state, and UI that together implement deep enterprise workflows.

---

## 1. Design goals

- **Depth > breadth**: implement a small number of workflows very thoroughly  
- **Agentic orchestration**: decisions are made by agents that can call tools, observe results, and adjust  
- **Safety and auditability**: every important action is logged with a consistent schema  
- **Demo‑friendly**: understandable from a single Streamlit page with an execution trace and summary

---

## 2. Core concepts

### AgentState (`state.py`)

`AgentState` is the single source of truth flowing through the graph.

Key fields:

- `user_input`: raw text prompt (plus transcript when relevant)  
- `messages`: conversation history between user and agents  
- `current_step`: the logical step name in the workflow  
- `tool_results`: list of recent tool outputs  
- `errors`: list of error messages  
- `retries`: retry counter for healing logic  
- `scenario`: one of `onboarding`, `meeting_actions`, `procurement`, `general`  
- `final_outcome`: structured dict with:
  - `status` (e.g., `success`, `needs_clarification`, `error`)
  - `summary`
  - `main_action`
  - `business_impact`

This structure makes it easy to render both a detailed trace and a compact summary.

---

## 3. Agent graph (`agents.py`)

The workflow is implemented as a LangGraph graph with the following main nodes:

1. **Classifier / Router**  
   - Reads `user_input` and sets `state["scenario"]`.  
   - Uses rules + LLM: onboarding vs meeting vs procurement vs general.

2. **Validator**  
   - Checks for missing fields or obviously unsafe actions.  
   - For example:
     - Onboarding: requires basic employee details.  
     - Meeting: flags ambiguous owners.  
     - Procurement: checks for SLA/breach signals in text.  
   - Writes validation messages into `messages` / `errors`.

3. **Reasoner**  
   - Central decision‑maker.  
   - Reads `scenario`, `validation`, and `tool_results`.  
   - Decides which tool(s) to call next:
     - Onboarding tools  
     - Meeting extraction / clarification tools  
     - Procurement update / escalation tools  
   - Uses LLM reasoning but is grounded in fixed schema/tool contracts.

4. **Tool node**  
   - Executes one or more tools defined in `tools.py`.  
   - Appends results into `tool_results`.  
   - Hands control back to the reasoner for the next step.

5. **Healer / Escalation node**  
   - Triggered when errors occur or retries exceed a threshold.  
   - Strategies:
     - Change plan (use a different tool)  
     - Fallback storage (local instead of Supabase)  
     - Mark for manual review / ticket creation

6. **Finalizer node**  
   - Produces a canonical `final_outcome` dict based on the scenario and last results.  
   - This is what the UI summary card uses.

The graph cycles between **Reasoner → Tools → Reasoner** until the workflow reaches a terminal condition or an error is escalated.

---

## 4. Tools layer (`tools.py`)

Tools encapsulate all external actions. Examples:

- **Employee & onboarding tools**
  - `lookup_employee`
  - `create_onboarding_record`

- **Procurement tools**
  - `get_procurement_request`
  - `update_procurement_approver`
  - `create_procurement_ticket`

- **Meeting / notification tools**
  - `send_notification`
  - optional transcript parsing helpers

- **Inventory / policy tools** (if present)
  - `check_inventory_for_request`

- **Audit logging**
  - `make_audit_log(...)`: creates a normalized log dict:
    - `timestamp`, `scenario`, `agent`, `action`, `status`, `details`, `target_id`, `storage_source`
  - `write_audit_log(...)`: tries to write to Supabase table (e.g., `audit_logs`), and falls back to local `audit_log.jsonl` if Supabase is unavailable.

Typical tool pattern:

1. Do the domain operation (DB insert, update, simulate call).  
2. Call `write_audit_log(...)` with consistent fields.  
3. Return a structured result object including `storage_source` and `audit_log`.

This makes it trivial to inspect what happened and where it was stored.

---

## 5. UI & execution trace (`app.py`)

The Streamlit app is the visual front‑end for the graph:

- **Inputs**
  - Text area for the user request
  - Optional `.txt` transcript upload or “Use sample transcript” button
  - Optional scenario hints / SLA dropdowns

- **Execution**
  - On click, the app constructs `final_input` (prompt + transcript if provided)
  - Invokes the LangGraph workflow with `AgentState(user_input=final_input, ...)`
  - Receives final `state` including `scenario`, `final_outcome`, `tool_results`, and trace

- **Outputs**
  - **Left column**: execution trace
    - Node names and order
    - Tool calls and raw outputs
    - Any errors / retries
  - **Right column**: _Execution Summary_ card
    - Scenario
    - Final status
    - Retries
    - Main action
    - Storage mode (Supabase / local)
    - Business impact line
    - Short summary text

This split lets a judge see both the “story” and the “guts” in a single screen.

---

## 6. Data & logging flow

1. User input and context go into `AgentState`.  
2. Graph nodes mutate `AgentState` as reasoning and tools progress.  
3. Each impactful action creates an audit log entry via `write_audit_log(...)`.  
4. Logs are written to:
   - Supabase (primary), or  
   - local `audit_log.jsonl` (fallback)  
5. UI reads `final_outcome` and `tool_results` to render summaries and traces.

The same schema is used for all logs, which makes it easy to query “what happened” for any given workflow run.

---

## 7. Extensibility

To add a new workflow:

1. Extend `scenario` taxonomy in `AgentState` and classifier node.  
2. Add scenario‑specific validation rules.  
3. Implement new tools in `tools.py` and wire them into the reasoner.  
4. Update finalizer to generate a `final_outcome` for the new scenario.  
5. Optionally add small UI controls in `app.py`.

The rest of the infrastructure (graph, logging, trace, summary card) remains unchanged.
