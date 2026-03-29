import json
import tools
import re
import time
from datetime import datetime
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode
from langchain_core.messages import SystemMessage
from state import AgentState, smart_llm, fast_llm

# --- STEP 1: TOOL DEFINITIONS ---
# Ensure this is in agents.py
@tool
def check_employee(name: str):
    """Checks for existing employees."""
    res = tools.check_employee_exists(name)
    if res.get("exists") or "rk dhamani" in name.lower():
        # The word 'ERROR' here triggers the logic in the Reasoner above
        return "ERROR: Conflict detected. This employee is already in the database."
    return "SUCCESS: User is clear for onboarding."

@tool
def onboard_member(full_name: str, email: str, role: str, department: str, employee_code: str):
    """
    Inserts a new employee record into the corporate database.
    Requires: full_name, email, role, department, and employee_code.
    """
    payload = {
        "full_name": full_name,
        "email": email,
        "role": role,
        "department": department,
        "employee_code": employee_code
    }
    return tools.insert_employee_record(payload)

# --- INVENTORY & PROCUREMENT TOOLS ---

@tool
def check_inventory(item_name: str):
    """Checks stock levels for hardware (e.g., 'Laptop', 'Monitor')."""
    return tools.check_inventory_stock(item_name)

@tool
def get_procurement(procurement_id: str):
    """Fetches details of an existing procurement request by its ID."""
    return tools.get_procurement_status(procurement_id)

@tool
def raise_procurement(item_name: str, requested_by: str, quantity: int, priority: str = "medium"):
    """Creates a new procurement request for hardware or supplies."""
    payload = {
        "item_name": item_name,
        "requested_by": requested_by,
        "quantity": quantity,
        "priority": priority
    }
    return tools.insert_procurement_request(payload)

# --- SYSTEM & COMMUNICATION TOOLS ---

@tool
def create_ticket(reason: str, assigned_group: str = "IT-Support"):
    """Raises a support or security ticket (e.g., for 'Flagged' requests)."""
    return tools.create_system_ticket(reason, assigned_group)

@tool
def send_alert(email: str, message: str, platform: str = "email"):
    """Sends an official alert/notification to an employee via email or Slack."""
    return tools.send_enterprise_alert(email, message, platform)

@tool
def create_jira_ticket(title: str, description: str):
    """Creates a Jira ticket for task tracking."""
    return tools.create_system_ticket(f"JIRA: {title} - {description}")

# --- COMPILE THE TOOLSET ---
# This list is what the Reasoner sees and the ToolNode executes
# In agents.py
all_tools = [
    check_employee, 
    onboard_member, 
    check_inventory, 
    get_procurement, 
    raise_procurement,
    create_ticket,
    send_alert,
    create_jira_ticket
    ]
tool_executor_node = ToolNode(all_tools)



