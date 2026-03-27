import streamlit as st
import time
from workflow import app
from langchain_core.messages import HumanMessage
import pandas as pd
import os
from supabase import create_client, Client

# --- SUPABASE CONFIG FOR SLA LISTING ---
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(url, key)

st.set_page_config(layout="wide", page_title="Enterprise Agentic OS")

# --- CUSTOM CSS FOR "TERMINAL" FEEL ---
st.markdown("""
    <style>
    .node-box { border-left: 5px solid #00ff00; padding: 10px; margin: 10px 0; background-color: #1e1e1e; color: white; border-radius: 5px; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏢 ENTERPRISE AGENTIC OS v1.0")
st.markdown("---")

# Initialize session state for user input and query
if 'query' not in st.session_state: st.session_state.query = ""
if 'show_onboard' not in st.session_state: st.session_state.show_onboard = False
if 'show_transcript' not in st.session_state: st.session_state.show_transcript = False
if 'show_procurements' not in st.session_state: st.session_state.show_procurements = False
if 'show_other' not in st.session_state: st.session_state.show_other = False

col1, col2 = st.columns([1, 1], gap="large")

# --- COLUMN 1: INTERACTION & CONTROLS ---
with col1:
    st.subheader("📥 Process Selection")
    
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if st.button("🚀 Onboarding"):
            st.session_state.show_onboard = True
    with c2:
        if st.button("👥 Analyze Transcript"):
            st.session_state.show_transcript = True
    with c3:
        if st.button("📄 Audit SLA"):
            st.session_state.show_procurements = True
    with c4:
        if st.button("❓ Any Other Scenario"):
            st.session_state.show_other = True

    # Onboarding Special Handling
    if st.session_state.show_onboard:
        st.info("Mention employee fullname, role and department in the text box below")
        st.session_state.query = ""
        st.session_state.show_onboard = False

    # Transcript Special Handling
    if st.session_state.show_transcript:
        st.info("Paste the Meeting script in the textbox below and click EXECUTE WORKFLOW")
        st.session_state.query = ""
        st.session_state.show_transcript = False

    # SLA Special Handling
    # SLA Special Handling
    if st.session_state.show_procurements:
        st.info("📊 Attempting to fetch live procurements...")
        
        try:
            # 1. Try to fetch from Supabase
            res = supabase.table("procurements").select("*").order("created_at", desc=True).limit(5).execute()
            
            if res.data:
                df = pd.DataFrame(res.data)
                available_cols = [c for c in ['id', 'item_name', 'created_at', 'status'] if c in df.columns]
                st.table(df[available_cols])
                
                selected_id = st.selectbox("Select ID to Audit:", df['id'].tolist())
                if st.button("Start SLA Audit"):
                    st.session_state.query = f"Run SLA Procurement Audit for ID: {selected_id}"
                    st.session_state.show_procurements = False
                    st.rerun()
            else:
                st.warning("No procurement data found.")
                
        except Exception as e:
            # 2. FALLBACK: If DB fails, don't crash. Show this instead:
            st.error("⚠️ Database Connection Failed (Offline Mode)")
            st.warning("Could not reach Supabase. You can manually enter an ID or prompt below to proceed with a simulated audit.")
            
            # Offer a "Simulated" path
            if st.button("Proceed with Manual/Recent ID"):
                # You can hardcode a 'test' ID here for the demo
                st.session_state.query = "Run SLA Procurement Audit for ID: PROC-999-TEST"
                st.session_state.show_procurements = False
                st.rerun()
    # Other Scenario
    if st.session_state.show_other:
        st.info("Please enter your query in the  textbox below and click EXECUTE WORKFLOW.")
        st.session_state.query = ""
        st.session_state.show_other = False

    query = st.text_area("Textbox", value=st.session_state.query, height=100)
    run_btn = st.button("EXECUTE WORKFLOW", type="primary")

# --- COLUMN 2: REAL-TIME AGENT TRACE ---
with col2:
    st.subheader("⚙️ Agentic Execution Trace")
    status_container = st.container()
    
    if run_btn and query:
        # Clear previous run
        status_container.empty()
        storage_mode = "Supabase Cloud DB"
        inputs = {"messages": [HumanMessage(content=query)], "recovery_attempts": 0}
        step_number = 1
        try:
            # Stream the workflow steps
            for output in app.stream(inputs, config={"recursion_limit": 30}):
                for node_name, state_update in output.items():
                    with status_container:
                        # Display the node progress
                        st.markdown(f"""
                            <div class="node-box">
                                <b>📍 STEP {step_number}: {node_name.upper()} Agent working...</b>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        # Show specific agent details
                        if "risk_level" in state_update:
                            st.caption(f"🛡️ Risk Score: {state_update['risk_level']}/10")
                        
                        if "task_status" in state_update:
                            st.write(f"Current Status: `{state_update['task_status']}`")
                        
                        if "audit_trail" in state_update:
                            for log in state_update["audit_trail"]:
                                if "SENT_LOCAL" in str(log) or "status': 'SENT_LOCAL'" in str(log):
                                    storage_mode = "Local Filesystem (logs/)"
                            last_log = state_update["audit_trail"][-1]
                            
                            # Use .get() to avoid KeyErrors if a field is missing
                            timestamp = last_log.get("timestamp", "00:00:00")
                            agent = last_log.get("agent", "UNKNOWN")
                            action = last_log.get("action", "Processing")
                            # Some of your agents use 'reasoning' or 'details' instead of 'message'
                            message = last_log.get("reasoning") or last_log.get("details") or "No details"
                            status = state_update.get("task_status", "Active")

                            # Display as a clean, single line
                            st.write(f"🕒 **{timestamp}** | 🤖 **{agent}** | ⚡ **{action}**")
                            st.caption(f"💬 {message} | 📊 Status: {status}")
                        st.divider()
                        step_number += 1
                        time.sleep(1) # For demo visual effect
                        
            st.success(f"✅ Workflow Execution Finished. Repository: {storage_mode}")
            
        except Exception as e:
            st.error(f"Critical System Failure: {str(e)}")