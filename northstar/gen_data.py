# 3Dogs Nexus — authorship fingerprint alexa-plus-v2-1422a2dd
"""Deterministic fictional data generator for the Northstar Outdoor Co. demo dataset.

All rows are synthetic. This module exists so tests have stable ground truth and
so the demo can display the fictional dataset. It performs no answering logic.
Run as a script (`python northstar/gen_data.py`) to write the CSV files into
`northstar/data/`, the directory next to this module. The CSV files are not
committed; regenerate them with the command above.
"""
import csv
import hashlib
import os
import random
from datetime import datetime, timedelta

COMPANY = "Northstar Outdoor Co."

REGIONS = ["Pacific", "Mountain", "Central", "Atlantic"]
CHANNELS = ["Retail", "Online", "Wholesale"]
CATEGORIES = [
    ("Tents", 120.0, 620.0),
    ("Sleeping Bags", 60.0, 340.0),
    ("Backpacks", 45.0, 290.0),
    ("Camp Stoves", 30.0, 210.0),
    ("Water Filters", 18.0, 95.0),
    ("Headlamps", 15.0, 70.0),
]
QUARTERS = [
    ("2025-01-05", "Q1 2025"),
    ("2025-04-06", "Q2 2025"),
    ("2025-07-06", "Q3 2025"),
    ("2025-10-05", "Q4 2025"),
    ("2026-01-04", "Q1 2026"),
    ("2026-04-05", "Q2 2026"),
]

PRODUCT_NAMES = {
    "Tents": ["Summit 2P Tent", "Ridgeline 4P Tent", "Aurora 6P Tent"],
    "Sleeping Bags": ["Glacier 0F Bag", "Trailhead 20F Bag", "Ember 40F Bag"],
    "Backpacks": ["Vista 30L Pack", "Meridian 55L Pack", "Drift 18L Daypack"],
    "Camp Stoves": ["Spark Duo Stove", "Titan Pro Stove"],
    "Water Filters": ["Clearbrook Filter", "Streamline Pump Filter"],
    "Headlamps": ["Lumen 200 Lamp", "Beacon 400 Lamp"],
}


def _seeded_rng(tag):
    digest = hashlib.sha256(tag.encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def build_products():
    products = []
    pid = 100
    for category, lo, hi in CATEGORIES:
        for name in PRODUCT_NAMES[category]:
            rng = _seeded_rng(name)
            price = round(rng.uniform(lo, hi), 2)
            products.append({
                "product_id": pid,
                "product_name": name,
                "category": category,
                "unit_price": price,
            })
            pid += 1
    return products


def build_sales(products):
    sales = []
    sid = 10000
    for start_date, quarter in QUARTERS:
        start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
        # Calculate end of quarter (approximated as 90 days)
        end_datetime = start_datetime + timedelta(days=90)
        quarter_days = (end_datetime - start_datetime).days
        
        for product in products:
            for region in REGIONS:
                rng = _seeded_rng(
                    f"{quarter}|{product['product_id']}|{region}"
                )
                # Generate a deterministic date within the quarter
                day_offset = rng.randint(0, quarter_days)
                sale_date = (start_datetime + timedelta(days=day_offset)).strftime("%Y-%m-%d")
                
                channel = rng.choice(CHANNELS)
                units = rng.randint(5, 180)
                revenue = round(units * product["unit_price"], 2)
                returns = rng.randint(0, max(1, units // 25))
                sales.append({
                    "sale_id": sid,
                    "sale_date": sale_date,
                    "quarter": quarter,
                    "region": region,
                    "channel": channel,
                    "product_id": product["product_id"],
                    "units_sold": units,
                    "revenue_usd": revenue,
                    "units_returned": returns,
                })
                sid += 1
    return sales


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def generate(output_dir="data"):
    os.makedirs(output_dir, exist_ok=True)
    products = build_products()
    sales = build_sales(products)
    write_csv(
        os.path.join(output_dir, "products.csv"),
        products,
        ["product_id", "product_name", "category", "unit_price"],
    )
    write_csv(
        os.path.join(output_dir, "sales.csv"),
        sales,
        ["sale_id", "sale_date", "quarter", "region", "channel",
         "product_id", "units_sold", "revenue_usd", "units_returned"],
    )
    return {"products": products, "sales": sales}


def summary(products, sales):
    total_revenue = round(sum(r["revenue_usd"] for r in sales), 2)
    total_units = sum(r["units_sold"] for r in sales)
    by_quarter = {}
    # Accumulate raw floats to avoid rounding errors
    for row in sales:
        quarter = row["quarter"]
        if quarter not in by_quarter:
            by_quarter[quarter] = 0.0
        by_quarter[quarter] += row["revenue_usd"]
    # Round once at the end
    for quarter in by_quarter:
        by_quarter[quarter] = round(by_quarter[quarter], 2)
    return {
        "company": COMPANY,
        "product_count": len(products),
        "sale_rows": len(sales),
        "total_units": total_units,
        "total_revenue_usd": total_revenue,
        "revenue_by_quarter": by_quarter,
    }


if __name__ == "__main__":
    # Anchor output directory to the script's location (northstar/data/)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(script_dir, "data")
    data = generate(output_dir)
    info = summary(data["products"], data["sales"])
    print(f"{info['company']} fictional dataset generated.")
    print(f"Products: {info['product_count']}  Sale rows: {info['sale_rows']}")
    print(f"Total revenue (USD): {info['total_revenue_usd']}")
