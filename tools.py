import os
import io
import json
import uuid
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(url, key)

AUDIT_LOG_FILE = "logs/audit_log.json"


# --- Unified audit helpers ---

def make_audit_log(
    scenario: str = "",
    agent: str = "",
    action: str = "",
    status: str = "",
    details: str = "",
    target_id: str = "",
    storage_source: str = ""
):
    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "scenario": scenario,
        "agent": agent,
        "action": action,
        "status": status,
        "details": details,
        "target_id": str(target_id) if target_id else "",
        "storage_source": storage_source,
    }


def write_audit_log(
    scenario: str = "",
    agent: str = "",
    action: str = "",
    status: str = "",
    details: str = "",
    target_id: str = "",
    supabase_client: Client | None = None,
    table_name: str = "audit_logs"
):
    """
    Preferred logging helper: writes to Supabase if available,
    otherwise falls back to local file, always returning the same shape.
    """
    # initial assumption about storage
    storage_source = "supabase" if supabase_client else "local"

    log_entry = make_audit_log(
        scenario=scenario,
        agent=agent,
        action=action,
        status=status,
        details=details,
        target_id=target_id,
        storage_source=storage_source,
    )

    # Try Supabase if provided
    if supabase_client is not None:
        try:
            supabase_client.table(table_name).insert(log_entry).execute()
            return log_entry
        except Exception as e:
            # downgrade to local fallback
            log_entry["status"] = "fallback_local"
            log_entry["details"] = f"{details} | Supabase failed: {str(e)}"
            log_entry["storage_source"] = "local"

    # Local file fallback
    os.makedirs(os.path.dirname(AUDIT_LOG_FILE), exist_ok=True)
    with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")

    return log_entry


# --- Legacy-style universal_log, now using unified format ---

def universal_log(scenario, action, details, status="INFO"):
    """
    Backwards-compatible logger used in existing tools.
    Now implemented using write_audit_log so format is unified.
    """
    try:
        # prefer supabase, with fallback handled inside helper
        entry = write_audit_log(
            scenario=scenario,
            agent="system",
            action=action,
            status=status,
            details=details,
            target_id="",
            supabase_client=supabase
        )
        return {
            "status": entry.get("status", "SUCCESS"),
            "source": entry.get("storage_source", "supabase")
        }
    except Exception as e:
        # extreme fallback: local file write without supabase
        try:
            entry = write_audit_log(
                scenario=scenario,
                agent="system",
                action=action,
                status="fallback_local",
                details=f"{details} | universal_log failure: {str(e)}",
                target_id="",
                supabase_client=None
            )
            return {
                "status": entry.get("status", "fallback_local"),
                "source": entry.get("storage_source", "local"),
                "error": str(e)
            }
        except Exception as file_err:
            return {
                "status": "CRITICAL_FAILURE",
                "error": str(file_err)
            }


# --- 2. DATABASE OPERATIONS ---

def check_employee_exists(name: str):
    try:
        count_res = supabase.table("employees").select("*", count="exact").execute()
        total_count = count_res.count if count_res.count is not None else 0

        name_res = (
            supabase.table("employees")
            .select("id")
            .ilike("full_name", f"%{name}%")
            .execute()
        )
        exists = len(name_res.data) > 0

        return {
            "status": "SUCCESS",
            "exists": exists,
            "total_workforce": total_count,
            "suggested_new_id": f"EMP-{total_count + 101}",
        }
    except Exception as e:
        universal_log("onboarding", "CHECK_DB_FAIL", str(e), "ERROR")
        return {"status": "ERROR", "message": str(e)}


def insert_employee_record(data: dict):
    try:
        payload = {
            "full_name": data.get("full_name"),
            "email": data.get("email")
            or f"{data.get('full_name').replace(' ', '.').lower()}@company.com",
            "role": data.get("role") or "New Joiner",
            "department": data.get("department"),
            "employee_code": data.get("employee_code")
            or f"EMP-{uuid.uuid4().hex[:5].upper()}",
        }
        res = supabase.table("employees").insert(payload).execute()

        # audit
        write_audit_log(
            scenario="onboarding",
            agent="onboarding_agent",
            action="insert_employee_record",
            status="success",
            details=f"Employee created: {payload.get('full_name')}",
            target_id=payload.get("employee_code"),
            supabase_client=supabase,
        )

        return {"status": "SUCCESS", "message": "Onboarding complete."}
    except Exception as e:
        universal_log("onboarding", "INSERT_EMP_FAIL", str(e), "ERROR")
        return {"status": "ERROR", "message": str(e)}


