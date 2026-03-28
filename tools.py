import os
import io
import json
import uuid
#import PyPDF2
from datetime import datetime, timedelta
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
# --- Supabase Setup ---
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(url, key)

# --- 1. UNIVERSAL AUDIT LOGGING ---
def log_scenario_activity(scenario: str, action: str, details: str, status: str = "INFO"):
    """
    Unified logger for all scenarios: employee, transcript, procurement, ticket, other.
    Logs directly to the 'audit_logs' table in Supabase.
    """
    try:
        log_entry = {
            "scenario": scenario,      # e.g., 'onboarding', 'transcript', 'procurement'
            "action": action,          # e.g., 'PDF_UPLOAD', 'DB_INSERT'
            "details": details,        # e.g., 'Extracted text for Sarah'
            "status": status,          # e.g., 'SUCCESS', 'ERROR', 'FLAGGED'
            "timestamp": datetime.now().isoformat()
        }
        supabase.table("audit_logs").insert(log_entry).execute()
        return True
    except Exception as e:
        print(f"Logging Failed: {e}")
        return False


# --- 2. PDF EXTRACTION (Streamlined) ---
def extract_text_from_pdf(file_bytes):
    """Returns only the core text content and a status message."""
    try:
        pdf_file = io.BytesIO(file_bytes)
        reader = PyPDF2.PdfReader(pdf_file)
        text = " ".join([page.extract_text() for page in reader.pages]).replace('\n', ' ')
        
        content = text[:1500] # Cleaned and capped for LLM
        log_scenario_activity("transcript", "PDF_EXTRACTION", "Successfully parsed PDF", "SUCCESS")
        return {"message": "✅ PDF Parsed Successfully", "content": content}
    except Exception as e:
        log_scenario_activity("transcript", "PDF_EXTRACTION", str(e), "ERROR")
        return {"message": "❌ PDF Extraction Failed", "content": ""}

# --- 2. DATABASE OPERATIONS ---
def check_employee_exists(name: str):
    """Checks if an employee exists and returns the current total workforce count."""
    try:
        # 1. Get total count of all employees
        count_res = supabase.table("employees").select("*", count="exact").execute()
        total_count = count_res.count if count_res.count is not None else 0
        
        # 2. Check if specific name exists
        name_res = supabase.table("employees").select("id").ilike("full_name", f"%{name}%").execute()
        exists = len(name_res.data) > 0
        
        return {
            "status": "SUCCESS",
            "exists": exists,
            "total_workforce": total_count,
            "suggested_new_id": f"EMP-{total_count + 101}" # Helper for the agent
        }
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

def insert_employee_record(data: dict):
    """
    Step 4: Inserts a new employee into the 'employees' table.
    Expects: {'full_name', 'email', 'role', 'department', 'employee_code'}
    """
    try:
        # We don't provide 'id' or 'created_at' as Supabase handles the defaults
        payload = {
            "full_name": data.get("full_name"),
            "email": data.get("email"),
            "role": data.get("role", "Associate"),
            "department": data.get("department", "General"),
            "employee_code": data.get("employee_code"),
            "status": "active"
        }
        
        res = supabase.table("employees").insert(payload).execute()
        
        if res.data:
            return {
                "status": "SUCCESS", 
                "message": f"Created {data.get('full_name')} with Code: {data.get('employee_code')}",
                "db_id": res.data[0]['id']
            }
        return {"status": "ERROR", "message": "Insert failed - no data returned"}
        
    except Exception as e:
        # Catch unique constraint violations (e.g., duplicate email/code)
        error_msg = str(e)
        if "unique_email" in error_msg.lower():
            return {"status": "ERROR", "message": "Email already exists in system."}
        return {"status": "ERROR", "message": error_msg}



def check_inventory_stock(item_name: str):
    """Checks if a hardware/software item is in stock."""
    try:
        res = supabase.table("inventory").select("*").ilike("item_name", f"%{item_name}%").execute()
        if res.data:
            item = res.data[0]
            if item['stock_count'] > 0:
                return {"status": "AVAILABLE", "count": item['stock_count'], "id": item['id']}
            return {"status": "OUT_OF_STOCK", "message": f"Zero units of {item_name} remaining"}
        return {"status": "ERROR", "message": "Item not found in inventory catalog"}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

# --- INVENTORY TOOLS ---

