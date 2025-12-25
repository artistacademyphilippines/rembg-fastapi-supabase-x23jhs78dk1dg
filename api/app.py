# app.py
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import base64
from io import BytesIO
from rembg import remove
import httpx

# -------------------
# Environment variables (set these in App Platform)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not all([SUPABASE_URL, SUPABASE_SERVICE_KEY]):
    raise RuntimeError("Missing SUPABASE environment variables")

# -------------------
app = FastAPI()

origins = ["http://127.0.0.1:5503"]  # adjust for your frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# -------------------
class RequestData(BaseModel):
    data_sent: str

# -------------------
async def check_credits(user_email: str):
    """Check if the user has rembg_credits > 0"""
    headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/wondr_users?select=rembg_credits,email&email=eq.{user_email}",
            headers=headers,
        )
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Error fetching user credits")
        data = r.json()
        if not data or data[0]["rembg_credits"] <= 0:
            return False
    return True

# -------------------
@app.post("/")
async def remove_background(request_data: RequestData, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    # We just use the email from frontend
    user_email = authorization.split(" ")[1]

    # Check credits
    if not await check_credits(user_email):
        raise HTTPException(status_code=403, detail="Insufficient rembg credits")

    # Decode image
    img_data = base64.b64decode(request_data.data_sent.split(",")[1])
    removed_background = remove(img_data, post_process_mask=True)
    new_data = BytesIO(removed_background)
    new_data.seek(0)
    new_base64 = base64.b64encode(new_data.getvalue()).decode("utf-8")
    data_received = f"data:image/png;base64,{new_base64}"

    return {"data_received": data_received}
