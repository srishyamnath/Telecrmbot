# zoho_auth.py
import requests
import json
import time
import os
import logging
from config import (
    ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, ZOHO_REDIRECT_URI,
    ZOHO_ACCOUNTS_URL, ZOHO_CRM_SCOPES
)

# Set up logging for better visibility
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Token Persistence Functions ---
TOKEN_FILE = "zoho_tokens.json"

def save_tokens_to_file(access_token, refresh_token, expires_in_seconds):
    """Saves Zoho tokens to a JSON file."""
    tokens = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": time.time() + expires_in_seconds - 300 # refresh 5 mins before expiry
    }
    try:
        with open(TOKEN_FILE, "w") as f:
            json.dump(tokens, f)
        logger.info(f"Zoho tokens saved to {TOKEN_FILE}")
    except IOError as e:
        logger.error(f"Error saving tokens to file: {e}")

def load_tokens_from_file():
    """Loads Zoho tokens from a JSON file."""
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r") as f:
                tokens = json.load(f)
            logger.info(f"Zoho tokens loaded from {TOKEN_FILE}")
            return tokens
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Error loading tokens from file: {e}")
            return None
    return None

# --- Zoho Authentication Functions ---

# We will now manage tokens via the file, so these globals are for internal use during a run
_ZOHO_ACCESS_TOKEN = None
_ZOHO_REFRESH_TOKEN = None
_ZOHO_TOKEN_EXPIRY = None # Timestamp

def update_tokens_in_memory(access_token, refresh_token, expires_in_seconds):
    """Updates in-memory global variables and saves to file."""
    global _ZOHO_ACCESS_TOKEN, _ZOHO_REFRESH_TOKEN, _ZOHO_TOKEN_EXPIRY
    _ZOHO_ACCESS_TOKEN = access_token
    _ZOHO_REFRESH_TOKEN = refresh_token
    _ZOHO_TOKEN_EXPIRY = time.time() + expires_in_seconds - 300 # refresh 5 mins before expiry
    save_tokens_to_file(access_token, refresh_token, expires_in_seconds) # Save to file here
    logger.info("Zoho tokens updated in memory and saved to file.")

def get_access_token():
    """
    Returns the current access token if valid, refreshes it if expired, or None.
    If tokens are not in memory, tries to load from file.
    """
    global _ZOHO_ACCESS_TOKEN, _ZOHO_REFRESH_TOKEN, _ZOHO_TOKEN_EXPIRY

    # Try to load from file if not in memory
    if not _ZOHO_ACCESS_TOKEN or not _ZOHO_REFRESH_TOKEN:
        loaded_tokens = load_tokens_from_file()
        if loaded_tokens:
            _ZOHO_ACCESS_TOKEN = loaded_tokens.get("access_token")
            _ZOHO_REFRESH_TOKEN = loaded_tokens.get("refresh_token")
            _ZOHO_TOKEN_EXPIRY = loaded_tokens.get("expires_at")
            logger.info("Tokens loaded from file into memory.")
        else:
            logger.warning("No tokens found in file. Initial generation may be needed.")
            return None

    # Check if current access token is valid
    if _ZOHO_ACCESS_TOKEN and _ZOHO_TOKEN_EXPIRY and time.time() < _ZOHO_TOKEN_EXPIRY:
        return _ZOHO_ACCESS_TOKEN
    # If access token is expired but we have a refresh token, try to refresh
    elif _ZOHO_REFRESH_TOKEN:
        logger.info("Access token expired or not available, attempting to refresh...")
        return refresh_access_token()
    
    logger.warning("No valid access token or refresh token available.")
    return None

