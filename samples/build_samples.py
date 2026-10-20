#!/usr/bin/env python3
"""Deterministic, dependency-free builder for samples/responses.json.

Usage:
    python samples/build_samples.py           # write samples/responses.json
    python samples/build_samples.py --check   # exit 1 if committed file differs

The script computes every number from northstar/gen_data.py so responses are
always consistent with the fictional dataset.  No literal dollar amounts or
unit counts are hard-coded.
"""

import importlib.util
import json
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Helpers for loading the data module without hard-coding any path assumptions
# ---------------------------------------------------------------------------

def _load_gen_data():
    """Import northstar/gen_data.py and return its module object."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    northstar_dir = os.path.join(repo_root, "northstar")
    mod_path = os.path.join(northstar_dir, "gen_data.py")
    if not os.path.isfile(mod_path):
        sys.exit(
            f"Missing data module: {mod_path}.  Regenerate the dataset with "
            f"'python northstar/gen_data.py' and try again."
        )
    spec = importlib.util.spec_from_file_location("gen_data", mod_path)
    if spec is None or spec.loader is None:
        sys.exit(f"Could not load spec for {mod_path}")
    mod = importlib.util.module_from_spec(spec)
    # Inject the module into sys.modules so relative-like references work
    sys.modules["gen_data"] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Money & percentage formatting conforming to the finding spec
# ---------------------------------------------------------------------------

def _fmt_usd(value: float) -> str:
    """Nearest dollar with thousands separators, e.g. '$769,742'."""
    rounded = round(value)
    return f"${rounded:,}"


def _fmt_spoken_usd(value: float) -> str:
    """Spoken amount: 'about 770 thousand dollars' or 'about 1.63 million dollars'."""
    abs_val = round(value)
    if abs_val >= 1_000_000:
        mil = abs_val / 1_000_000
        return f"about {mil:.2f} million dollars"
    thousands = abs_val / 1_000
    if thousands == int(thousands):
        return f"about {int(thousands)} thousand dollars"
    return f"about {thousands:.0f} thousand dollars"


def _pct_change(old: float, new: float) -> str:
    """Return '+9.1%' or '-3.2%' for (new-old)/old * 100 to one decimal."""
    if old == 0:
        return "N/A"
    value = (new - old) / old * 100
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1f}%"


def _pct_share(part: float, whole: float) -> str:
    """part/whole * 100, rounded to nearest integer with '%'."""
    if whole == 0:
        return "0%"
    return f"{round(part / whole * 100)}%"


def _pct_spoken(value: float) -> str:
    """Return '11 percent' or '18.7 percent' for values like 10.8 or -18.7."""
    abs_pct = abs(value)
    if abs_pct == int(abs_pct):
        return f"{int(abs_pct)} percent"
    return f"{abs_pct:.1f} percent"


# ---------------------------------------------------------------------------
# Data munging helpers
# ---------------------------------------------------------------------------

def _quarter_revenue(sales: List[Dict[str, Any]], quarter: str) -> float:
    return round(sum(s["revenue_usd"] for s in sales if s["quarter"] == quarter), 2)


def _quarter_category_region(sales: List[Dict[str, Any]],
                             products: List[Dict[str, Any]],
                             quarter: str, category: str,
                             region: Optional[str] = None) -> Tuple[float, int]:
    """(revenue, units) for a category in a quarter, optionally filtered by region."""
    cat_ids = {p["product_id"] for p in products if p["category"] == category}
    rows = [
        s for s in sales
        if s["quarter"] == quarter and s["product_id"] in cat_ids
    ]
    if region is not None:
        rows = [s for s in rows if s["region"] == region]
    rev = round(sum(r["revenue_usd"] for r in rows), 2)
    units = sum(r["units_sold"] for r in rows)
    return rev, units


def _ytd_category_region(sales: List[Dict[str, Any]],
                         products: List[Dict[str, Any]],
                         ytd_quarters: List[str], category: str) -> List[Dict[str, Any]]:
    """Aggregate (region, revenue, units) for a category across ytd_quarters."""
    cat_ids = {p["product_id"] for p in products if p["category"] == category}
    agg: Dict[str, Tuple[float, int]] = defaultdict(lambda: (0.0, 0))
    for s in sales:
        if s["quarter"] in ytd_quarters and s["product_id"] in cat_ids:
            rev, units = agg[s["region"]]
            agg[s["region"]] = (rev + s["revenue_usd"], units + s["units_sold"])
    # Round once
    result = []
    for region, (rev, units) in agg.items():
        result.append({"region": region, "revenue_usd": round(rev, 2), "units": units})
    result.sort(key=lambda x: x["revenue_usd"], reverse=True)
    return result


def _channel_breakdown(sales: List[Dict[str, Any]],
                       products: List[Dict[str, Any]],
                       quarter: str, region: str, category: str) -> List[Dict[str, Any]]:
    """Per-channel revenue for a given quarter/region/category."""
    cat_ids = {p["product_id"] for p in products if p["category"] == category}
    rows = [
        s for s in sales
        if s["quarter"] == quarter and s["region"] == region
        and s["product_id"] in cat_ids
    ]
    ch_agg: Dict[str, float] = defaultdict(float)
    for r in rows:
        ch_agg[r["channel"]] += r["revenue_usd"]
    total = sum(ch_agg.values())
    result = []
    for ch, rev in ch_agg.items():
        result.append({"channel": ch, "revenue_usd": round(rev, 2),
                        "share": _pct_share(rev, total)})
    result.sort(key=lambda x: x["revenue_usd"], reverse=True)
    return result


def _total_revenue_quarter(sales: List[Dict[str, Any]], quarter: str) -> float:
    return round(sum(s["revenue_usd"] for s in sales if s["quarter"] == quarter), 2)


def _total_revenue_channel_quarter(sales: List[Dict[str, Any]],
                                    quarter: str, channel: str) -> float:
    return round(sum(s["revenue_usd"] for s in sales
                      if s["quarter"] == quarter and s["channel"] == channel), 2)


def _quarter_region_returns(sales: List[Dict[str, Any]], quarter: str,
                            region: str) -> int:
    return sum(s["units_returned"] for s in sales
               if s["quarter"] == quarter and s["region"] == region)


# ---------------------------------------------------------------------------
# Build the full responses list
# ---------------------------------------------------------------------------

def _build_responses(mod) -> List[Dict[str, Any]]:
    products: List[Dict[str, Any]] = mod.build_products()
    sales: List[Dict[str, Any]] = mod.build_sales(products)
    # Constants from gen_data
    REGIONS = ["Pacific", "Mountain", "Central", "Atlantic"]
    CHANNELS = ["Retail", "Online", "Wholesale"]
    quarters_order = ["Q1 2025", "Q2 2025", "Q3 2025", "Q4 2025",
                      "Q1 2026", "Q2 2026"]
    last_q = "Q2 2026"
    prior_q = "Q1 2026"
    ytd_quarters = ["Q1 2026", "Q2 2026"]
    # Also need Q4 2025 for item 1 and H1 2025 for item 5
    q4_2025 = "Q4 2025"
    q3_2025 = "Q3 2025"
    h1_2025_quarters = ["Q1 2025", "Q2 2025"]

    rev_q3_2025 = _quarter_revenue(sales, q3_2025)

    # ---- 1. Revenue last quarter ----
    rev_last = _quarter_revenue(sales, last_q)
    rev_prior = _quarter_revenue(sales, prior_q)
    rev_q4_2025 = _quarter_revenue(sales, q4_2025)
    change_vs_prior = _pct_change(rev_prior, rev_last)
    change_prior_vs_q4 = _pct_change(rev_q4_2025, rev_prior)
    change_q4_vs_q3 = _pct_change(rev_q3_2025, rev_q4_2025)

    # Spoken: "down about 11 percent" with computed whole-number percent
    rev_change_pct = (rev_last - rev_prior) / rev_prior * 100
    up_down = "up" if rev_last >= rev_prior else "down"
    spoken_rev = (
        f"Last quarter, Northstar Outdoor Co. booked "
        f"{_fmt_spoken_usd(rev_last)} in revenue. "
        f"That was {up_down} about {_pct_spoken(rev_change_pct)} from the prior quarter."
    )

    item1 = {
        "key": "ask_revenue_q2_2026",
        "kind": "ask",
        "question": "How much revenue did Northstar make last quarter?",
        "spoken": spoken_rev,
        "card": {
            "title": "Revenue — Q2 2026",
            "columns": ["Quarter", "Revenue (USD)", "Change vs prior"],
            "rows": [
                [last_q, _fmt_usd(rev_last), change_vs_prior],
                [prior_q, _fmt_usd(rev_prior), change_prior_vs_q4],
                [q4_2025, _fmt_usd(rev_q4_2025), change_q4_vs_q3],
            ],
            "chart_hint": "bar",
            "sources": ["Northstar fictional demo dataset"],
            "confidence": "high",
        },
        "answer_id": "sample-ans-0001",
        "session_id": "sample-session-001",
    }

    # ---- 2. Tents this year by region ----
    tent_ytd = _ytd_category_region(sales, products, ytd_quarters, "Tents")
    leader_ytd = tent_ytd[0]
    runner_up_ytd = tent_ytd[1]
    spoken_tent_ytd = (
        f"The {leader_ytd['region']} region leads tent sales this year with "
        f"{_fmt_spoken_usd(leader_ytd['revenue_usd'])}. "
        f"{runner_up_ytd['region']} is second at "
        f"{_fmt_spoken_usd(runner_up_ytd['revenue_usd'])}."
    )
    item2 = {
        "key": "ask_top_region_tents",
        "kind": "ask",
        "question": "Which region sold the most tents this year?",
        "spoken": spoken_tent_ytd,
        "card": {
            "title": "Tent Sales by Region — 2026 YTD",
            "columns": ["Region", "Tent Revenue (USD)", "Units"],
            "rows": [
                [r["region"], _fmt_usd(r["revenue_usd"]), str(r["units"])]
                for r in tent_ytd
            ],
            "chart_hint": "bar",
            "sources": ["Northstar fictional demo dataset"],
            "confidence": "high",
        },
        "answer_id": "sample-ans-0002",
        "session_id": "sample-session-002",
    }

    # ---- 3. And last quarter? (Q2 2026, following item 2 which was 2026 YTD) ----
    tent_last_q = _ytd_category_region(sales, products, [last_q], "Tents")
    leader_last = tent_last_q[0]
    # Compare regional order between YTD and last quarter
    ytd_order = [r["region"] for r in tent_ytd]
    last_q_order = [r["region"] for r in tent_last_q]
    if ytd_order == last_q_order:
        order_text = "the same"
    else:
        # Find which regions swapped positions
        diffs = []
        for i, (ytd_r, last_r) in enumerate(zip(ytd_order, last_q_order)):
            if ytd_r != last_r:
                diffs.append(f"{last_r} moved to position {i+1} from {ytd_order.index(last_r)+1}")
        if diffs:
            order_text = "different: " + "; ".join(diffs[:2])  # concise
        else:
            order_text = "different"
    spoken_last = (
        f"In {last_q}, {leader_last['region']} led tent sales "
        f"at {_fmt_spoken_usd(leader_last['revenue_usd'])}, ahead of "
        f"{tent_last_q[1]['region']}. "
        f"For the year so far, {leader_ytd['region']} still leads."
    )
    item3 = {
        "key": "followup_last_quarter",
        "kind": "follow-up",
        "question": "And last quarter?",
        "context": "Follows ask_top_region_tents in the same session.",
        "spoken": spoken_last,
        "card": {
            "title": f"Tent Sales by Region — {last_q}",
            "columns": ["Region", "Tent Revenue (USD)", "Units"],
            "rows": [
                [r["region"], _fmt_usd(r["revenue_usd"]), str(r["units"])]
                for r in tent_last_q
            ],
            "chart_hint": "bar",
            "sources": ["Northstar fictional demo dataset"],
            "confidence": "high",
        },
        "answer_id": "sample-ans-0003",
        "session_id": "sample-session-002",
        "parent_answer_id": "sample-ans-0002",
    }

    # ---- 4. Break down by channel for the leader of item 3 ----
    region_for_breakdown = leader_last["region"]
    channels = _channel_breakdown(sales, products, last_q,
                                  region_for_breakdown, "Tents")
    # Build spoken: "Wholesale made up 63 percent of Q2 2026 tent revenue..."
    share_texts = []
    for ch in channels:
        pct_int = round((ch["revenue_usd"] / sum(c["revenue_usd"] for c in channels)) * 100)
        share_texts.append(f"{ch['channel'].lower()} made up {pct_int} percent")
    spoken_breakdown = (
        f"In the {region_for_breakdown} region, {share_texts[0]} of "
        f"{last_q} tent revenue, {share_texts[1]} and {share_texts[2]}."
    )
    item4 = {
        "key": "breakdown_by_channel",
        "kind": "breakdown",
        "question": "Break that down by sales channel.",
        "context": "Follows followup_last_quarter in the same session.",
        "spoken": spoken_breakdown,
        "card": {
            "title": f"{region_for_breakdown} Tent Revenue by Channel — {last_q}",
            "columns": ["Channel", "Revenue (USD)", "Share"],
            "rows": [
                [ch["channel"], _fmt_usd(ch["revenue_usd"]), ch["share"]]
                for ch in channels
            ],
            "chart_hint": "bar",
            "sources": ["Northstar fictional demo dataset"],
            "confidence": "medium",
        },
        "answer_id": "sample-ans-0004",
        "session_id": "sample-session-002",
        "parent_answer_id": "sample-ans-0003",
    }

    # ---- 5. Explain what that number means ----
    # "that number" refers to answer_id sample-ans-0001 (Q2 revenue)
    biggest_channel_q2 = max(
        CHANNELS,
        key=lambda ch: _total_revenue_channel_quarter(sales, last_q, ch)
    )
    h1_2026_rev = sum(_quarter_revenue(sales, q) for q in ytd_quarters)
    h1_2025_rev = sum(_quarter_revenue(sales, q) for q in h1_2025_quarters)
    trend_up_down = "Up" if rev_last >= rev_prior else "Down"
    trend_pct = _pct_change(rev_prior, rev_last)
    # trend_pct is like '-10.8%'; strip sign and trailing zero
    trend_abs_pct = abs(round((rev_last - rev_prior) / rev_prior * 100, 1))
    year_change = (h1_2026_rev - h1_2025_rev) / h1_2025_rev * 100
    spoken_explain = (
        f"In {last_q}, revenue was down {_pct_spoken(trend_abs_pct)} versus "
        f"{prior_q}. The biggest channel was {biggest_channel_q2.lower()}. "
        f"For the first half of 2026, revenue was "
        f"{_fmt_spoken_usd(h1_2026_rev)} compared to "
        f"{_fmt_spoken_usd(h1_2025_rev)} in the first half of 2025 "
        f"(down {_pct_spoken(abs(year_change))})."
    )
    item5 = {
        "key": "explain_revenue_q2_2026",
        "kind": "explain",
        "question": "What does that number mean for the business?",
        "refers_to_answer_id": "sample-ans-0001",
        "spoken": spoken_explain,
        "card": {
            "title": "What Q2 2026 Revenue Means",
            "columns": ["Signal", "Reading"],
            "rows": [
                ["Quarter trend", f"{trend_up_down} {trend_pct[1:]} vs Q1 2026"],
                ["Biggest channel", biggest_channel_q2],
                ["Year pace",
                 f"H1 2026 {_fmt_usd(h1_2026_rev)} vs H1 2025 {_fmt_usd(h1_2025_rev)} ({_pct_change(h1_2025_rev, h1_2026_rev)})"],
            ],
            "chart_hint": "table",
            "sources": ["Northstar fictional demo dataset"],
            "confidence": "medium",
        },
        "answer_id": "sample-ans-0005",
        "session_id": "sample-session-001",
    }

    # ---- 6. Low-confidence Central returns ----
    cent_ret_q2 = _quarter_region_returns(sales, last_q, "Central")
    cent_ret_q1 = _quarter_region_returns(sales, prior_q, "Central")
    spoken_lowconf = (
        "I'm not confident in this one. Return counts in the Central region "
        "are low but the demo dataset doesn't carry margin detail, so this "
        "is directional only."
    )
    item6 = {
        "key": "low_confidence_returns",
        "kind": "low-confidence",
        "question": "Are returns hurting our margins in the Central region?",
        "spoken": spoken_lowconf,
        "card": {
            "title": "Central Region Returns — Directional",
            "columns": ["Quarter", "Units Returned", "Note"],
            "rows": [
                [last_q, str(cent_ret_q2), "Margins not in dataset"],
                [prior_q, str(cent_ret_q1), "Margins not in dataset"],
            ],
            "chart_hint": "table",
            "sources": ["Northstar fictional demo dataset"],
            "confidence": "low",
        },
        "answer_id": "sample-ans-0006",
        "session_id": "sample-session-003",
    }

    # ---- 7. Feedback-improved sleeping bags last quarter ----
    sb_last = _ytd_category_region(sales, products, [last_q], "Sleeping Bags")
    sb_leader = sb_last[0]
    sb_runner = sb_last[1]
    spoken_sb = (
        f"Improved from your feedback: the {sb_leader['region']} region led "
        f"sleeping-bag sales last quarter at "
        f"{_fmt_spoken_usd(sb_leader['revenue_usd'])}, ahead of the "
        f"{sb_runner['region']} region."
    )
    item7 = {
        "key": "feedback_corrected_region",
        "kind": "feedback-improved",
        "question": "Which region sold the most sleeping bags last quarter?",
        "spoken": spoken_sb,
        "card": {
            "title": f"Sleeping Bag Sales by Region — {last_q}",
            "columns": ["Region", "Revenue (USD)", "Units"],
            "rows": [
                [r["region"], _fmt_usd(r["revenue_usd"]), str(r["units"])]
                for r in sb_last
            ],
            "chart_hint": "bar",
            "sources": ["Northstar fictional demo dataset",
                        "User feedback applied"],
            "confidence": "high",
        },
        "answer_id": "sample-ans-0007",
        "original_answer_id": "sample-ans-0006",
        "session_id": "sample-session-004",
    }

    # ---- 8. Weekly business brief ----
    # Top region by total Q2 revenue
    region_revenues = {}
    for r in REGIONS:
        rev = sum(s["revenue_usd"] for s in sales
                  if s["quarter"] == last_q and s["region"] == r)
        region_revenues[r] = round(rev, 2)
    top_region_q2 = max(region_revenues, key=region_revenues.get)
    top_region_rev = region_revenues[top_region_q2]
    top_region_share = _pct_share(top_region_rev, rev_last)

    # Top channel by total Q2 revenue
    top_channel_q2 = biggest_channel_q2
    top_channel_prev_rev = _total_revenue_channel_quarter(sales, prior_q, top_channel_q2)
    top_channel_curr_rev = _total_revenue_channel_quarter(sales, last_q, top_channel_q2)
    top_channel_trend = "Growing" if top_channel_curr_rev >= top_channel_prev_rev else "Shrinking"

    qoq_change_pct = abs(round(rev_change_pct))
    spoken_brief = (
        f"Here's your weekly brief. Revenue is "
        f"{'up' if rev_last >= rev_prior else 'down'} "
        f"{_pct_spoken(qoq_change_pct)} "
        f"quarter over quarter, the {top_region_q2} region leads overall, and "
        f"{top_channel_q2.lower()} is the biggest channel "
        f"(it {'grew' if top_channel_trend == 'Growing' else 'shrank'} from {prior_q})."
    )
    item8 = {
        "key": "weekly_brief",
        "kind": "brief",
        "question": "Give me the weekly business brief.",
        "spoken": spoken_brief,
        "cards": [
            {
                "title": "Weekly Brief",
                "columns": ["Metric", "Value", "Trend"],
                "rows": [
                    ["Revenue", _fmt_usd(rev_last),
                     f"{'Up' if rev_last >= rev_prior else 'Down'} {qoq_change_pct}% QoQ"],
                    ["Top region", top_region_q2, top_region_share],
                    ["Top channel", top_channel_q2,
                     f"{top_channel_trend} vs Q1 2026"],
                ],
                "chart_hint": "table",
                "sources": ["Northstar fictional demo dataset"],
                "confidence": "high",
            },
        ],
        "answer_id": "sample-ans-0008",
        "session_id": "sample-session-005",
    }

    return [item1, item2, item3, item4, item5, item6, item7, item8]


# ---------------------------------------------------------------------------
# Top-level driver
# ---------------------------------------------------------------------------

RESPONSES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "samples", "responses.json",
)

TEMPLATE = {
    "mode": "SAMPLE_MODE",
    "version": "2026-10-02",
    "notice": (
        "Sample answer: illustrative responses in the style of Northstar Ask "
        "over a fictional retail dataset. In SAMPLE_MODE every spoken reply "
        "is prefixed 'Sample answer:' by the client so nothing recorded is "
        "presented as live. Figures are precomputed from the fictional dataset."
    ),
    "card_contract": (
        "Per issue #134: brief responses carry cards ONLY in the 'cards' array; "
        "single-answer responses (ask, follow-up, breakdown, explain, "
        "low-confidence, feedback-improved) carry ONE card in the singular "
        "'card' field. The two shapes never mix, so no card is ever rendered "
        "twice."
    ),
    "confidence_mapping": {
        "description": "Confidence values are mapped from internal scoring ranges",
        "high": "Score >= 0.8 - High certainty in the answer's accuracy",
        "medium": "Score >= 0.5 and < 0.8 - Moderate certainty, answer is directionally correct",
        "low": "Score < 0.5 - Low certainty, answer may be speculative or incomplete",
    },
    "supported_kinds": [
        "ask",
        "follow-up",
        "breakdown",
        "explain",
        "low-confidence",
        "feedback-improved",
        "brief",
    ],
}


def build():
    """Return the full responses.json-compatible dict."""
    mod = _load_gen_data()
    responses = _build_responses(mod)
    return {**TEMPLATE, "responses": responses}


def main():
    target = build()
    json_text = json.dumps(target, indent=2, ensure_ascii=False) + "\n"

    if "--check" in sys.argv:
        try:
            with open(RESPONSES_PATH, "r", encoding="utf-8") as fh:
                committed = fh.read()
        except FileNotFoundError:
            print("CHECK FAILED: samples/responses.json does not exist")
            sys.exit(1)
        if committed != json_text:
            print("CHECK FAILED: samples/responses.json differs from computed output")
            sys.exit(1)
        print("CHECK PASSED: samples/responses.json matches computed output")
        sys.exit(0)

    os.makedirs(os.path.dirname(RESPONSES_PATH), exist_ok=True)
    with open(RESPONSES_PATH, "w", encoding="utf-8") as fh:
        fh.write(json_text)
    print(f"Wrote {RESPONSES_PATH}")


if __name__ == "__main__":
    main()
