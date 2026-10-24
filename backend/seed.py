"""Seed the database with demo data.

================================  SYNTHETIC DATA  ================================
Everything generated here is FAKE, produced by a random model for demo purposes
only. It is NOT real sales data from any store. The generator mixes a per-item
base demand, weekly seasonality (weekend uplift), random noise, and festival
spikes (Diwali, Pongal, Eid, Holi) so the forecasting models have something
realistic-looking to learn from.
=================================================================================

Run:  python seed.py
This DROPS and recreates all tables, then inserts ~15 items and 12 months of
daily sales. A few items are given deliberately low stock so stockout alerts
show up during the demo.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

import numpy as np

from db import Base, SessionLocal, engine, init_db
from models import Item, Sale

RANDOM_SEED = 42
DAYS_OF_HISTORY = 365

# (name, unit, base_daily_demand, weekend_multiplier, current_stock, reorder_level)
# base_daily_demand is the average units sold per day (SYNTHETIC).
# Items where current_stock < reorder_level start LOW and trigger alerts.
ITEMS: list[tuple[str, str, float, float, float, float]] = [
    # --- Grains & staples ---
    ("Rice",            "kg",     20, 1.4,   8,  25),   # LOW
    ("Basmati Rice",    "kg",      8, 1.4,  30,  15),
    ("Atta",            "kg",     15, 1.3,  40,  20),
    ("Wheat Flour",     "kg",      7, 1.2,  22,  10),
    ("Maida",           "kg",      5, 1.2,  18,   8),
    ("Sooji Rava",      "kg",      4, 1.1,  15,   6),
    ("Poha",            "packet",  6, 1.2,  20,   8),
    # --- Pulses ---
    ("Toor Dal",        "kg",      9, 1.2,  28,  12),
    ("Moong Dal",       "kg",      6, 1.2,  10,  12),   # LOW
    ("Chana Dal",       "kg",      5, 1.1,  16,   8),
    ("Urad Dal",        "kg",      4, 1.1,  14,   6),
    ("Rajma",           "kg",      3, 1.2,  12,   5),
    ("Chickpeas Chana", "kg",      4, 1.2,  15,   6),
    # --- Sugar & salt ---
    ("Sugar",           "kg",     10, 1.2,   5,  15),   # LOW
    ("Jaggery",         "kg",      3, 1.1,  10,   5),
    ("Salt",            "kg",      6, 1.1,  25,  10),
    # --- Oils & ghee ---
    ("Cooking Oil",     "litre",   8, 1.3,  30,  12),
    ("Sunflower Oil",   "litre",   6, 1.3,   9,  12),   # LOW
    ("Mustard Oil",     "litre",   4, 1.2,  14,   6),
    ("Ghee",            "packet",  5, 1.3,  20,   8),
    # --- Dairy ---
    ("Milk",            "litre",  25, 1.1,  18,  30),   # LOW
    ("Curd",            "packet", 12, 1.1,  20,  10),
    ("Paneer",          "packet",  6, 1.4,   8,  10),   # LOW
    ("Butter",          "packet",  7, 1.3,  15,   8),
    ("Cheese",          "packet",  4, 1.4,  12,   6),
    # --- Beverages ---
    ("Tea",             "packet", 12, 1.2,  50,  15),
    ("Coffee",          "packet",  6, 1.2,  25,  10),
    ("Cold Drinks",     "piece",  16, 1.6,  40,  22),
    ("Fruit Juice",     "piece",   8, 1.5,  18,  10),
    ("Bottled Water",   "piece",  20, 1.3,  30,  20),
    # --- Snacks ---
    ("Biscuits",        "packet", 18, 1.5,  60,  25),
    ("Namkeen",         "packet", 10, 1.4,  25,  12),
    ("Chips",           "packet", 14, 1.6,  10,  15),   # LOW
    ("Chocolate",       "piece",   9, 1.5,  22,  12),
    ("Noodles",         "packet", 12, 1.4,  28,  15),
    # --- Spices & condiments ---
    ("Spices Masala",   "packet", 11, 1.2,  33,  15),
    ("Turmeric Powder", "packet",  5, 1.1,  18,   8),
    ("Chilli Powder",   "packet",  5, 1.1,  16,   8),
    ("Garam Masala",    "packet",  4, 1.2,  14,   6),
    ("Tomato Ketchup",  "packet",  4, 1.3,  12,   6),
    # --- Personal care ---
    ("Soap",            "piece",  14, 1.3,  45,  20),
    ("Shampoo",         "packet", 10, 1.4,  38,  15),
    ("Toothpaste",      "piece",   8, 1.2,  20,  10),
    ("Hair Oil",        "packet",  5, 1.2,  15,   8),
    # --- Household ---
    ("Detergent",       "packet",  8, 1.3,  30,  12),
    ("Dish Soap",       "piece",   6, 1.2,  10,  12),   # LOW
    ("Agarbatti",       "packet",  5, 1.2,  18,   8),
    ("Candles",         "piece",   3, 1.1,  12,   5),
    ("Matchbox",        "piece",   7, 1.1,  25,  10),
]

# Festival dates within the last ~year with a demand spike multiplier (SYNTHETIC).
# Dates are illustrative; the point is to create learnable seasonal spikes.
FESTIVALS: dict[str, tuple[date, float]] = {
    "Diwali": (date(2025, 10, 20), 2.5),
    "Pongal": (date(2026, 1, 14), 1.8),
    "Holi":   (date(2026, 3, 14), 2.0),
    "Eid":    (date(2026, 3, 31), 2.2),
}


def is_festival(day: date) -> bool:
    """True if `day` is within +/-1 day of any festival (the spike window)."""
    for fest_date, _ in FESTIVALS.values():
        if abs((day - fest_date).days) <= 1:
            return True
    return False


def _festival_multiplier(day: date) -> float:
    mult = 1.0
    for fest_date, spike in FESTIVALS.values():
        delta = abs((day - fest_date).days)
        if delta == 0:
            mult = max(mult, spike)
        elif delta == 1:
            mult = max(mult, 1 + (spike - 1) * 0.5)  # softer shoulder day
    return mult


def generate_sales(item_cfg: tuple[str, str, float, float, float, float], start: date, end: date) -> list[float]:
    """Generate one SYNTHETIC daily sales series for an item."""
    _, _, base, weekend_mult, _, _ = item_cfg
    series: list[float] = []
    day = start
    while day <= end:
        demand = base
        # Weekly seasonality: Saturday(5)/Sunday(6) get a weekend uplift.
        if day.weekday() >= 5:
            demand *= weekend_mult
        # Festival spikes.
        demand *= _festival_multiplier(day)
        # Multiplicative noise so variance scales with demand.
        demand *= np.random.normal(1.0, 0.18)
        series.append(max(0.0, round(demand, 1)))
        day += timedelta(days=1)
    return series


def seed() -> None:
    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)

    # Fresh start every run.
    Base.metadata.drop_all(bind=engine)
    init_db()

    end = date.today()
    start = end - timedelta(days=DAYS_OF_HISTORY - 1)

    db = SessionLocal()
    try:
        for cfg in ITEMS:
            name, unit, _base, _wmult, stock, reorder = cfg
            item = Item(name=name, unit=unit, current_stock=stock, reorder_level=reorder)
            db.add(item)
            db.flush()  # assign item.id

            qtys = generate_sales(cfg, start, end)
            day = start
            for qty in qtys:
                db.add(Sale(item_id=item.id, date=day, qty=qty))
                day += timedelta(days=1)

        db.commit()

        n_items = db.query(Item).count()
        n_sales = db.query(Sale).count()
        low = [c[0] for c in ITEMS if c[4] < c[5]]
        print("=" * 60)
        print("SYNTHETIC demo data seeded.")
        print(f"  Items: {n_items}")
        print(f"  Sales rows: {n_sales} ({DAYS_OF_HISTORY} days x {n_items} items)")
        print(f"  Date range: {start} -> {end}")
        print(f"  Low-stock items (will trigger alerts): {', '.join(low)}")
        print("=" * 60)
    finally:
        db.close()


if __name__ == "__main__":
    seed()