def insert_procurement_request(data: dict):
    try:
        payload = {
            "item_name": data.get("item_name"),
            "requested_by": data.get("requested_by"),
            "quantity": data.get("quantity", 1),
            "priority": data.get("priority", "medium"),
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        }
        res = supabase.table("procurements").insert(payload).execute()

        # audit
        write_audit_log(
            scenario="procurement",
            agent="procurement_agent",
            action="insert_procurement_request",
            status="success",
            details=f"Item: {data.get('item_name')}",
            target_id=res.data[0]["id"] if res.data else "",
            supabase_client=supabase,
        )

        return {"status": "SUCCESS", "procurement_id": res.data[0]["id"]}
    except Exception as e:
        universal_log("procurement", "RAISE_FAIL", str(e), "ERROR")
        return {"status": "ERROR", "message": "Procurement cached locally."}


def get_procurement_status(request_id: str):
    """
    Fetches the current status and basic metadata for a procurement request.
    Used by agents to reason about SLA risk, escalation, etc.
    """
    try:
        res = (
            supabase.table("procurements")
            .select("id, item_name, requested_by, quantity, priority, status, created_at, updated_at")
            .eq("id", request_id)
            .single()
            .execute()
        )

        if not res.data:
            write_audit_log(
                scenario="procurement",
                agent="procurement_agent",
                action="get_procurement_status",
                status="not_found",
                details=f"Procurement not found: {request_id}",
                target_id=request_id,
                supabase_client=supabase,
            )
            return {
                "status": "NOT_FOUND",
                "message": f"No procurement found for id {request_id}",
            }

        record = res.data

        write_audit_log(
            scenario="procurement",
            agent="procurement_agent",
            action="get_procurement_status",
            status="success",
            details=f"Fetched procurement {request_id} with status={record.get('status')}",
            target_id=request_id,
            supabase_client=supabase,
        )

        return {
            "status": "SUCCESS",
            "procurement": record,
        }

    except Exception as e:
        universal_log("procurement", "STATUS_FAIL", str(e), "ERROR")
        return {
            "status": "ERROR",
            "message": f"Failed to fetch procurement status: {str(e)}",
        }

def create_system_ticket(reason: str, assigned_group: str = "IT-Support"):
    try:
        ticket_id = f"TIX-{str(uuid.uuid4())[:8].upper()}"
        payload = {
            "ticket_id": ticket_id,
            "reason": reason,
            "assigned_group": assigned_group,
            "status": "open",
            "created_at": datetime.now().isoformat(),
        }
        supabase.table("tickets").insert(payload).execute()

        # audit
        write_audit_log(
            scenario="security",
            agent="ticketing_agent",
            action="create_system_ticket",
            status="success",
            details=reason[:80],
            target_id=ticket_id,
            supabase_client=supabase,
        )

        return {"status": "SUCCESS", "ticket_id": ticket_id}
    except Exception as e:
        universal_log("security", "TICKET_FAIL", str(e), "ERROR")
        return {"status": "ERROR", "message": "Ticket saved to offline logs."}


# --- 3. COMMUNICATION ---

def send_enterprise_alert(recipient_email: str, message: str, platform="email"):
    print(f"[Communication] Sending {platform} to {recipient_email}...")
    try:
        log_data = {
            "recipient": recipient_email,
            "message": message,
            "channel": platform,
            "sent_at": datetime.now().isoformat(),
        }
        supabase.table("notifications").insert(log_data).execute()

        # audit
        write_audit_log(
            scenario="notifications",
            agent="notification_agent",
            action="send_enterprise_alert",
            status="success",
            details=f"Channel={platform}, Recipient={recipient_email}",
            target_id=recipient_email,
            supabase_client=supabase,
        )

        return {"status": "SUCCESS", "message": f"Alert sent via {platform}"}
    except Exception as e:
        universal_log("notifications", "NOTIFY_FAIL", str(e), "ERROR")
        # Dead-end message for LLM safety
        return {
            "status": "FATAL_ERROR",
            "message": "Notification system is down. Do not retry alerts.",
        }


# --- 4. INVENTORY ---

def check_inventory_stock(item_name: str):
    try:
        res = (
            supabase.table("inventory")
            .select("*")
            .ilike("item_name", f"%{item_name}%")
            .execute()
        )
        if res.data:
            stock = res.data[0].get("stock", 0)

            write_audit_log(
                scenario="inventory",
                agent="inventory_agent",
                action="check_inventory_stock",
                status="success",
                details=f"Item found: {item_name}, stock={stock}",
                target_id=res.data[0].get("id", ""),
                supabase_client=supabase,
            )

            return {"status": "SUCCESS", "exists": True, "stock": stock}

        write_audit_log(
            scenario="inventory",
            agent="inventory_agent",
            action="check_inventory_stock",
            status="success",
            details=f"Item not found: {item_name}",
            target_id="",
            supabase_client=supabase,
        )

        return {"status": "SUCCESS", "exists": False, "stock": 0}
    except Exception as e:
        universal_log("inventory", "CHECK_FAIL", str(e), "ERROR")
        return {"status": "ERROR", "message": str(e)}