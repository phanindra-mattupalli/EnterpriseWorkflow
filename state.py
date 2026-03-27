import os
from dotenv import load_dotenv
from typing import Annotated, TypedDict, Union, List
from langgraph.graph.message import add_messages
from langchain_groq import ChatGroq

# Load environment variables
load_dotenv()

# Step 1: LLM Setup
# Use Llama-3.3-70b for "Heavy" reasoning (DecisionAgent)
smart_llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0, max_tokens=None, timeout=None, max_retries=2,)
# Use Llama-3.1-8b for "Lite" processing (IngestionAgent, AuditAgent)
fast_llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0, max_tokens=None, timeout=None, max_retries=2,)

def append_audit(left: list, right: list) -> list:
    """Usually In these types of systems, when a new value is sent to the state, the default behavior is to overwrite the old value.
       This function changes that rule,  It takes the existing list (left) and the new data (right) and merges them. It ensures the audit_trail acts like a ledger.  """
    return left + right

class AgentState(TypedDict):
    #New messages are appended to the chat rather than replacing the old ones.
    messages: Annotated[list, add_messages]
    #The 'Decision Ledger' for the Traceability Clerk
    audit_trail: Annotated[List[dict], append_audit] 
    # Tracks the current state of the workflow (e.g., 'pending', 'active', 'failed', 'flagged').
    task_status: str 
    # A numeric score to flag dangerous or biased outputs.
    risk_level: int # 1-10
    # A folder for technical data, like database IDs or raw API results, that doesn't fit in the chat.
    context: dict
    # A routing instruction which node to move to next
    next_step: str