def generate_initial_tokens(grant_token):
    """
    Exchanges the authorization code (grant_token) for an access token and refresh token.
    """
    logger.info("Attempting to generate initial Zoho tokens...")
    
    token_url = f"{ZOHO_ACCOUNTS_URL}/oauth/v2/token"
    params = {
        "grant_type": "authorization_code",
        "client_id": ZOHO_CLIENT_ID,
        "client_secret": ZOHO_CLIENT_SECRET,
        "redirect_uri": ZOHO_REDIRECT_URI,
        "code": grant_token,
    }
    
    try:
        response = requests.post(token_url, data=params)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)

        data = response.json()
        
        if "access_token" in data:
            update_tokens_in_memory( # Use the new update function
                data["access_token"],
                data.get("refresh_token"),
                data["expires_in"] # Corrected key
            )
            logger.info("Successfully generated initial Zoho tokens.")
            return True
        else:
            logger.error(f"Error generating initial Zoho tokens (no access_token in response): {data.get('error', data)}")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Network or request error during initial token generation: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Zoho Error Response (if available): {e.response.text}")
        return False

def refresh_access_token():
    """
    Refreshes the access token using the stored refresh token.
    """
    global _ZOHO_REFRESH_TOKEN
    if not _ZOHO_REFRESH_TOKEN:
        logger.warning("No refresh token available to refresh access token.")
        return None

    token_url = f"{ZOHO_ACCOUNTS_URL}/oauth/v2/token"
    params = {
        "grant_type": "refresh_token",
        "client_id": ZOHO_CLIENT_ID,
        "client_secret": ZOHO_CLIENT_SECRET,
        "refresh_token": _ZOHO_REFRESH_TOKEN,
    }
    try:
        response = requests.post(token_url, data=params)
        response.raise_for_status()
        data = response.json()

        if "access_token" in data:
            update_tokens_in_memory( # Use the new update function
                data["access_token"],
                _ZOHO_REFRESH_TOKEN, # Refresh token usually remains the same when refreshing
                data["expires_in"] # Corrected key
            )
            logger.info("Successfully refreshed Zoho access token.")
            return _ZOHO_ACCESS_TOKEN
        else:
            logger.error(f"Error refreshing Zoho access token: {data.get('error', data)}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Network or request error during token refresh: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Zoho Error Response (if available): {e.response.text}")
        return None

# --- Main execution block for zoho_auth.py ---
if __name__ == "__main__":
    # >>> REPLACE THIS WITH THE GRANT TOKEN YOU COPIED FROM YOUR BROWSER'S URL <<<
    # You MUST generate a NEW grant token from the Zoho API Console EACH TIME you run this script for the first time
    # This token expires quickly and is single-use.
    your_manual_grant_token ="1000.cf9d69a2e03ea6e0ad6e148613866a06.a84dd0b21f09cb727f2230bd26bd9057" # <<<<<<<<<<<<<<<

    # Attempt to load tokens from file first
    loaded_tokens = load_tokens_from_file()
    if loaded_tokens and loaded_tokens.get("access_token") and time.time() < loaded_tokens.get("expires_at", 0):
        print("\nZoho tokens already exist and are valid in zoho_tokens.json.")
        print("You can proceed to run your main Telegram bot (python telegram_bot.py).")
        # Update in-memory for this run's context if not already
        update_tokens_in_memory(loaded_tokens["access_token"], loaded_tokens["refresh_token"], (loaded_tokens["expires_at"] - time.time() + 300))
    elif your_manual_grant_token and your_manual_grant_token != "YOUR_MANUAL_GRANT_TOKEN_HERE":
        # If no valid tokens in file, but a manual grant token is provided
        if generate_initial_tokens(your_manual_grant_token):
            print("\nZoho authentication successful! Tokens saved to zoho_tokens.json.")
            print(f"Access Token: {get_access_token()}") # Get from memory/file
            print(f"Refresh Token: {_ZOHO_REFRESH_TOKEN}")
            print("\nYou can now run your main Telegram bot (python telegram_bot.py).")
        else:
            print("\nFailed to generate initial Zoho tokens. Please review the logs above for specific errors.")
    else:
        print("\n🚨 No valid Zoho tokens found in file and no manual grant token provided.")
        print("Please update 'your_manual_grant_token' in zoho_auth.py with the actual grant token from Zoho API Console.")
        print(f"You can generate it from your 'Self Client' application in Zoho API Console under 'Generate Code'.")
        print("Remember to copy the code from the pop-up immediately after generating it, then run this script.")