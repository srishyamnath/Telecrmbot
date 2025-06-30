# zoho_leads.py
import requests
import json
from zoho_auth import get_access_token # Import the token retrieval function
from config import ZOHO_CRM_API_URL
import logging

logger = logging.getLogger(__name__)

def search_lead_by_phone(phone_number: str):
    access_token = get_access_token()
    if not access_token:
        logger.error("No Zoho access token available for lead search.")
        return None

    # Zoho CRM expects phone numbers to be stored in the 'Phone' field or 'Mobile' field.
    # It's good practice to search both or prioritize.
    # Note: Zoho's search can be sensitive to formatting (+91 vs 0 vs no prefix)
    query = f"(Phone:starts_with:{phone_number} or Mobile:starts_with:{phone_number})"
    search_url = f"{ZOHO_CRM_API_URL}/Leads/search"
    headers = {
        "Authorization": f"Zoho-oauthtoken {access_token}"
    }
    params = {
        "criteria": query
    }
    try:
        response = requests.get(search_url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        if data.get('data'):
            # Assuming first result is the most relevant or only one expected for exact match
            logger.info(f"Found existing lead: {data['data'][0].get('Full_Name')}")
            return data['data'][0]
        else:
            logger.info(f"No lead found for phone number: {phone_number}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error searching lead in Zoho CRM: {e}")
        logger.error(f"Zoho Search Response: {response.text if 'response' in locals() else 'No response'}")
        return None

def create_lead(first_name: str, last_name: str, email: str, phone_number: str):
    access_token = get_access_token()
    if not access_token:
        logger.error("No Zoho access token available for lead creation.")
        return None

    create_url = f"{ZOHO_CRM_API_URL}/Leads"
    headers = {
        "Authorization": f"Zoho-oauthtoken {access_token}",
        "Content-Type": "application/json"
    }
    lead_data = {
        "data": [
            {
                "First_Name": first_name,
                "Last_Name": last_name, # Zoho CRM often requires a Last_Name
                "Email": email,
                "Phone": phone_number,
                "Lead_Source": "Telegram Bot" # You can customize this
            }
        ]
    }
    try:
        response = requests.post(create_url, headers=headers, data=json.dumps(lead_data))
        response.raise_for_status()
        data = response.json()
        if data.get('data') and data['data'][0].get('code') == 'SUCCESS':
            logger.info(f"Successfully created lead: {data['data'][0].get('details', {}).get('id')}")
            return data['data'][0].get('details')
        else:
            logger.error(f"Error creating lead in Zoho CRM: {data.get('message', 'Unknown error')}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Network or request error during lead creation: {e}")
        logger.error(f"Zoho Create Response: {response.text if 'response' in locals() else 'No response'}")
        return None