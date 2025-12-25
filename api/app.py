from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from rembg import remove
from io import BytesIO
import base64
import asyncpg
import jwt
import os

# --------------------
# CONFIG
# --------------------
SUPABASE_JWT_SECRET = os.environ["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1kc2ticXBnaGxwdHNrZ2xzZWtwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MzgwNjg5MzQsImV4cCI6MjA1MzY0NDkzNH0.73MEv89D96Uzm0Ft65lRPhY0gQghia8jvVdwK1G5UkU"]
DATABASE_URL = os.environ["https://mdskbqpghlptskglsekp.supabase.co"]

# --------------------
# APP
# --------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5503",
        "http://localhost:5503",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------
# MODEL
# --------------------
class RequestData(BaseModel):
    data_sent: str

# --------------------
# HELPERS
# --------------------
def get_user_id(token: str) -> str:
    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        return payload["sub"]
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

# --------------------
# ROUTE
# --------------------
@app.post("/")
async def remove_background(
    request: RequestData,
    authorization: str = Header(...)
):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.split(" ")[1]
    user_id = get_user_id(token)

    # ---- CHECK CREDITS ----
    conn = await asyncpg.connect(DATABASE_URL)

    credits = await conn.fetchval(
        """
        SELECT rembg_credits
        FROM wondr_users.wondr_users
        WHERE user_id = $1
        """,
        user_id,
    )

    await conn.close()

    if credits is None or credits <= 0:
        raise HTTPException(status_code=403, detail="No credits left")

    # ---- REMOVE BACKGROUND ----
    img_bytes = base64.b64decode(request.data_sent.split(",")[1])
    output = remove(img_bytes, post_process_mask=True)

    buffer = BytesIO(output)
    encoded = base64.b64encode(buffer.getvalue()).decode()

    return {
        "data_received": f"data:image/png;base64,{encoded}"
    }
