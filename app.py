import streamlit as st
import json
import time
from workflow import app
from langchain_core.messages import HumanMessage

st.set_page_config(layout="wide", page_title="Enterprise OS")

# --- UI HEADER ---
st.title("🏢 ENTERPRISE AGENTIC OS v1.0")
st.markdown("---")

# --- 1. DEFINE THE THREE COLUMNS ---
col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    st.subheader("📥 Input Command")
    st.write("Triages requests, assesses risk, and executes enterprise tasks.")
    
    # Quick buttons
    if st.button("🚀 Onboard Sarah Jenkins"):
        st.session_state.query = "Onboard Sarah Jenkins as Lead Data Scientist. She starts Monday."
    if st.button("👥 Assing John as security lead"):
        st.session_state.query = "In recent meeting john has been assigned as security team lead"
    if st.button("📄 Send Procurement update"):
        st.session_state.query = "Send a procurement update to the Finance team about the new server parts."
    
    # Input Area
    query = st.text_area("Do you have any other query?", value=st.session_state.get('query', ""), height=100)
    run_btn = st.button("Execute Workflow", type="primary")

# --- 2. EXECUTION LOGIC ---
if run_btn and query:
    # Initialize State
    inputs = {
        "messages": [HumanMessage(content=query)],
        "audit_trail": [],
        "task_status": "pending",
        "context": {},
        "risk_level": 0
    }

    # These containers will stay "open" so we can write to them from the loop
    with col2:
        st.subheader("📍 Agent Progress")
        node_placeholder = st.container()

    with col3:
        st.subheader("📜 System Logs")
        log_placeholder = st.container()

    try:
        # 3. STREAM THE WORKFLOW
        # This mirrors your 'for output in app.stream' terminal code
        for output in app.stream(inputs, config={"recursion_limit": 25}):
            for node_name, state_update in output.items():
                
                # Update Column 2 (Agent Actions)
                with node_placeholder:
                    st.markdown(f"**📍 Node Completed: {node_name.upper()}**")
                    
                    if "risk_level" in state_update:
                        st.info(f"🛡️ Risk Assessment: {state_update['risk_level']}/10")
                    
                    if "execution_plan" in state_update:
                        st.success(f"📝 Plan Generated: {len(state_update['execution_plan'])} steps.")
                    
                    if "task_status" in state_update:
                        st.code(f"Status: {state_update['task_status']}")
                    st.divider()

                # Update Column 3 (Logs/JSON)
                with log_placeholder:
                    if "audit_trail" in state_update and state_update["audit_trail"]:
                        # Show the most recent log entry in a JSON box
                        st.json(state_update["audit_trail"][-1])

                # Small sleep to force Streamlit to "Draw" the update
                time.sleep(0.5)
        st.success("✅ WORKFLOW COMPLETE")

    except Exception as e:
        with col2:
            st.error(f"💥 SYSTEM CRASH: {str(e)}")
            st.warning("Check terminal for details.")