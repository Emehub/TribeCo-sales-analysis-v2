"""
Extract every core TribeCo table, scoped to Ghana only, into a single Excel
workbook with one tab per table -- so Ghana data doesn't have to be picked out
of tables that mix it with Kenya every time.

Run: python3 scripts/export_ghana_data_workbook.py
Output: exports/TribeCo_Ghana_Data_<date>.xlsx
"""
import os
import pandas as pd
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
today = datetime.now().strftime("%Y-%m-%d")
OUT = os.path.join(BASE, "exports", f"TribeCo_Ghana_Data_{today}.xlsx")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

def load(name):
    return pd.read_csv(f"{DATA}/{name}.csv")

# ── Load raw tables (still mixed GH/KE at this point) ──────────────────────────
payment   = load("payment")
invoice   = load("invoice")
repayment = load("repayment")
rc        = load("retail_centre")
product   = load("product")
il        = load("invoice_line")
ir        = load("inventory_request")
ibv       = load("inventory_balances_view")
camp      = load("preorder_campaign")
irf       = load("inventory_request_fulfillment")

# ── Ghana scoping -- same logic the dashboard itself uses ──────────────────────
invoice_gh = invoice[invoice["Country Code"] == "GH"].copy()
repayment_gh = repayment[repayment["Country Code"] == "GH"].copy()
rc_gh = rc[rc["Country Code"] == "GH"].copy()
ir_gh = ir[ir["Country Code"] == "GH"].copy()

gh_invoice_ids = set(invoice_gh["ID"].dropna())
gh_rc_ids = set(rc_gh["ID"].dropna())
gh_request_ids = set(ir_gh["ID"].dropna())

invoice_line_gh = il[il["Invoice ID"].isin(gh_invoice_ids)].copy()
inventory_balances_gh = ibv[ibv["Retail Centre ID"].isin(gh_rc_ids)].copy()
fulfillment_gh = irf[irf["Request ID"].isin(gh_request_ids)].copy()

# Flag which rows actually feed the dashboard's own KPIs (a narrower slice than "all
# Ghana" -- excludes cancelled invoices, non-standard order types, and BufferPesa).
invoice_gh["Included in Dashboard KPIs"] = (
    (invoice_gh["Order Type"] == 1) &
    (invoice_gh["Channel"] != "BufferPesa") &
    (invoice_gh["Status"] != 5))
qualifying_ids = set(invoice_gh[invoice_gh["Included in Dashboard KPIs"]]["ID"])
repayment_gh["Included in Dashboard KPIs"] = repayment_gh["Invoice ID"].isin(qualifying_ids)
invoice_line_gh["Included in Dashboard KPIs"] = invoice_line_gh["Invoice ID"].isin(qualifying_ids)

# Product catalogue has no reliable per-market field (its "Country" column is a
# mix of manufacturing origin and market codes, e.g. "CN", "GH,KE", "Ghana").
# Scope it instead to products that have actually been sold to a Ghana invoice --
# a meaningful, reliable definition of "Ghana-relevant" for this catalogue.
gh_sold_product_ids = set(invoice_line_gh["Product ID"].dropna())
product_gh = product[product["ID"].isin(gh_sold_product_ids)].copy()

# payment.csv and preorder_campaign.csv have no country field and no reliable
# link back to a Ghana-scoped table -- included in full, flagged in the README tab.
payment_all = payment.copy()
campaign_all = camp.copy()

