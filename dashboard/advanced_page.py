"""
Advanced Analytics page -- rendering only; the calculations live in advanced_analytics.py.

app.py calls render(ui) with a SimpleNamespace of its shared helpers (card_open, kpi_card,
theme tokens, ...) so this page looks exactly like the others without importing app.py.
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import advanced_analytics as aa

SEG_COLORS = {
    "Champions": "#1f7a4d", "Loyal": "#3fa873", "Promising": "#14b8a6", "Needs attention": "#e0b980",
    "At risk": "#f97316", "Can't lose": "#dc2626", "Hibernating": "#9ca3af",
}
STATUS_COLORS = {"On track": "#16a34a", "Due now": "#e0b980", "Late": "#f97316", "Lapsed": "#dc2626",
                 "Dormant 12m+": "#9ca3af"}
DRIVER_COLORS = {"up": "#1f7a4d", "down": "#dc2626", "total": "#c9975a"}


def ghs(v, short=True):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "–"
    if not short:
        return f"GHS {v:,.0f}"
    a = abs(v)
    if a >= 1e6:
        return f"GHS {v / 1e6:,.2f}M"
    if a >= 1e3:
        return f"GHS {v / 1e3:,.1f}k"
    return f"GHS {v:,.0f}"


@st.cache_data(ttl=300, show_spinner="Running the analysis...")
def _compute(inv_fbc, rc_names, il, prod, window_days, horizon):
    df = aa.prep_invoices(inv_fbc, rc_names)
    if df.empty:
        return None
    as_of = df["Date"].max()
    start = aa.trading_start(df)
    # Always forecast far enough to reach 31 Dec for the year-end projection; the page shows `horizon` weeks.
    weeks_to_ye = int(np.ceil((pd.Timestamp(year=as_of.year, month=12, day=31) - as_of).days / 7)) + 1
    fc = aa.forecast_weekly(df, start, horizon=max(horizon, weeks_to_ye, 8))
    ye = aa.year_end_projection(df, fc, as_of) if fc is not None else None
    r = aa.rfm(df[df["Date"] >= start], as_of)
    churn, gap = aa.churn_risk(df, as_of)
    ret, size = aa.cohorts(df, start)
    recent = df[df["Date"] >= as_of - pd.Timedelta(days=365)]
    cust_conc = aa.concentration(recent.groupby("Customer")["Value"].sum())
    lines = il[il["Invoice ID"].isin(set(recent["Invoice ID"]))].copy()
    names = prod.set_index("ID")
    nm = names["Generic Name"].fillna(names["Brand Name"]) if "Generic Name" in names.columns else names["Brand Name"]
    lines["Product"] = lines["Product ID"].map(nm).fillna("Unknown").astype(str).str.strip()
    lines["Rev"] = pd.to_numeric(lines["Quantity"], errors="coerce").fillna(0) * pd.to_numeric(lines["Price"], errors="coerce").fillna(0)
    prod_conc = aa.concentration(lines.groupby("Product")["Rev"].sum())
    bridge = aa.customer_bridge(df, as_of, window_days)
    pvm = aa.product_price_volume(df, il, prod, as_of, window_days)
    pairs = aa.basket_pairs(recent, il, prod)
    return dict(horizon=horizon, df=df, as_of=as_of, start=start, fc=fc, ye=ye, rfm=r, seg=aa.segment_summary(r),
                churn=churn, gap=gap, ret=ret, size=size, cust_conc=cust_conc, prod_conc=prod_conc,
                bridge=bridge, pvm=pvm, pairs=pairs)


def next_weeks(fc, n=4):
    """The next n full weeks after the in-progress one, their total and an 80% range for the total
    (variances added, so the range is not the sum of every week's extreme)."""
    f = fc.future.iloc[1:1 + n] if fc.partial_week is not None else fc.future.head(n)
    se = (f["Hi80"] - f["Forecast"]) / 1.2816
    tot, se_tot = float(f["Forecast"].sum()), float(np.sqrt((se ** 2).sum()))
    return f, tot, max(tot - 1.2816 * se_tot, 0.0), tot + 1.2816 * se_tot


def _wrap(label):
    """'Existing: grew' -> 'Existing<br>grew', 'New customers' -> 'New<br>customers'."""
    return label.replace(": ", "<br>") if ": " in label else label.replace(" ", "<br>", 1)


def _layout(ui, height, **kw):
    base = dict(height=height, margin=dict(t=16, b=40, l=12, r=12),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color=ui.chart_font), hovermode="x unified")
    base.update(kw)
    return base


