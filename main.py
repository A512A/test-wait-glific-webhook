import asyncio
import logging
from fastapi import FastAPI, BackgroundTasks, Request
from pydantic import BaseModel
import glific_client as gc
import json


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

class WebhookPayload(BaseModel):
    phone: str

async def process_long_task(phone: str):
    """Wait 10s then resume the Glific flow."""
    try:
        # Simulate the long-running process
        logger.info(f"Task started for {phone}. Waiting 10s...")
        await asyncio.sleep(10)
        
        result_payload = {"status": "waited 10s"}

        # Orchestrate the Glific resume process
        token = await gc.get_auth_token()
        flow_id = await gc.get_flow_id(token)
        contact_id = await gc.get_contact_id(token, phone)
        
        await gc.resume_contact_flow(token, flow_id, contact_id, result_payload)
        logger.info(f"Successfully resumed flow for {phone}")
        
    except Exception as e:
        logger.error(f"Failed to resume flow for {phone}: {str(e)}")

# @app.post("/webhook")
# async def handle_webhook(payload: WebhookPayload, background_tasks: BackgroundTasks):
#     # This sends an immediate 200 OK back to Glific
#     background_tasks.add_task(process_long_task, payload.phone)
#     return {"status": "accepted", "message": "Processing started in background"}
@app.post("/webhook")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    # 1. Manually get the raw body
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8")
    
    try:
        # 2. Parse the string into a dict
        data = json.loads(body_str)
        
        # If Glific double-stringified it (happens sometimes), parse again
        if isinstance(data, str):
            data = json.loads(data)
            
        phone = data.get("phone")
        if not phone:
            return {"error": "No phone provided"}, 400
            
        # 3. Trigger the background task
        background_tasks.add_task(process_long_task, str(phone))
        return {"status": "accepted"}
        
    except Exception as e:
        logger.error(f"Failed to parse webhook body: {body_str} - Error: {e}")
        return {"error": "Invalid JSON format"}, 400