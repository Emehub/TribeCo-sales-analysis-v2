"""
Build a detailed Excel workbook comparing invoice records between
Metabase (tribecodb) and the Sales Ledger for 2026.

Run:  python scripts/build_invoice_tracker.py
Out:  exports/Invoice_Tracker_2026.xlsx
"""
import pandas as pd
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import warnings
import os

warnings.filterwarnings("ignore")

DATA   = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
LEDGER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "Sales ledger data", "Sales Ledger 2026 (1).xlsx")
OUT    = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "exports", "Invoice_Tracker_2026.xlsx")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

# ── Load Metabase invoices ────────────────────────────────────────────────────
inv_raw = pd.read_csv(f"{DATA}/invoice.csv", parse_dates=["Created At", "Due Date"])
inv_raw.columns = [c.replace(" → ", "_") for c in inv_raw.columns]
inv_s = inv_raw[
    (inv_raw["Country Code"] == "GH") &
    (inv_raw["Order Type"] == 1) &
    (inv_raw["Channel"] != "BufferPesa")
].copy()

inv_s["dv"]          = pd.to_numeric(inv_s["Discountedvalue"],   errors="coerce").fillna(0)
inv_s["tov"]         = pd.to_numeric(inv_s["Total Order Value"], errors="coerce").fillna(0)
inv_s["Revenue"]     = inv_s["dv"].where(inv_s["dv"] > 0, inv_s["tov"])
inv_s["Totalrepaid"] = pd.to_numeric(inv_s["Totalrepaid"], errors="coerce").fillna(0)
inv_s["Outstanding"] = (inv_s["Revenue"] - inv_s["Totalrepaid"]).clip(lower=0)
mb_2026 = inv_s[inv_s["Created At"].dt.year == 2026].copy()
mb_2026["Month"]        = mb_2026["Created At"].dt.to_period("M").astype(str)
mb_2026["Invoice Date"] = mb_2026["Created At"].dt.date

# ── Load Sales Ledger invoices ────────────────────────────────────────────────
xl     = pd.ExcelFile(LEDGER)
sl_inv = pd.read_excel(xl, "B-Invoices", parse_dates=["Invoice Date", "Due Date"])
sl_inv.columns = [c.strip() for c in sl_inv.columns]
sl_2026 = sl_inv[sl_inv["Invoice Date"].dt.year == 2026].copy()
sl_2026["Month"]             = sl_2026["Invoice Date"].dt.to_period("M").astype(str)
sl_2026["Invoice Date Clean"] = sl_2026["Invoice Date"].dt.date

mb_ids = set(mb_2026["ID"].dropna().astype(int))
sl_ids = set(sl_2026["Invoice Number"].dropna().astype(int))

# ── Sheet 1: Master Tracker ───────────────────────────────────────────────────
tracker = sl_2026[[
    "Invoice Number", "Invoice Date Clean", "Month", "Customer Name",
    "Warehouse Name", "Total", "Payment", "Balance",
    "Payment Terms", "Payment Mode", "Sales Person"
]].copy()
tracker.columns = [
    "Invoice ID", "Invoice Date", "Month", "Customer Name",
    "Warehouse", "Total (GHS)", "Collected (GHS)", "Balance (GHS)",
    "Payment Terms", "Payment Mode", "Sales Person"
]
tracker["In Metabase?"] = tracker["Invoice ID"].apply(
    lambda x: "YES" if int(x) in mb_ids else "MISSING"
)
tracker["Notes"] = tracker["In Metabase?"].apply(
    lambda x: "" if x == "YES" else "Not found in tribecodb — needs to be entered"
)
tracker = tracker.sort_values(["Month", "Invoice ID"]).reset_index(drop=True)

# ── Sheet 2: Missing invoices ─────────────────────────────────────────────────
missing = tracker[tracker["In Metabase?"] == "MISSING"][[
    "Invoice ID", "Invoice Date", "Month", "Customer Name",
    "Warehouse", "Total (GHS)", "Collected (GHS)", "Balance (GHS)",
    "Payment Terms", "Payment Mode", "Sales Person"
]].copy().reset_index(drop=True)
missing.index = missing.index + 1

# ── Sheet 3: Metabase invoices ────────────────────────────────────────────────
mb_sheet = mb_2026[[
    "ID", "Invoice Date", "Month", "Customer City",
    "Revenue", "Totalrepaid", "Outstanding", "Repayment Status"
]].copy()
mb_sheet.columns = [
    "Invoice ID", "Invoice Date", "Month", "Customer City",
    "Revenue (GHS)", "Collected (GHS)", "Outstanding (GHS)", "Repayment Status"
]
mb_sheet["In Sales Ledger?"] = mb_sheet["Invoice ID"].apply(
    lambda x: "YES" if int(x) in sl_ids else "NOT IN LEDGER"
)
mb_sheet = mb_sheet.sort_values(["Month", "Invoice ID"]).reset_index(drop=True)