# ── README / notes sheet ────────────────────────────────────────────────────────
readme_rows = [
    ("Generated", datetime.now().strftime("%d %b %Y %H:%M")),
    ("", ""),
    ("Sheet", "Ghana scoping applied"),
    ("Invoice", f"Country Code = GH  ({len(invoice_gh)} of {len(invoice)} rows). "
                f"'Included in Dashboard KPIs' column flags the narrower "
                f"{invoice_gh['Included in Dashboard KPIs'].sum()}-row slice the dashboard itself reports "
                f"on (excludes cancelled invoices, non-standard order types, and BufferPesa-channel orders)."),
    ("Repayment", f"Country Code = GH  ({len(repayment_gh)} of {len(repayment)} rows). Same 'Included in "
                  f"Dashboard KPIs' flag, based on whether its invoice qualifies."),
    ("Retail Centre", f"Country Code = GH  ({len(rc_gh)} of {len(rc)} rows)"),
    ("Invoice Line", f"Invoice ID belongs to a GH invoice  ({len(invoice_line_gh)} of {len(il)} rows). "
                     f"Same 'Included in Dashboard KPIs' flag."),
    ("Inventory Request", f"Country Code = GH  ({len(ir_gh)} of {len(ir)} rows)"),
    ("Inventory Balances", f"Retail Centre ID belongs to a GH retail centre  ({len(inventory_balances_gh)} of {len(ibv)} rows)"),
    ("Inventory Fulfillment", f"Request ID belongs to a GH inventory request  ({len(fulfillment_gh)} of {len(irf)} rows)"),
    ("Product", f"Product ID has actually sold on a GH invoice  ({len(product_gh)} of {len(product)} rows). "
                f"NOTE: the catalogue's own 'Country' field mixes manufacturing origin (e.g. CN, NL) with "
                f"market codes and isn't reliable for Ghana/Kenya scoping, so this sheet is scoped by actual "
                f"Ghana sales instead."),
    ("Payment", f"NOT scoped -- no country field and no reliable link to Ghana records. Included in full "
                f"({len(payment_all)} rows). Treat as a mixed GH/KE table."),
    ("Preorder Campaign", f"NOT scoped -- no country field and only {len(campaign_all)} rows total. "
                          f"Included in full."),
]
readme_df = pd.DataFrame(readme_rows, columns=["Item", "Detail"])

# ── Write workbook ───────────────────────────────────────────────────────────────
with pd.ExcelWriter(OUT, engine="openpyxl") as writer:
    readme_df.to_excel(writer, sheet_name="README", index=False)
    invoice_gh.to_excel(writer, sheet_name="Invoice", index=False)
    repayment_gh.to_excel(writer, sheet_name="Repayment", index=False)
    rc_gh.to_excel(writer, sheet_name="Retail Centre", index=False)
    invoice_line_gh.to_excel(writer, sheet_name="Invoice Line", index=False)
    ir_gh.to_excel(writer, sheet_name="Inventory Request", index=False)
    inventory_balances_gh.to_excel(writer, sheet_name="Inventory Balances", index=False)
    fulfillment_gh.to_excel(writer, sheet_name="Inventory Fulfillment", index=False)
    product_gh.to_excel(writer, sheet_name="Product", index=False)
    payment_all.to_excel(writer, sheet_name="Payment (unfiltered)", index=False)
    campaign_all.to_excel(writer, sheet_name="Preorder Campaign (unfiltered)", index=False)

    # Widen README columns and freeze header row on every sheet
    for name in writer.sheets:
        ws = writer.sheets[name]
        ws.freeze_panes = "A2"
    writer.sheets["README"].column_dimensions["A"].width = 24
    writer.sheets["README"].column_dimensions["B"].width = 100

print(f"Workbook saved: {OUT}")
print(f"Sheets: README, Invoice ({len(invoice_gh)}), Repayment ({len(repayment_gh)}), "
      f"Retail Centre ({len(rc_gh)}), Invoice Line ({len(invoice_line_gh)}), "
      f"Inventory Request ({len(ir_gh)}), Inventory Balances ({len(inventory_balances_gh)}), "
      f"Inventory Fulfillment ({len(fulfillment_gh)}), Product ({len(product_gh)}), "
      f"Payment unfiltered ({len(payment_all)}), Preorder Campaign unfiltered ({len(campaign_all)})")
