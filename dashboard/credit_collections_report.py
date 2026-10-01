"""
Sales Credit & Collections Performance workbook, built from Metabase data.

Mirrors the layout of the hand-built "06_Sales_Credit_and_Collections_Performance" workbook
(styling comes from templates/credit_collections_template.xlsx). The three data sheets
(Invoice Aging, Receipt Detail, Customer Credit Matrix) are filled from the dashboard's
scoped invoice / repayment data; every summary figure stays a live Excel formula over them,
so the downloaded file can be audited and re-worked like the original.

prepare_data() also mirrors those formulas in pandas, so the dashboard page can preview the
same numbers the workbook will show.
"""
import io
import os
import re
from copy import copy

import numpy as np
import openpyxl
import pandas as pd
from openpyxl.formatting.rule import Rule

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates",
                        "credit_collections_template.xlsx")

AGING_ORDER = ["Current / not due", "1-30 days", "31-60 days", "61-90 days", "90+ days"]
STATUS_ORDER = ["Paid", "Partially paid", "Unpaid"]


# ══════════════════════════════════════════════════════════════════════════════════
# DATA
# ══════════════════════════════════════════════════════════════════════════════════
def _to_naive_date(s):
    return pd.to_datetime(s, errors="coerce", utc=True).dt.tz_convert(None).dt.normalize()


def period_label(start, end):
    if start.year == end.year:
        return f"{start:%b}-{end:%b %Y}" if start.month != end.month else f"{start:%b %Y}"
    return f"{start:%b %Y}-{end:%b %Y}"


