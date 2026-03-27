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

    # 1. Security/Escalation Path
    if status == "flagged" or next_hop == "escalator":
        return "escalator"
    
    # 2. Planning Path
    if status == "active":
        return "architect"
    
    # 3. Execution Path (Handles both first run and Healer retries)
    if status == "planned" or status == "retrying":
        return "executor"
    
    # 4. Verification & Self-Healing Path
    if status == "completed":
        return "healer"
    
    # 5. Completion Path
    if status == "verified" or status == "escalated" or next_hop == "end":
        return END

    return END

# --- GRAPH DEFINITION ---
workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("classifier", classifier_agent)
workflow.add_node("escalator", escalator_agent)
workflow.add_node("architect", architect_agent)
workflow.add_node("executor", executor_agent)
workflow.add_node("healer", healer_agent)

# Entry Point
workflow.set_entry_point("classifier")

# Define Edges with the Router
workflow.add_conditional_edges(
    "classifier",
    router,
    {"escalator": "escalator", "architect": "architect", END:END}
)

workflow.add_conditional_edges(
    "architect",
    router,
    {"executor": "executor"}
)

workflow.add_conditional_edges(
    "executor",
    router,
    {"healer": "healer"}
)

workflow.add_conditional_edges(
    "healer",
    router,
    {
        "executor": "executor",
        "escalator": "escalator",
        END: END  # Use the END constant as both key and value
    }
)

workflow.add_edge("escalator", END)

# Compile the final app
app = workflow.compile()