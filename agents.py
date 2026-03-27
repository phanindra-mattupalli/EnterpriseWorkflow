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

# --- AGENT 2: ESCALATOR ---
def escalator_agent(state: AgentState):
    risk_reason = state["audit_trail"][-1].get("reasoning", "Security Risk")
    ticket_result = tools.create_system_ticket(reason=risk_reason, assigned_group="Security-Ops")
    
    return {
        "task_status": "escalated",
        "next_step": "end",
        "audit_trail": [{
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "agent": "Escalator",
            "action": "Security Lockout Triggered",
            "ticket_id": ticket_result["ticket_id"]
        }]
    }

# --- AGENT 3: ARCHITECT ---
def architect_agent(state: AgentState):
    user_input = state["messages"][-1].content
    category = state.get("next_step", "adhoc")
    entities = state.get("current_entities", {})
    
    architect_prompt = f"""
    Create a mandatory 6-step plan for category: {category}.
    User Request: {user_input}
    Entities: {entities}

    Templates:
    - onboarding: [Grab details, Generate ID, Create DB Record, Request ID Card, Check Inventory, Send Welcome Email]
    - meeting_action: [Extract items, Check working days, Check employee leave, Generate task, Send to teams, Log Audit]
    - procurement: [List procurements, Select target, Check 48hr SLA, Raise concern, Reroute to delegate, Rewrite DB Log]
    - adhoc: [Verify escalation, Raise ticket, Allot team, Post to DB]

    Return ONLY JSON: {{"plan_name": "string", "steps": ["step 1", "step 2", "step 3", "step 4", "step 5", "step 6"]}}
    """

    response = smart_llm.invoke(architect_prompt)
    plan = robust_json_parser(response.content)

    return {
        "task_status": "planned",
        "next_step": "executor",
        "context": {**state.get("context", {}), "execution_plan": plan["steps"]},
        "audit_trail": [{
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "agent": "Architect",
            "action": f"Generated {category} workflow",
            "steps": len(plan["steps"])
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

    return {
        "task_status": "completed",
        "next_step": "healer",
        "context": {**state.get("context", {}), "execution_log": execution_results},
        "audit_trail": [{
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "agent": "Executor",
            "action": f"Executed {len(execution_results)} steps"
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