def prepare_data(inv_scoped, rep_scoped, rc, ir, start, end, cutoff, terms_days):
    """Build the invoice / receipt / customer tables for [start, end] invoices, with
    collections counted up to `cutoff` (all dates are tz-naive, day precision)."""
    start, end, cutoff = (pd.Timestamp(d).normalize() for d in (start, end, cutoff))

    inv = inv_scoped.copy()
    inv["Invoice Date"] = _to_naive_date(inv["Created At"])
    inv = inv[(inv["Invoice Date"] >= start) & (inv["Invoice Date"] <= end)].copy()
    inv["Invoice Number"] = inv["ID"].astype("int64").astype(str)

    names = rc.set_index("ID")
    inv["Customer Name"] = inv["Customer ID"].map(names["Name"]).fillna("Unknown customer")
    inv["Sales Person"]  = (inv["Customer ID"].map(names["Account Manager"])
                            if "Account Manager" in names.columns else "")
    inv["Region"] = inv.get("Customer City", pd.Series("", index=inv.index)).fillna("")
    if "Warehouse Name" in ir.columns and "Order ID" in inv.columns:
        inv["Warehouse"] = inv["Order ID"].map(ir.drop_duplicates("ID").set_index("ID")["Warehouse Name"])
    else:
        inv["Warehouse"] = ""
    terms = pd.to_numeric(inv.get("Customerpaymentterms"), errors="coerce").fillna(0)
    inv["Payment Terms"] = np.where(terms > 0, "Credit", "Cash")
    inv["Invoice Total"] = pd.to_numeric(inv["Discountedvalue"], errors="coerce").fillna(0)
    inv["Source Payment"] = pd.to_numeric(inv.get("Totalrepaid"), errors="coerce").fillna(0)
    inv["Source Balance"] = inv["Invoice Total"] - inv["Source Payment"]

    # Receipts: confirmed repayments on these invoices, dated by the recorded repayment
    # date (when the money actually arrived), not the system entry timestamp.
    rep = rep_scoped[rep_scoped["Invoice ID"].isin(inv["ID"])].copy()
    # Mistyped years exist in the source (e.g. "0002-07-28") -- treat anything before 2020 as
    # missing and fall back to the system entry date.
    _rd = _to_naive_date(rep["Repayment Date"])
    rep["Payment Date"] = _rd.where(_rd >= pd.Timestamp("2020-01-01")).fillna(_to_naive_date(rep["Created At"]))
    rep = rep[rep["Payment Date"] <= cutoff].copy()
    rep["Invoice Number"] = rep["Invoice ID"].astype("int64").astype(str)
    ref = rep.get("Reference Transaction ID", pd.Series(index=rep.index, dtype=object))
    rep["Payment Number"] = ref.where(ref.notna() & (ref.astype(str).str.strip() != ""), rep["ID"]).astype(str)
    rep["Amount Received"] = pd.to_numeric(rep["Amount"], errors="coerce").fillna(0)
    rep["Mode of Payment"] = rep.get("Payment Method", pd.Series("", index=rep.index)).fillna("")
    rep = rep.merge(inv[["Invoice Number", "Invoice Date", "Customer Name", "Payment Terms", "Invoice Total"]],
                    on="Invoice Number", how="left")
    rep["Payment Lag"] = (rep["Payment Date"] - rep["Invoice Date"]).dt.days
    rep = rep.sort_values(["Payment Date", "Invoice Number"]).reset_index(drop=True)

    # Invoice-level aging -- same logic as the workbook's formulas.
    by_inv = rep.groupby("Invoice Number")
    inv["Receipt Count"] = inv["Invoice Number"].map(by_inv.size()).fillna(0).astype(int)
    inv["Collected"]     = inv["Invoice Number"].map(by_inv["Amount Received"].sum()).fillna(0)
    inv["Payment Mode"]  = inv["Invoice Number"].map(
        by_inv["Mode of Payment"].agg(lambda s: " / ".join(sorted(set(x for x in s if x))))).fillna("")
    inv["Due Date"]   = inv["Invoice Date"] + pd.Timedelta(days=terms_days)
    inv["Net Balance"] = inv["Invoice Total"] - inv["Collected"]
    inv["Gross Outstanding"] = inv["Net Balance"].clip(lower=0)
    inv["Overpayment"] = (-inv["Net Balance"]).clip(lower=0)
    inv["Status"] = np.where(inv["Net Balance"] <= 0.005, "Paid",
                             np.where(inv["Collected"] > 0, "Partially paid", "Unpaid"))
    dpd = (cutoff - inv["Due Date"]).dt.days.clip(lower=0)
    inv["Days Past Due"] = np.where(inv["Gross Outstanding"] == 0, 0, dpd)
    inv["Aging Bucket"] = np.select(
        [inv["Gross Outstanding"] == 0, inv["Days Past Due"] == 0, inv["Days Past Due"] <= 30,
         inv["Days Past Due"] <= 60, inv["Days Past Due"] <= 90],
        ["Paid / overpaid", "Current / not due", "1-30 days", "31-60 days", "61-90 days"], "90+ days")
    inv["Overdue Balance"] = np.where(inv["Days Past Due"] > 0, inv["Gross Outstanding"], 0)
    early = set(rep.loc[rep["Payment Lag"] < 0, "Invoice Number"])
    inv["Data Quality Flag"] = np.where(inv["Invoice Number"].isin(early), "Payment date before invoice",
                                        np.where(inv["Overpayment"] > 0, "Overpayment", ""))
    inv = inv.sort_values(["Invoice Date", "Invoice Number"]).reset_index(drop=True)

    # Customer credit matrix, largest credit exposure first (the Executive Summary's
    # "Top Credit Exposures" reads the first ten rows).
    credit = inv["Payment Terms"] == "Credit"
    g = inv.assign(credit_total=inv["Invoice Total"].where(credit, 0), credit_n=credit.astype(int),
                   flagged=(inv["Data Quality Flag"] != "").astype(int))
    cust = g.groupby("Customer Name").agg(
        Region=("Region", lambda s: s.mode().iat[0] if len(s.mode()) else ""),
        **{"Invoice Count": ("Invoice Number", "size"), "Credit Invoice Count": ("credit_n", "sum"),
           "Total Invoiced": ("Invoice Total", "sum"), "Credit Issued": ("credit_total", "sum"),
           "Collections": ("Collected", "sum"), "Gross Outstanding": ("Gross Outstanding", "sum"),
           "Overpayments": ("Overpayment", "sum"), "Overdue Balance": ("Overdue Balance", "sum"),
           "Paid Invoices": ("Status", lambda s: (s == "Paid").sum()),
           "Partial Invoices": ("Status", lambda s: (s == "Partially paid").sum()),
           "Unpaid Invoices": ("Status", lambda s: (s == "Unpaid").sum()),
           "Data Quality Flags": ("flagged", "sum")}).reset_index()
    cust["Cash / Other Invoiced"] = cust["Total Invoiced"] - cust["Credit Issued"]
    cust["Net Balance"] = cust["Gross Outstanding"] - cust["Overpayments"]
    cust["Collection Rate"] = np.where(cust["Total Invoiced"] == 0, 0,
                                       cust["Collections"] / cust["Total Invoiced"].replace(0, np.nan))
    tot_credit = cust["Credit Issued"].sum()
    cust["Credit Concentration"] = cust["Credit Issued"] / tot_credit if tot_credit else 0
    cust["Risk Flag"] = np.select(
        [cust["Credit Issued"] == 0, cust["Overdue Balance"] == 0, cust["Collection Rate"] >= 0.8],
        ["Cash / non-credit", "Current", "Watch"], "Elevated")
    cust["Customer Type"] = np.where(cust["Credit Issued"] > 0, "Credit customer", "Cash / project only")
    cust = cust.sort_values(["Credit Issued", "Total Invoiced"], ascending=False).reset_index(drop=True)

    return dict(invoices=inv, receipts=rep, customers=cust, start=start, end=end,
                cutoff=cutoff, terms_days=terms_days)


