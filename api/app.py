from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import base64
from io import BytesIO
from rembg import remove
import httpx
import jwt  # PyJWT

# -------------------
# Environment variables (set these in your App Platform)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")  # service role key
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET")    # legacy HS256

if not all([SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_JWT_SECRET]):
    raise RuntimeError("Missing SUPABASE environment variables")

# -------------------
app = FastAPI()

origins = ["http://127.0.0.1:5503"]  # adjust to your frontend
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
async def has_credits(email: str) -> bool:
    """Check if the user has rembg_credits > 0"""
    from urllib.parse import quote
    safe_email = quote(email)

    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{SUPABASE_URL}/rest/v1/wondr_users?select=rembg_credits&email=eq.{safe_email}",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Accept": "application/json",
            },
        )

    # Debug prints
    print("Supabase GET status:", res.status_code)
    print("Supabase GET body:", res.text)

    if res.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to fetch credits from Supabase")

    data = res.json()
    print("Supabase GET data:", data)

    return bool(data and data[0]["rembg_credits"] > 0)

# -------------------
@app.post("/")
async def remove_background(request_data: RequestData, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.split(" ")[1]

    try:
        payload = jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"])
        user_email = payload.get("email")
        if not user_email:
            raise HTTPException(status_code=401, detail="Token missing email")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Check credits
    if not await has_credits(user_email):
        raise HTTPException(status_code=403, detail="Insufficient rembg credits")

    # Decode image
    try:
        img_data = base64.b64decode(request_data.data_sent.split(",")[1])
    except Exception as e:
        print("Failed to decode image:", e)
        raise HTTPException(status_code=400, detail="Invalid image data")

    # Remove background
    removed_background = remove(img_data, post_process_mask=True)
    new_data = BytesIO(removed_background)
    new_data.seek(0)
    new_base64 = base64.b64encode(new_data.getvalue()).decode("utf-8")
    data_received = f"data:image/png;base64,{new_base64}"

    return {"data_received": data_received}
