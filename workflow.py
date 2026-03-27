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

    # 1. Security First
    if status == "flagged":
        return "escalator"
    
    # 2. Planning Phase
    if status == "active":
        return "architect"
    
    # 3. Execution Phase
    if status == "planned" or status == "retrying":
        return "executor"
    
    # 4. Verification/Healing Phase
    if status == "completed":
        return "healer"
    
    # 5. Exit
    if status == "verified" or next_hop == "end":
        return END

    return END

# --- GRAPH DEFINITION ---
workflow = StateGraph(AgentState)

# Add all 5 Agents as Nodes
workflow.add_node("classifier", classifier_agent)
workflow.add_node("escalator", escalator_agent)
workflow.add_node("architect", architect_agent)
workflow.add_node("executor", executor_agent)
workflow.add_node("healer", healer_agent)

# Set the Entry Point
workflow.set_entry_point("classifier")

# Define the Paths
workflow.add_conditional_edges(
    "classifier",
    router,
    {"escalator": "escalator", "architect": "architect"}
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
    {"executor": "executor", END: END} # The Healing Loop!
)

workflow.add_edge("escalator", END)

# Final Compilation
app = workflow.compile()