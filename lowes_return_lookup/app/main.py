from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from .lookup import lookup_product

app = FastAPI(title="Lowe's Return Timeframe Lookup", version="1.0.0")
app.mount("/static", StaticFiles(directory="static"), name="static")

class LookupRequest(BaseModel):
    query: str

@app.get("/")
def index():
    return FileResponse("static/index.html")

@app.post("/api/lookup")
async def lookup(req: LookupRequest):
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Enter an item number or model number.")
    try:
        return await lookup_product(query)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Lookup failed: {e}")
