import os
import time
import json
from datetime import datetime, timedelta
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# --- Supabase Setup ---
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(url, key)

def load_db(file_name):
    """Fallback for local logging if DB is unreachable"""
    path = os.path.join('logs', file_name)
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

# --- ENTERPRISE TOOLS ---

def update_inventory_ledger(item: str, action: str):
    """Step 5 (Onboarding): Checks stock and raises request if 0."""
    print(f"🔍 [Inventory] Checking stock for: {item}")
    try:
        res = supabase.table("inventory").select("*").eq("item_name", item).execute()
        if res.data and res.data[0]['stock'] > 0:
            # Reduce stock by 1
            new_stock = res.data[0]['stock'] - 1
            supabase.table("inventory").update({"stock": new_stock}).eq("item_name", item).execute()
            return {"status": "SUCCESS", "message": f"{item} provisioned. Remaining: {new_stock}"}
        else:
            return {"status": "ERROR", "message": f"OUT_OF_STOCK: {item}"}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

def create_workflow_task(summary: str, entity: str):
    """Step 3/4 (Onboarding/Meeting): Creates records in Employee/Task DB."""
    print(f"📝 [DB] Creating record for: {entity}")
    try:
        data = {
            "entity_name": entity,
            "description": summary,
            "created_at": datetime.now().isoformat(),
            "status": "pending"
        }
        res = supabase.table("employee_tasks").insert(data).execute()
        return {"status": "SUCCESS", "id": res.data[0]['id']}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

def create_system_ticket(reason: str, assigned_group: str):
    """General: Used for Escalations and ID Card requests."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    ticket_id = f"INC-{timestamp}-REQ"
    try:
        data = {"ticket_id": ticket_id, "reason": reason, "group": assigned_group, "status": "open"}
        supabase.table("tickets").insert(data).execute()
        return {"status": "SUCCESS", "ticket_id": ticket_id}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

def send_slack_alert(channel: str, message: str):
    """Step 6 (Onboarding/Meeting): Real-time notification simulation."""
    print(f"📡 [Communication] Sending to {channel}...")
    # In a real scenario, use slack_sdk here. For hackathon, we log to Supabase 'notifications'
    try:
        supabase.table("notifications").insert({
            "channel": channel, 
            "message": message, 
            "sent_at": datetime.now().isoformat()
        }).execute()
        return {"status": "SENT", "channel": channel}
    except:
        return {"status": "SENT_LOCAL", "message": message}

def check_sla_breach(procurement_id: str):
    """Step 3 (SLA): Checks if 48hr window is exceeded."""
    try:
        res = supabase.table("procurements").select("*").eq("id", procurement_id).execute()
        if not res.data: return {"status": "ERROR", "message": "Procurement not found"}
        
        created_at = datetime.fromisoformat(res.data[0]['created_at'])
        if datetime.now() > created_at + timedelta(hours=48):
            return {"status": "ERROR", "message": "SLA_BREACH_DETECTED"}
        return {"status": "SUCCESS", "message": "SLA Compliant"}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}