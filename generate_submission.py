#!/usr/bin/env python3
"""
generate_submission.py — Generates the 30 canonical test messages for submission.jsonl

Reads test_pairs.json from the expanded dataset, runs compose() on each pair,
and writes out submission.jsonl adhering to the exact challenge brief schema.
"""

import sys
from pathlib import Path
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import json
import glob
from composer import compose

def main():
    root_dir = Path(__file__).resolve().parent
    expanded_dir = root_dir / "dataset" / "expanded"
    if not expanded_dir.exists():
        expanded_dir = root_dir / "dataset"
        
    test_pairs_path = expanded_dir / "test_pairs.json"
    if not test_pairs_path.exists():
        print(f"Error: Could not find {test_pairs_path}")
        sys.exit(1)
        
    with open(test_pairs_path, "r", encoding="utf-8") as f:
        pairs = json.load(f)["pairs"]
        
    # Load all categories
    categories = {}
    for f in (expanded_dir / "categories").glob("*.json"):
        with open(f, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            categories[data.get("slug", f.stem)] = data
            
    print(f"Loaded {len(categories)} categories. Composing {len(pairs)} test messages...")
    
    submission_path = root_dir / "submission.jsonl"
    with open(submission_path, "w", encoding="utf-8") as out_fp:
        for p in pairs:
            test_id = p["test_id"]
            tid = p["trigger_id"]
            mid = p["merchant_id"]
            cid = p.get("customer_id")
            
            with open(expanded_dir / "triggers" / f"{tid}.json", "r", encoding="utf-8") as fp:
                trigger = json.load(fp)
            with open(expanded_dir / "merchants" / f"{mid}.json", "r", encoding="utf-8") as fp:
                merchant = json.load(fp)
            category = categories.get(merchant.get("category_slug"), {"slug": merchant.get("category_slug")})
            
            customer = None
            if cid:
                with open(expanded_dir / "customers" / f"{cid}.json", "r", encoding="utf-8") as fp:
                    customer = json.load(fp)
                    
            composed = compose(category, merchant, trigger, customer)
            
            entry = {
                "test_id": test_id,
                "body": composed.get("body", ""),
                "cta": composed.get("cta", "binary"),
                "send_as": composed.get("send_as", "vera"),
                "suppression_key": composed.get("suppression_key", f"{tid}:{mid}"),
                "rationale": composed.get("rationale", "")
            }
            out_fp.write(json.dumps(entry, ensure_ascii=False) + "\n")
            print(f"  [{test_id}] Composed for {mid} ({trigger.get('kind')})")

    print(f"\nDone! Successfully wrote {len(pairs)} lines to {submission_path}")

if __name__ == "__main__":
    main()
