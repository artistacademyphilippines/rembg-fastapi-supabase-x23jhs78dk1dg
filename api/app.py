import os
import base64
from io import BytesIO

import jwt
import httpx
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from rembg import remove

# -------------------------------
# CONFIG
# -------------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL")  # e.g. https://xyz.supabase.co
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET")  # HS256 JWT signing key
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")  # for server-side access

if not SUPABASE_URL or not SUPABASE_JWT_SECRET or not SUPABASE_SERVICE_KEY:
    raise RuntimeError("Missing SUPABASE environment variables")

# -------------------------------
# FASTAPI INIT
# -------------------------------
app = FastAPI()
origins = ["http://127.0.0.1:5503"]  # Add your frontend origin(s)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# -------------------------------
# REQUEST MODEL
# -------------------------------
class RequestData(BaseModel):
    data_sent: str  # base64 image string

# -------------------------------
# HELPERS
# -------------------------------
def get_user_id_from_token(token: str) -> str:
    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload["sub"]
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid token")

async def has_credits(user_id: str) -> bool:
    """Return True if user has rembg_credits > 0"""
    url = f"{SUPABASE_URL}/rest/v1/wondr_users?id=eq.{user_id}"
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(status_code=500, detail="Supabase request failed")
        data = resp.json()
        if not data or data[0].get("rembg_credits", 0) <= 0:
            return False
        return True

# -------------------------------
# ENDPOINT
# -------------------------------
@app.post("/")
async def remove_background(
    request_data: RequestData,
    authorization: str = Header(...)
):
    # 1. Extract Bearer token
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.split(" ")[1]

    # 2. Verify JWT
    user_id = get_user_id_from_token(token)

    # 3. Check rembg_credits
    if not await has_credits(user_id):
        raise HTTPException(status_code=403, detail="Insufficient credits")

    # 4. Decode base64 image
    try:
        img_data = base64.b64decode(request_data.data_sent.split(",")[1])
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image")

    # 5. Remove background
    removed_background = remove(img_data, post_process_mask=True)

    # 6. Convert to base64
    new_data = BytesIO(removed_background)
    new_data.seek(0)
    new_base64 = base64.b64encode(new_data.getvalue()).decode("utf-8")
    data_received = f"data:image/png;base64,{new_base64}"

    return {"data_received": data_received}
