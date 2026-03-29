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

def render_summary_card(result_state):
    final_outcome = result_state.get("final_outcome", {}) or {}
    scenario = result_state.get("scenario", "unknown")
    retries = result_state.get("recovery_attempts", 0)
    tool_results = result_state.get("tool_results", []) or []
    storage_mode = "unknown"

    for item in tool_results:
        if isinstance(item, dict) and item.get("storage_source"):
            storage_mode = item.get("storage_source")
            break

    st.subheader("Execution Summary")
    st.markdown(f"**Scenario:** {scenario}")
    st.markdown(f"**Final Status:** {final_outcome.get('status', 'unknown')}")
    st.markdown(f"**Retries Used:** {retries}")
    st.markdown(f"**Main Action:** {final_outcome.get('main_action', 'No action recorded')}")
    st.markdown(f"**Storage Mode:** {storage_mode}")
    st.markdown(f"**Impact:** {final_outcome.get('business_impact', 'No impact recorded')}")
    st.caption(final_outcome.get("summary", "No summary available"))

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

col1, col2, col3 = st.columns([1, 1, 1], gap="small")

# --- COLUMN 1: INTERACTION & CONTROLS ---
with col1:
    st.subheader("📥 Process Selection")
    
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🚀 Onboarding"):
            st.session_state.show_onboard = True
    with c2:
        if st.button("👥 Analyze Transcript"):
            st.session_state.show_transcript = True
    c3, c4 = st.columns(2)
    with c3:
        if st.button("📄 Audit SLA"):
            st.session_state.show_procurements = True
    with c4:
        if st.button("❓ Other Scenario"):
            st.session_state.show_other = True

    # Onboarding Special Handling
    if st.session_state.show_onboard:
        st.info("Onboard [ex: Alex Rivera] to the [ex: Engineering] team as a [ex: Senior Frontend Developer].")
        st.session_state.query = "Onboard [ex: Alex Rivera] to the [ex: Engineering] team as a [ex: Senior Frontend Developer]."
        st.session_state.show_onboard = False

    # Transcript Special Handling
    if st.session_state.show_transcript:
        st.info("In the sync yesterday, [ex:Sara Ali Khan] mentioned we need to update the project documentation by Friday.")
        st.session_state.query = "In the sync yesterday, [ex:Sara Ali Khan] mentioned we need to update the project documentation by Friday."
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
            st.warning("Could not reach Supabase. You can manually enter SLA audit details below to proceed with a simulated audit.")
            
            
            # Offer a "Simulated" path
            if st.button("Proceed with Manual/Recent ID"):
                # You can hardcode a 'test' ID here for the demo
                st.info("URGENT: 48hr SLA breach on '[ex: MacBook Pro M3 Batch]'. Notify procurement at [ex: supply@enterprise.com] and raise an [ex: IT ticket].")
                st.session_state.query = "URGENT: 48hr SLA breach on '[ex: MacBook Pro M3 Batch]'. Notify procurement at [ex: supply@enterprise.com] and raise an [ex: IT ticket]."
                st.session_state.show_procurements = False
                st.rerun()
    # Other Scenario
    if st.session_state.show_other:
        st.session_state.query = ""
        st.session_state.show_other = False
    uploaded_file = st.file_uploader(
        "upload a file (.txt)",
        type=["txt"]
    )
    if uploaded_file is not None:
        uploaded_text = uploaded_file.read().decode("utf-8")
        st.session_state["uploaded_transcript"] = uploaded_text
        st.success("Transcript uploaded successfully.")
        st.session_state.query = "Can we proceed with this document?"

    uploaded_text = st.session_state.get("uploaded_transcript", "")
    query = st.text_area("Textbox", value=st.session_state.query, height=100)

    final_query = query
    if uploaded_text:
        final_query = f"{query}\n\nContent:\n{uploaded_text}"

    run_btn = st.button("EXECUTE WORKFLOW", type="primary")

# --- COLUMN 2: REAL-TIME AGENT TRACE ---
with col2:
    st.subheader("⚙️ Agentic Execution Trace")
    # with st.container(height=600, border=True):
    #     status_container = st.container()
    status_container = st.container()
    if run_btn and query:
        # Clear previous run
        status_container.empty()
        storage_mode = "Supabase Cloud DB"
        inputs = {"messages": [HumanMessage(content=query)], "recovery_attempts": 0}
        
        global_step = 1
        final_state = None

        try:
            # Stream the workflow steps
            for output in app.stream(inputs, config={"recursion_limit": 30}):
                for node_name, state_update in output.items():
                    final_state = state_update
                    with status_container:
                        # Display the node progress
                        st.markdown(f"""
                            <div class="node-box">
                                <b>Node {global_step}: {node_name.upper()} Agent working...</b>
                            </div>
                        """, unsafe_allow_html=True)

                        global_step += 1
                        
                        # Show specific agent details
                        if "risk_level" in state_update:
                            st.caption(f"🛡️ Risk Score: {state_update['risk_level']}/10")
                        
                        if "task_status" in state_update:
                            st.write(f"Current Status: `{state_update['task_status']}`")
                        
                        timestamp = time.strftime("%H:%M:%S")
                        
                        action_map = {
                            "classifier": "Classifying Intent",
                            "validator": "Validating Environment",
                            "reasoner": "Determining Next Steps",
                            "tools": "Executing Tool Operations",
                            "healer": "Applying Recovery Measures",
                            "escalator": "Escalating Security Issue"
                        }
                        action = action_map.get(node_name, "Processing")
                        
                        st.write(f"🕒 **{timestamp}** | 🤖 **{node_name.upper()}** | ⚡ **{action}**")
                        
                        # Display internal steps/plan details
                        plan_from_log = state_update.get("plan_details", [])
                        if plan_from_log:
                            with st.expander(f"📋 Details & Status", expanded=True):
                            # Show which sub-step is running
                                for i, step in enumerate(plan_from_log, 1):
                                    st.caption(f" Step {global_step-1}.{i}: {step}")
                        time.sleep(0.5)

                        # 2. Plan Display
                        # plan_from_log = state_update.get("plan_details", [])
                        # if plan_from_log:
                        #     with st.expander(f"📋 Details & Status", expanded=True):
                        #         for step in plan_from_log:
                        #             st.write(f"✅ {step}")

                        # # 3. Execution Display (for tools)
                        # if node_name == "tools" and "messages" in state_update:
                        #     last_msg = state_update["messages"][-1]
                        #     with st.expander(f"🚀 Execution Result", expanded=True):
                        #         if "ERROR" in last_msg.content or "Conflict" in last_msg.content or "Breach" in last_msg.content:
                        #             st.error(last_msg.content)
                        #         else:
                        #             st.success(last_msg.content)
                        st.session_state["result_state"] = final_state
                        time.sleep(0.5) # For demo visual effect
    
    

            st.success(f"✅ Workflow Execution Finished. Repository: {storage_mode}")
                
        except Exception as e:
            st.error(f"Critical System Failure: {str(e)}")
with col3:
    if "result_state" in st.session_state:
       render_summary_card(st.session_state["result_state"])