def summary(d):
    """Headline numbers -- the same figures the Executive Summary sheet computes."""
    inv, cust = d["invoices"], d["customers"]
    credit = inv["Payment Terms"] == "Credit"
    total, credit_issued = inv["Invoice Total"].sum(), inv.loc[credit, "Invoice Total"].sum()
    collected = inv["Collected"].sum()
    return {
        "invoice_count": len(inv), "invoice_value": total, "credit_issued": credit_issued,
        "collections": collected, "collection_rate": collected / total if total else 0,
        "gross_outstanding": inv["Gross Outstanding"].sum(), "overdue": inv["Overdue Balance"].sum(),
        "credit_collection_rate": inv.loc[credit, "Collected"].sum() / credit_issued if credit_issued else 0,
        "credit_customers": int((cust["Customer Type"] == "Credit customer").sum()),
    }


# ══════════════════════════════════════════════════════════════════════════════════
# WORKBOOK
# ══════════════════════════════════════════════════════════════════════════════════
def _row_styles(ws, row, max_col):
    return {c: copy(ws.cell(row, c)._style) for c in range(1, max_col + 1)}


def _apply(ws, row, styles):
    for c, s in styles.items():
        ws.cell(row, c)._style = copy(s)


def _reset_body(ws, first_row):
    """Clear everything from first_row down -- values, merges and stale row heights."""
    for rng in [r for r in ws.merged_cells.ranges if r.min_row >= first_row]:
        ws.unmerge_cells(str(rng))
    if ws.max_row >= first_row:
        ws.delete_rows(first_row, ws.max_row - first_row + 1)
    for r in [r for r in ws.row_dimensions if r >= first_row]:
        ws.row_dimensions[r].height = None


def _resize_table_sheet(ws, last_row, last_col_letter):
    for t in ws.tables.values():
        t.ref = f"A4:{last_col_letter}{last_row}"
        if t.autoFilter is not None:
            t.autoFilter.ref = t.ref
    rules = [(str(cf.sqref), cf.rules) for cf in ws.conditional_formatting]
    ws.conditional_formatting = type(ws.conditional_formatting)()
    for sqref, rs in rules:
        new_ref = re.sub(r"(\d+)$", str(last_row), sqref)
        for r in rs:
            ws.conditional_formatting.add(new_ref, r)


def _fill_rows(ws, rows, styles):
    for i, values in enumerate(rows):
        r = 5 + i
        _apply(ws, r, styles)
        for c, v in enumerate(values, start=1):
            ws.cell(r, c).value = v(r) if callable(v) else v


def _blank(v):
    return None if (v is None or (isinstance(v, float) and np.isnan(v)) or v == "") else v


