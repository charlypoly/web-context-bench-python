"""Generate pages/fixtures/table/index.html: a long, deterministic data table.

Uses a fixed-seed linear congruential generator (no library RNG whose
algorithm could change between Python versions), so the output is
byte-identical on every run. The generated file is committed.
"""

from __future__ import annotations

from html import escape

from wpbench import PAGES_DIR

ROWS = 500

CUSTOMERS = [
    "Avery Chen", "Bruno Silva", "Chloe Martin", "Dmitri Volkov", "Elena Garcia", "Farah Haddad",
    "George Okafor", "Hiro Tanaka", "Isla McKenzie", "Jonas Berg", "Kavya Rao", "Lucas Moreau",
    "Maya Cohen", "Nikolai Petrov", "Olivia Brown", "Pedro Santos", "Qi Wang", "Rosa Delgado",
    "Samir Khan", "Tess Walker", "Umar Farouk", "Valentina Ricci", "Wei Zhang", "Ximena Ortiz",
    "Yusuf Demir", "Zoe Fischer",
]
REGIONS = ["North", "South", "East", "West", "Central"]
PRODUCTS = [
    ("Desk Lamp", 34.00), ("Ergonomic Chair", 289.00), ("Monitor Arm", 79.50), ("USB-C Dock", 149.99),
    ("Standing Desk", 549.00), ("Keyboard", 99.00), ("Webcam", 69.95), ("Noise-cancelling Headset", 199.00),
    ("Cable Tray", 24.50), ("Footrest", 42.00),
]
STATUSES = ["Delivered", "Delivered", "Delivered", "Shipped", "Processing", "Cancelled", "Returned"]


class LCG:
    def __init__(self, seed: int):
        self.state = seed

    def next(self, n: int) -> int:
        self.state = (1103515245 * self.state + 12345) % (2**31)
        return self.state % n


def money(x: float) -> str:
    return f"${x:,.2f}"


def main() -> None:
    rng = LCG(20260401)
    rows = []
    grand_total = 0.0
    for i in range(ROWS):
        order_id = f"ORD-{20001 + i}"
        month = 1 + (i * 9) // ROWS
        day = 1 + rng.next(28)
        date = f"2026-{month:02d}-{day:02d}"
        customer = CUSTOMERS[rng.next(len(CUSTOMERS))]
        region = REGIONS[rng.next(len(REGIONS))]
        product, price = PRODUCTS[rng.next(len(PRODUCTS))]
        qty = 1 + rng.next(9)
        status = STATUSES[rng.next(len(STATUSES))]
        total = round(price * qty, 2)
        grand_total += total
        rows.append((order_id, date, customer, region, product, qty, price, total, status))

    body = "\n".join(
        f'<tr><td>{o}</td><td>{d}</td><td>{escape(c)}</td><td>{r}</td><td>{escape(p)}</td>'
        f'<td class="num">{q}</td><td class="num">{money(pr)}</td><td class="num">{money(t)}</td><td>{s}</td></tr>'
        for o, d, c, r, p, q, pr, t, s in rows
    )
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Orders export &mdash; Halcyon Office Supply</title>
<style>
  body {{ margin: 0; font-family: Arial, sans-serif; color: #1f2933; }}
  header {{ padding: 16px 28px; background: #102a43; color: #fff; display: flex; justify-content: space-between; align-items: center; }}
  header a {{ color: #d9e2ec; margin-left: 16px; }}
  main {{ padding: 16px 28px; }}
  .toolbar {{ display: flex; gap: 12px; align-items: center; margin-bottom: 12px; font-size: 14px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th, td {{ border: 1px solid #d9e2ec; padding: 5px 8px; text-align: left; }}
  thead th {{ background: #f0f4f8; position: sticky; top: 0; }}
  th button {{ background: none; border: 0; font: inherit; font-weight: bold; cursor: pointer; padding: 0; }}
  td.num {{ text-align: right; }}
  tfoot td {{ font-weight: bold; background: #f0f4f8; }}
  .pager {{ display: flex; gap: 10px; align-items: center; margin: 14px 0 40px; font-size: 14px; }}
</style>
</head>
<body>
<header><strong>Halcyon Office Supply &mdash; Admin</strong><nav aria-label="Admin"><a href="#">Dashboard</a><a href="#">Orders</a><a href="#">Inventory</a><a href="#">Sign out</a></nav></header>
<main>
  <h1>Orders, January&ndash;September 2026</h1>
  <div class="toolbar">
    <label for="filter">Filter orders</label>
    <input id="filter" type="search" placeholder="Customer, product or order ID">
    <label for="status">Status</label>
    <select id="status"><option selected>All statuses</option><option>Delivered</option><option>Shipped</option><option>Processing</option><option>Cancelled</option><option>Returned</option></select>
    <button type="button">Download CSV</button>
    <span>{ROWS} orders</span>
  </div>
  <table id="orders">
    <caption style="text-align:left;padding:6px 0">All orders, sorted by order ID (ascending)</caption>
    <thead><tr>
      <th scope="col"><button type="button">Order ID</button></th><th scope="col"><button type="button">Date</button></th>
      <th scope="col"><button type="button">Customer</button></th><th scope="col"><button type="button">Region</button></th>
      <th scope="col"><button type="button">Product</button></th><th scope="col"><button type="button">Qty</button></th>
      <th scope="col"><button type="button">Unit price</button></th><th scope="col"><button type="button">Total</button></th>
      <th scope="col"><button type="button">Status</button></th>
    </tr></thead>
    <tbody>
{body}
    </tbody>
    <tfoot><tr><td colspan="7">Grand total</td><td class="num">{money(grand_total)}</td><td></td></tr></tfoot>
  </table>
  <div class="pager">
    <button type="button" disabled>Previous page</button>
    <span>Page 1 of 1</span>
    <button type="button" disabled>Next page</button>
    <a href="#">Back to top</a>
  </div>
</main>
</body>
</html>
"""
    out = PAGES_DIR / "fixtures" / "table" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    print(f"wrote {out} ({ROWS} rows, grand total {money(grand_total)})")


if __name__ == "__main__":
    main()