def _waterfall(ui, start_label, start_val, steps, end_label, end_val, height=360):
    x = [start_label] + [_wrap(i) for i in steps.index] + [end_label]
    y = [start_val] + list(steps.values) + [end_val]
    measure = ["absolute"] + ["relative"] * len(steps) + ["total"]
    fig = go.Figure(go.Waterfall(
        x=x, y=y, measure=measure, text=[ghs(v) for v in y], textposition="outside",
        connector=dict(line=dict(color=ui.chart_grid, width=1)),
        increasing=dict(marker=dict(color=DRIVER_COLORS["up"])),
        decreasing=dict(marker=dict(color=DRIVER_COLORS["down"])),
        totals=dict(marker=dict(color=DRIVER_COLORS["total"])),
        hovertemplate="%{x}: GHS %{y:,.0f}<extra></extra>",
    ))
    fig.update_layout(**_layout(ui, height, hovermode="closest", showlegend=False),
                      yaxis=dict(title="GHS", gridcolor=ui.chart_grid, rangemode="tozero"),
                      xaxis=dict(tickangle=0))
    return fig


def _insights(ui, R):
    """Plain-language findings computed from the results -- no hand-written commentary."""
    out = []
    fc, ye = R["fc"], R["ye"]
    if fc is not None:
        h = fc.history
        last4 = h["Revenue"].iloc[-4:].sum()
        _, nxt4, _, _ = next_weeks(fc)
        chg = (nxt4 / last4 - 1) * 100 if last4 else 0
        trend = "rise" if chg > 3 else ("ease" if chg < -3 else "hold steady")
        out.append(("#1f7a4d", "Sales outlook",
                    f"The model expects the next 4 full weeks to <b>{trend}</b> to about <b>{ghs(nxt4)}</b> "
                    f"({chg:+.0f}% vs the last 4 complete weeks, {ghs(last4)})."))
        if ye:
            out.append(("#c9975a", f"{R['as_of'].year} landing",
                        f"<b>{ghs(ye[0])}</b> booked so far; on current momentum the year closes near "
                        f"<b>{ghs(ye[0] + ye[1])}</b>."))
    c = R["churn"]
    if len(c):
        risk = c[c["Status"].isin(["Late", "Lapsed"])]
        if len(risk):
            top = risk.iloc[0]
            out.append(("#dc2626", "Revenue at risk",
                        f"<b>{len(risk)}</b> active customers are well past their usual reorder rhythm, worth "
                        f"<b>{ghs(risk['Avg monthly revenue'].sum())}/month</b>. Call <b>{top['Customer']}</b> first "
                        f"({top['Days since last order']} days quiet vs a usual {top['Typical gap (days)']})."))
    cc = R["cust_conc"]
    if cc:
        out.append(("#6366f1", "Concentration",
                    f"<b>{cc['n_for_80']}</b> of {cc['n']} customers make up 80% of the last 12 months' revenue "
                    f"(Gini {cc['gini']:.2f}). Losing one top account moves the month."))
    b = R["bridge"]
    if b["prev"]:
        steps = b["steps"]
        big = steps.abs().idxmax()
        out.append(("#14b8a6", "What moved revenue",
                    f"Last {ui.window_days} days vs the {ui.window_days} before: <b>{(b['cur'] / b['prev'] - 1) * 100:+.0f}%</b>. "
                    f"Biggest driver: <b>{big.lower()}</b> ({ghs(steps[big])})."))
    p = R["pairs"]
    if p is not None and len(p):
        t = p.iloc[0]
        out.append(("#f97316", "Cross-sell",
                    f"{t['Confidence %']:.0f}% of orders with <b>{t['If they buy']}</b> also include "
                    f"<b>{t['They also buy']}</b> ({t['Lift']:.0f}× more than chance): bundle them."))
    return out


