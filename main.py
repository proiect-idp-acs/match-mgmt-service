from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator
import httpx

app = FastAPI(title="Match Management Service", description="Business Logic și State Machine")

Instrumentator().instrument(app).expose(app)

# Schema pentru actualizarea scorului
class ScoreUpdate(BaseModel):
    match_id: int
    point_winner: str # ex: "player1" sau "player2"

@app.get("/")
def read_root():
    return {"message": "Match Management Service (Business Logic) este activ!"}

@app.post("/api/matches/score")
async def update_score(update: ScoreUpdate):
    """
    Aici va fi implementat State Machine-ul.
    1. Verificăm token-ul arbitrului (cerere către Auth Service)
    2. Calculăm noul scor (15-0, 30-0 etc.) pe baza regulilor de tenis
    3. Trimitem noul scor către Data Service pentru a fi salvat în DB
    """
    
    # Exemplu de cerere internă către Data Service (momentan comentată până unificăm rețeaua)
    # async with httpx.AsyncClient() as client:
    #     response = await client.get("http://tennis-data:5002/api/data/matches")
    #     matches = response.json()

    return {
        "status": "success",
        "action": f"Punct acordat pentru {update.point_winner}",
        "message": "State Machine-ul urmează să fie integrat aici."
    }