from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from rembg import remove
from io import BytesIO
import base64
import os
import jwt
import httpx

# --------------------
# ENV VARIABLES
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY or not SUPABASE_JWT_SECRET:
    raise RuntimeError("Missing SUPABASE environment variables")

# --------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5503"],
    allow_credentials=True,
    allow_methods=["POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# --------------------
class RequestData(BaseModel):
    data_sent: str

# --------------------
async def user_has_credits(user_id: str) -> bool:
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }

    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{SUPABASE_URL}/rest/v1/wondr_users"
            f"?select=rembg_credits&id=eq.{user_id}",
            headers=headers,
        )

    if res.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to fetch credits")

    data = res.json()
    if not data:
        return False

    return data[0]["rembg_credits"] > 0

# --------------------
@app.post("/")
async def remove_background(
    request_data: RequestData,
    authorization: str = Header(None),
):
    # ---- AUTH HEADER ----
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    token = authorization.replace("Bearer ", "")

    # ---- VERIFY JWT ----
    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # ---- CHECK CREDITS ----
    if not await user_has_credits(user_id):
        raise HTTPException(status_code=403, detail="No rembg credits")

    # ---- PROCESS IMAGE ----
    img_bytes = base64.b64decode(request_data.data_sent.split(",")[1])
    result = remove(img_bytes, post_process_mask=True)

    buffer = BytesIO(result)
    buffer.seek(0)
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return {
        "data_received": f"data:image/png;base64,{encoded}"
    }
