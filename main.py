from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator
import httpx
import os
import jwt
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(title="Match Management Service", description="Business Logic si State Machine pentru Tenis")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
Instrumentator().instrument(app).expose(app)

DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://data_service:5002")

# CONFIGURARE SECURITATE JWT
SECRET_KEY = "super_secret_tennis_key"
security = HTTPBearer()

def verify_arbitru_role(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Extrage token-ul, il decodeaza si verifica rolul
    """
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if payload.get("role") != "arbitru":
            raise HTTPException(status_code=403, detail="Acces interzis! Doar arbitrii pot modifica scorul.")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token-ul a expirat.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token invalid.")
    

class ScoreUpdateRequest(BaseModel):
    point_winner: str  # Trebuie sa fie "player1" sau "player2"

def calculate_next_score(score: dict, winner: str) -> tuple[dict, str, str]:
    """
    Logica pentru scorul unui meci de tenis.
    Returneaza (noul_scor, noul_status, castigatorul_meciului)
    """
    p_idx = 0 if winner == "player1" else 1
    o_idx = 1 if p_idx == 0 else 0
    
    sets = score["sets"]
    games = score["games"]
    points = score["points"]
    
    tennis_points = ["0", "15", "30", "40", "Adv"]
    
    match_status = "In_Progress"
    match_winner = None
    
    # LOGICA DE PUNCTE
    current_p = points[p_idx]
    current_o = points[o_idx]
    
    won_game = False
    
    if current_p == "40":
        if current_o == "40":
            points[p_idx] = "Adv"
        elif current_o == "Adv":
            points[o_idx] = "40" # Deuce
        else:
            won_game = True
    elif current_p == "Adv":
        won_game = True
    else:
        # Trecem la urmatorul punct (0->15, 15->30, 30->40)
        idx = tennis_points.index(current_p)
        points[p_idx] = tennis_points[idx + 1]

    # LOGICA DE GAME-URI SI SET-URI
    if won_game:
        points = ["0", "0"] # Resetam punctele
        games[p_idx] += 1
        
        # Verificam daca a castigat setul (6 game-uri, diferenta de 2)
        if games[p_idx] >= 6 and (games[p_idx] - games[o_idx]) >= 2:
            sets[p_idx] += 1
            games = [0, 0] # Resetam game-urile pentru noul set
            
            # Verificam daca a castigat meciul (Primul la 2 seturi castigate)
            if sets[p_idx] == 2:
                match_status = "Completed"
                match_winner = winner

    return {"sets": sets, "games": games, "points": points}, match_status, match_winner


@app.post("/api/matches/{match_id}/score")
async def update_match_score(
    match_id: int,
    request: ScoreUpdateRequest,
    user_data: dict = Depends(verify_arbitru_role)
    ):
    if request.point_winner not in ["player1", "player2"]:
        raise HTTPException(status_code=400, detail="Castigatorul trebuie sa fie 'player1' sau 'player2'")

    async with httpx.AsyncClient() as client:
        # Obtinem starea actuala a meciului de la Data Service
        try:
            get_resp = await client.get(f"{DATA_SERVICE_URL}/api/data/matches/{match_id}")
            if get_resp.status_code == 404:
                raise HTTPException(status_code=404, detail="Meciul nu a fost gasit")
            match_data = get_resp.json()
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="Eroare de comunicare cu Data Service")

        if match_data["status"] == "Completed":
            raise HTTPException(status_code=400, detail="Acest meci s-a terminat deja")

        # Calculam noul scor
        current_score = match_data["score"]
        new_score, new_status, new_winner = calculate_next_score(current_score, request.point_winner)

        # Trimitem noul scor înapoi la Data Service
        update_payload = {
            "status": new_status,
            "score": new_score,
            "winner": new_winner
        }
        
        update_resp = await client.put(
            f"{DATA_SERVICE_URL}/api/data/matches/{match_id}",
            json=update_payload
        )
        
        if update_resp.status_code != 200:
            raise HTTPException(
                status_code=update_resp.status_code, 
                detail=f"Data Service a refuzat cererea: {update_resp.text}"
            )

        return {
            "message": f"Punct acordat pentru {request.point_winner}",
            "match": update_resp.json()
        }

# Extragerea tuturor meciurilor pentru public/spectatori
@app.get("/api/matches")
async def get_tournament_schedule():
    """
    Ruta publica pentru spectatori si jucatori.
    Returneaza programul turneului si scorurile curente.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{DATA_SERVICE_URL}/api/data/matches")
            if response.status_code != 200:
                raise HTTPException(status_code=500, detail="Eroare la preluarea datelor")
            return response.json()
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="Tournament Data Service este indisponibil")

# Extragerea unui singur meci în timp real
@app.get("/api/matches/{match_id}")
async def get_live_match_score(match_id: int):
    """
    Ruta publica pentru live scoring-ul unui meci specific.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{DATA_SERVICE_URL}/api/data/matches/{match_id}")
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Meciul nu exista")
            elif response.status_code != 200:
                raise HTTPException(status_code=500, detail="Eroare la preluarea scorului")
            return response.json()
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="Tournament Data Service este indisponibil")