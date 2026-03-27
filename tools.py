import os
import time
import json
from datetime import datetime

import os

# Create the db folder if it doesn't exist just in case
if not os.path.exists('logs'):
    os.makedirs('logs')

def load_db(file_name):
    # This ensures it looks inside the db/ folder
    path = os.path.join('logs', file_name)
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        # Create the file with empty data if it's missing
        if "inventory" in file_name:
            return {"laptops": {"stock": 10}, "servers": {"stock": 2}}
        return []

def save_db(file_name, data):
    path = os.path.join('db', file_name)
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)

# --- THE TOOLS ---

def create_system_ticket(reason, assigned_group):
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    ticket_id = f"INC-{timestamp}-SEC"
    print(f"📡 Routing to Department: {assigned_group}...")
    time.sleep(1)
    print(f"✅ Ticket {ticket_id} created successfully.")
    return {"status": "SUCCESS", "ticket_id": ticket_id, "group": assigned_group}

def send_slack_alert(channel, message):
    print(f"💬 [SLACK] Connecting to {channel}...")
    time.sleep(1)
    print(f"📤 [SLACK] Message Sent: {message[:50]}...")
    return {"status": "SENT", "ts": datetime.now().isoformat()}

def provision_access_tool(user, service):
    print(f"🔑 [IAM] Provisioning {service} for {user}...")
    time.sleep(1.5)
    # Simulate a "Self-Healer" trigger (Random Failure 10% of time)
    import random
    if random.random() < 0.1:
        return {"status": "ERROR", "message": "API Timeout"}
    return {"status": "SUCCESS", "account_id": f"{user[:3].upper()}-{random.randint(100,999)}"}

def update_inventory_ledger(item, action):
    print(f"📦 [ERP] Updating Ledger for: {item}...")
    time.sleep(1)
    return {"status": "UPDATED", "transaction_id": f"TXN-{datetime.now().microsecond}"}

def create_workflow_task(summary, entity):
    print(f"📋 [JIRA] Creating Task: {summary[:30]}... for {entity}")
    time.sleep(1)
    return {"status": "SUCCESS", "task_key": f"TASK-{datetime.now().microsecond // 1000}"}