def check_inventory_stock(item_name: str):
    """Checks if an item exists in inventory and returns current stock levels."""
    try:
        res = supabase.table("inventory").select("*").ilike("item_name", f"%{item_name}%").execute()
        if res.data:
            item = res.data[0]
            return {
                "status": "SUCCESS",
                "exists": True,
                "stock": item.get("stock", 0),
                "item_id": item.get("id"),
                "message": f"Found {item_name}: {item.get('stock')} in stock."
            }
        return {"status": "SUCCESS", "exists": False, "stock": 0, "message": "Item not found in inventory."}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

# --- PROCUREMENT TOOLS ---

def get_procurement_status(procurement_id: str):
    """Fetches details and status of a specific procurement request."""
    try:
        res = supabase.table("procurements").select("*").eq("id", procurement_id).execute()
        if res.data:
            return {"status": "SUCCESS", "data": res.data[0]}
        return {"status": "ERROR", "message": "Procurement ID not found."}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

def insert_procurement_request(data: dict):
    """
    Creates a new procurement record. 
    Expects: {'item_name', 'requested_by', 'quantity', 'priority'}
    """
    try:
        payload = {
            "item_name": data.get("item_name"),
            "requested_by": data.get("requested_by"),
            "quantity": data.get("quantity", 1),
            "priority": data.get("priority", "medium"),
            "status": "pending",
            "created_at": datetime.now().isoformat()
        }
        res = supabase.table("procurements").insert(payload).execute()
        if res.data:
            return {
                "status": "SUCCESS", 
                "message": f"Procurement raised for {data.get('item_name')}",
                "procurement_id": res.data[0]['id']
            }
        return {"status": "ERROR", "message": "Failed to create procurement."}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

def update_procurement_status(procurement_id: str, new_status: str, notes: str = None):
    """Updates the status of an existing procurement (e.g., to 'approved' or 'completed')."""
    try:
        update_data = {"status": new_status}
        if notes:
            update_data["notes"] = notes
            
        res = supabase.table("procurements").update(update_data).eq("id", procurement_id).execute()
        if res.data:
            return {"status": "SUCCESS", "message": f"Procurement {procurement_id} marked as {new_status}."}
        return {"status": "ERROR", "message": "Update failed - ID not found."}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}


def create_system_ticket(reason: str, assigned_group: str = "IT-Support"):
    """
    Creates a support or security ticket in the 'tickets' table.
    Expects: 'reason' (string) and 'assigned_group' (string)
    """
    try:
        ticket_id = f"TIX-{str(uuid.uuid4())[:8].upper()}"
        payload = {
            "ticket_id": ticket_id,
            "reason": reason,
            "assigned_group": assigned_group,
            "status": "open",
            "created_at": datetime.now().isoformat()
        }
        
        res = supabase.table("tickets").insert(payload).execute()
        
        if res.data:
            return {
                "status": "SUCCESS", 
                "message": f"Ticket {ticket_id} raised for {assigned_group}",
                "ticket_id": ticket_id
            }
        return {"status": "ERROR", "message": "Failed to create ticket record"}
        
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

















# --- 4. COMMUNICATION ---
def send_enterprise_alert(recipient_email: str, message: str, platform="email"):
    """Mega-Tool: Sends alerts across different channels."""
    print(f"📡 [Communication] Sending {platform} to {recipient_email}...")
    try:
        log_data = {
            "recipient": recipient_email,
            "message": message,
            "channel": platform,
            "sent_at": datetime.now().isoformat()
        }
        supabase.table("notifications").insert(log_data).execute()
        return {"status": "SUCCESS", "message": f"Alert sent via {platform}"}
    except:
        # Fallback if notification table fails
        return {"status": "SENT_LOCAL", "message": "Logged to local buffer"}

# --- 5. FAULT-INJECTION TOOLS (For Healer Agent Demo) ---
def sync_slack_account(user_id: str):
    """FORCED FAILURE: Demonstrates the Healer agent's recovery logic."""
    time_stamp = datetime.now().strftime("%H:%M:%S")
    return {
        "status": "ERROR", 
        "message": f"[{time_stamp}] Connection Timeout: Slack API unreachable for user {user_id}"
    }

def create_jira_ticket(issue_data: dict):
    """FORCED FAILURE: Demonstrates authentication error handling."""
    return {
        "status": "ERROR", 
        "message": "Authentication Failure: Invalid Jira Token (Token Expired)"
    }