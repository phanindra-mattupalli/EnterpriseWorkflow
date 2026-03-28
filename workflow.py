from langgraph.graph import StateGraph, END
from state import AgentState
from agents import (
    classifier_agent,
    escalator_agent,
    architect_agent,
    executor_agent,
    healer_agent  
)

def router(state: AgentState):
    status = state.get("task_status")
    next_hop = state.get("next_step")
    attempts = state.get("recovery_attempts", 0)

    if status == "flagged" or next_hop == "escalator":
        return "escalator"
    if status == "active":
        return "architect"
    
    # ADDED: If status is failed, we must route to the healer
    if status == "planned" or status == "retrying":
        return "executor"
    
    if status == "failed" or status == "completed":
        return "healer"
    
    if status == "verified" or status == "failed_critical" or attempts > 2:
        return "end"
    
    return "end"

# --- THE FIX: Define workflow BEFORE using it ---
workflow = StateGraph(AgentState)

workflow.add_node("classifier", classifier_agent)
workflow.add_node("escalator", escalator_agent)
workflow.add_node("architect", architect_agent)
workflow.add_node("executor", executor_agent)
workflow.add_node("healer", healer_agent)

workflow.set_entry_point("classifier")

# Use "end": END to map the router's string to the actual exit
workflow.add_conditional_edges(
    "classifier", router, {"escalator": "escalator", "architect": "architect", "end": END}
)
workflow.add_conditional_edges(
    "architect", router, {"executor": "executor", "end": END}
)
workflow.add_conditional_edges(
    "executor", router, {"healer": "healer", "end": END}
)
workflow.add_conditional_edges(
    "healer", router, {"executor": "executor", "escalator": "escalator", "end": END}
)

workflow.add_edge("escalator", END)
app = workflow.compile()