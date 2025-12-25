from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from rembg import remove
import base64
from io import BytesIO
import asyncpg
from jose import jwt, JWTError
import os

app = FastAPI()

# CORS
origins = ["http://127.0.0.1:5503", "https://artistaacademy.github.io"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# --- Supabase Config ---
SUPABASE_JWT_SECRET = os.getenv("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1kc2ticXBnaGxwdHNrZ2xzZWtwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MzgwNjg5MzQsImV4cCI6MjA1MzY0NDkzNH0.73MEv89D96Uzm0Ft65lRPhY0gQghia8jvVdwK1G5UkU")
DATABASE_URL = os.getenv("https://mdskbqpghlptskglsekp.supabase.co")

# --- DB pool ---
async def get_db_pool():
    return await asyncpg.create_pool(DATABASE_URL)

# --- JWT verification ---
def verify_token(token: str) -> str:
    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False}
        )
        return payload["sub"]  # user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# --- Consume credit atomically ---
async def consume_credit(pool, user_id: str) -> bool:
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("""
                UPDATE wondr_users.wondr_users
                SET rembg_credits = rembg_credits - 1
                WHERE user_id = $1
                  AND rembg_credits > 0
                RETURNING rembg_credits
            """, user_id)
            return bool(row)

# --- Request Model ---
class RequestData(BaseModel):
    data_sent: str

# --- Main endpoint ---
@app.post('/')
async def remove_background(
    request_data: RequestData,
    authorization: str = Header(...)
):
    # 1️⃣ Verify JWT
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ")[1]
    user_id = verify_token(token)

    # 2️⃣ Check & deduct credit
    pool = await get_db_pool()
    success = await consume_credit(pool, user_id)
    if not success:
        raise HTTPException(status_code=402, detail="Out of credits")

    # 3️⃣ Decode image from base64
    img_data = base64.b64decode(request_data.data_sent.split(',')[1])

    # 4️⃣ Remove background
    removed_background = remove(img_data, post_process_mask=True)

    # 5️⃣ Convert to base64
    new_data = BytesIO(removed_background)
    new_data.seek(0)
    new_base64 = base64.b64encode(new_data.getvalue()).decode('utf-8')
    data_received = f"data:image/png;base64,{new_base64}"

    # 6️⃣ Return result
    return {"data_received": data_received, "credit_used": 1}