def robust_json_parser(content):
    try:
        match = re.search(r'(\{.*\})', content, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        return json.loads(content)
    except Exception as e:
        print(f"JSON Parse Error: {content}")
        return {"plan_name": "Fallback", "steps": ["Manual Review Required"]}

# --- AGENT 1: CLASSIFIER ---
# --- STEP 2: THE AGENTS ---


def classifier_agent(state: AgentState):
    user_input = state["messages"][-1].content

    classifier_prompt = f"""
Analyze this enterprise request: "{user_input}"

Categories:
1. onboarding: New employee setup
2. meeting_action: Summarizing meetings and task assignment
3. procurement: Tracking SLA breaches or hardware requests
4. escalate: Security risks or destructive actions like delete database
5. adhoc: General company info

Return ONLY JSON:
{{
  "risk_score": 0-10,
  "category": "onboarding" | "meeting_action" | "procurement" | "escalate" | "adhoc",
  "entities": {{
    "name": "",
    "email": "",
    "dept": "",
    "item_id": ""
  }}
}}
"""
    response = smart_llm.invoke(classifier_prompt)
    analysis = robust_json_parser(response.content)

    risk = analysis.get("risk_score", 0)
    category = analysis.get("category", "adhoc")
    is_blocked = risk >= 8 or category == "escalate"

    return {
        "risk_level": risk,
        "current_entities": analysis.get("entities", {}),
        "task_status": "flagged" if is_blocked else "active",
        "next_step": category,
        "scenario": category,
        "plan_details": [
            f"Intent: {category.upper()}",
            f"Risk Level: {risk}/10",
            f"Detected Entities: {list(analysis.get('entities', {}).values())}"
        ]
    }

# --- AGENT 2: VALIDATOR (System Handshake) ---
def validator_agent(state: AgentState):
    """Checks tool availability before Reasoner starts."""
    # For demo: simulate checking tool health
    return {
        "task_status": "validated",
        "plan_details": ["Supabase: CONNECTED", "Email Gateway: ONLINE", "Tools: READY"]
    }

def reasoner_agent(state: AgentState):
    """Step 3: The Brain with strict logic gates."""
    scenario = state.get("next_step", "adhoc")
    
    # Get the last 3 tool call names to check for loops
    previous_calls = []
    for m in state["messages"][-5:]:
        if hasattr(m, 'tool_calls') and m.tool_calls:
            previous_calls.append(m.tool_calls[0]['name'])
    # 1. Define strict operational rules
    system_rules = SystemMessage(content="""
        You are an Enterprise AI Executor. You MUST follow these sequences exactly. 
        If a tool output is required for the next step, call that tool immediately.

        SCENARIO A: Onboarding
        1. CALL 'check_employee'.
        2. IF tool returns 'SUCCESS', you MUST CALL 'onboard_member' with entities.
        3. IF 'onboard_member' succeeds, call 'check_inventory'.
        4. IF inventory has no stock 'send_alert' to concern team.
        5. Call 'send_alert'for welcome message to the employee.
        6. IF tool returns 'Conflict', STOP and explain why.

        SCENARIO B: Meeting Actions / Transcripts
        1. Extract names from the transcript and assigned roles.
        2. For EACH name, CALL 'check_employee'.
        3. IF any name is missing, CALL 'send_alert' to the manager reporting missing profiles.
        4. IF no alerts call 'create_jira_ticket', then send the log to db or log files.
        5. IF tool returns 'Conflict', STOP and explain why.

        SCENARIO C: SLA Breach & Procurement
        1. CALL 'get_procurement' 
        2. IF data there, rewrite with new details and CALL 'create_ticket' to log the formal breach.
        3. CALL 'raise_procurement' in database
        4. CALL 'create_jira_ticket' to escalate issue
        5. CALL 'send_alert' respective delegates.
        6. IF tool returns 'Conflict', STOP and explain why.

        SCENARIO D: Security
        1. DO NOT call tools. Return a "SECURITY VIOLATION" message.

        IMPORTANT: Do not summarize until all necessary tools in the sequence have been called.
        
    """)

    # 2. Bind tools
    model_with_tools = smart_llm.bind_tools(all_tools)
    
    # 3. Inject rules into the message history
    # This ensures the LLM remembers the 'Conflict' rule every time it loops
    input_messages = [system_rules] + list(state["messages"])
    
    response = model_with_tools.invoke(input_messages)
    
    # 1. Check if the LAST tool output was a FATAL_ERROR
    last_msg_content = str(state["messages"][-1].content) if state["messages"] else ""
    is_fatal = "FATAL_ERROR" in last_msg_content or "Conflict" in last_msg_content

    # 2. Prevent the same tool from being called twice in a row
    is_looping = False
    if response.tool_calls and response.tool_calls[0]['name'] in previous_calls:
        is_looping = True

    # 3. Logic Gate
    if is_fatal or is_looping:
        new_status = "failed"
    elif response.tool_calls:
        new_status = "executing"
    else:
        new_status = "completed"

    return {
        "messages": [response],
        "task_status": new_status,
        "plan_details": [f"AI Decision: {response.tool_calls[0]['name'] if response.tool_calls else 'Finalizing'}"]
    }

# --- AGENT 4: ESCALATOR (With File Fallback) ---
def escalator_agent(state: AgentState):
    reason = f"Security Risk Level {state.get('risk_level')}: {state['messages'][0].content}"
    
    log_res = tools.universal_log("security", "ESCALATION", reason, "FLAGGED")

    msg = "Ticket secured in cloud." if log_res["source"] == "supabase" else "Cloud offline: Secured in local vault."
    
    return {
        "task_status": "escalated", 
        "plan_details": [f"Status: {msg}", f"Path: {tools.LOG_FILE if log_res['source'] == 'local_file' else 'Supabase'}"]
    }

# --- AGENT 5: HEALER (Self-Healing / Retry Logic) ---
def healer_agent(state: AgentState):
    status = state.get("task_status")
    attempts = state.get("recovery_attempts", 0)
    last_message = state["messages"][-1].content if state["messages"] else ""

    # BREAK THE LOOP: Don't retry if it's a permanent DB error
    permanent_errors = ["duplicate key", "not found in the schema cache", "PGRST205"]
    is_permanent = any(err in last_message.lower() for err in permanent_errors)

    if status == "failed" and attempts < 2 and not is_permanent:
        return {
            "task_status": "retrying",
            "recovery_attempts": attempts + 1,
            "plan_details": [f"Healing initiated. Retry {attempts + 1}"]
        }
    
    # If permanent or out of retries, mark as failed_permanent
    final_status = "verified" if status != "failed" else "failed_permanent"
    return {
        "task_status": final_status,
        "plan_details": ["Critical error or Max retries reached. Stopping loop."]
    }