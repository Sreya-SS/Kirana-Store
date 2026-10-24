"""Stockout alerts.

For each item, compare current stock to the forecast demand over the next few
days (default 3). If stock won't cover it, raise an alert telling the owner to
reorder. Runs nightly via APScheduler and on demand via POST /alerts/run.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from forecast import forecast_next_n_total
from models import Alert, Item

HORIZON_DAYS = 3


def _fmt(x: float) -> str:
    """Show whole numbers without a trailing .0."""
    return str(int(round(x))) if abs(x - round(x)) < 0.05 else str(round(x, 1))


def run_check(db: Session, horizon_days: int = HORIZON_DAYS) -> list[Alert]:
    """Regenerate alerts from the current stock + forecast.

    Each run clears previous alerts and rebuilds a fresh snapshot, so the list
    always reflects the latest stock levels (and pressing "Run check now"
    repeatedly won't pile up duplicates).
    """
    db.query(Alert).delete()

    created: list[Alert] = []
    for item in db.query(Item).order_by(Item.name).all():
        demand = forecast_next_n_total(db, item.id, horizon_days)
        if item.current_stock < demand:
            msg = (
                f"{item.name}: stock {_fmt(item.current_stock)} {item.unit}, "
                f"expected demand {_fmt(demand)} {item.unit} in {horizon_days} days. "
                f"Reorder now."
            )
            alert = Alert(item_id=item.id, message=msg)
            db.add(alert)
            created.append(alert)

    db.commit()
    for a in created:
        db.refresh(a)
    return created


def nightly_job() -> None:
    """APScheduler entry point -- owns its own DB session."""
    from db import SessionLocal

    db = SessionLocal()
    try:
        created = run_check(db)
        print(f"[scheduler] Nightly alert check: {len(created)} alert(s) created.")
    finally:
        db.close()
