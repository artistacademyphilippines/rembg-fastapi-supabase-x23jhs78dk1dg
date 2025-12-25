from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from rembg import remove
from io import BytesIO
import base64
import os
import httpx

# ---------------- ENV ----------------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise RuntimeError("Missing Supabase env vars")

# ---------------- APP ----------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5503"],
    allow_credentials=True,
    allow_methods=["POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# ---------------- MODEL ----------------
class RequestData(BaseModel):
    data_sent: str

# ---------------- HELPERS ----------------
async def get_user_email_from_token(token: str) -> str:
    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": SUPABASE_SERVICE_KEY,
            },
        )

    if res.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid session token")

    return res.json()["email"]


async def has_credits(email: str) -> bool:
    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{SUPABASE_URL}/rest/v1/wondr_users"
            f"?select=rembg_credits&email=eq.{email}",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            },
        )

    if res.status_code != 200:
        print("Supabase error:", res.text)
        raise HTTPException(status_code=500, detail="Failed to fetch credits")

    data = res.json()
    return bool(data and data[0]["rembg_credits"] > 0)

# ---------------- ROUTE ----------------
@app.post("/")
async def remove_background(
    request_data: RequestData,
    authorization: str = Header(None),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing auth header")

    token = authorization.replace("Bearer ", "")

    # ✅ AUTH VALIDATION (Supabase does it)
    email = await get_user_email_from_token(token)

    # ✅ CREDIT CHECK
    if not await has_credits(email):
        raise HTTPException(status_code=403, detail="No rembg credits")

    # ✅ REMOVE BACKGROUND
    img_bytes = base64.b64decode(request_data.data_sent.split(",")[1])
    output = remove(img_bytes, post_process_mask=True)

    buffer = BytesIO(output)
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return {
        "data_received": f"data:image/png;base64,{encoded}"
    }
