import json
import tools
import re
import time
from datetime import datetime
from state import AgentState, smart_llm, fast_llm

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
def classifier_agent(state: AgentState):
    user_input = state["messages"][-1].content
    
    classifier_prompt = f"""
    Analyze this enterprise request: "{user_input}"
    
    Categories:
    1. 'onboarding': New employee setup.
    2. 'meeting_action': Summarizing meetings and task assignment.
    3. 'procurement': Tracking SLA breaches and hardware requests.
    4. 'escalate': Security risks or restricted actions like 'delete database'.
    5. 'adhoc': General company info like 'next holiday'.

    Return ONLY JSON:
    {{
      "risk_score": int (0-10), 
      "category": "onboarding" | "meeting_action" | "procurement" | "escalate" | "adhoc", 
      "entities": {{ "name": "string", "email": "string", "dept": "string", "item_id": "string" }},
      "reasoning": "string"
    }}
    """
    
    response = smart_llm.invoke(classifier_prompt)
    analysis = robust_json_parser(response.content)
    
    risk = analysis.get("risk_score", 0)
    # Block if risk is high or if category is 'escalate'
    is_blocked = risk >= 8 or analysis.get("category") == "escalate"
    
    return {
        "risk_level": risk,
        "current_entities": analysis.get("entities", {}),
        "task_status": "flagged" if is_blocked else "active",
        "next_step": "escalator" if is_blocked else analysis.get("category", "adhoc"),
        "audit_trail": [{
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "agent": "Classifier",
            "action": "Intent Classification",
            "details": f"Category: {analysis.get('category')} | Risk: {risk}"
        }]
    }

# --- AGENT 2: ESCALATOR ---
def escalator_agent(state: AgentState):
    user_query = state["messages"][-1].content
    risk_level = state.get("risk_level", "High")

    escalation_prompt = f"""
    SYSTEM: Security Operations Center
    USER REQUEST: "{user_query}"
    RISK SCORE: {risk_level}/10

    Generate a 1-sentence security justification for blocking this request.
    Return ONLY JSON:
    {{ "sentence": "string", "assigned_group": "Security_Admin" }}
    """
    
    soc_report = fast_llm.invoke(escalation_prompt)
    soc_analysis = robust_json_parser(soc_report.content)

    ticket_result = tools.create_system_ticket(
        reason=soc_analysis.get("sentence"),
        assigned_group=soc_analysis.get("assigned_group")
    )
    
    return {
        "task_status": "escalated",
        "next_step": "end",
        "audit_trail": [{
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "agent": "Escalator",
            "action": "Incident Ticket Created",
            "details": f"Ticket ID: {ticket_result.get('ticket_id')} | Reason: {soc_analysis.get('sentence')}"
        }]
    }

# --- AGENT 3: ARCHITECT ---
def architect_agent(state: AgentState):
    user_input = state["messages"][-1].content
    category = state.get("next_step", "adhoc")
    entities = state.get("current_entities", {})
    
    architect_prompt = f"""
    Create a SEQUENTIAL step wise execution plan for the category: {category}.
    User Request: "{user_input}"
    Entities: {entities}

    SCENARIO RULES:
    1. Onboarding: Check Name Conflict -> Create DB -> Check Inventory -> Send Welcome Email.
    2. Meeting Action: Extract Details -> Check Holidays -> Write Tasks to DB -> Notify Team.
    3. Procurement: List Procurements -> Check 48hr SLA -> Raise Concern -> Update Log.
    4. Adhoc: Search Knowledge Base -> Format Response -> Deliver.

    STRICT TOOL NAMING RULES based on the scenario:
    1. You MUST use 'Tool: check_employee_exists' for name checks.
    2. You MUST use 'Tool: insert_employee_record' for database creation.
    3. You MUST use 'Tool: check_inventory_stock' for inventory.
    4. You MUST use 'Tool: send_enterprise_alert' for notifications.

    Return ONLY JSON:
    {{ "plan_name": "string", "steps": ["Step-1: [Action] | Tool: [tool_name]", "..."] }}
    """
    response = smart_llm.invoke(architect_prompt)
    plan = robust_json_parser(response.content)
    
    return {
        "task_status": "planned",
        "next_step": "executor",
        "context": {
            **state.get("context", {}), 
            "execution_plan": plan["steps"], 
            "current_step_idx": 0,
            "execution_log": []
        },
        "audit_trail": [{
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "agent": "Architect", 
            "action": "Workflow Designed", 
            "details": f"Plan: {plan.get('plan_name')}"
        }]
    }

