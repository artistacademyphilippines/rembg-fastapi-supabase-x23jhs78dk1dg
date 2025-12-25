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
# Environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")

if not all([SUPABASE_URL, SUPABASE_KEY, SUPABASE_JWT_SECRET]):
    raise RuntimeError("Missing SUPABASE environment variables")

# -------------------
app = FastAPI()

origins = ["http://127.0.0.1:5503"]
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
async def check_credits(user_id: str) -> bool:
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/wondr_users"
            f"?select=rembg_credits&id=eq.{user_id}",
            headers=headers,
        )

        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Supabase query failed")

        data = r.json()
        return bool(data and data[0]["rembg_credits"] > 0)

# -------------------
@app.post("/")
async def remove_background(
    request_data: RequestData,
    authorization: str = Header(None),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    token = authorization.split(" ")[1]

    # 🔥 THIS WAS THE BUG
    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
        user_id = payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        print("JWT ERROR:", e)
        raise HTTPException(status_code=401, detail="Invalid token")

    if not await check_credits(user_id):
        raise HTTPException(status_code=403, detail="Insufficient credits")

    # Remove background
    img_data = base64.b64decode(request_data.data_sent.split(",")[1])
    removed = remove(img_data, post_process_mask=True)

    buf = BytesIO(removed)
    new_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return {
        "data_received": f"data:image/png;base64,{new_base64}"
    }