def render(ui):
    inv_fbc, rc_names, il, prod = ui.inv_fbc, ui.rc_names, ui.il, ui.prod

    # ── Controls ─────────────────────────────────────────────────────────────────
    ui.card_open("Analysis settings", "Applies to the comparison and forecast sections below")
    c1, c2, c3 = st.columns([2, 2, 3], vertical_alignment="bottom")
    with c1:
        window = st.segmented_control("Compare the last", ["30 days", "60 days", "90 days"],
                                      default="90 days", key="aa_window")
    with c2:
        horizon = st.segmented_control("Forecast ahead", ["4 weeks", "8 weeks", "12 weeks"],
                                       default="8 weeks", key="aa_horizon")
    window_days = int((window or "90 days").split()[0])
    horizon_w = int((horizon or "8 weeks").split()[0])
    ui.window_days = window_days
    R = _compute(inv_fbc, rc_names, il, prod, window_days, horizon_w)
    if R is None:
        ui.card_close()
        st.info("No invoices to analyse yet.")
        return
    with c3:
        st.markdown(
            f'<div class="method-note">Uses <b>{len(R["df"]):,}</b> FBC invoices from <b>{R["start"]:%b %Y}</b> '
            f'(first month of sustained trading) to <b>{R["as_of"]:%d %b %Y}</b>, '
            f'{R["df"]["Customer ID"].nunique()} customers. Earlier pilot months are left out of trends.</div>',
            unsafe_allow_html=True)
    ui.card_close()

    fc, ye = R["fc"], R["ye"]

    # ── Headline KPIs ────────────────────────────────────────────────────────────
    k = ""
    if fc is not None:
        _, n4, lo, hi = next_weeks(fc)
        k += ui.kpi_card("Forecast · next 4 full weeks", ghs(n4), f"80% range {ghs(lo)} – {ghs(hi)}", ui.green)
    if ye:
        k += ui.kpi_card(f"Projected {R['as_of'].year} revenue", ghs(ye[0] + ye[1]),
                         f"{ghs(ye[0])} booked + {ghs(ye[1])} forecast", ui.gold)
    c = R["churn"]
    risk = c[c["Status"].isin(["Late", "Lapsed"])] if len(c) else c
    k += ui.kpi_card("Revenue at risk / month", ghs(risk["Avg monthly revenue"].sum()) if len(risk) else "GHS 0.0",
                     f"{len(risk)} customers past their reorder rhythm", "#dc2626",
                     f"{len(risk)}" if len(risk) else "", "#dc2626")
    if R["cust_conc"]:
        cc = R["cust_conc"]
        k += ui.kpi_card("Top-20% customer share", f"{cc['top20_share']:.0f}%",
                         f"Gini {cc['gini']:.2f} · last 12 months", "#6366f1")
    st.markdown(ui.kpi_grid(k), unsafe_allow_html=True)

    # ── Key findings ─────────────────────────────────────────────────────────────
    ui.section_label("Key findings")
    cards = "".join(
        f'<div class="insight"><span class="insight-dot" style="background:{col}"></span>'
        f'<div><div class="insight-title">{t}</div><div class="insight-text">{txt}</div></div></div>'
        for col, t, txt in _insights(ui, R))
    st.markdown(f'<div class="insight-grid">{cards}</div>', unsafe_allow_html=True)

    tabs = st.tabs(["Forecast", "Customer segments", "Churn risk", "Cohorts",
                    "Concentration", "Growth drivers", "Cross-sell"])

    # ── 1. Forecast ──────────────────────────────────────────────────────────────
    with tabs[0]:
        if fc is None:
            st.info("At least 12 weeks of trading are needed for a forecast.")
        else:
            h, f = fc.history, fc.future.head(R["horizon"])
            l, r = st.columns([7, 3])
            with l:
                ui.card_open("Weekly revenue forecast",
                             "Holt damped-trend exponential smoothing · shaded bands are 80% and 95% prediction intervals")
                fig = go.Figure()
                fig.add_bar(x=h["Week"], y=h["Revenue"], name="Actual", marker=dict(color=ui.green_light, opacity=0.55,
                            cornerradius=4), hovertemplate="GHS %{y:,.0f}")
                fig.add_scatter(x=h["Week"], y=h["Fitted"], name="Model fit", mode="lines",
                                line=dict(color=ui.green, width=2), hovertemplate="GHS %{y:,.0f}")
                band_x = list(f["Week"]) + list(f["Week"][::-1])
                fig.add_scatter(x=band_x, y=list(f["Hi95"]) + list(f["Lo95"][::-1]), fill="toself", mode="lines",
                                fillcolor="rgba(201,151,90,0.14)", line=dict(width=0), name="95% range", hoverinfo="skip")
                fig.add_scatter(x=band_x, y=list(f["Hi80"]) + list(f["Lo80"][::-1]), fill="toself", mode="lines",
                                fillcolor="rgba(201,151,90,0.28)", line=dict(width=0), name="80% range", hoverinfo="skip")
                fig.add_scatter(x=[h["Week"].iloc[-1]] + list(f["Week"]), y=[h["Fitted"].iloc[-1]] + list(f["Forecast"]),
                                name="Forecast", mode="lines+markers", line=dict(color=ui.gold, width=2.5, dash="dot"),
                                marker=dict(size=6), hovertemplate="GHS %{y:,.0f}")
                if fc.partial_week is not None:
                    fig.add_bar(x=[fc.partial_week - pd.Timedelta(days=3)], y=[fc.partial_value], name="This week so far",
                                width=[6 * 86400000],
                                marker=dict(color="rgba(201,151,90,0.35)", line=dict(color=ui.gold, width=1.5),
                                            pattern=dict(shape="/", fgcolor=ui.gold), cornerradius=4),
                                hovertemplate="Booked so far: GHS %{y:,.0f}")
                an = h[h["Anomaly"] != ""]
                if len(an):
                    fig.add_scatter(x=an["Week"], y=an["Revenue"], mode="markers", name="Unusual week",
                                    marker=dict(size=13, color="rgba(0,0,0,0)", line=dict(color="#dc2626", width=2.5)),
                                    hovertemplate="Unusual: GHS %{y:,.0f}<extra></extra>")
                fig.update_layout(**_layout(ui, 380), legend=dict(orientation="h", y=-0.14, x=0),
                                  yaxis=dict(title="GHS per week", gridcolor=ui.chart_grid, rangemode="tozero"),
                                  xaxis=dict(tickformat="%d %b"), barmode="overlay")
                st.plotly_chart(fig, use_container_width=True, config=ui.chart_cfg)
                ui.card_close()
            with r:
                ui.card_open("How reliable is it?", f"Back-test on the last {fc.holdout_weeks} weeks")
                better = (1 - fc.wape_model / fc.wape_naive) * 100 if fc.wape_naive else 0
                st.markdown(ui.kpi_grid(
                    ui.kpi_card("Model error (WAPE)", f"{fc.wape_model * 100:.0f}%", "Lower is better", ui.green) +
                    ui.kpi_card("Simple average error", f"{fc.wape_naive * 100:.0f}%",
                                f"Model is {abs(better):.0f}% {'better' if better >= 0 else 'worse'}", "#9ca3af")),
                    unsafe_allow_html=True)
                note = (f"<b>Smoothing</b> α={fc.params['alpha']}, β={fc.params['beta']}, damping φ={fc.params['phi']}. "
                        "Damping flattens the trend further out, so long-range forecasts stay conservative.")
                if fc.partial_week is not None:
                    note += (f"<br><br>The week ending <b>{fc.partial_week:%d %b}</b> is still in progress "
                             f"({ghs(fc.partial_value)} so far) and is not used to fit the model.")
                st.markdown(f'<div class="method-note">{note}</div>', unsafe_allow_html=True)
                ui.card_close()

            ui.card_open("Forecast by week", "Expected revenue with 80% range")
            t = f.copy()
            t["Week ending"] = t["Week"].dt.strftime("%d %b %Y")
            t["Booked so far"] = np.where(t["Week"] == fc.partial_week, fc.partial_value, np.nan)
            cols = ["Week ending", "Forecast", "Lo80", "Hi80"] + (["Booked so far"] if fc.partial_week is not None else [])
            st.dataframe(t[cols].rename(columns={"Lo80": "Low (80%)", "Hi80": "High (80%)"}),
                         hide_index=True, use_container_width=True,
                         column_config={c: st.column_config.NumberColumn(format="GHS %,.0f")
                                        for c in ["Forecast", "Low (80%)", "High (80%)", "Booked so far"]})
            if len(an):
                st.markdown('<div class="method-note"><b>Unusual weeks</b> are more than 2.5 robust standard deviations '
                            'from what the model expected — worth checking for bulk orders, data entry batches or stock-outs.</div>',
                            unsafe_allow_html=True)
                a2 = an.copy()
                a2["Week ending"] = a2["Week"].dt.strftime("%d %b %Y")
                st.dataframe(a2[["Week ending", "Revenue", "Fitted", "Anomaly"]].rename(columns={"Fitted": "Expected", "Anomaly": "Type"}),
                             hide_index=True, use_container_width=True,
                             column_config={c: st.column_config.NumberColumn(format="GHS %,.0f") for c in ["Revenue", "Expected"]})
            ui.card_close()

    # ── 2. Segments ──────────────────────────────────────────────────────────────
    with tabs[1]:
        seg, rf = R["seg"], R["rfm"]
        l, r = st.columns([1, 1])
        with l:
            ui.card_open("Revenue by segment", "RFM: recency, frequency and spend, each scored 1–5 across customers")
            fig = go.Figure(go.Bar(
                y=seg["Segment"], x=seg["Revenue"], orientation="h",
                marker=dict(color=[SEG_COLORS[s] for s in seg["Segment"]], cornerradius=4),
                text=[f"{ghs(v)} · {n} cust." for v, n in zip(seg["Revenue"], seg["Customers"])],
                textposition="outside", hovertemplate="%{y}: GHS %{x:,.0f}<extra></extra>", cliponaxis=False))
            fig.update_layout(**_layout(ui, 340, hovermode="closest", margin=dict(t=8, b=8, l=8, r=120)),
                              xaxis=dict(visible=False), yaxis=dict(autorange="reversed", gridcolor="rgba(0,0,0,0)"))
            st.plotly_chart(fig, use_container_width=True, config=ui.chart_cfg)
            ui.card_close()
        with r:
            ui.card_open("Every customer, mapped", "Days since last order vs total spend · bubble size = number of orders")
            fig = go.Figure()
            for s in aa.SEGMENT_ORDER:
                d = rf[rf["Segment"] == s]
                if d.empty:
                    continue
                fig.add_scatter(x=d["Recency (days)"], y=d["Revenue"], mode="markers", name=s,
                                marker=dict(size=np.clip(np.sqrt(d["Orders"]) * 5, 7, 34), color=SEG_COLORS[s],
                                            opacity=0.8, line=dict(color="white", width=1)),
                                customdata=d[["Customer", "Orders"]],
                                hovertemplate="<b>%{customdata[0]}</b><br>%{x} days since last order<br>"
                                              "GHS %{y:,.0f} · %{customdata[1]} orders<extra></extra>")
            fig.update_layout(**_layout(ui, 340, hovermode="closest"), legend=dict(orientation="h", y=-0.2),
                              xaxis=dict(title="Days since last order", gridcolor=ui.chart_grid),
                              yaxis=dict(title="Revenue (GHS)", type="log", gridcolor=ui.chart_grid,
                                         tickvals=[1e3, 1e4, 1e5, 1e6], ticktext=["1k", "10k", "100k", "1M"]))
            st.plotly_chart(fig, use_container_width=True, config=ui.chart_cfg)
            ui.card_close()
        ui.card_open("What to do with each segment")
        st.dataframe(seg[["Segment", "Customers", "Revenue", "Revenue share", "Avg recency (days)", "Action"]],
                     hide_index=True, use_container_width=True,
                     column_config={"Revenue": st.column_config.NumberColumn(format="GHS %,.0f"),
                                    "Revenue share": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
                                    "Avg recency (days)": st.column_config.NumberColumn(format="%.0f"),
                                    "Action": st.column_config.TextColumn(width="large")})
        with st.expander("Customer list by segment"):
            pick = st.multiselect("Segments", list(seg["Segment"]), default=[], key="aa_seg_pick",
                                  placeholder="All segments")
            show = rf[rf["Segment"].isin(pick)] if pick else rf
            st.dataframe(show.sort_values("Revenue", ascending=False)[
                ["Customer", "Segment", "Orders", "Revenue", "Recency (days)", "R", "F", "M", "Outstanding"]],
                hide_index=True, use_container_width=True,
                column_config={c: st.column_config.NumberColumn(format="GHS %,.0f") for c in ["Revenue", "Outstanding"]})
        ui.card_close()

    # ── 3. Churn risk ────────────────────────────────────────────────────────────
    with tabs[2]:
        c = R["churn"]
        if c.empty:
            st.info("Not enough repeat orders to judge reorder rhythm yet.")
        else:
            counts = c["Status"].value_counts()
            chips = "".join(ui.kpi_card(s, f"{int(counts.get(s, 0))}",
                                        f"{ghs(c.loc[c['Status'] == s, 'Avg monthly revenue'].sum())}/month run-rate",
                                        STATUS_COLORS[s]) for s in STATUS_COLORS)
            st.markdown(ui.kpi_grid(chips), unsafe_allow_html=True)
            l, r = st.columns([3, 2])
            with l:
                ui.card_open("Call list", "Customers past their usual reorder gap, ranked by revenue at stake")
                calls = c[c["Priority"] > 0].head(20)
                st.dataframe(calls[["Customer", "Status", "Days since last order", "Typical gap (days)",
                                    "Overdue ratio", "Avg monthly revenue"]].rename(columns={
                                        "Days since last order": "Days quiet", "Typical gap (days)": "Usual gap",
                                        "Avg monthly revenue": "Monthly revenue"}),
                             hide_index=True, use_container_width=True, height=min(38 + 35 * len(calls), 560),
                             column_config={"Monthly revenue": st.column_config.NumberColumn(format="GHS %,.0f"),
                                            "Overdue ratio": st.column_config.NumberColumn(format="%.1f×",
                                                help="Days since last order ÷ the customer's usual gap between orders")})
                ui.card_close()
            with r:
                ui.card_open("Rhythm map", "Lines mark 1×, 1.5× and 3× the usual gap; above a line = overdue")
                act = c[c["Status"] != "Dormant 12m+"]
                fig = go.Figure()
                mx = max(act["Typical gap (days)"].max() if len(act) else 30, 30) * 1.3
                for m_, dash in ((1, "solid"), (1.5, "dash"), (3, "dot")):
                    fig.add_scatter(x=[5, mx], y=[5 * m_, mx * m_], mode="lines", line=dict(color=ui.chart_grid, width=1.5, dash=dash),
                                    showlegend=False, hoverinfo="skip")
                for s in ["On track", "Due now", "Late", "Lapsed"]:
                    d = act[act["Status"] == s]
                    if d.empty:
                        continue
                    fig.add_scatter(x=d["Typical gap (days)"], y=d["Days since last order"].clip(lower=1), mode="markers", name=s,
                                    marker=dict(size=np.clip(np.sqrt(d["Avg monthly revenue"]) / 6, 6, 30),
                                                color=STATUS_COLORS[s], opacity=0.85, line=dict(color="white", width=1)),
                                    customdata=d[["Customer"]],
                                    hovertemplate="<b>%{customdata[0]}</b><br>usual gap %{x} d · quiet %{y} d<extra></extra>")
                fig.update_layout(**_layout(ui, 400, hovermode="closest"), legend=dict(orientation="h", y=-0.18),
                                  xaxis=dict(title="Usual days between orders (log)", type="log",
                                             range=[np.log10(5), np.log10(mx)], gridcolor=ui.chart_grid,
                                             tickvals=[7, 14, 30, 60, 90]),
                                  yaxis=dict(title="Days since last order (log)", type="log", gridcolor=ui.chart_grid,
                                             tickvals=[1, 7, 30, 90, 180, 365]))
                st.plotly_chart(fig, use_container_width=True, config=ui.chart_cfg)
                ui.card_close()
            st.markdown(f'<div class="method-note">Each customer is judged against <b>their own</b> median gap between '
                        f'orders (company median, {R["gap"]:.0f} days, for customers with fewer than 3 orders). '
                        f'<b>Due now</b> = 1–1.5× their gap, <b>Late</b> = 1.5–3×, <b>Lapsed</b> = over 3×. '
                        f'Customers silent for over a year are listed as dormant, not at risk.</div>', unsafe_allow_html=True)

    # ── 4. Cohorts ───────────────────────────────────────────────────────────────
    with tabs[3]:
        ret, size = R["ret"], R["size"]
        ui.card_open("Customer retention by first-order month",
                     "Share of each month's new customers who ordered again N months later")
        ylab = [f"{i}  ({int(size[i])})" for i in ret.index]
        z = ret.values
        fig = go.Figure(go.Heatmap(
            z=z, x=[f"M+{c}" for c in ret.columns], y=ylab, zmin=0, zmax=100,
            colorscale=[[0, "rgba(31,122,77,0.04)"], [0.5, "#3fa873"], [1, "#024b30"]],
            text=[[("" if np.isnan(v) else f"{v:.0f}%") for v in row] for row in z], texttemplate="%{text}",
            textfont=dict(size=11), hovertemplate="%{y}<br>%{x}: %{z:.0f}%<extra></extra>",
            colorbar=dict(title="%", thickness=10), xgap=2, ygap=2))
        fig.update_layout(**_layout(ui, 60 + 30 * len(ret), hovermode="closest"),
                          yaxis=dict(autorange="reversed"), xaxis=dict(side="top"))
        st.plotly_chart(fig, use_container_width=True, config=ui.chart_cfg)
        # customer-weighted average curve, only over cohorts old enough for each offset
        act = (ret.fillna(np.nan).mul(size.values, axis=0))
        avail = ret.notna().mul(size.values, axis=0)
        curve = (act.sum() / avail.sum()).dropna()
        cols = [c for c in curve.index if c > 0][:6]
        if cols:
            st.markdown('<div class="method-note">Average across cohorts, weighted by cohort size: ' +
                        " · ".join(f"<b>M+{c}</b> {curve[c]:.0f}%" for c in cols) +
                        '. Cohort size is in brackets; single-customer cohorts swing between 0% and 100%.</div>',
                        unsafe_allow_html=True)
        ui.card_close()

    # ── 5. Concentration ─────────────────────────────────────────────────────────
    with tabs[4]:
        l, r = st.columns(2)
        for col, key, title in ((l, "cust_conc", "Customers"), (r, "prod_conc", "Products")):
            cc = R[key]
            with col:
                ui.card_open(f"{title}: how concentrated is revenue?", "Lorenz curve, last 12 months")
                if not cc:
                    st.info("No revenue in the last 12 months.")
                    ui.card_close()
                    continue
                fig = go.Figure()
                fig.add_scatter(x=[0, 100], y=[0, 100], mode="lines", name="Perfect equality",
                                line=dict(color=ui.chart_grid, dash="dash"))
                fig.add_scatter(x=cc["lorenz_x"] * 100, y=cc["lorenz_y"] * 100, mode="lines", name="Actual",
                                fill="tonexty", fillcolor="rgba(31,122,77,0.10)", line=dict(color=ui.green, width=2.5),
                                hovertemplate="Bottom %{x:.0f}% of " + title.lower() + " = %{y:.0f}% of revenue<extra></extra>")
                fig.update_layout(**_layout(ui, 280, hovermode="closest"), showlegend=False,
                                  xaxis=dict(title=f"% of {title.lower()} (smallest first)", gridcolor=ui.chart_grid, ticksuffix="%"),
                                  yaxis=dict(title="% of revenue", gridcolor=ui.chart_grid, ticksuffix="%"))
                st.plotly_chart(fig, use_container_width=True, config=ui.chart_cfg)
                t = cc["table"]
                abc = t.groupby("Class").agg(Count=("Name", "count"), Revenue=("Revenue", "sum")).reindex(["A", "B", "C"]).fillna(0)
                st.markdown(ui.kpi_grid(
                    ui.kpi_card("Gini", f"{cc['gini']:.2f}", "0 = equal, 1 = one takes all", ui.green) +
                    ui.kpi_card("Class A", f"{int(abc.loc['A', 'Count'])} of {cc['n']}", "make up 80% of revenue", ui.gold)),
                    unsafe_allow_html=True)
                with st.expander(f"ABC table ({title.lower()})"):
                    st.dataframe(t, hide_index=True, use_container_width=True,
                                 column_config={"Revenue": st.column_config.NumberColumn(format="GHS %,.0f"),
                                                "Share": st.column_config.NumberColumn(format="%.1f%%"),
                                                "Cumulative": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100)})
                ui.card_close()

    # ── 6. Growth drivers ────────────────────────────────────────────────────────
    with tabs[5]:
        b, pv = R["bridge"], R["pvm"]
        p0, p1, p2 = b["window"]
        lbl0 = f"{p0:%d %b}–{(p1 - pd.Timedelta(days=1)):%d %b}"
        lbl1 = f"{p1:%d %b}–{(p2 - pd.Timedelta(days=1)):%d %b}"
        l, r = st.columns(2)
        with l:
            ui.card_open("Revenue bridge by customer", f"Invoice value, {lbl0} → {lbl1}")
            st.plotly_chart(_waterfall(ui, "Before", b["prev"], b["steps"], "Now", b["cur"]),
                            use_container_width=True, config=ui.chart_cfg)
            ui.card_close()
        with r:
            ui.card_open("Revenue bridge by product", f"Units × price on invoice lines, {lbl0} → {lbl1}")
            st.plotly_chart(_waterfall(ui, "Before", pv["prev"], pv["steps"], "Now", pv["cur"]),
                            use_container_width=True, config=ui.chart_cfg)
            ui.card_close()
        with st.container():
            ui.card_open("Biggest customer movers", "Largest gains and losses between the two periods")
            d = b["detail"]
            mv = pd.concat([d.head(6), d.tail(6)]).drop_duplicates("Customer").sort_values("Change")
            mv = mv[mv["Change"] != 0]
            fig = go.Figure(go.Bar(y=mv["Customer"], x=mv["Change"], orientation="h",
                                   marker=dict(color=[DRIVER_COLORS["up"] if v > 0 else DRIVER_COLORS["down"] for v in mv["Change"]],
                                               cornerradius=4),
                                   text=[ghs(v) for v in mv["Change"]], textposition="outside", cliponaxis=False,
                                   customdata=mv[["Driver"]], hovertemplate="%{y}: GHS %{x:+,.0f} (%{customdata[0]})<extra></extra>"))
            lo_x = min(mv["Change"].min(), 0) if len(mv) else 0
            hi_x = max(mv["Change"].max(), 0) if len(mv) else 1
            pad = (hi_x - lo_x) * 0.18
            fig.update_layout(**_layout(ui, 60 + 30 * max(len(mv), 1), hovermode="closest",
                                        margin=dict(t=8, b=40, l=8, r=8)),
                              xaxis=dict(title="Change (GHS)", gridcolor=ui.chart_grid, zeroline=True,
                                         zerolinecolor=ui.chart_grid, range=[lo_x - pad, hi_x + pad]))
            st.plotly_chart(fig, use_container_width=True, config=ui.chart_cfg)
            ui.card_close()
        with st.container():
            ui.card_open("Product drivers", "Volume effect = change in units at the old price; price effect = price change on new units")
            t = pv["table"]
            t = t[t["Change"] != 0]
            t = pd.concat([t.head(6), t.tail(6)]).drop_duplicates("Product").sort_values("Change", ascending=False)
            st.dataframe(t[["Product", "Revenue before", "Revenue now", "Change", "Volume effect", "Price effect"]],
                         hide_index=True, use_container_width=True, height=38 + 35 * len(t),
                         column_config={c: st.column_config.NumberColumn(format="GHS %,.0f")
                                        for c in ["Revenue before", "Revenue now", "Change", "Volume effect", "Price effect"]})
            ui.card_close()

    # ── 7. Cross-sell ────────────────────────────────────────────────────────────
    with tabs[6]:
        p = R["pairs"]
        ui.card_open("Products bought together", "Market-basket analysis of the last 12 months' invoices")
        if p is None or p.empty:
            st.info("No product pair appears together often enough yet (needs 4+ shared orders).")
        else:
            st.dataframe(p.head(25), hide_index=True, use_container_width=True,
                         column_config={"Support %": st.column_config.NumberColumn(format="%.1f%%",
                                            help="Share of all orders containing both"),
                                        "Confidence %": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100,
                                            help="Of orders with the first product, the share that also had the second"),
                                        "Lift": st.column_config.NumberColumn(format="%.1f×",
                                            help="How much more often they appear together than if unrelated")})
            st.markdown('<div class="method-note"><b>How to use it:</b> where confidence is high, offer the second '
                        'product whenever the first is ordered; where lift is high but confidence low, the pair is a '
                        'niche bundle worth a targeted offer.</div>', unsafe_allow_html=True)
        ui.card_close()

    # ── Download ─────────────────────────────────────────────────────────────────
    sheets = {"Customer segments": R["rfm"].drop(columns=["Customer ID"]),
              "Churn risk": R["churn"].drop(columns=["Customer ID"])}
    if fc is not None:
        sheets["Forecast"] = fc.future.head(R["horizon"])
        sheets["Weekly history"] = fc.history
    sheets["Customer bridge"] = b["detail"]
    sheets["Product drivers"] = pv["table"]
    if R["pairs"] is not None and len(R["pairs"]):
        sheets["Cross-sell"] = R["pairs"]
    ui.dl_button(sheets, f"Advanced_Analytics_{R['as_of']:%Y%m%d}.xlsx", "Download analysis (Excel)")
