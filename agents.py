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
    Return ONLY a JSON object:
    {{
      "risk_score": int, 
      "category": "onboarding" | "meeting_action" | "procurement" | "adhoc", 
      "entities": {{"name": "string", "id": "string", "item": "string"}},
      "reasoning": "string"
    }}
    """
    
    response = smart_llm.invoke(classifier_prompt)
    analysis = robust_json_parser(response.content)
    
    risk = analysis.get("risk_score", 0)
    is_blocked = risk >= 8
    
    return {
        "risk_level": risk,
        "current_entities": analysis.get("entities", {}),
        "task_status": "flagged" if is_blocked else "active",
        "next_step": "escalator" if is_blocked else analysis.get("category", "adhoc"),
        "audit_trail": [{
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "agent": "Classifier",
            "action": "Intent & Entity Extraction",
            "reasoning": analysis.get("reasoning")
        }]
    }

# --- AGENT 2: ESCALATOR
def escalator_agent(state: AgentState):
    # 1. Pull context from the Classifier's work
    user_query = state["messages"][-1].content
    initial_reasoning = state["audit_trail"][-1].get("reasoning", "Suspicious activity detected.")
    risk_level = state.get("risk_level", "Unknown")

    escalation_prompt = f"""
    SYSTEM: Security Operations Center (SOC)
    USER REQUEST: "{user_query}"
    CLASSIFIER FINDINGS: "{initial_reasoning}"
    RISK SCORE: {risk_level}/10

    Task: Generate a 1-sentence professional security justification for locking this request.
    Example: "Attempted unauthorized database manipulation via prompt injection detected."
    Return ONLY a JSON object:
    {{
      "sentence": "string", 
      "reasoning": "string",
      "assigned_group": "string"
    }}
    """
    
    soc_report = fast_llm.invoke(escalation_prompt)
    soc_analysis = robust_json_parser(soc_report.content)

    ticket_result = tools.create_system_ticket(
        reason=soc_analysis.get("sentence"),
        assigned_group=soc_analysis.get("assigned_group")
    )
    
    return {
        "task_status": "escalated",
        "next_step": "end", # This tells the router to stop the graph
        "audit_trail": [{
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "agent": "Escalator",
            "action": "CRITICAL: Security Lockout",
            "incident_report": soc_report,
            "ticket_id": ticket_result.get("ticket_id", "ERR-LOG"),
            "reasoning": analysis.get("reasoning")
        }]
    }

# --- AGENT 3: ARCHITECT ---
def architect_agent(state: AgentState):
    user_input = state["messages"][-1].content
    category = state.get("next_step", "adhoc")
    entities = state.get("current_entities", {})
    
    architect_prompt = f"""
    Create a SEQUENTIAL step-wise execution plan for: {category}.
    User Request: "{user_input}"
    Entities identified: {entities}

    STRICT CONSTRAINTS:
    1. PLAN LENGTH: Minimum 5 steps (Can be more if the task is complex).
    2. STEP FORMAT: Each step MUST start with 'Step-X: ' followed by a short 3-5 word action.
    3. SEQUENTIAL LOGIC: Step 2 must logically follow Step 1.

    Return ONLY a JSON object:
    {{
      "plan_name": "string",
      "reasoning": "string",
      "steps": ["Step-1: [Action]", "Step-2: [Action]", "...", "Step-N: [Action]"]
    }}
    """

    response = smart_llm.invoke(architect_prompt)
    plan = robust_json_parser(response.content)
    steps = plan.get("steps", [])

    return {
        "task_status": "planned",
        "next_step": "executor",
        "context": {**state.get("context", {}), "execution_plan": plan["steps"]},
        "audit_trail": [{
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "agent": "Architect",
            "action": f"Created {len(plan['steps'])}-step {category} plan",
            "reasoning": plan.get("reasoning"),
            "plan_details": steps,
            "details": f"Plan: {plan.get('plan_name')}"
        }]
    }

# --- AGENT 4: EXECUTOR ---
def executor_agent(state: AgentState):
    plan = state["context"].get("execution_plan", [])
    entities = state.get("current_entities", {})
    execution_results = []
    
    for step in plan:
        # Tool Mapping Logic
        if "Inventory" in step or "Check" in step:
            res = tools.update_inventory_ledger(item=entities.get("item", "General"), action="Check Stock")
        elif "Email" in step or "Send" in step:
            res = tools.send_slack_alert(channel="#alerts", message=f"Task: {step}")
        elif "Ticket" in step or "Request" in step:
            res = tools.create_workflow_task(summary=step, entity=entities.get("name", "System"))
        elif "SLA" in step:
            # FORCE A FAILURE for demo purposes if SLA is mentioned
            res = {"status": "ERROR", "message": "SLA Breach Detected: 52 hours elapsed"}
        else:
            res = {"status": "SUCCESS", "step": step}
        
        execution_results.append(res)
    
    step_summary = []
    for i in range(len(plan)):
        status = execution_results[i].get('status', 'UNKNOWN')
        msg = execution_results[i].get('message', '')
        step_summary.append(f"{plan[i]} ➔ {status} {'(' + msg + ')' if msg else ''}")

    return {
        "task_status": "completed",
        "next_step": "healer",
        "context": {**state.get("context", {}), "execution_log": execution_results},
        "audit_trail": [{
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "agent": "Executor",
            "action": f"Completed Pipeline",
            "details": f"Processed {len(execution_results)} steps",
            "execution_summary": step_summary,
        }]
    }

# --- AGENT 5: HEALER (The "Winning" Logic) ---
def healer_agent(state: AgentState):
    logs = state["context"].get("execution_log", [])
    attempts = state.get("recovery_attempts", 0)
    
    # Identify specific failure types
    failures = [log for log in logs if log.get("status") == "ERROR"]
    
    if not failures:
        return {"task_status": "verified", "next_step": "end"}

    if attempts >= 1:
        # If we already tried to fix it once and failed, escalate to human
        return {
            "task_status": "failed_critical", 
            "next_step": "escalator",
            "audit_trail": [{"agent": "Healer", "action": "Max retries reached. Escalating."}]
        }

    # BRAIN LOGIC: Create a "Healing Plan"
    print(f"🛠️ HEALER: Analyzing {len(failures)} failures...")
    healing_steps = []
    for f in failures:
        if "SLA" in f.get("message", ""):
            healing_steps.append("Reroute to Delegate Manager")
        if "Stock" in f.get("message", "") or "Inventory" in f.get("message", ""):
            healing_steps.append("Create Emergency Procurement Ticket")

    return {
        "task_status": "retrying",
        "recovery_attempts": attempts + 1,
        "next_step": "executor",
        "context": {**state.get("context", {}), "execution_plan": healing_steps},
        "audit_trail": [{
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "agent": "Healer",
            "action": "Self-Correction Triggered",
            "details": f"Injecting recovery steps: {healing_steps}"
        }]
    }