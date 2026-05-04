"""
Async Glific API client.
Handles the multi-step process of resuming a flow in Glific:
  1. Authenticate using Admin phone/password.
  2. Locate the numeric 'Flow ID' using a human-readable name.
  3. Locate the numeric 'Contact ID' using the phone number.
  4. Post results back to the 'resumeContactFlow' GraphQL mutation.

Environment variables required:
  GLIFIC_BASE_URL   - The API root for your Glific instance.
  GLIFIC_PHONE      - Admin credentials.
  GLIFIC_PASSWORD   - Admin credentials.
  GLIFIC_FLOW_NAME  - The name of the extraction flow in Glific.
"""

import os
import json
import logging
import httpx

logger = logging.getLogger(__name__)

# Constants from environment
GLIFIC_BASE_URL = os.getenv("GLIFIC_BASE_URL", "")
GLIFIC_PHONE = os.getenv("GLIFIC_PHONE", "")
GLIFIC_PASSWORD = os.getenv("GLIFIC_PASSWORD", "")
GLIFIC_FLOW_NAME = os.getenv("GLIFIC_FLOW_NAME", "vopro-extract")


async def get_auth_token() -> str:
    """
    Step 1: Exchange Admin credentials for a session JWT.
    
    Returns:
        str: The 'access_token' required for all subsequent GraphQL calls.
    """
    url = f"{GLIFIC_BASE_URL}/api/v1/session"
    payload = {"user": {"phone": GLIFIC_PHONE, "password": GLIFIC_PASSWORD}}
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=15.0)
        resp.raise_for_status()
        token = resp.json()["data"]["access_token"]
        logger.info("GLIFIC CLIENT: Session token successfully retrieved")
        return token


async def get_flow_id(auth_token: str) -> str:
    """
    Step 2: Find the internal numeric ID of the flow we want to resume.
    
    Args:
        auth_token (str): Valid Glific session token.
        
    Returns:
        str: The internal Glific ID of the flow.
    """
    query = """
    query flows($filter: FlowFilter, $opts: Opts) {
      flows(filter: $filter, opts: $opts) {
        id
        name
      }
    }
    """
    # Filter by the flow name set in environment variables
    variables = {
        "filter": {"name": GLIFIC_FLOW_NAME},
        "opts": {"limit": 1, "offset": 0, "order": "ASC"},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GLIFIC_BASE_URL}/api",
            json={"query": query, "variables": variables},
            headers={"authorization": auth_token, "Content-Type": "application/json"},
            timeout=15.0,
        )
        resp.raise_for_status()
        flows = resp.json()["data"]["flows"]
        if not flows:
            raise ValueError(f"GLIFIC CLIENT ERROR: Flow named '{GLIFIC_FLOW_NAME}' not found.")
        flow_id = flows[0]["id"]
        logger.info(f"GLIFIC CLIENT: Found Flow ID '{flow_id}' for name '{GLIFIC_FLOW_NAME}'")
        return flow_id


async def get_contact_id(auth_token: str, phone: str) -> str:
    """
    Step 3: Convert the phone number from the request into a Glific Contact ID.
    
    Args:
        phone (str): The phone number to look up.
        
    Returns:
        str: The internal Glific ID for this contact.
    """
    query = """
    query contacts($filter: ContactFilter, $opts: Opts) {
      contacts(filter: $filter, opts: $opts) {
        id
        name
        phone
      }
    }
    """
    variables = {"filter": {"phone": phone}, "opts": {"limit": 1}}
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GLIFIC_BASE_URL}/api",
            json={"query": query, "variables": variables},
            headers={"authorization": auth_token, "Content-Type": "application/json"},
            timeout=15.0,
        )
        resp.raise_for_status()
        contacts = resp.json()["data"]["contacts"]
        if not contacts:
            raise ValueError(f"GLIFIC CLIENT ERROR: Contact with phone '{phone}' not found.")
        contact_id = contacts[0]["id"]
        logger.info(f"GLIFIC CLIENT: Found Contact ID '{contact_id}' for phone '{phone}'")
        return contact_id


async def resume_contact_flow(auth_token: str, flow_id: str, contact_id: str, result: dict) -> None:
    """
    Step 4: Push the final results back to Glific to unpause the flow.
    
    Args:
        auth_token (str): Valid session token.
        flow_id (str): ID of the flow to resume.
        contact_id (str): ID of the contact whose flow is paused.
        result (dict): The extracted profile data.
    """
    mutation = """
    mutation resumeContactFlow($flowId: ID!, $contactId: ID!, $result: Json!) {
      resumeContactFlow(flowId: $flowId, contactId: $contactId, result: $result) {
        success
        errors {
          key
          message
        }
      }
    }
    """
    # NOTE: Glific requires the 'result' value to be a STRINGIFIED JSON object
    variables = {
        "flowId": flow_id,
        "contactId": contact_id,
        "result": json.dumps(result), 
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GLIFIC_BASE_URL}/api",
            json={"query": mutation, "variables": variables},
            headers={"authorization": auth_token, "Content-Type": "application/json"},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        resume_result = data.get("data", {}).get("resumeContactFlow", {})
        
        if not resume_result.get("success"):
            errors = resume_result.get("errors", [])
            logger.error(f"GLIFIC CLIENT ERROR: Mutation failed with errors: {errors}")
            raise RuntimeError(f"Glific resumeContactFlow failed: {errors}")
            
        logger.info(f"GLIFIC CLIENT SUCCESS: Flow resumed for contact_id={contact_id}")
