from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import base64
from io import BytesIO
from rembg import remove
import httpx
import jwt

# -------------------
# Environment variables
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET")

if not all([SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_JWT_SECRET]):
    raise RuntimeError("Missing SUPABASE environment variables")

# -------------------
app = FastAPI()

# Update origins to allow your actual frontend
origins = [
    "http://127.0.0.1:5503",
    "http://localhost:5503",
    # Add your production frontend URL here
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------
class RequestData(BaseModel):
    data_sent: str

# -------------------
async def get_user_credits(user_id: str) -> int:
    """Get user's current rembg_credits by user ID"""
    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{SUPABASE_URL}/rest/v1/wondr_users?select=rembg_credits&id=eq.{user_id}",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Accept": "application/json",
            },
        )
    
    print("GET credits status:", res.status_code)
    print("GET credits response:", res.text)
    
    if res.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to fetch credits")
    
    data = res.json()
    if not data:
        raise HTTPException(status_code=404, detail="User not found")
    
    return data[0]["rembg_credits"]

async def deduct_credit(user_id: str) -> int:
    """Deduct 1 credit from user and return new balance"""
    async with httpx.AsyncClient() as client:
        # Get current credits first
        current_credits = await get_user_credits(user_id)
        
        if current_credits <= 0:
            raise HTTPException(status_code=403, detail="Insufficient rembg credits")
        
        # Deduct 1 credit
        new_credits = current_credits - 1
        
        res = await client.patch(
            f"{SUPABASE_URL}/rest/v1/wondr_users?id=eq.{user_id}",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            json={"rembg_credits": new_credits}
        )
    
    print("PATCH credits status:", res.status_code)
    print("PATCH credits response:", res.text)
    
    if res.status_code not in [200, 204]:
        raise HTTPException(status_code=500, detail="Failed to deduct credit")
    
    return new_credits

# -------------------
@app.get("/")
async def root():
    return {"status": "FastAPI rembg service is running"}

@app.post("/")
async def remove_background(request_data: RequestData, authorization: str = Header(None)):
    # Validate authorization header
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    
    token = authorization.split(" ")[1]
    
    # Decode JWT token to get user info
    try:
        payload = jwt.decode(
            token, 
            SUPABASE_JWT_SECRET, 
            algorithms=["HS256"],
            audience="authenticated"
        )
        user_id = payload.get("sub")  # User ID is in 'sub' claim
        user_email = payload.get("email")
        
        if not user_id:
            raise HTTPException(status_code=401, detail="Token missing user ID")
        
        print(f"Authenticated user: {user_email} (ID: {user_id})")
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        print(f"JWT decode error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # Check and deduct credits
    try:
        remaining_credits = await deduct_credit(user_id)
        print(f"Credits deducted. Remaining: {remaining_credits}")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deducting credits: {e}")
        raise HTTPException(status_code=500, detail="Failed to process credits")
    
    # Decode image
    try:
        if "," in request_data.data_sent:
            img_data = base64.b64decode(request_data.data_sent.split(",")[1])
        else:
            img_data = base64.b64decode(request_data.data_sent)
    except Exception as e:
        print(f"Failed to decode image: {e}")
        # Refund credit on error
        try:
            current = await get_user_credits(user_id)
            await httpx.AsyncClient().patch(
                f"{SUPABASE_URL}/rest/v1/wondr_users?id=eq.{user_id}",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "Content-Type": "application/json",
                },
                json={"rembg_credits": current + 1}
            )
        except:
            pass
        raise HTTPException(status_code=400, detail="Invalid image data")
    
    # Remove background
    try:
        removed_background = remove(img_data, post_process_mask=True)
        new_data = BytesIO(removed_background)
        new_data.seek(0)
        new_base64 = base64.b64encode(new_data.getvalue()).decode("utf-8")
        data_received = f"data:image/png;base64,{new_base64}"
        
        return {
            "data_received": data_received,
            "remaining_credits": remaining_credits
        }
    except Exception as e:
        print(f"Failed to remove background: {e}")
        # Refund credit on error
        try:
            current = await get_user_credits(user_id)
            await httpx.AsyncClient().patch(
                f"{SUPABASE_URL}/rest/v1/wondr_users?id=eq.{user_id}",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "Content-Type": "application/json",
                },
                json={"rembg_credits": current + 1}
            )
        except:
            pass
        raise HTTPException(status_code=500, detail="Failed to process image")
