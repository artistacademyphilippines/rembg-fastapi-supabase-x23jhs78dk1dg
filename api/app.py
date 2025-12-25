from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from rembg import remove
import base64
from io import BytesIO
import os
import logging
import jwt  # PyJWT library for JWT decoding

# -----------------------
# CONFIG
# -----------------------
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET")

# Frontend origins allowed to call this API
origins = [
    "http://127.0.0.1:5503",  # local dev
    "http://localhost:5503",
    "https://artistaacademy.github.io"  # production frontend
]

# -----------------------
# FASTAPI SETUP
# -----------------------
app = FastAPI()
logging.basicConfig(level=logging.INFO)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------
# REQUEST MODEL
# -----------------------
class RequestData(BaseModel):
    data_sent: str  # base64 image string

# -----------------------
# HELPER FUNCTION TO VERIFY JWT
# -----------------------
def verify_supabase_jwt(token: str):
    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False}  # optional, depending on your Supabase config
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing user id")
        return user_id
    except Exception as e:
        logging.error(f"JWT verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

# -----------------------
# ROUTE
# -----------------------
@app.post("/")
async def remove_background(
    request_data: RequestData,
    authorization: str = Header(...)
):
    # Expect header: Authorization: Bearer <JWT>
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    
    token = authorization.split(" ")[1]
    
    # Verify JWT
    user_id = verify_supabase_jwt(token)
    logging.info(f"Processing request for user_id: {user_id}")

    try:
        # Decode base64 image
        if "," in request_data.data_sent:
            img_data = base64.b64decode(request_data.data_sent.split(",")[1])
        else:
            img_data = base64.b64decode(request_data.data_sent)

        # Remove background
        removed_background = remove(img_data, post_process_mask=True)

        # Convert to base64 for frontend
        bio = BytesIO(removed_background)
        bio.seek(0)
        new_base64 = base64.b64encode(bio.getvalue()).decode("utf-8")
        result_data = f"data:image/png;base64,{new_base64}"

        return {"data_received": result_data}

    except Exception as e:
        logging.error(f"Failed to process image: {e}")
        raise HTTPException(status_code=500, detail="Failed to remove background")
