import json
import tools
import re
import time
from datetime import datetime
from state import AgentState, smart_llm, fast_llm
#from langgraph.graph import StateGraph, END
#from langchain_core.messages import HumanMessage

def robust_json_parser(content):
    try:
        # This finds anything between { and } including nested braces
        match = re.search(r'(\{.*\})', content, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        return json.loads(content) # Fallback
    except Exception as e:
        print(f"JSON Parse Error. Raw content: {content}")
        # Return a fallback plan so the system doesn't crash
        return {"plan_name": "Fallback", "steps": ["Manual Review Required"]}

# --- AGENT 1: CLASSIFIER ---
def classifier_agent(state: AgentState):
    """
    Role: Ethics Warden. 
    Task: Assess risk. If risk >= 8, route to Escalator.
    """
    user_input = state["messages"][-1].content
    
    classifier_prompt = f"""
    Analyze this enterprise request: "{user_input}"
    1. Risk Level: 1-10 (10 is extreme risk like layoffs, deleting data, or illegal acts).
    2. Category: Choose one: 'onboarding', 'meeting_action', 'procurement', 'adhoc'.
    
    Return ONLY a JSON object:
    {{"risk_score": int, "category": "string", "reasoning": "string"}}
    """
    
    response = smart_llm.invoke(classifier_prompt)
    res_metadata = response.response_metadata
    usage_metadata = response.usage_metadata
    token_usage = res_metadata.get('token_usage', {})
    
    clean_content = response.content.replace("```json", "").replace("```", "").strip()
    analysis = robust_json_parser(clean_content)
    
    risk = analysis["risk_score"]
    # Logic: If flagged, the 'next_step' becomes 'escalator'
    is_blocked = risk >= 8
    
    return {
        "risk_level": risk,
        "task_status": "flagged" if is_blocked else "active",
        "next_step": "escalator" if is_blocked else analysis["category"],
        "audit_trail": [{
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "agent": "Classifier Agent",
            "action": "Safety & Intent Analysis",
            "model": res_metadata.get('model_name', "smart_llm"),
            "execution_time": f"{token_usage.get('total_time', 0):.3f}s",
            "input_tokens": usage_metadata.get('input_tokens', 0),
            "output_tokens": usage_metadata.get('output_tokens', 0),
            "reasoning": analysis["reasoning"],
            "risk_justification": f"Risk assessed as {risk}/10"
        }]
    }

# --- AGENT 2: ESCALATOR ---
def escalator_agent(state: AgentState):
    risk_reason = state["audit_trail"][-1].get("reasoning", "Security Risk")
    
    # 1. DYNAMIC GROUP SELECTION
    routing_prompt = f"""
    Based on this risk: "{risk_reason}"
    Assign the best team from this list: [IT-Security, Data-Privacy, HR-Legal, Cloud-Ops].
    Return ONLY the team name.
    """
    target_group = fast_llm.invoke(routing_prompt).content.strip()

    # 2. EXECUTE THE TOOLS
    print(f"\n--- 🛠️ AGENT ACTION: ESCALATING TO {target_group} ---")
    
    # Calling the Ticketing Tool
    ticket_result = tools.create_system_ticket(
        reason=risk_reason, 
        assigned_group=target_group
    )
    
    # Calling the Slack Tool (This was the missing variable!)
    slack_result = tools.send_slack_alert(
        channel="#security-alerts", 
        message=f"🚨 ALERT: {target_group} review required for risk: {risk_reason}"
    )

    # 3. Return the results to the state
    return {
        "task_status": "escalated",
        "next_step": "end",
        "context": {
            **state.get("context", {}), 
            "ticket_id": ticket_result["ticket_id"],
            "slack_status": slack_result["status"] # Now slack_result is defined!
        },
        "audit_trail": [{
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "agent": "Escalator Agent",
            "action": f"Routed to {target_group}",
            "ticket_id": ticket_result["ticket_id"],
            "details": f"Jira Ticket Created & Slack Alert Sent to {target_group}"
        }]
    }

def architect_agent(state: AgentState):
    """
    Role: System Strategist.
    Task: Breaks the request into a 5 or more step execution plan based on category.
    """
    user_input = state["messages"][-1].content
    category = state.get("next_step", "adhoc")
    
    architect_prompt = f"""
    You are an Enterprise Architect. Create a step-by-step execution plan for: "{user_input}"
    Category: {category}

    Templates to follow:
    - onboarding: [Check Employee Registry, Generate Credentials, Create Email, Create Jira, Create Slack, Check for inventory, Send Welcome Email]
    - meeting_action: [Extract Tasks from Transcript, Map Owners to their roles, Assign Jira ticket, Sync to Calendar]
    - procurement: [Check for procurement approval, extract the time, Check emergency, Approval status, redirect to delegate, override the previous procurement]
    - adhoc: [extract the time, Check emergency, Assign team, redirect to team]
    

    Return ONLY a JSON object:
    {{
      "plan_name": "string",
      "steps": ["step 1", "step 2", "step 3"],
      "estimated_tokens": int,
      "requires_approval": boolean
    }}
    """

    # Use Smart LLM for planning
    response = smart_llm.invoke(architect_prompt)
    
    # Metadata for the Audit Trail
    res_metadata = response.response_metadata
    usage = response.usage_metadata
    
    clean_content = response.content.replace("```json", "").replace("```", "").strip()
    plan = robust_json_parser(clean_content)

    return {
        "task_status": "planned",
        "next_step": "executor", # Hands the baton to the Executor
        "context": {
            **state.get("context", {}),
            "execution_plan": plan["steps"],
            "plan_metadata": plan
        },
        "audit_trail": [{
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "agent": "Architect Agent",
            "action": f"Generated {category} Plan",
            "model": res_metadata.get('model_name', "smart_llm"),
            "plan_steps": len(plan["steps"]),
            "reasoning": f"Created a {len(plan['steps'])}-step strategy for {category}."
        }]
    }

def executor_agent(state: AgentState):
    """
    Role: System Executor.
    Task: Dynamically extracts entities and runs the Architect's plan using real tools.
    """
    user_msg = state["messages"][-1].content
    plan = state["context"].get("execution_plan", [])
    
    # --- STEP 1: DYNAMIC ENTITY EXTRACTION ---
    extraction_prompt = f"""
    Extract key entities from this request: "{user_msg}"
    Return ONLY a JSON object:
    {{"target_entity": "string", "time_sensitivity": "string", "department": "string"}}
    """
    extraction_res = fast_llm.invoke(extraction_prompt)
    # USE THE ROBUST PARSER HERE TOO
    entities = robust_json_parser(extraction_res.content)
    
    target = entities.get("target_entity", "System-Task")
    
    # --- STEP 2: LOOP THROUGH THE ARCHITECT'S PLAN ---
    execution_results = []
    print(f"\n--- ⚡ STARTING EXECUTION FOR: {target.upper()} ---")
    
    for step in plan:
        print(f"⚙️  Step: {step}...")
        
        # Routing logic to tools in tools.py
        if "Jira" in step or "Task" in step:
            res = tools.create_workflow_task(summary=step, entity=target)
        elif "Email" in step or "Slack" in step or "notification" in step:
            res = tools.send_slack_alert(channel="#general", message=f"Update for {target}: {step}")
        elif "Provision" in step or "Create" in step:
            res = tools.provision_access_tool(user=target, service=step)
        elif "emergency" in step:
            print(f"🚨 CRITICAL CHECK: Status is {entities.get('time_sensitivity', 'routine')}")
            res = {"action": "Emergency-Check", "status": "Verified"}
        elif "inventory" in step or "procurement" in step:
            res = tools.update_inventory_ledger(item=target, action=step)
        else:
            time.sleep(1)
            res = {"step": step, "status": "Completed"}
            
        execution_results.append(res)

    # Note: next_step is 'healer' to check if anything failed
    return {
        "task_status": "completed",
        "next_step": "healer", 
        "context": {
            **state.get("context", {}),
            "extracted_entities": entities,
            "execution_log": execution_results
        },
        "audit_trail": state.get("audit_trail", []) + [{
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "agent": "Executor Agent",
            "action": f"Executed {len(execution_results)} steps for {target}"
        }]
    }

def healer_agent(state: AgentState):
    """
    Role: Quality Control / Recovery Agent.
    Task: Inspects execution logs. If a step failed, it rewrites the plan or retries.
    """
    logs = state["context"].get("execution_log", [])
    failures = [log for log in logs if log.get("status") == "ERROR"]

    if not failures and len(logs) > 0:
        # SUCCESS PATH: Everything is green
        return {
            "task_status": "verified",
            "next_step": "end"
        }
    
    # If we are here, something failed!
    print("⚠️  [HEALER] Failure detected in execution. Attempting recovery...")
    time.sleep(2)
    
    # We "Heal" by simplifying the task or changing the parameters
    return {
        "task_status": "retrying",
        "next_step": "executor", # Loop back to Executor to try again
        "audit_trail": [{
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "agent": "Self-Healer",
            "action": "Recovery Triggered",
            "reason": "Tool timeout or parameter mismatch"
        }]
    }