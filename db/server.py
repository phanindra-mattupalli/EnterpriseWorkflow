# EnterpriseWorkflow/db/app.py

import os
import streamlit as st
import json
import random
import string
from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client, Client
import uuid

load_dotenv()
st.set_page_config(page_title="Enterprise DB Console", layout="wide")

# ---- Connection controls (top section) ----
st.header("🛠️ Enterprise DB Console")
default_url = os.environ.get("SUPABASE_URL", "")
default_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

@st.cache_resource
def get_client():
    return create_client(default_url, default_key)

supabase = get_client()

if not supabase:
    st.error("❌ Supabase .env vars missing")
    st.stop()

# ---- Helper functions ----
def fetch_table(name: str):
    try:
        res = supabase.table(name).select("*").execute()
        return res.data or []
    except Exception as e:
        st.error(f"Error fetching {name}: {e}")
        return []

def insert_row(table: str, row: dict):
    try:
        res = supabase.table(table).insert(row).execute()
        st.success("✅ Inserted")
        return res
    except Exception as e:
        st.error(f"❌ Insert failed: {e}")

def update_row(table: str, row_id: str, row: dict, id_col: str = "id"):
    try:
        res = supabase.table(table).update(row).eq(id_col, row_id).execute()
        st.success("✅ Updated")
        return res
    except Exception as e:
        st.error(f"❌ Update failed: {e}")

# ---- Random data generators ----
def random_data_generators():
    return {
        "employees": lambda: {
            "id": str(uuid.uuid4()),
            "full_name": f"Employee {random.randint(1, 999)}",
            "email": f"emp{random.randint(1000,9999)}@company.com",
            "role": random.choice(["Engineer", "Manager", "Analyst"]),
            "department": random.choice(["Engineering", "Sales", "HR"]),
            "status": "active"
        },
        "inventory": lambda: {
            "id": str(uuid.uuid4()),
            "device_type": random.choice(["laptop", "monitor"]),
            "model": f"Model-{random.randint(100,999)}",
            "location": random.choice(["HQ", "Branch"]),
            "status": random.choice(["available", "allocated"])
        },
        "notifications": lambda: {
            "id": str(uuid.uuid4()),
            "employee_id": None,
            "start_date": (datetime.now() + timedelta(days=random.randint(1,30))).strftime("%Y-%m-%d"),
            "status": "pending"
        },
        "procurements": lambda: {
            "id": str(uuid.uuid4()),
            "description": f"Procurement {random.randint(1,99)}",
            "amount": round(random.uniform(1000, 50000), 2),
            "vendor": f"Vendor{random.randint(1,10)}",
            "status": "pending"
        },
        "tickets": lambda: {
            "id": str(uuid.uuid4()),
            "source": random.choice(["onboarding", "meeting", "procurement"]),
            "title": f"Ticket {random.randint(1,999)}",
            "priority": random.choice(["low", "medium", "high"]),
            "status": "open"
        },
    }

TABLES = [
    ("employees", "Employees"),
    ("inventory", "Inventory"),
    ("notifications", "Notifications"),
    ("procurements", "Procurements"),
    ("tickets", "Tickets"),
    ("audit_logs", "Audit Logs"),
]

# ---- Tabbed interface (100% width) ----
tabs = st.tabs([label for _, label in TABLES])

for (table_name, label), tab in zip(TABLES, tabs):
    with tab:
        st.markdown(f"### {label}")
        
        # Fetch and show table
        data = fetch_table(table_name)
        
        if data:
            # Editable dataframe
            edited_df = st.data_editor(
                data,
                num_rows="dynamic",
                column_config={"id": st.column_config.TextColumn("ID", disabled=True)},
                width="stretch",
                hide_index=False,
            )
            
            # Random insert button
            if st.button(f"🎲 Random Insert", key=f"rand_{table_name}"):
                gen = random_data_generators()
                row = gen[table_name]()
                insert_row(table_name, row)
                st.rerun()
            
            # Per-row update buttons
            st.markdown("**Update specific rows:**")
            for idx, row in enumerate(data):
                with st.expander(f"Row {row.get('id', idx)} - Edit", expanded=False):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        row_json = st.text_area(
                            "Edit row JSON",
                            value=json.dumps(row, indent=2),
                            height=150,
                            key=f"edit_row_{table_name}_{row.get('id', idx)}"
                        )
                    with col2:
                        if st.button("💾 Update", key=f"upd_row_{table_name}_{row.get('id', idx)}"):
                            try:
                                new_row = json.loads(row_json)
                                update_row(table_name, row["id"], new_row)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Invalid JSON: {e}")
        else:
            st.info(f"No data in {table_name} yet. Use Random Insert to add sample data.")

st.markdown("---")
st.caption("Enterprise Workflow DB Console | Insert/Update only | No Delete")