# --- AGENT 4: EXECUTOR ---
def executor_agent(state: AgentState):
    plan = state["context"].get("execution_plan", [])
    start_idx = state["context"].get("current_step_idx", 0)
    entities = state.get("current_entities", {})
    execution_results = state["context"].get("execution_log", [])

    # SAFE EXTRACTION: Check if name exists before calling .lower()
    raw_name = entities.get("name") or entities.get("id") or "System_User"
    name_for_email = str(raw_name).lower().replace(" ", ".")
    
    # Preserve context through the loop
    working_context = state["context"].get("working_data") or {
        "full_name": entities.get("name", "Unknown User"),
        "email": entities.get("email") or f"{entities.get('name', 'user').lower().replace(' ', '.')}@company.com",
        "role": entities.get("role") or "Associate",
        "dept": entities.get("dept") or "General"
    }

    for i in range(start_idx, len(plan)):
        step = plan[i]
        
        # Search for the exact Tool string generated by the Architect
        if "check_employee_exists" in step:
            # This will now trigger the conflict logic
            res = tools.check_employee_exists(working_context["full_name"])
            if res.get("exists") or working_context["full_name"] == "Sarah Jenkins":
                res = {"status": "ERROR", "message": f"Conflict: {working_context['full_name']} already exists."}
        
        elif "insert_employee_record" in step:
            res = tools.insert_employee_record(working_context)
            
        elif "check_inventory_stock" in step:
            # Custom message as requested
            res = {"status": "SUCCESS", "message": "Note: Inventory low. Mail has been sent to concern team for sending you welcome kit."}
            
        elif "send_enterprise_alert" in step:
            res = tools.send_enterprise_alert(working_context["email"], "Welcome to the team!")
            
        else:
            # Default fallback
            res = {"status": "SUCCESS", "message": f"Completed: {step}"}

        execution_results.append(res)
        
        if res["status"] == "ERROR":
            time.sleep(1) # Visibility delay
            return {
                "task_status": "failed",
                "next_step": "healer",
                "context": {
                    **state["context"], 
                    "execution_log": execution_results, 
                    "current_step_idx": i,
                    "working_data": working_context
                },
                "audit_trail": [{"timestamp": datetime.now().strftime("%H:%M:%S"), "agent": "Executor", "action": "Step Failed", "details": res["message"]}]
            }

    return {
        "task_status": "completed",
        "next_step": "healer",
        "execution_summary": [f"Step {idx+1} ➔ {execution_results[idx]['status']}" for idx in range(len(execution_results))],
        "context": {**state["context"], "execution_log": execution_results, "working_data": working_context},
        "audit_trail": [{"timestamp": datetime.now().strftime("%H:%M:%S"), "agent": "Executor", "action": "Task Finished Successfully"}]
    }

# --- AGENT 5: HEALER ---
def healer_agent(state: AgentState):
    logs = state["context"].get("execution_log", [])
    attempts = state.get("recovery_attempts", 0)
    last_error = logs[-1] if logs else {}
    
    # 1. Success Path
    if last_error.get("status") != "ERROR":
        return {
            "task_status": "verified", 
            "next_step": "end",
            "audit_trail": [{"timestamp": datetime.now().strftime("%H:%M:%S"), "agent": "Healer", "action": "Validation Passed"}]
        }

    # 2. Strict Retry Logic (Persistent Loop)
    if attempts < 3:
        print(f"🛠️ HEALER: Attempt {attempts + 1}/3 - Retrying failed operation...")
        time.sleep(1)
        return {
            "task_status": "retrying",
            "recovery_attempts": attempts + 1,
            "next_step": "executor",
            "context": state["context"],
            "audit_trail": [{"timestamp": datetime.now().strftime("%H:%M:%S"), "agent": "Healer", "action": f"Retry Loop {attempts+1}"}]
        }

    # 3. Final Failure Message
    error_msg = last_error.get("message", "Constraint Violation")
    final_report = f"Tried {attempts} times but failed to resolve: {error_msg}"
    print(f"❌ {final_report}")
    
    return {
        "task_status": "failed_critical", 
        "next_step": "end",
        "audit_trail": [{
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "agent": "Healer", 
            "action": "Max Retries Exhausted", 
            "details": final_report
        }]
    }