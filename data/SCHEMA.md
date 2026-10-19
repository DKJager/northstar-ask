# Northstar Outdoor Co. — Fictional Dataset Schema

All data in this dataset is **synthetic and fictional**. It exists only for the
Northstar Ask hackathon demo and for test ground truth. No real customer,
retailer, or transaction data is included anywhere in this repository.

The dataset is generated deterministically by `python northstar/gen_data.py`
(same output on every run), which writes two CSV files to `northstar/data/`
(`northstar/data/products.csv` and `northstar/data/sales.csv`). The CSV files
are not committed; run the generator to produce them:

## products.csv

| Column       | Type   | Description                                |
|--------------|--------|--------------------------------------------|
| product_id   | int    | Unique product identifier (starts at 100)  |
| product_name | string | Fictional product name                     |
| category     | string | One of: Tents, Sleeping Bags, Backpacks, Camp Stoves, Water Filters, Headlamps |
| unit_price   | decimal| Fictional unit price in USD                |

## sales.csv

| Column         | Type   | Description                                    |
|----------------|--------|------------------------------------------------|
| sale_id        | int    | Unique sale-row identifier (starts at 10000)   |
| sale_date      | date   | Fictional sale date (a deterministic day inside the quarter)         |
| quarter        | string | Quarter label, e.g. `Q1 2025` … `Q2 2026`      |
| region         | string | One of: Pacific, Mountain, Central, Atlantic   |
| channel        | string | One of: Retail, Online, Wholesale              |
| product_id     | int    | Foreign reference to products.csv              |
| units_sold     | int    | Units sold in the row                          |
| revenue_usd    | decimal| Gross revenue (units_sold × unit_price); returns not subtracted |
| units_returned | int    | Small fictional return count                   |

## Coverage

- 15 products across 6 categories.
- 6 fiscal quarters (Q1 2025 through Q2 2026).
- One sale row per product × region × quarter (360 rows), with one deterministic channel (Retail, Online or Wholesale) and one deterministic date inside the quarter per row.

## Intended demo questions

- "How did revenue look last quarter?"
- "Which region sold the most tents?"
- "How does this compare to the same quarter last year?" (follow-up style; only valid for 2026 quarters due to lack of prior-year data)
- "Give me the weekly business brief." (weekly framing derived from quarterly trends by the answering service)

The answering itself is performed by the private 3Dogs Nexus service; this
repository only stores the fictional display data.
