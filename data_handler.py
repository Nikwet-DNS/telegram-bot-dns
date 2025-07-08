
import json
import os

DATA_FILE = "data.json"
CHAT_IDS_FILE = "chat_ids.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_chat_ids():
    if os.path.exists(CHAT_IDS_FILE):
        with open(CHAT_IDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_chat_ids(chat_ids):
    with open(CHAT_IDS_FILE, "w", encoding="utf-8") as f:
        json.dump(chat_ids, f, indent=2, ensure_ascii=False)