# ── Sheet 4: Monthly Summary ──────────────────────────────────────────────────
months = sorted(set(sl_2026["Month"]) | set(mb_2026["Month"]))
rows = []
for m in months:
    sl_m    = sl_2026[sl_2026["Month"] == m]
    mb_m    = mb_2026[mb_2026["Month"] == m]
    miss_m  = sl_m[~sl_m["Invoice Number"].isin(mb_ids)]
    rows.append({
        "Month":                m,
        "SL Invoice Count":     len(sl_m),
        "MB Invoice Count":     len(mb_m),
        "Missing from MB":      len(miss_m),
        "SL Revenue (GHS)":     round(sl_m["Total"].sum(), 2),
        "MB Revenue (GHS)":     round(mb_m["Revenue"].sum(), 2),
        "Revenue Gap (GHS)":    round(mb_m["Revenue"].sum() - sl_m["Total"].sum(), 2),
        "Missing Value (GHS)":  round(miss_m["Total"].sum(), 2),
    })
summary = pd.DataFrame(rows)

# ── Write Excel ───────────────────────────────────────────────────────────────
with pd.ExcelWriter(OUT, engine="openpyxl") as writer:
    tracker.to_excel(writer,  sheet_name="Master Tracker",    index=False)
    missing.to_excel(writer,  sheet_name="Missing Invoices",  index=True)
    mb_sheet.to_excel(writer, sheet_name="Metabase Invoices", index=False)
    summary.to_excel(writer,  sheet_name="Monthly Summary",   index=False)

# ── Style ─────────────────────────────────────────────────────────────────────
wb = openpyxl.load_workbook(OUT)

HDR_FILL   = PatternFill("solid", fgColor="14532D")
HDR_FONT   = Font(bold=True, color="FFFFFF", size=10)
MATCH_FILL = PatternFill("solid", fgColor="DCFCE7")
MISS_FILL  = PatternFill("solid", fgColor="FEE2E2")
AMBER_FILL = PatternFill("solid", fgColor="FEF3C7")
MISS_FONT  = Font(color="991B1B", bold=True, size=10)
MATCH_FONT = Font(color="166534", bold=True, size=10)
AMBER_FONT = Font(color="92400E", bold=True, size=10)
THIN = Border(
    left=Side(style="thin",   color="D1D5DB"),
    right=Side(style="thin",  color="D1D5DB"),
    top=Side(style="thin",    color="D1D5DB"),
    bottom=Side(style="thin", color="D1D5DB"),
)

def style_header(ws, col_widths):
    for cell in ws[1]:
        cell.fill      = HDR_FILL
        cell.font      = HDR_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border    = THIN
    ws.row_dimensions[1].height = 32
    for i, width in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.border    = THIN
            cell.alignment = Alignment(vertical="center")
    ws.freeze_panes = "A2"

# Master Tracker
ws = wb["Master Tracker"]
style_header(ws, [14, 14, 10, 28, 20, 16, 16, 16, 14, 18, 18, 14, 38])
for row in ws.iter_rows(min_row=2):
    status = row[11].value  # col 12 = "In Metabase?"
    if status == "MISSING":
        for cell in row:
            cell.fill = MISS_FILL
        row[11].font = MISS_FONT
    else:
        row[11].fill = MATCH_FILL
        row[11].font = MATCH_FONT

# Missing Invoices
ws2 = wb["Missing Invoices"]
style_header(ws2, [6, 14, 14, 10, 28, 20, 16, 16, 16, 14, 18, 18])
for row in ws2.iter_rows(min_row=2):
    for cell in row:
        cell.fill = MISS_FILL

# Metabase Invoices
ws3 = wb["Metabase Invoices"]
style_header(ws3, [14, 14, 10, 22, 18, 18, 18, 20, 18])
for row in ws3.iter_rows(min_row=2):
    status = row[8].value  # col 9 = "In Sales Ledger?"
    if status == "NOT IN LEDGER":
        row[8].fill = AMBER_FILL
        row[8].font = AMBER_FONT
    else:
        row[8].fill = MATCH_FILL
        row[8].font = MATCH_FONT

# Monthly Summary
ws4 = wb["Monthly Summary"]
style_header(ws4, [12, 16, 16, 18, 20, 20, 20, 22])
for row in ws4.iter_rows(min_row=2):
    missing_count = row[3].value
    if missing_count and missing_count > 0:
        for cell in row:
            cell.fill = MISS_FILL
    else:
        for cell in row:
            cell.fill = MATCH_FILL
    for cell in row[3:]:
        if isinstance(cell.value, (int, float)):
            cell.number_format = "#,##0"

wb.save(OUT)
print(f"Saved: {OUT}")
print(f"  Sheet 1 — Master Tracker:    {len(tracker)} rows")
print(f"  Sheet 2 — Missing Invoices:  {len(missing)} rows")
print(f"  Sheet 3 — Metabase Invoices: {len(mb_sheet)} rows")
print(f"  Sheet 4 — Monthly Summary:   {len(summary)} rows")
