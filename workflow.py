from langgraph.graph import StateGraph, END
from state import AgentState
from agents import (
    classifier_agent, validator_agent, reasoner_agent, 
    tool_executor_node, healer_agent, escalator_agent
)
from langchain_core.messages import ToolMessage

def router(state: AgentState):
    status = state.get("task_status")
    risk = state.get("risk_level", 0)
    intent = state.get("next_step", "")
    messages = state.get("messages", [])

    # 1. PRIORITY: If we just came back from a tool, go to Reasoner to evaluate
    if messages and isinstance(messages[-1], ToolMessage):
        return "reasoner"

    # 2. Security/Escalation Logic
    if status == "flagged":
        # Only bypass escalation for Procurement if risk is manageable
        if intent == "PROCUREMENT" and risk <= 8:
            return "validator"
        return "escalator"
        
    # 3. Standard Flow
    if status == "active": return "validator"
    if status == "validated" or status == "retrying": return "reasoner"
    if status == "executing": return "tools"
    
    # 4. Termination/Recovery
    if status == "completed": return END
    if status == "failed": return "healer"
    
    return END

workflow = StateGraph(AgentState)

# Nodes
workflow.add_node("classifier", classifier_agent)
workflow.add_node("validator", validator_agent)
workflow.add_node("reasoner", reasoner_agent)
workflow.add_node("tools", tool_executor_node)
workflow.add_node("healer", healer_agent)
workflow.add_node("escalator", escalator_agent)

workflow.set_entry_point("classifier")

# Conditional Edges
# Every node uses the router to decide the next hop
workflow.add_conditional_edges("classifier", router)
workflow.add_conditional_edges("validator", router)
workflow.add_conditional_edges("reasoner", router)
workflow.add_conditional_edges("tools", router)
workflow.add_conditional_edges("healer", router)

# Escalator is a terminal node for security
workflow.add_edge("escalator", END)

app = workflow.compile()