def build_workbook(d):
    inv, rep, cust = d["invoices"], d["receipts"], d["customers"]
    start, end, cutoff, terms_days = d["start"], d["end"], d["cutoff"], d["terms_days"]
    plabel = period_label(start, end)
    LI = 4 + max(len(inv), 1)    # last Invoice Aging row
    LR = 4 + max(len(rep), 1)    # last Receipt Detail row
    LC = 4 + max(len(cust), 1)   # last Customer Credit Matrix row
    IA, RD, CM = "'04 Invoice Aging'", "'05 Receipt Detail'", "'03 Customer Credit Matrix'"

    wb = openpyxl.load_workbook(TEMPLATE)

    # ── 00 Controls ──────────────────────────────────────────────────────────────
    ws = wb["00 Controls"]
    ws["B5"], ws["B6"], ws["B7"] = start.to_pydatetime(), end.to_pydatetime(), cutoff.to_pydatetime()
    ws["B8"] = "Metabase (TribeCo platform data)"
    ws["B10"] = f"Invoices issued {plabel}; collections allocated through the cut-off date"
    ws["A11"], ws["B11"] = "Standard Payment Term (days)", terms_days
    ws["A11"]._style, ws["B11"]._style = copy(ws["A9"]._style), copy(ws["B9"]._style)
    ws["B11"].number_format = "0"
    notes = [
        "• Source: Metabase platform data -- FBC invoices (excluding cancelled and BufferPesa orders), "
        "confirmed repayments, retail-centre names and account managers, and order warehouses.",
        "• Payment Terms: an invoice is labelled Credit when Metabase records payment terms on it, "
        "otherwise Cash. Due date = invoice date + the standard payment term above.",
        "• Collections are allocated by invoice number and dated by the recorded repayment date. Receipts "
        "dated before their invoice date are retained and flagged for review.",
        "• Sales Zone is not held in Metabase and is left blank; Region shows the customer city on the "
        "invoice. Source Payment / Balance are Metabase's running totals as of today, so reconciliation "
        "differences mostly reflect payments received after the cut-off.",
    ]
    for i, n in enumerate(notes):
        ws.cell(14 + i, 1).value = n

    # ── 04 Invoice Aging ─────────────────────────────────────────────────────────
    ws = wb["04 Invoice Aging"]
    ws["A2"] = (f"All {len(inv)} invoices issued {plabel}; collections measured through "
                f"{cutoff:%d %b %Y}.")
    styles = _row_styles(ws, 5, 25)
    _reset_body(ws, 5)
    rows = []
    for _, x in inv.iterrows():
        rows.append([
            x["Invoice Number"], x["Invoice Date"].to_pydatetime(), x["Customer Name"], None,
            _blank(x["Region"]), _blank(x["Warehouse"]), x["Payment Terms"], _blank(x["Payment Mode"]),
            float(x["Invoice Total"]),
            lambda r: f"=B{r}+'00 Controls'!$B$11",
            lambda r: f"=COUNTIF({RD}!$C$5:$C${LR},A{r})",
            lambda r: f"=SUMIF({RD}!$C$5:$C${LR},A{r},{RD}!$H$5:$H${LR})",
            lambda r: f"=I{r}-L{r}",
            lambda r: f"=MAX(M{r},0)",
            lambda r: f"=MAX(-M{r},0)",
            lambda r: f'=IF(M{r}<=0.005,"Paid",IF(L{r}>0,"Partially paid","Unpaid"))',
            lambda r: f"=IF(N{r}=0,0,MAX(0,'00 Controls'!$B$7-J{r}))",
            lambda r: (f'=IF(N{r}=0,"Paid / overpaid",IF(Q{r}=0,"Current / not due",IF(Q{r}<=30,'
                       f'"1-30 days",IF(Q{r}<=60,"31-60 days",IF(Q{r}<=90,"61-90 days","90+ days")))))'),
            lambda r: f"=IF(Q{r}>0,N{r},0)",
            float(x["Source Payment"]), float(x["Source Balance"]),
            lambda r: f"=L{r}-T{r}",
            lambda r: f"=M{r}-U{r}",
            lambda r: (f'=IF(COUNTIFS({RD}!$C$5:$C${LR},A{r},{RD}!$J$5:$J${LR},"<0")>0,'
                       f'"Payment date before invoice",IF(O{r}>0,"Overpayment",""))'),
            _blank(x["Sales Person"]),
        ])
    _fill_rows(ws, rows, styles)
    _resize_table_sheet(ws, LI, "Y")

    # ── 05 Receipt Detail ────────────────────────────────────────────────────────
    ws = wb["05 Receipt Detail"]
    ws["A2"] = f"Payment receipts linked to {plabel} invoices and recorded through {cutoff:%d %b %Y}."
    styles = _row_styles(ws, 5, 11)
    _reset_body(ws, 5)
    rows = [[x["Payment Number"], x["Payment Date"].to_pydatetime(), x["Invoice Number"],
             x["Invoice Date"].to_pydatetime(), x["Customer Name"], x["Payment Terms"],
             _blank(x["Mode of Payment"]), float(x["Amount Received"]), float(x["Invoice Total"]),
             lambda r: f"=B{r}-D{r}",
             lambda r: f'=IF(J{r}<0,"Before invoice date","On/after invoice date")']
            for _, x in rep.iterrows()]
    _fill_rows(ws, rows, styles)
    _resize_table_sheet(ws, LR, "K")

    # ── 03 Customer Credit Matrix ────────────────────────────────────────────────
    ws = wb["03 Customer Credit Matrix"]
    ws["A2"] = (f"Customer-level exposure, collections, outstanding balances and overdue risk for "
                f"{plabel} invoices.")
    styles = _row_styles(ws, 5, 21)
    _reset_body(ws, 5)
    C, I_ = f"{IA}!$C$5:$C${LI}", lambda col: f"{IA}!${col}$5:${col}${LI}"
    rows = [[x["Customer Name"], None, _blank(x["Region"]),
             lambda r: f"=COUNTIF({C},A{r})",
             lambda r: f'=COUNTIFS({C},A{r},{I_("G")},"Credit")',
             lambda r: f"=SUMIF({C},A{r},{I_('I')})",
             lambda r: f'=SUMIFS({I_("I")},{C},A{r},{I_("G")},"Credit")',
             lambda r: f"=F{r}-G{r}",
             lambda r: f"=SUMIF({C},A{r},{I_('L')})",
             lambda r: f"=SUMIF({C},A{r},{I_('N')})",
             lambda r: f"=SUMIF({C},A{r},{I_('O')})",
             lambda r: f"=J{r}-K{r}",
             lambda r: f"=IF(F{r}=0,0,I{r}/F{r})",
             lambda r: f"=SUMIF({C},A{r},{I_('S')})",
             lambda r: f'=COUNTIFS({C},A{r},{I_("P")},"Paid")',
             lambda r: f'=COUNTIFS({C},A{r},{I_("P")},"Partially paid")',
             lambda r: f'=COUNTIFS({C},A{r},{I_("P")},"Unpaid")',
             lambda r: f"=IF(SUM($G$5:$G${LC})=0,0,G{r}/SUM($G$5:$G${LC}))",
             lambda r: f'=IF(G{r}=0,"Cash / non-credit",IF(N{r}=0,"Current",IF(M{r}>=0.8,"Watch","Elevated")))',
             lambda r: f'=COUNTIFS({C},A{r},{I_("X")},"<>")',
             lambda r: f'=IF(G{r}>0,"Credit customer","Cash / project only")']
            for _, x in cust.iterrows()]
    _fill_rows(ws, rows, styles)
    _resize_table_sheet(ws, LC, "U")

    # ── 01 Executive Summary ─────────────────────────────────────────────────────
    ws = wb["01 Executive Summary"]
    ws["A2"] = f"{plabel} invoice cohort; collections recorded through {cutoff:%d %B %Y}."
    ws["A4"] = "INVOICE VALUE"
    ws["A7"] = f"{len(inv)} invoices issued {plabel}"
    for row in ws.iter_rows():
        for c in row:
            if isinstance(c.value, str) and c.value.startswith("="):
                c.value = re.sub(r"\$440\b", f"${LI}", re.sub(r"\$47\b", f"${LC}", c.value))
    for i in range(10):                       # Top Credit Exposures -> matrix rows 5..14
        if i >= len(cust):
            for col in range(1, 8):
                ws.cell(24 + i, col).value = None

    # ── 02 Monthly Performance ───────────────────────────────────────────────────
    ws = wb["02 Monthly Performance"]
    st_cohort, st_total = _row_styles(ws, 6, 28), _row_styles(ws, 12, 28)
    st_title, st_head, st_rcpt = _row_styles(ws, 15, 13), _row_styles(ws, 16, 5), _row_styles(ws, 17, 5)
    _reset_body(ws, 6)
    months = pd.date_range(start.replace(day=1), end, freq="MS")
    B, IAr = f"{IA}!$B$5:$B${LI}", lambda col: f"{IA}!${col}$5:${col}${LI}"
    in_month = lambda r: f'{B},">="&A{r},{B},"<"&EDATE(A{r},1)'
    r = 6
    for m in months:
        _apply(ws, r, st_cohort)
        vals = [m.to_pydatetime(), f"=COUNTIFS({in_month(r)})",
                f"=SUMIFS({IAr('I')},{in_month(r)})",
                f'=SUMIFS({IAr("I")},{in_month(r)},{IAr("G")},"Credit")',
                f"=IF(C{r}=0,0,D{r}/C{r})",
                f"=SUMIFS({IAr('L')},{in_month(r)})", f"=SUMIFS({IAr('N')},{in_month(r)})",
                f"=SUMIFS({IAr('O')},{in_month(r)})", f"=G{r}-H{r}", f"=IF(C{r}=0,0,F{r}/C{r})",
                f"=SUMIFS({IAr('S')},{in_month(r)})",
                f'=COUNTIFS({in_month(r)},{IAr("P")},"Paid")', f"=B{r}-L{r}"]
        for c, v in enumerate(vals, start=1):
            ws.cell(r, c).value = v
        ws.cell(r, 26).value, ws.cell(r, 27).value, ws.cell(r, 28).value = f"{m:%b-%y}", f"=C{r}", f"=F{r}"
        r += 1
    first, last = 6, r - 1
    _apply(ws, r, st_total)
    ws.cell(r, 1).value = "Period Total"
    for col in "BCDFGHIKLM":
        ws[f"{col}{r}"] = f"=SUM({col}{first}:{col}{last})"
    ws[f"E{r}"], ws[f"J{r}"] = f"=IF(C{r}=0,0,D{r}/C{r})", f"=IF(C{r}=0,0,F{r}/C{r})"

    r += 3
    _apply(ws, r, st_title)
    ws.cell(r, 1).value = "Receipt Activity by Payment Month"
    ws.merge_cells(f"A{r}:E{r}"); ws.merge_cells(f"G{r}:M{r}")
    ws.row_dimensions[r].height = 21.75
    r += 1
    _apply(ws, r, st_head)
    for c, h in enumerate(["Payment Month", "Receipt Count", "Amount Received (GHS)",
                           "Share of Collections", "Timing Scope"], start=1):
        ws.cell(r, c).value = h
    ws.row_dimensions[r].height = 33.75
    pay_start = min(rep["Payment Date"].min(), start) if len(rep) else start
    pay_months = pd.date_range(pay_start.replace(day=1), cutoff, freq="MS")
    r0 = r + 1
    rl = r0 + max(len(pay_months), 1) - 1
    PB = f"{RD}!$B$5:$B${LR}"
    for i, m in enumerate(pay_months):
        rr = r0 + i
        _apply(ws, rr, st_rcpt)
        ws.cell(rr, 1).value = m.to_pydatetime()
        ws.cell(rr, 2).value = f'=COUNTIFS({PB},">="&A{rr},{PB},"<"&EDATE(A{rr},1))'
        ws.cell(rr, 3).value = f'=SUMIFS({RD}!$H$5:$H${LR},{PB},">="&A{rr},{PB},"<"&EDATE(A{rr},1))'
        ws.cell(rr, 4).value = f"=IF(SUM($C${r0}:$C${rl})=0,0,C{rr}/SUM($C${r0}:$C${rl}))"
        ws.cell(rr, 5).value = "Allocated to period invoices"

    wb.calculation.fullCalcOnLoad = True   # formulas have no cached values until Excel calculates
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
