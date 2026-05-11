"""Regenerate all test fixtures. Run: python tests/fixtures/_generate.py"""
from pathlib import Path
import polars as pl
import datetime as dt
import random

OUT = Path(__file__).parent

def make_clean_xlsx():
    rows = []
    regions = ["North", "South", "East", "West"]
    products = ["Alpha", "Beta", "Gamma"]
    start = dt.date(2026, 7, 1)
    random.seed(42)
    for i in range(200):
        d = start + dt.timedelta(days=i % 90)
        rows.append({
            "Date": d,
            "Region": regions[i % 4],
            "Product": products[i % 3],
            "Revenue": round(random.uniform(1000, 50000), 2),
            "Cost": round(random.uniform(500, 30000), 2),
            "Units": random.randint(1, 500),
        })
    df = pl.DataFrame(rows)
    df.write_excel(OUT / "sample_clean.xlsx")

def make_messy_xlsx():
    # 40% nulls in Cost — triggers viability exclusion
    rows = []
    random.seed(7)
    for i in range(100):
        rows.append({
            "Region": ["North", "South"][i % 2],
            "Revenue": round(random.uniform(1000, 50000), 2),
            "Cost": None if random.random() < 0.4 else round(random.uniform(500, 30000), 2),
        })
    df = pl.DataFrame(rows)
    df.write_excel(OUT / "sample_messy.xlsx")

def make_csv():
    rows = []
    random.seed(3)
    for i in range(50):
        rows.append({
            "Question": f"Q{i % 5 + 1}",
            "Score": random.randint(1, 5),
        })
    df = pl.DataFrame(rows)
    df.write_csv(OUT / "sample.csv")

def make_pii_csv():
    rows = []
    for i in range(20):
        rows.append({
            "Customer_Name": f"Person {i}",
            "SSN": f"{100+i:03d}-{20+i:02d}-{1000+i:04d}",
            "Email": f"user{i}@example.com",
            "Revenue": 1000 * (i + 1),
        })
    df = pl.DataFrame(rows)
    df.write_csv(OUT / "sample_pii.csv")

def make_large_csv():
    rows = [{"id": i, "value": i * 2.5} for i in range(100_000)]
    df = pl.DataFrame(rows)
    df.write_csv(OUT / "large.csv")

def make_pdf():
    # Use pymupdf to create a minimal PDF with one table.
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    text = "Quarterly Report\n\nRegion | Revenue | Cost\nNorth  | 1000    | 500\nSouth  | 2000    | 1500\nEast   | 1500    | 800\n"
    page.insert_text((50, 100), text, fontsize=11)
    doc.save(OUT / "sample.pdf")
    doc.close()

if __name__ == "__main__":
    make_clean_xlsx()
    make_messy_xlsx()
    make_csv()
    make_pii_csv()
    make_large_csv()
    make_pdf()
    print("fixtures regenerated")
