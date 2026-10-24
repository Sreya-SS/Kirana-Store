"""KiranaIQ FastAPI application.

Run (from the backend/ directory):
    python seed.py
    uvicorn main:app --host 0.0.0.0 --port 8000

Endpoints are added step by step. Step 1 ships /health only.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import alerts as alerts_mod
import forecast
import voice
from db import get_db, init_db
from models import Alert, Item


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure tables exist on startup (seed.py normally creates them first).
    init_db()
    # Train the forecasting model once at startup so the first request is fast.
    from db import SessionLocal

    db = SessionLocal()
    try:
        forecast.train_global_model(db)
        print("[startup] Forecast model trained.")
    except Exception as exc:  # pragma: no cover - startup diagnostics
        print(f"[startup] Forecast model NOT trained (run seed.py?): {exc}")
    finally:
        db.close()

    # Preload Whisper so the first /voice/transcribe isn't slow in the demo.
    try:
        voice.load_model()
        print("[startup] Whisper model preloaded.")
    except Exception as exc:  # pragma: no cover
        print(f"[startup] Whisper NOT preloaded: {exc}")

    # Nightly stockout check at 00:30. Manual trigger: POST /alerts/run.
    scheduler = BackgroundScheduler()
    scheduler.add_job(alerts_mod.nightly_job, "cron", hour=0, minute=30, id="nightly_alerts")
    scheduler.start()
    print("[startup] Scheduler started (nightly alert check at 00:30).")

    yield

    scheduler.shutdown(wait=False)


app = FastAPI(title="KiranaIQ API", version="0.1.0", lifespan=lifespan)

# Open CORS for the demo -- the Expo app calls this from a phone on the LAN.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class ItemIn(BaseModel):
    name: str = Field(..., min_length=1)
    unit: str = Field(..., min_length=1)
    current_stock: float = 0
    reorder_level: float = 0


class StockUpdate(BaseModel):
    current_stock: float


class ItemOut(BaseModel):
    id: int
    name: str
    unit: str
    current_stock: float
    reorder_level: float
    low_stock: bool

    @classmethod
    def from_item(cls, item: Item) -> "ItemOut":
        return cls(
            id=item.id,
            name=item.name,
            unit=item.unit,
            current_stock=item.current_stock,
            reorder_level=item.reorder_level,
            low_stock=item.current_stock < item.reorder_level,
        )


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "kiranaiq"}


# --------------------------------------------------------------------------- #
# Step 3: Inventory
# --------------------------------------------------------------------------- #
@app.get("/items", response_model=list[ItemOut])
def list_items(db: Session = Depends(get_db)) -> list[ItemOut]:
    items = db.query(Item).order_by(Item.name).all()
    return [ItemOut.from_item(i) for i in items]


@app.post("/items", response_model=ItemOut, status_code=201)
def create_item(payload: ItemIn, db: Session = Depends(get_db)) -> ItemOut:
    existing = db.query(Item).filter(Item.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Item '{payload.name}' already exists")
    item = Item(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return ItemOut.from_item(item)


@app.put("/items/{item_id}/stock", response_model=ItemOut)
def update_stock(item_id: int, payload: StockUpdate, db: Session = Depends(get_db)) -> ItemOut:
    item = db.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    if payload.current_stock < 0:
        raise HTTPException(status_code=400, detail="Stock cannot be negative")
    item.current_stock = payload.current_stock
    db.commit()
    db.refresh(item)
    return ItemOut.from_item(item)


# --------------------------------------------------------------------------- #
# Step 4: Voice onboarding
# --------------------------------------------------------------------------- #
class ParseTextIn(BaseModel):
    text: str


class BulkLine(BaseModel):
    item: str
    quantity: float
    unit: str


class BulkIn(BaseModel):
    lines: list[BulkLine]


def _known_items(db: Session) -> list[tuple[int, str, str]]:
    return [(i.id, i.name, i.unit) for i in db.query(Item).all()]


@app.post("/voice/transcribe")
async def voice_transcribe(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    try:
        audio_bytes = await file.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Empty audio upload.")
        suffix = os.path.splitext(file.filename or "")[1] or ".m4a"
        transcript = voice.transcribe_file(audio_bytes, suffix=suffix)
        parsed = voice.parse_order(transcript, _known_items(db))
        return {"transcript": transcript, "parsed": parsed}
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}")


@app.post("/voice/parse-text")
def voice_parse_text(payload: ParseTextIn, db: Session = Depends(get_db)) -> dict:
    """Fallback: run typed text through the SAME parser as the audio path."""
    parsed = voice.parse_order(payload.text, _known_items(db))
    return {"transcript": payload.text, "parsed": parsed}


@app.post("/items/bulk")
def items_bulk(payload: BulkIn, db: Session = Depends(get_db)) -> dict:
    """Confirmed review rows: fuzzy-match to existing SKUs and restock, else create.

    Matching an existing item ADDS the quantity to its stock (a restock); an
    unmatched item becomes a new SKU with that quantity as its starting stock.
    """
    known = _known_items(db)
    updated: list[ItemOut] = []
    created: list[ItemOut] = []

    for line in payload.lines:
        match = voice.match_item(line.item, known)
        if match:
            item = db.get(Item, match[0])
            item.current_stock += line.quantity
            updated.append(item)  # converted after commit
        else:
            item = Item(
                name=line.item.strip().title(),
                unit=line.unit or "piece",
                current_stock=line.quantity,
                reorder_level=0,
            )
            db.add(item)
            created.append(item)
            # Make the new item matchable for later lines in the same batch.
            db.flush()
            known.append((item.id, item.name, item.unit))

    db.commit()
    return {
        "updated": [ItemOut.from_item(i) for i in updated],
        "created": [ItemOut.from_item(i) for i in created],
    }


# --------------------------------------------------------------------------- #
# Step 5: Stockout alerts
# --------------------------------------------------------------------------- #
class AlertOut(BaseModel):
    id: int
    item_id: int
    item_name: str
    message: str
    created_at: str
    resolved: bool
    useful: bool | None

    @classmethod
    def from_alert(cls, a: Alert) -> "AlertOut":
        return cls(
            id=a.id,
            item_id=a.item_id,
            item_name=a.item.name if a.item else "",
            message=a.message,
            created_at=a.created_at.isoformat() if a.created_at else "",
            resolved=a.resolved,
            useful=a.useful,
        )


class FeedbackIn(BaseModel):
    useful: bool


@app.get("/alerts", response_model=list[AlertOut])
def list_alerts(db: Session = Depends(get_db)) -> list[AlertOut]:
    rows = db.query(Alert).order_by(Alert.created_at.desc()).all()
    return [AlertOut.from_alert(a) for a in rows]


@app.post("/alerts/run")
def run_alerts(db: Session = Depends(get_db)) -> dict:
    try:
        created = alerts_mod.run_check(db)
        return {"created": len(created), "alerts": [AlertOut.from_alert(a) for a in created]}
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Alert check failed: {exc}")


@app.post("/alerts/{alert_id}/feedback", response_model=AlertOut)
def alert_feedback(alert_id: int, payload: FeedbackIn, db: Session = Depends(get_db)) -> AlertOut:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    alert.useful = payload.useful
    db.commit()
    db.refresh(alert)
    return AlertOut.from_alert(alert)


# --------------------------------------------------------------------------- #
# Step 2: Forecasting
# --------------------------------------------------------------------------- #
@app.get("/forecast/{item_id}")
def get_forecast(item_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        return forecast.forecast_item(db, item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Forecast failed: {exc}")


@app.get("/metrics")
def get_metrics(db: Session = Depends(get_db)) -> dict:
    try:
        return forecast.get_metrics(db)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Metrics failed: {exc}")
