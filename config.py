# config.py
import os
from dotenv import load_dotenv
import json
import time
import logging

load_dotenv() # Load environment variables from .env file

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Zoho CRM Configuration
ZOHO_CLIENT_ID = os.getenv("ZOHO_CLIENT_ID")
ZOHO_CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET")
ZOHO_REDIRECT_URI = os.getenv("ZOHO_REDIRECT_URI")
ZOHO_ACCOUNTS_URL = "https://accounts.zoho.in" # Ensure this matches your Zoho region (.com, .eu, .in, etc.)
ZOHO_CRM_API_URL = "https://www.zohoapis.in/crm/v6" # Ensure this matches your Zoho region
ZOHO_CRM_SCOPES = "ZohoCRM.modules.leads.CREATE,ZohoCRM.modules.leads.READ,ZohoCRM.modules.users.READ,aaaserver.profile.READ"

# Ollama Configuration (if you use Ollama)
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi3:mini")

# --- Persistent Token Storage for the entire application ---
TOKEN_FILE = "zoho_tokens.json"

# Initialize global token variables
ZOHO_ACCESS_TOKEN = None
ZOHO_REFRESH_TOKEN = None
ZOHO_TOKEN_EXPIRY = None # Timestamp

def load_zoho_tokens_for_app():
    """Loads Zoho tokens from file into global config variables if valid."""
    global ZOHO_ACCESS_TOKEN, ZOHO_REFRESH_TOKEN, ZOHO_TOKEN_EXPIRY
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r") as f:
                tokens = json.load(f)
            
            # Check if tokens are still valid before assigning
            if tokens and tokens.get("access_token") and tokens.get("expires_at", 0) > time.time():
                ZOHO_ACCESS_TOKEN = tokens["access_token"]
                ZOHO_REFRESH_TOKEN = tokens.get("refresh_token")
                ZOHO_TOKEN_EXPIRY = tokens["expires_at"]
                logging.info(f"Zoho tokens loaded from {TOKEN_FILE} into app config.")
                return True
            else:
                logging.warning(f"Tokens in {TOKEN_FILE} are expired or invalid. Will attempt refresh/new generation.")
                return False
        except (IOError, json.JSONDecodeError) as e:
            logging.error(f"Error loading tokens from {TOKEN_FILE}: {e}")
            return False
    return False

# Attempt to load tokens when config.py is imported
load_zoho_tokens_for_app()