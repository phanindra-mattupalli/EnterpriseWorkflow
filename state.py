import os
from dotenv import load_dotenv
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import add_messages
from typing_extensions import Annotated
from langchain_groq import ChatGroq

# Load environment variables
load_dotenv()

# Step 1: LLM Setup
smart_llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0, max_tokens=None, timeout=None, max_retries=2)
fast_llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0, max_tokens=None, timeout=None, max_retries=2)

def append_audit(left: list, right: list) -> list:
    return left + right

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    audit_trail: Annotated[List[dict], append_audit]
    task_status: str
    risk_level: int
    context: dict
    next_step: str
    recovery_attempts: int
    current_entities: dict
    plan_details: list
    scenario: Optional[str]
    final_outcome: Optional[Dict[str, Any]]