import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px
from io import BytesIO

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Monitoramento de Preços | IceCream Portugal",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}
h1, h2, h3 { font-family: 'DM Serif Display', serif; }

.main { background: #f7f5f0; }
.block-container { padding: 2rem 2.5rem 3rem; }

.metric-card {
    background: white;
    border-radius: 12px;
    padding: 1.2rem 1.4rem;
    border-left: 4px solid #1a1a1a;
    box-shadow: 0 1px 4px rgba(0,0,0,.06);
}
.metric-card h4 { margin:0; font-size:.75rem; color:#888; letter-spacing:.08em; text-transform:uppercase; }
.metric-card p  { margin:.2rem 0 0; font-size:1.9rem; font-weight:600; color:#1a1a1a; }

.tag {
    display:inline-block; padding:2px 9px;
    border-radius:20px; font-size:.72rem; font-weight:600;
    margin:2px;
}
.tag-new   { background:#dcfce7; color:#166534; }
.tag-promo { background:#fef9c3; color:#854d0e; }
.tag-alert { background:#fee2e2; color:#991b1b; }
.tag-cont  { background:#dbeafe; color:#1e40af; }
.tag-auch  { background:#ede9fe; color:#5b21b6; }
.tag-ping  { background:#fce7f3; color:#9d174d; }
.tag-pu    { background:#e0f2fe; color:#0c4a6e; }
.tag-hl    { background:#fef3c7; color:#92400e; }
.tag-novo-high { background:#fce7f3; color:#9d174d; font-size:.75rem; padding:3px 10px; border-radius:6px; display:inline-block; }
.tag-novo-low  { background:#fef9c3; color:#854d0e; font-size:.75rem; padding:3px 10px; border-radius:6px; display:inline-block; }
.alert-box {
    background:#fffbeb; border:1px solid #fbbf24;
    border-left:4px solid #f59e0b;
    border-radius:8px; padding:.8rem 1rem;
    margin:.4rem 0;
}
.alert-box-high {
    background:#fdf2f8; border:1px solid #f9a8d4;
    border-left:4px solid #ec4899;
    border-radius:8px; padding:.8rem 1rem;
    margin:.4rem 0;
}

.retailer-badge {
    font-size:.8rem; font-weight:600; padding:3px 10px;
    border-radius:6px; display:inline-block;
}
.section-header {
    border-bottom:2px solid #1a1a1a;
    padding-bottom:.4rem;
    margin-bottom:1.2rem;
    font-family:'DM Serif Display',serif;
    font-size:1.4rem;
}
</style>
""", unsafe_allow_html=True)

RETAILER_COLORS = {
    "Continente": "#2563eb",
    "Auchan":     "#7c3aed",
    "PingoDoce":  "#db2777",
}
RETAILER_TAG = {
    "Continente": "tag-cont",
    "Auchan":     "tag-auch",
    "PingoDoce":  "tag-ping",
}

# ── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_data(source):
    """Load from uploaded file or URL."""
    if isinstance(source, BytesIO) or hasattr(source, "read"):
        xl = pd.ExcelFile(source)
    else:
        xl = pd.ExcelFile(source)

    sheets = {}
    for name in ["Continente", "Auchan", "PingoDoce"]:
        if name not in xl.sheet_names:
            continue
        df = xl.parse(name)
        # Identify date columns: start with digit and contain '_'
        meta_cols = ["PID", "Nome", "Marca", "Quantidade"]
        date_cols = [c for c in df.columns if str(c)[0].isdigit() and "_" in str(c)]
        # Parse date part only (drop hour suffix for deduplication)
        date_map = {}
        for col in date_cols:
            date_str = str(col).split("_")[0]
            try:
                date_map[col] = pd.to_datetime(date_str)
            except Exception:
                pass

        # Keep only parseable date cols; collapse duplicate days by taking last non-NaN
        if date_map:
            df_long = df[meta_cols].copy()
            df_long["Retalhista"] = name
            # Build tidy format
            rows = []
            for _, row in df.iterrows():
                for col, dt in date_map.items():
                    val = row[col]
                    if pd.notna(val):
                        rows.append({
                            "PID":        row["PID"],
                            "Nome":       row["Nome"],
                            "Marca":      row["Marca"],
                            "Quantidade": row["Quantidade"],
                            "Retalhista": name,
                            "Data":       dt,
                            "Preco":      float(val),
                        })
            sheets[name] = pd.DataFrame(rows)

    if not sheets:
        return pd.DataFrame()

    df_all = pd.concat(sheets.values(), ignore_index=True)
    df_all["Data"] = pd.to_datetime(df_all["Data"])
    # One price per (PID, Retalhista, Date) — keep last reading of the day
    df_all = df_all.sort_values("Data")
    df_all = df_all.drop_duplicates(subset=["PID","Retalhista","Data"], keep="last")
    return df_all


def badge(retailer):
    color = RETAILER_COLORS.get(retailer, "#666")
    return f'<span class="retailer-badge" style="background:{color}22;color:{color}">{retailer}</span>'


# ── Price classification logic ────────────────────────────────────────────────
from collections import Counter as _Counter

def classify_sku(price_series):
    """Classify a SKU's pricing strategy and detect anomalous new prices."""
    prices = [float(p) for p in price_series if pd.notna(p)]
    n = len(prices)
    if n == 0:
        return {"tipo": "Sem dados", "preco_high": None, "preco_low": None,
                "prof_promo": 0.0, "alerta": None}

    cnt = _Counter(prices)
    unique_prices = sorted(set(prices))

    # ── Preço Único: dominant price ≥ 90% of readings ──
    most_common_count = cnt.most_common(1)[0][1]
    if most_common_count / n >= 0.90 or len(unique_prices) == 1:
        return {"tipo": "Preço Único", "preco_high": max(prices),
                "preco_low": None, "prof_promo": 0.0, "alerta": None}

    # ── High-Low: find established high & low ──
    median_price = float(np.median(prices))
    highs = [p for p in unique_prices if p >= median_price]
    lows  = [p for p in unique_prices if p <  median_price]
    if not lows:
        lows  = [min(unique_prices)]
        highs = [p for p in unique_prices if p > min(unique_prices)]

    est_high = max(highs, key=lambda p: cnt[p])
    est_low  = max(lows,  key=lambda p: cnt[p])

    known = {est_high, est_low}
    new_prices = [p for p in unique_prices if p not in known]

    prof = (1 - est_low / est_high) * 100 if est_high > 0 else 0.0

    alerts = []
    for np_ in new_prices:
        dist_high = abs(np_ - est_high)
        dist_low  = abs(np_ - est_low)
        if np_ > est_high:
            kind = "Novo High ↑"
            old_val = est_high
            new_prof = (1 - est_low / np_) * 100
        elif np_ < est_low:
            kind = "Novo Low ↓"
            old_val = est_low
            new_prof = (1 - np_ / est_high) * 100
        elif dist_low <= dist_high:
            kind = "Novo Low ↓"
            old_val = est_low
            new_prof = (1 - np_ / est_high) * 100
        else:
            kind = "Novo High ↑"
            old_val = est_high
            new_prof = (1 - est_low / np_) * 100
        alerts.append({
            "tipo": kind,
            "preco_anterior": old_val,
            "preco_novo": np_,
            "prof_anterior": round(prof, 1),
            "prof_nova": round(new_prof, 1),
        })

    return {
        "tipo": "High-Low",
        "preco_high": est_high,
        "preco_low":  est_low,
        "prof_promo": round(prof, 1),
        "alerta": alerts if alerts else None,
    }


@st.cache_data(ttl=300)
def build_classifications(df_input):
    """Pre-compute pricing classification for every SKU using full history."""
    records = []
    for (pid, ret), grp in df_input.groupby(["PID", "Retalhista"]):
        grp = grp.sort_values("Data")
        cls = classify_sku(grp["Preco"].tolist())
        row_meta = grp.iloc[0]
        records.append({
            "PID":        pid,
            "Retalhista": ret,
            "Nome":       row_meta["Nome"],
            "Marca":      row_meta["Marca"],
            "Quantidade": row_meta["Quantidade"],
            "Tipo_Preco": cls["tipo"],
            "Preco_High": cls["preco_high"],
            "Preco_Low":  cls["preco_low"],
            "Prof_Promo": cls["prof_promo"],
            "Alertas":    cls["alerta"],        # list or None
        })
    return pd.DataFrame(records)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Configuração")
    st.markdown("---")

    uploaded = st.file_uploader(
        "📂 Carregar ficheiro Excel",
        type=["xlsx"],
        help="Carrega o ficheiro gerado pelo teu script de scraping"
    )

    st.markdown("---")
    st.markdown("**Fonte de dados activa:**")
    if uploaded:
        data_source = BytesIO(uploaded.read())
        st.success("✅ Ficheiro carregado")
    else:
        # Default: load from repo / local sample
        data_source = "precos_CAPD.xlsx"
        st.info("Usando ficheiro de demonstração")

    st.markdown("---")
    st.markdown("**Retalhistas**")
    retailers_sel = st.multiselect(
        "Filtrar por retalhista",
        ["Continente", "Auchan", "PingoDoce"],
        default=["Continente", "Auchan", "PingoDoce"],
    )

    st.markdown("---")
    st.markdown("**Período de análise**")

# ── Load data ─────────────────────────────────────────────────────────────────
try:
    df = load_data(data_source)
except Exception as e:
    st.error(f"Erro ao carregar dados: {e}")
    st.stop()

if df.empty:
    st.warning("Sem dados para apresentar.")
    st.stop()

# Filter retailers
df = df[df["Retalhista"].isin(retailers_sel)]

min_date = df["Data"].min().date()
max_date = df["Data"].max().date()

with st.sidebar:
    date_range = st.date_input(
        "Intervalo de datas",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        d_start, d_end = date_range
    else:
        d_start, d_end = min_date, max_date

    st.markdown("---")
    new_prod_days = st.slider(
        "🆕 Novos produtos: primeiros dados nos últimos N dias",
        min_value=3, max_value=60, value=7, step=1,
    )

df_period = df[(df["Data"].dt.date >= d_start) & (df["Data"].dt.date <= d_end)]

# Build SKU classifications from FULL history (not period-filtered)
sku_cls = build_classifications(df)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<h1 style='font-family:"DM Serif Display",serif; font-size:2.4rem; margin-bottom:.2rem;'>
    Monitoramento de Preços | IceCream Portugal
</h1>
<p style='color:#888; font-size:.95rem; margin-bottom:1.5rem;'>
    Monitorização de preços · Continente · Auchan · Pingo Doce
</p>
""", unsafe_allow_html=True)

# ── KPI row ───────────────────────────────────────────────────────────────────
n_skus   = df_period[["PID","Retalhista"]].drop_duplicates().shape[0]
n_brands = df_period["Marca"].nunique()
n_obs    = len(df_period)
n_days   = (d_end - d_start).days + 1

col1, col2, col3, col4 = st.columns(4)
for col, label, val in [
    (col1, "SKUs monitorizados", n_skus),
    (col2, "Marcas",             n_brands),
    (col3, "Leituras de preço",  f"{n_obs:,}"),
    (col4, "Dias de histórico",  n_days),
]:
    col.markdown(f"""
    <div class="metric-card">
        <h4>{label}</h4>
        <p>{val}</p>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════════════
# TABS
# ════════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3 = st.tabs([
    "🆕 Produtos Novos",
    "📈 Alerta de Mudança de Preço",
    "📋 Todos os Produtos",
])

# ─────────────────────────────────────────────────────────────────
# TAB 1 — NOVOS PRODUTOS
# ─────────────────────────────────────────────────────────────────
with tab1:
    st.markdown('<div class="section-header">🆕 Produtos Novos</div>', unsafe_allow_html=True)
    st.markdown(
        f"Produtos cuja **primeira leitura de preço** ocorreu nos últimos **{new_prod_days} dias** "
        f"(a contar de {max_date})."
    )

    cutoff = pd.Timestamp(max_date) - timedelta(days=new_prod_days)

    # For each (PID, Retalhista) find the very first date with a price
    first_seen = (
        df.groupby(["PID", "Retalhista"])["Data"]
        .min()
        .reset_index()
        .rename(columns={"Data": "Primeira_Leitura"})
    )
    new_products = first_seen[first_seen["Primeira_Leitura"] >= cutoff].copy()

    if new_products.empty:
        st.info(f"Nenhum produto novo nos últimos {new_prod_days} dias.")
    else:
        # Join with latest price
        latest_price = (
            df.sort_values("Data")
            .groupby(["PID","Retalhista"])
            .last()[["Preco","Nome","Marca","Quantidade"]]
            .reset_index()
        )
        new_products = new_products.merge(latest_price, on=["PID","Retalhista"])
        new_products = new_products[new_products["Retalhista"].isin(retailers_sel)]
        new_products = new_products.sort_values(["Primeira_Leitura","Retalhista"], ascending=[False,True])

        st.markdown(f"**{len(new_products)} produto(s) encontrado(s)**")

        for ret in retailers_sel:
            sub = new_products[new_products["Retalhista"] == ret]
            if sub.empty:
                continue
            color = RETAILER_COLORS.get(ret, "#333")
            st.markdown(f"#### {ret} &nbsp; <span style='font-size:.85rem;color:{color}'>{len(sub)} novos</span>", unsafe_allow_html=True)

            display = sub[["PID","Nome","Marca","Quantidade","Preco","Primeira_Leitura"]].copy()
            display.columns = ["ID","Nome","Marca","Quantidade","Preço atual (€)","1ª Leitura"]
            display["1ª Leitura"] = display["1ª Leitura"].dt.strftime("%d/%m/%Y")
            display["Preço atual (€)"] = display["Preço atual (€)"].map("{:.2f} €".format)
            st.dataframe(display, use_container_width=True, hide_index=True)

    # Chart: timeline of first appearances
    if not first_seen.empty:
        st.markdown("#### Histórico de entrada de novos produtos")
        timeline = first_seen.copy()
        timeline["Semana"] = timeline["Primeira_Leitura"].dt.to_period("W").dt.start_time
        weekly = (
            timeline.groupby(["Semana","Retalhista"])
            .size()
            .reset_index(name="Novos SKUs")
        )
        fig = px.bar(
            weekly,
            x="Semana", y="Novos SKUs", color="Retalhista",
            color_discrete_map=RETAILER_COLORS,
            barmode="group",
            template="plotly_white",
        )
        fig.update_layout(legend_title_text="", height=320, margin=dict(t=20,b=20))
        st.plotly_chart(fig, use_container_width=True, key="chart_1")

# ─────────────────────────────────────────────────────────────────
# TAB 2 — ALERTA DE MUDANÇA DE PREÇO
# ─────────────────────────────────────────────────────────────────
with tab2:
    st.markdown('<div class="section-header">📈 Alerta de Mudança de Preço</div>', unsafe_allow_html=True)
    st.markdown("Classificação de estratégia de preço e alertas de novos High/Low detectados no histórico completo.")

    # ── Filters ──
    fa2, fb2, fc2 = st.columns([1, 1, 2])
    with fa2:
        ret_filter_tab2 = st.multiselect("Retalhista", retailers_sel, default=retailers_sel, key="ret_tab2")
    with fb2:
        brand_filter_tab2 = st.multiselect("Marca", sorted(sku_cls["Marca"].dropna().unique()), key="brand_tab2")
    with fc2:
        search_tab2 = st.text_input("🔎 Pesquisar por nome", placeholder="ex: Ben & Jerry's", key="search_tab2")

    ca2, cb2 = st.columns(2)
    with ca2:
        show_alerts_only = st.checkbox("🚨 Apenas SKUs com alertas (Novo High / Novo Low)", value=False)
    with cb2:
        show_hl_only = st.checkbox("🔁 Apenas SKUs High-Low", value=False)

    # ── Apply filters ──
    RETAILER_ORDER = ["Continente", "PingoDoce", "Auchan"]
    cls_filtered = sku_cls.copy()
    if ret_filter_tab2:
        cls_filtered = cls_filtered[cls_filtered["Retalhista"].isin(ret_filter_tab2)]
    if brand_filter_tab2:
        cls_filtered = cls_filtered[cls_filtered["Marca"].isin(brand_filter_tab2)]
    if search_tab2:
        cls_filtered = cls_filtered[cls_filtered["Nome"].str.contains(search_tab2, case=False, na=False)]
    if show_alerts_only:
        cls_filtered = cls_filtered[cls_filtered["Alertas"].notna()]
    if show_hl_only:
        cls_filtered = cls_filtered[cls_filtered["Tipo_Preco"] == "High-Low"]

    cls_filtered["_ro"] = cls_filtered["Retalhista"].map({r: i for i, r in enumerate(RETAILER_ORDER)}).fillna(99)
    cls_filtered = cls_filtered.sort_values(["_ro", "Marca", "Nome"]).drop(columns=["_ro"])

    # ── Summary KPIs ──
    n_pu    = (cls_filtered["Tipo_Preco"] == "Preço Único").sum()
    n_hl    = (cls_filtered["Tipo_Preco"] == "High-Low").sum()
    n_alert = cls_filtered["Alertas"].notna().sum()

    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(f'<div class="metric-card"><h4>Total SKUs</h4><p>{len(cls_filtered)}</p></div>', unsafe_allow_html=True)
    k2.markdown(f'<div class="metric-card" style="border-color:#0284c7"><h4>Preço Único</h4><p>{n_pu}</p></div>', unsafe_allow_html=True)
    k3.markdown(f'<div class="metric-card" style="border-color:#d97706"><h4>High-Low</h4><p>{n_hl}</p></div>', unsafe_allow_html=True)
    k4.markdown(f'<div class="metric-card" style="border-color:#dc2626"><h4>Com Alertas</h4><p>{n_alert}</p></div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Display grouped by retailer ──
    current_ret2 = None
    for _, row in cls_filtered.iterrows():
        if row["Retalhista"] != current_ret2:
            current_ret2 = row["Retalhista"]
            color = RETAILER_COLORS.get(current_ret2, "#333")
            sub_ret = cls_filtered[cls_filtered["Retalhista"] == current_ret2]
            st.markdown(f"#### {current_ret2} &nbsp; <span style='font-size:.85rem;color:{color}'>{len(sub_ret)} SKUs</span>", unsafe_allow_html=True)

        tipo = row["Tipo_Preco"]
        alertas = row["Alertas"]
        has_alert = alertas is not None and len(alertas) > 0

        # Build expander label with badges
        tipo_badge = (
            '<span class="tag tag-pu">💰 Preço Único</span>'
            if tipo == "Preço Único"
            else '<span class="tag tag-hl">🔁 High-Low</span>'
        )
        alert_badge = '<span class="tag tag-alert">🚨 Alerta</span>' if has_alert else ""
        expander_label = f"{row['Nome']} — {row['Marca']} | {tipo}"
        if has_alert:
            expander_label += "  ⚠️"

        with st.expander(expander_label, expanded=has_alert):
            # ── Metrics row ──
            if tipo == "Preço Único":
                m1, m2, m3 = st.columns(3)
                m1.metric("Estratégia", "Preço Único")
                m2.metric("Preço", f"{row['Preco_High']:.2f} €" if row['Preco_High'] else "—")
                m3.metric("Prof. Promo", "0%")
            else:
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Estratégia", "High-Low")
                m2.metric("High (sem promo)", f"{row['Preco_High']:.2f} €" if row['Preco_High'] else "—")
                m3.metric("Low (com promo)", f"{row['Preco_Low']:.2f} €" if row['Preco_Low'] else "—")
                m4.metric("Prof. Promocional", f"{row['Prof_Promo']:.1f}%")

            # ── Alert boxes ──
            if has_alert:
                st.markdown("**Alertas detectados:**")
                for al in alertas:
                    is_high = "High" in al["tipo"]
                    box_class = "alert-box-high" if is_high else "alert-box"
                    icon = "📈" if is_high else "📉"
                    direction = "subida" if is_high else "redução"
                    prof_delta = al["prof_nova"] - al["prof_anterior"]
                    prof_txt = (
                        f"+{prof_delta:.1f}pp (profundidade aumentou)" if prof_delta > 0
                        else f"{prof_delta:.1f}pp (profundidade reduziu)"
                    )
                    st.markdown(f"""
<div class="{box_class}">
{icon} <strong>{al["tipo"]}</strong> — {direction} de preço detectada<br>
&nbsp;&nbsp;Preço anterior: <strong>{al["preco_anterior"]:.2f} €</strong> → Novo preço: <strong>{al["preco_novo"]:.2f} €</strong><br>
&nbsp;&nbsp;Prof. promo anterior: <strong>{al["prof_anterior"]:.1f}%</strong> → Nova: <strong>{al["prof_nova"]:.1f}%</strong> &nbsp; <em>({prof_txt})</em>
</div>""", unsafe_allow_html=True)

            # ── Price history chart ──
            sub_hist = df[(df["PID"] == row["PID"]) & (df["Retalhista"] == row["Retalhista"])].sort_values("Data")
            if len(sub_hist) > 1:
                fig = go.Figure()
                # Add shaded bands for High and Low
                if tipo == "High-Low" and row["Preco_High"] and row["Preco_Low"]:
                    fig.add_hrect(y0=row["Preco_Low"]*0.99, y1=row["Preco_High"]*1.01,
                                  fillcolor="rgba(234,179,8,0.07)", line_width=0,
                                  annotation_text="range H-L", annotation_position="top right")
                    fig.add_hline(y=row["Preco_High"], line_dash="dot",
                                  line_color="rgba(220,38,38,0.5)", annotation_text=f"High {row['Preco_High']:.2f}€")
                    fig.add_hline(y=row["Preco_Low"],  line_dash="dot",
                                  line_color="rgba(22,163,74,0.5)",  annotation_text=f"Low {row['Preco_Low']:.2f}€")
                fig.add_trace(go.Scatter(
                    x=sub_hist["Data"], y=sub_hist["Preco"],
                    mode="lines+markers",
                    line=dict(color=RETAILER_COLORS.get(row["Retalhista"], "#333"), width=2),
                    marker=dict(size=6),
                    name="Preço",
                ))
                # Mark anomalous prices
                if has_alert:
                    alert_prices = {al["preco_novo"] for al in alertas}
                    anomaly = sub_hist[sub_hist["Preco"].isin(alert_prices)]
                    if not anomaly.empty:
                        fig.add_trace(go.Scatter(
                            x=anomaly["Data"], y=anomaly["Preco"],
                            mode="markers",
                            marker=dict(size=12, color="#f59e0b", symbol="diamond",
                                        line=dict(color="#1a1a1a", width=1.5)),
                            name="Preço novo",
                        ))
                fig.update_layout(
                    height=220, margin=dict(t=20,b=10,l=10,r=10),
                    yaxis_title="€", xaxis_title="",
                    template="plotly_white",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                )
                st.plotly_chart(fig, use_container_width=True, key=f"chart_tab2_{row['PID']}_{row['Retalhista']}")

# ─────────────────────────────────────────────────────────────────
# TAB 3 — TODOS OS PRODUTOS
# ─────────────────────────────────────────────────────────────────
with tab3:
    st.markdown('<div class="section-header">📋 Todos os Produtos</div>', unsafe_allow_html=True)
    st.markdown("Catálogo completo com histórico de preços e profundidade promocional.")

    # ── Filters ──
    fa, fb, fc, fd = st.columns(4)
    with fa:
        f_ret = st.multiselect("Retalhista", retailers_sel, default=retailers_sel, key="f_ret_all")
    with fb:
        all_brands = sorted(df["Marca"].dropna().unique())
        f_brand = st.multiselect("Marca", all_brands, key="f_brand_all")
    with fc:
        all_sizes = sorted(df["Quantidade"].dropna().astype(str).unique())
        f_size = st.multiselect("Tamanho", all_sizes, key="f_size_all")
    with fd:
        all_min = df["Data"].min().date()
        all_max = df["Data"].max().date()
        f_period = st.date_input("Período histórico", value=(all_min, all_max),
                                  min_value=all_min, max_value=all_max, key="f_period_all")
        if isinstance(f_period, (list, tuple)) and len(f_period) == 2:
            fp_start, fp_end = f_period
        else:
            fp_start, fp_end = all_min, all_max

    f_search = st.text_input("🔎 Pesquisar por nome", placeholder="ex: Häagen-Dazs, Cornetto…", key="search_all")

    # ── Filter data ──
    df_all_f = df[(df["Data"].dt.date >= fp_start) & (df["Data"].dt.date <= fp_end)].copy()
    if f_ret:
        df_all_f = df_all_f[df_all_f["Retalhista"].isin(f_ret)]
    if f_brand:
        df_all_f = df_all_f[df_all_f["Marca"].isin(f_brand)]
    if f_size:
        df_all_f = df_all_f[df_all_f["Quantidade"].astype(str).isin(f_size)]
    if f_search:
        df_all_f = df_all_f[df_all_f["Nome"].str.contains(f_search, case=False, na=False)]

    # ── Aggregate ──
    all_summary = (
        df_all_f.groupby(["PID","Retalhista","Nome","Marca","Quantidade"])["Preco"]
        .agg(
            Preco_Atual="last",
            Preco_Min="min",
            Preco_Max="max",
            Leituras="count",
        )
        .reset_index()
    )
    # Merge classification from full-history sku_cls
    cls_merge = sku_cls[["PID","Retalhista","Tipo_Preco","Preco_High","Preco_Low","Prof_Promo","Alertas"]]
    all_summary = all_summary.merge(cls_merge, on=["PID","Retalhista"], how="left")

    # Profundidade promocional: use classify_sku Prof_Promo; fallback to period calc
    all_summary["Prof_Promo_Pct"] = all_summary["Prof_Promo"].fillna(
        ((1 - all_summary["Preco_Min"] / all_summary["Preco_Max"]) * 100).round(1)
    )
    all_summary["Prof_Promo_Pct"] = all_summary["Prof_Promo_Pct"].round(1)
    all_summary["Tem_Alerta"] = all_summary["Alertas"].notna()

    # Sort: retailer order then brand then name
    RET_ORD = ["Continente", "PingoDoce", "Auchan"]
    all_summary["_ro"] = all_summary["Retalhista"].map({r: i for i, r in enumerate(RET_ORD)}).fillna(99)
    all_summary = all_summary.sort_values(["_ro", "Marca", "Nome"]).drop(columns=["_ro"])

    st.markdown(f"**{len(all_summary)} produto(s)** encontrado(s)")

    # Display by retailer
    for ret in RET_ORD:
        sub = all_summary[all_summary["Retalhista"] == ret]
        if sub.empty:
            continue
        color = RETAILER_COLORS.get(ret, "#333")
        st.markdown(f"#### {ret} &nbsp; <span style='font-size:.85rem;color:{color}'>{len(sub)} SKUs</span>", unsafe_allow_html=True)

        display_all = sub[["PID","Nome","Marca","Quantidade","Tipo_Preco","Preco_Atual","Preco_Min","Preco_Max","Prof_Promo_Pct","Tem_Alerta","Leituras"]].copy()
        display_all.columns = ["ID","Nome","Marca","Tamanho","Estratégia","Preço Atual (€)","Preço Mín (€)","Preço Máx (€)","Prof. Promo (%)","Alerta","Leituras"]
        display_all["Preço Atual (€)"] = display_all["Preço Atual (€)"].map("{:.2f}".format)
        display_all["Preço Mín (€)"]   = display_all["Preço Mín (€)"].map("{:.2f}".format)
        display_all["Preço Máx (€)"]   = display_all["Preço Máx (€)"].map("{:.2f}".format)
        display_all["Prof. Promo (%)"] = display_all["Prof. Promo (%)"].apply(
            lambda x: f"{x:.1f}%" if x > 0 else "—"
        )
        display_all["Estratégia"] = display_all["Estratégia"].fillna("—")
        display_all["Alerta"] = display_all["Alerta"].apply(lambda x: "🚨 Sim" if x else "")
        st.dataframe(display_all, use_container_width=True, hide_index=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<p style='text-align:center;color:#bbb;font-size:.8rem;'>"
    "Monitoramento de Preços IceCream Portugal · Actualizado automaticamente com o ficheiro Excel do scraper"
    "</p>",
    unsafe_allow_html=True,
)
