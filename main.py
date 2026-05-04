import asyncio
import logging
import json
from fastapi import FastAPI, BackgroundTasks, Request
import glific_client as gc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

async def process_long_task(phone: str):
    """The 'Push' phase: Waits 15s then calls the Glific Mutation."""
    try:
        logger.info(f"Task started for {phone}. Waiting 15s...")
        await asyncio.sleep(15)
        
        result_payload = {"status": "waited 15s"}

        # Perform the logic seen in image_a6ee25.png
        token = await gc.get_auth_token()
        flow_id = await gc.get_flow_id(token)
        contact_id = await gc.get_contact_id(token, phone)
        
        await gc.resume_contact_flow(token, flow_id, contact_id, result_payload)
        logger.info(f"Successfully resumed flow for {phone}")
        
    except Exception as e:
        logger.error(f"Failed to resume flow for {phone}: {str(e)}")

@app.post("/webhook")
def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    """The 'Receipt' phase: Returns 200 OK immediately."""
    try:
        # Standard 'def' + asyncio.run ensures this returns instantly
        body_bytes = asyncio.run(request.body())
        data = json.loads(body_bytes.decode("utf-8"))
        
        # Double-check for stringified JSON from Glific
        if isinstance(data, str):
            data = json.loads(data)
            
        phone = data.get("phone")
        if not phone:
            return {"error": "No phone provided"}, 400
            
        # Hand off and return
        background_tasks.add_task(process_long_task, str(phone))
        return {"status": "accepted"}
        
    except Exception as e:
        logger.error(f"Webhook entry error: {e}")
        return {"error": "Invalid request"}, 400