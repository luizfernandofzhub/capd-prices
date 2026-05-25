import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px
from io import BytesIO
from collections import Counter as _Counter

st.set_page_config(
    page_title="Monitoramento de Preços | IceCream Portugal",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'DM Serif Display', serif; }
.main { background: #f7f5f0; }
.block-container { padding: 1.5rem 2.5rem 3rem; }

/* ── Slim KPI bar ── */
.kpi-bar {
    display:flex; gap:1rem; margin-bottom:1rem;
}
.kpi-item {
    background:white; border-radius:8px;
    padding:.45rem 1rem; flex:1;
    border-left:3px solid #1a1a1a;
    box-shadow:0 1px 3px rgba(0,0,0,.06);
}
.kpi-item h4 { margin:0; font-size:.65rem; color:#999; letter-spacing:.07em; text-transform:uppercase; }
.kpi-item p  { margin:.1rem 0 0; font-size:1.3rem; font-weight:700; color:#1a1a1a; }

/* ── Alert tags ── */
.tag { display:inline-block; padding:1px 8px; border-radius:20px; font-size:.68rem; font-weight:700; margin:1px; white-space:nowrap; }
.tag-pu       { background:#e0f2fe; color:#0c4a6e; }
.tag-hl       { background:#fef3c7; color:#92400e; }
.tag-alert    { background:#fee2e2; color:#991b1b; }
.tag-new-h    { background:#fdf2f8; color:#9d174d; }
.tag-new-l    { background:#fefce8; color:#713f12; }
.tag-new-hl   { background:#f3e8ff; color:#6b21a8; }
.tag-cont     { background:#dbeafe; color:#1e40af; }
.tag-auch     { background:#ede9fe; color:#5b21b6; }
.tag-ping     { background:#fce7f3; color:#9d174d; }

.retailer-badge { font-size:.78rem; font-weight:600; padding:2px 9px; border-radius:5px; display:inline-block; }
.section-header { border-bottom:2px solid #1a1a1a; padding-bottom:.3rem; margin-bottom:1rem;
                  font-family:'DM Serif Display',serif; font-size:1.35rem; }

/* ── Brand summary table ── */
.brand-table { width:100%; border-collapse:collapse; font-size:.82rem; margin-bottom:1rem; }
.brand-table th { background:#f1f5f9; padding:5px 10px; text-align:left; font-weight:600; border-bottom:2px solid #e2e8f0; }
.brand-table td { padding:4px 10px; border-bottom:1px solid #f1f5f9; }
.brand-table tr:hover td { background:#fafafa; }

/* ── Alert pill ── */
.pill-high { background:#fdf2f8; color:#9d174d; border:1px solid #f9a8d4; padding:2px 9px; border-radius:20px; font-size:.7rem; font-weight:700; display:inline-block; }
.pill-low  { background:#fffbeb; color:#92400e; border:1px solid #fcd34d; padding:2px 9px; border-radius:20px; font-size:.7rem; font-weight:700; display:inline-block; }
.pill-both { background:#f3e8ff; color:#6b21a8; border:1px solid #d8b4fe; padding:2px 9px; border-radius:20px; font-size:.7rem; font-weight:700; display:inline-block; }
</style>
""", unsafe_allow_html=True)

RETAILER_COLORS = {"Continente":"#2563eb","Auchan":"#7c3aed","PingoDoce":"#db2777"}
RETAILER_ORDER  = ["Continente","PingoDoce","Auchan"]

def badge(retailer):
    color = RETAILER_COLORS.get(retailer,"#666")
    return f'<span class="retailer-badge" style="background:{color}22;color:{color}">{retailer}</span>'

# ── Data loading ───────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_data(source):
    xl = pd.ExcelFile(source)
    sheets = {}
    for name in ["Continente","Auchan","PingoDoce"]:
        if name not in xl.sheet_names: continue
        df = xl.parse(name)
        meta_cols = ["PID","Nome","Marca","Quantidade"]
        date_map = {}
        for col in df.columns:
            if str(col)[0].isdigit() and "_" in str(col):
                try: date_map[col] = pd.to_datetime(str(col).split("_")[0])
                except: pass
        rows = []
        for _, row in df.iterrows():
            formato = row["Formato"] if "Formato" in df.columns and pd.notna(row.get("Formato")) else None
            for col, dt in date_map.items():
                val = row[col]
                if pd.notna(val):
                    rows.append({"PID":row["PID"],"Nome":row["Nome"],"Marca":row["Marca"],
                                 "Quantidade":row["Quantidade"],"Formato":formato,
                                 "Retalhista":name,"Data":dt,"Preco":float(val)})
        sheets[name] = pd.DataFrame(rows)
    if not sheets: return pd.DataFrame()
    df_all = pd.concat(sheets.values(), ignore_index=True)
    df_all["Data"] = pd.to_datetime(df_all["Data"])
    df_all = df_all.sort_values("Data").drop_duplicates(subset=["PID","Retalhista","Data"], keep="last")
    return df_all

GLOSSARIO_KEY = "glossario_formato_v1"
FORMATO_OPTIONS = ["Bars","Bites","Bites - PromoPack","Cakes","Cones","Cups",
                   "Frozen Fruits","Other","Pints","Pints - PromoPack",
                   "Pots","Sandwich","Sticks","Tubs"]

def load_glossario():
    """Load the persisted glossário from session_state (backed by st.cache_resource trick).
    Returns a dict {'PID_Retalhista': 'Formato'}."""
    if GLOSSARIO_KEY not in st.session_state:
        st.session_state[GLOSSARIO_KEY] = {}
    return st.session_state[GLOSSARIO_KEY]

def save_glossario(glossario_dict):
    """Save the glossário dict back to session_state."""
    st.session_state[GLOSSARIO_KEY] = glossario_dict

def glossario_to_df(glossario_dict):
    """Convert glossário dict to a PID/Retalhista/Formato DataFrame."""
    rows = []
    for key, fmt in glossario_dict.items():
        parts = key.rsplit("_", 1)
        if len(parts) == 2:
            rows.append({"PID": parts[0], "Retalhista": parts[1], "Formato": fmt})
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["PID","Retalhista","Formato"])

def import_glossario_csv(uploaded_csv):
    """Import a glossário CSV and merge into the persisted dict."""
    try:
        df_csv = pd.read_csv(uploaded_csv)
        df_csv["PID"] = df_csv["PID"].astype(str)
        glossario = load_glossario()
        imported = 0
        for _, row in df_csv.iterrows():
            if pd.notna(row.get("Formato")) and str(row.get("Formato","")) not in ("","nan"):
                key = f"{row['PID']}_{row['Retalhista']}"
                glossario[key] = str(row["Formato"])
                imported += 1
        save_glossario(glossario)
        return imported
    except Exception as e:
        return f"Erro: {e}"

@st.cache_data(ttl=300)
def load_sku_list_from_excel(source):
    """Load only the meta columns (PID, Nome, Marca, Quantidade) from the Excel.
    Does NOT require a Formato column — that comes from the glossário."""
    xl = pd.ExcelFile(source)
    frames = []
    for name in ["Continente","Auchan","PingoDoce"]:
        if name not in xl.sheet_names: continue
        df_raw = xl.parse(name)
        meta_cols = [c for c in ["PID","Nome","Marca","Quantidade"] if c in df_raw.columns]
        meta = df_raw[meta_cols].copy()
        meta["PID"] = meta["PID"].astype(str)
        meta["Retalhista"] = name
        frames.append(meta)
    if not frames:
        return pd.DataFrame(columns=["PID","Retalhista","Nome","Marca","Quantidade"])
    df_meta = pd.concat(frames, ignore_index=True)
    df_meta = df_meta.drop_duplicates(subset=["PID","Retalhista"])
    return df_meta

def build_formato_lookup(glossario_dict, sku_list_df):
    """Merge glossário into the SKU list to produce the final PID/Retalhista/Formato table."""
    gl_df = glossario_to_df(glossario_dict)
    if gl_df.empty:
        result = sku_list_df[["PID","Retalhista"]].copy()
        result["Formato"] = None
        return result
    merged = sku_list_df[["PID","Retalhista"]].merge(gl_df, on=["PID","Retalhista"], how="left")
    return merged


# ── Classification logic ───────────────────────────────────────────────────────
def classify_sku(price_series, outlier_min_count=3, outlier_min_pct=5.0):
    prices = [float(p) for p in price_series if pd.notna(p)]
    n = len(prices)
    if n == 0:
        return {"tipo":"Sem dados","preco_high":None,"preco_low":None,"prof_promo":0.0,"alerta":None}
    cnt = _Counter(prices)
    unique_prices = sorted(set(prices))
    most_common_count = cnt.most_common(1)[0][1]
    if most_common_count/n >= 0.90 or len(unique_prices) == 1:
        return {"tipo":"Preço Único","preco_high":max(prices),"preco_low":None,"prof_promo":0.0,"alerta":None}
    median_p = float(np.median(prices))
    highs = [p for p in unique_prices if p >= median_p]
    lows  = [p for p in unique_prices if p <  median_p]
    if not lows:
        lows  = [min(unique_prices)]
        highs = [p for p in unique_prices if p > min(unique_prices)]
    est_high = max(highs, key=lambda p: cnt[p])
    est_low  = max(lows,  key=lambda p: cnt[p])
    known = {est_high, est_low}
    prof = (1 - est_low/est_high)*100 if est_high > 0 else 0.0
    alerts = []
    for np_ in unique_prices:
        if np_ in known: continue
        cnt_p = cnt[np_]
        pct_p = cnt_p/n*100
        # Outlier filter: must appear ≥ outlier_min_count times AND ≥ outlier_min_pct of readings
        if cnt_p < outlier_min_count or pct_p < outlier_min_pct: continue
        dist_high = abs(np_ - est_high)
        dist_low  = abs(np_ - est_low)
        if np_ > est_high:
            kind = "Novo High ↑"; old_val = est_high; new_prof = (1-est_low/np_)*100
        elif np_ < est_low:
            kind = "Novo Low ↓";  old_val = est_low;  new_prof = (1-np_/est_high)*100
        elif dist_low <= dist_high:
            kind = "Novo Low ↓";  old_val = est_low;  new_prof = (1-np_/est_high)*100
        else:
            kind = "Novo High ↑"; old_val = est_high; new_prof = (1-est_low/np_)*100
        alerts.append({"tipo":kind,"preco_anterior":old_val,"preco_novo":np_,
                        "prof_anterior":round(prof,1),"prof_nova":round(new_prof,1),
                        "n_leituras":cnt_p,"pct_leituras":round(pct_p,1)})
    return {"tipo":"High-Low","preco_high":est_high,"preco_low":est_low,
            "prof_promo":round(prof,1),"alerta":alerts if alerts else None}

@st.cache_data(ttl=300)
def build_classifications(df_input):
    records = []
    for (pid, ret), grp in df_input.groupby(["PID","Retalhista"]):
        grp = grp.sort_values("Data")
        cls = classify_sku(grp["Preco"].tolist())
        m = grp.iloc[0]
        has_high = cls["alerta"] and any("High" in a["tipo"] for a in cls["alerta"])
        has_low  = cls["alerta"] and any("Low"  in a["tipo"] for a in cls["alerta"])
        alert_label = None
        if has_high and has_low: alert_label = "Novo High+Low"
        elif has_high:           alert_label = "Novo High"
        elif has_low:            alert_label = "Novo Low"
        fmt = m.get("Formato") if hasattr(m, "get") else (m["Formato"] if "Formato" in m.index else None)
        records.append({
            "PID":m["PID"],"Retalhista":ret,"Nome":m["Nome"],"Marca":m["Marca"],
            "Quantidade":m["Quantidade"],"Formato":fmt,"Tipo_Preco":cls["tipo"],
            "Preco_High":cls["preco_high"],"Preco_Low":cls["preco_low"],
            "Prof_Promo":cls["prof_promo"],"Alertas":cls["alerta"],
            "Alert_Label":alert_label,
        })
    return pd.DataFrame(records)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Configuração")
    st.markdown("---")
    uploaded = st.file_uploader("📂 Carregar ficheiro Excel", type=["xlsx"])
    st.markdown("---")
    st.markdown("**Fonte de dados activa:**")
    if uploaded:
        data_source = BytesIO(uploaded.read()); st.success("✅ Ficheiro carregado")
    else:
        data_source = "precos_CAPD.xlsx"; st.info("Usando ficheiro de demonstração")
    st.markdown("---")
    st.markdown("**Retalhistas**")
    retailers_sel = st.multiselect("Filtrar por retalhista",["Continente","Auchan","PingoDoce"],
                                    default=["Continente","Auchan","PingoDoce"])
    st.markdown("---")
    st.markdown("**Período de análise**")

try:
    df = load_data(data_source)
except Exception as e:
    st.error(f"Erro ao carregar dados: {e}"); st.stop()
if df.empty:
    st.warning("Sem dados para apresentar."); st.stop()

df = df[df["Retalhista"].isin(retailers_sel)]
min_date = df["Data"].min().date()
max_date = df["Data"].max().date()

with st.sidebar:
    date_range = st.date_input("Intervalo de datas", value=(min_date,max_date),
                                min_value=min_date, max_value=max_date)
    d_start, d_end = (date_range[0], date_range[1]) if len(date_range)==2 else (min_date, max_date)
    st.markdown("---")
    new_prod_days = st.slider("🆕 Novos produtos: últimos N dias", min_value=3, max_value=60, value=7)

df_period = df[(df["Data"].dt.date >= d_start) & (df["Data"].dt.date <= d_end)]
sku_cls   = build_classifications(df)

# ── Formato lookup — built from glossário + SKU list ─────────────────────
df_sku_list   = load_sku_list_from_excel(data_source)
_glossario    = load_glossario()
df_fmt_lookup = build_formato_lookup(_glossario, df_sku_list)

# ── SKU static metadata (one row per PID×Retalhista, with Formato) ──────
df_sku_meta = (df.sort_values("Data")
               .drop_duplicates(subset=["PID","Retalhista"], keep="last")
               [["PID","Retalhista","Nome","Marca","Quantidade","Formato"]])

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("""
<h1 style='font-family:"DM Serif Display",serif;font-size:2.2rem;margin-bottom:.1rem;'>
    Monitoramento de Preços | IceCream Portugal
</h1>
<p style='color:#888;font-size:.88rem;margin-bottom:.8rem;'>
    Monitorização de preços · Continente · Auchan · Pingo Doce
</p>""", unsafe_allow_html=True)

# ── Slim KPI bar ───────────────────────────────────────────────────────────────
n_skus   = df_period[["PID","Retalhista"]].drop_duplicates().shape[0]
n_brands = df_period["Marca"].nunique()
n_obs    = len(df_period)
n_days   = (d_end - d_start).days + 1
n_alerts = sku_cls[sku_cls["Retalhista"].isin(retailers_sel)]["Alert_Label"].notna().sum()

st.markdown(f"""
<div class="kpi-bar">
  <div class="kpi-item"><h4>SKUs monitorizados</h4><p>{n_skus}</p></div>
  <div class="kpi-item"><h4>Marcas</h4><p>{n_brands}</p></div>
  <div class="kpi-item"><h4>Leituras de preço</h4><p>{n_obs:,}</p></div>
  <div class="kpi-item"><h4>Dias de histórico</h4><p>{n_days}</p></div>
  <div class="kpi-item" style="border-color:#dc2626"><h4>SKUs com alerta</h4><p style="color:#dc2626">{n_alerts}</p></div>
</div>
""", unsafe_allow_html=True)

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🆕 Produtos Novos",
    "📈 Alerta de Mudança de Preço",
    "📋 Todos os Produtos",
    "📊 Evolução de Preços",
    "🏷️ SKUs não classificados",
])

# ═══════════════════════════════════════════════════════════════════
# TAB 1 — NOVOS PRODUTOS
# ═══════════════════════════════════════════════════════════════════
with tab1:
    st.markdown('<div class="section-header">🆕 Produtos Novos</div>', unsafe_allow_html=True)
    st.markdown(f"Produtos cuja **primeira leitura** ocorreu nos últimos **{new_prod_days} dias** (a contar de {max_date}).")
    cutoff = pd.Timestamp(max_date) - timedelta(days=new_prod_days)
    first_seen = df.groupby(["PID","Retalhista"])["Data"].min().reset_index().rename(columns={"Data":"Primeira_Leitura"})
    new_products = first_seen[first_seen["Primeira_Leitura"] >= cutoff].copy()
    if new_products.empty:
        st.info(f"Nenhum produto novo nos últimos {new_prod_days} dias.")
    else:
        latest_price = df.sort_values("Data").groupby(["PID","Retalhista"]).last()[["Preco","Nome","Marca","Quantidade"]].reset_index()
        new_products = new_products.merge(latest_price, on=["PID","Retalhista"])
        new_products = new_products[new_products["Retalhista"].isin(retailers_sel)]
        new_products = new_products.sort_values(["Primeira_Leitura","Retalhista"], ascending=[False,True])
        # Add Formato from static lookup
        new_products["PID"] = new_products["PID"].astype(str)
        new_products = new_products.merge(df_fmt_lookup, on=["PID","Retalhista"], how="left")
        st.markdown(f"**{len(new_products)} produto(s) encontrado(s)**")
        for ret in RETAILER_ORDER:
            sub = new_products[new_products["Retalhista"]==ret]
            if sub.empty: continue
            color = RETAILER_COLORS.get(ret,"#333")
            st.markdown(f"#### {ret} &nbsp; <span style='font-size:.85rem;color:{color}'>{len(sub)} novos</span>", unsafe_allow_html=True)
            d = sub[["PID","Nome","Marca","Quantidade","Formato","Preco","Primeira_Leitura"]].copy()
            d.columns = ["ID","Nome","Marca","Quantidade","Formato","Preço atual (€)","1ª Leitura"]
            d["Formato"] = d["Formato"].fillna("—")
            d["1ª Leitura"] = d["1ª Leitura"].dt.strftime("%d/%m/%Y")
            d["Preço atual (€)"] = d["Preço atual (€)"].map("{:.2f} €".format)
            st.dataframe(d, use_container_width=True, hide_index=True)
    if not first_seen.empty:
        st.markdown("#### Histórico de entrada de novos produtos")
        tl = first_seen.copy()
        tl["Semana"] = tl["Primeira_Leitura"].dt.to_period("W").dt.start_time
        weekly = tl.groupby(["Semana","Retalhista"]).size().reset_index(name="Novos SKUs")
        fig = px.bar(weekly, x="Semana", y="Novos SKUs", color="Retalhista",
                     color_discrete_map=RETAILER_COLORS, barmode="group", template="plotly_white")
        fig.update_layout(legend_title_text="", height=300, margin=dict(t=20,b=20))
        st.plotly_chart(fig, use_container_width=True, key="chart_tab1_timeline")

# ═══════════════════════════════════════════════════════════════════
# TAB 2 — ALERTA DE MUDANÇA DE PREÇO
# ═══════════════════════════════════════════════════════════════════
with tab2:
    st.markdown('<div class="section-header">📈 Alerta de Mudança de Preço</div>', unsafe_allow_html=True)

    # ── Filters ──
    f2a, f2b, f2c, f2e, f2d = st.columns([1,1,1,1,2])
    with f2a:
        ret2 = st.multiselect("Retalhista", retailers_sel, default=retailers_sel, key="ret2")
    with f2b:
        brand2 = st.multiselect("Marca", sorted(sku_cls["Marca"].dropna().unique()), key="brand2")
    with f2c:
        tipo2 = st.multiselect("Estratégia", ["Preço Único","High-Low"], default=["Preço Único","High-Low"], key="tipo2")
    with f2e:
        fmt2_opts = sorted(df_fmt_lookup["Formato"].dropna().unique()) if not df_fmt_lookup.empty else []
        fmt2 = st.multiselect("Formato", fmt2_opts, key="fmt2")
    with f2d:
        search2 = st.text_input("🔎 Pesquisar por nome", placeholder="ex: Ben & Jerry's", key="search2")

    col_chk1, col_chk2 = st.columns(2)
    with col_chk1:
        only_alerts2 = st.checkbox("🚨 Apenas SKUs com alertas", value=False, key="chk_alerts2")
    with col_chk2:
        alert_type2 = st.multiselect("Tipo de alerta", ["Novo High","Novo Low","Novo High+Low"], key="alert_type2")

    # ── Filter ──
    cf = sku_cls[sku_cls["Retalhista"].isin(ret2 or retailers_sel)].copy()
    if brand2:  cf = cf[cf["Marca"].isin(brand2)]
    if tipo2:   cf = cf[cf["Tipo_Preco"].isin(tipo2)]
    if search2: cf = cf[cf["Nome"].str.contains(search2, case=False, na=False)]
    if only_alerts2: cf = cf[cf["Alert_Label"].notna()]
    if alert_type2:  cf = cf[cf["Alert_Label"].isin(alert_type2)]
    if fmt2:         cf = cf[cf["Formato"].isin(fmt2)]
    cf["_ro"] = cf["Retalhista"].map({r:i for i,r in enumerate(RETAILER_ORDER)}).fillna(99)
    cf = cf.sort_values(["_ro","Marca","Nome"]).drop(columns=["_ro"])
    # Ensure Formato is in cf (always merge from static lookup)
    cf["PID"] = cf["PID"].astype(str)
    if "Formato" in cf.columns:
        cf = cf.drop(columns=["Formato"])
    cf = cf.merge(df_fmt_lookup, on=["PID","Retalhista"], how="left")

    # ── KPIs ──
    n_pu2 = (cf["Tipo_Preco"]=="Preço Único").sum()
    n_hl2 = (cf["Tipo_Preco"]=="High-Low").sum()
    n_al2 = cf["Alert_Label"].notna().sum()
    st.markdown(f"""
<div class="kpi-bar">
  <div class="kpi-item"><h4>Total SKUs</h4><p>{len(cf)}</p></div>
  <div class="kpi-item" style="border-color:#0284c7"><h4>💰 Preço Único</h4><p style="color:#0284c7">{n_pu2}</p></div>
  <div class="kpi-item" style="border-color:#d97706"><h4>🔁 High-Low</h4><p style="color:#d97706">{n_hl2}</p></div>
  <div class="kpi-item" style="border-color:#dc2626"><h4>🚨 Com Alertas</h4><p style="color:#dc2626">{n_al2}</p></div>
</div>""", unsafe_allow_html=True)

    # ── Brand summary table ──
    for ret in RETAILER_ORDER:
        sub_ret = cf[cf["Retalhista"]==ret]
        if sub_ret.empty: continue
        color = RETAILER_COLORS.get(ret,"#333")
        st.markdown(f"### {ret}", unsafe_allow_html=True)

        # Brand summary
        brand_summary = sub_ret.groupby("Marca").agg(
            SKUs=("PID","count"),
            Alertas=("Alert_Label", lambda x: x.notna().sum())
        ).reset_index().sort_values("Alertas", ascending=False)
        rows_html = ""
        for _, br in brand_summary.iterrows():
            alert_cell = f'<span style="color:#dc2626;font-weight:700">{int(br["Alertas"])}</span>' if br["Alertas"]>0 else "—"
            rows_html += f'<tr><td>{br["Marca"]}</td><td>{int(br["SKUs"])}</td><td>{alert_cell}</td></tr>'
        st.markdown(f"""
<details><summary style="cursor:pointer;font-size:.85rem;color:#666;margin-bottom:.5rem;">
▶ Resumo por marca ({len(brand_summary)} marcas)
</summary>
<table class="brand-table">
<tr><th>Marca</th><th>SKUs</th><th>Com Alerta</th></tr>
{rows_html}
</table>
</details>""", unsafe_allow_html=True)

        # ── Main table + detail ──
        sub_sorted = sub_ret.copy()
        # Build display rows
        rows_display = []
        for _, row in sub_sorted.iterrows():
            al = row["Alert_Label"]
            if al == "Novo High+Low": alert_pill = '<span class="pill-both">⚡ Novo High+Low</span>'
            elif al == "Novo High":   alert_pill = '<span class="pill-high">📈 Novo High</span>'
            elif al == "Novo Low":    alert_pill = '<span class="pill-low">📉 Novo Low</span>'
            else:                     alert_pill = ""

            if row["Tipo_Preco"] == "Preço Único":
                tipo_str  = '<span class="tag tag-pu">💰 Preço Único</span>'
                high_str  = f'{row["Preco_High"]:.2f} €' if row["Preco_High"] else "—"
                low_str   = "—"; prof_str = "—"
                new_h_str = "—"; new_l_str = "—"; new_prof_str = "—"
            else:
                tipo_str  = '<span class="tag tag-hl">🔁 High-Low</span>'
                high_str  = f'🔴 {row["Preco_High"]:.2f} €' if row["Preco_High"] else "—"
                low_str   = f'🟢 {row["Preco_Low"]:.2f} €'  if row["Preco_Low"]  else "—"
                prof_str  = f'{row["Prof_Promo"]:.1f}%'      if row["Prof_Promo"] else "—"
                als = row["Alertas"] or []
                new_highs = [a for a in als if "High" in a["tipo"]]
                new_lows  = [a for a in als if "Low"  in a["tipo"]]
                new_h_str  = " | ".join(f'📈 {a["preco_novo"]:.2f}€' for a in new_highs) or "—"
                new_l_str  = " | ".join(f'📉 {a["preco_novo"]:.2f}€' for a in new_lows)  or "—"
                # New prof = from most recent alert
                all_als = new_highs + new_lows
                new_prof_str = f'{all_als[-1]["prof_nova"]:.1f}%' if all_als else "—"

            _fv = row.get("Formato","") if hasattr(row,"get") else (row["Formato"] if "Formato" in row.index else "")
            fmt_val = str(_fv) if (_fv is not None and str(_fv) not in ("nan","<NA>","None","")) else "—"
            rows_display.append({
                "PID":row["PID"], "Nome":row["Nome"], "Marca":row["Marca"],
                "Quantidade":row["Quantidade"], "Formato": fmt_val if pd.notna(fmt_val) else "—",
                "Estratégia":row["Tipo_Preco"],
                "High":high_str, "Low":low_str, "Prof.%":prof_str,
                "Novo High":new_h_str, "Novo Low":new_l_str, "Nova Prof.%":new_prof_str,
                "Alerta":al or "",
            })

        df_display = pd.DataFrame(rows_display)

        # Show table + on-select graph
        left_col, right_col = st.columns([3,2])
        with left_col:
            sel = st.dataframe(
                df_display[["PID","Nome","Marca","Quantidade","Formato","Estratégia","High","Low","Prof.%","Novo High","Novo Low","Nova Prof.%","Alerta"]],
                use_container_width=True, hide_index=True,
                on_select="rerun", selection_mode="single-row",
                key=f"tbl_{ret}",
            )
        with right_col:
            selected_rows = sel.selection.rows if sel.selection.rows else []
            if selected_rows:
                idx = selected_rows[0]
                row = sub_sorted.iloc[idx]
                sub_hist = df[(df["PID"]==row["PID"]) & (df["Retalhista"]==row["Retalhista"])].sort_values("Data")
                st.markdown(f"**{row['Nome']}**  \n_{row['Marca']} · {row['Quantidade']}_")
                fig2 = go.Figure()
                if row["Tipo_Preco"]=="High-Low" and row["Preco_High"] and row["Preco_Low"]:
                    fig2.add_hrect(y0=row["Preco_Low"]*0.99, y1=row["Preco_High"]*1.01,
                                   fillcolor="rgba(234,179,8,0.06)", line_width=0)
                    fig2.add_hline(y=row["Preco_High"], line_dash="dot", line_color="rgba(220,38,38,0.6)",
                                   annotation_text=f"High {row['Preco_High']:.2f}€", annotation_position="top right")
                    fig2.add_hline(y=row["Preco_Low"], line_dash="dot", line_color="rgba(22,163,74,0.6)",
                                   annotation_text=f"Low {row['Preco_Low']:.2f}€", annotation_position="bottom right")
                fig2.add_trace(go.Scatter(
                    x=sub_hist["Data"], y=sub_hist["Preco"], mode="lines+markers",
                    line=dict(color=RETAILER_COLORS.get(row["Retalhista"],"#333"), width=2),
                    marker=dict(size=5), name="Preço",
                ))
                if row["Alertas"]:
                    alert_prices = {a["preco_novo"] for a in row["Alertas"]}
                    anom = sub_hist[sub_hist["Preco"].isin(alert_prices)]
                    if not anom.empty:
                        fig2.add_trace(go.Scatter(
                            x=anom["Data"], y=anom["Preco"], mode="markers",
                            marker=dict(size=11, color="#f59e0b", symbol="diamond",
                                        line=dict(color="#1a1a1a",width=1.5)),
                            name="Preço novo ⚠️",
                        ))
                fig2.update_layout(height=320, margin=dict(t=10,b=10,l=10,r=10),
                                   yaxis_title="€", template="plotly_white",
                                   legend=dict(orientation="h", yanchor="bottom", y=1.01))
                st.plotly_chart(fig2, use_container_width=True, key=f"chart2_{row['PID']}_{ret}")
            else:
                st.info("← Clica numa linha da tabela para ver o gráfico de evolução de preço.")

        st.markdown("---")

# ═══════════════════════════════════════════════════════════════════
# TAB 3 — TODOS OS PRODUTOS
# ═══════════════════════════════════════════════════════════════════
with tab3:
    st.markdown('<div class="section-header">📋 Todos os Produtos</div>', unsafe_allow_html=True)
    fa, fb, fc, fd, fe = st.columns(5)
    with fa:
        f_ret  = st.multiselect("Retalhista", retailers_sel, default=retailers_sel, key="f_ret_all")
    with fb:
        f_brand = st.multiselect("Marca", sorted(df["Marca"].dropna().unique()), key="f_brand_all")
    with fc:
        f_size  = st.multiselect("Tamanho", sorted(df["Quantidade"].dropna().astype(str).unique()), key="f_size_all")
    with fe:
        all_fmts = sorted(df_fmt_lookup["Formato"].dropna().unique()) if not df_fmt_lookup.empty else []
        f_fmt = st.multiselect("Formato", all_fmts, key="f_fmt_all")
    with fd:
        f_period = st.date_input("Período", value=(min_date,max_date), min_value=min_date, max_value=max_date, key="f_period_all")
        fp_s, fp_e = (f_period[0],f_period[1]) if len(f_period)==2 else (min_date,max_date)
    f_search3 = st.text_input("🔎 Pesquisar por nome", placeholder="ex: Häagen-Dazs, Cornetto…", key="search3")

    df3 = df[(df["Data"].dt.date>=fp_s)&(df["Data"].dt.date<=fp_e)].copy()
    if f_ret:    df3 = df3[df3["Retalhista"].isin(f_ret)]
    if f_brand:  df3 = df3[df3["Marca"].isin(f_brand)]
    if f_size:   df3 = df3[df3["Quantidade"].astype(str).isin(f_size)]
    if f_search3:df3 = df3[df3["Nome"].str.contains(f_search3, case=False, na=False)]
    # Formato filter applied after merge (see below)

    all_sum = (df3.groupby(["PID","Retalhista","Nome","Marca","Quantidade"])["Preco"]
               .agg(Preco_Atual="last", Preco_Min="min", Preco_Max="max", Leituras="count").reset_index())
    cls_m = sku_cls[["PID","Retalhista","Tipo_Preco","Preco_High","Preco_Low","Prof_Promo","Alert_Label"]]
    all_sum = all_sum.merge(cls_m, on=["PID","Retalhista"], how="left")
    # Merge Formato from static lookup (robust to cache/column-missing issues)
    all_sum["PID"] = all_sum["PID"].astype(str)
    all_sum = all_sum.merge(df_fmt_lookup, on=["PID","Retalhista"], how="left")
    if f_fmt: all_sum = all_sum[all_sum["Formato"].isin(f_fmt)]
    all_sum["Prof_Promo"] = all_sum["Prof_Promo"].fillna(
        ((1-all_sum["Preco_Min"]/all_sum["Preco_Max"])*100).round(1))
    all_sum["_ro"] = all_sum["Retalhista"].map({r:i for i,r in enumerate(RETAILER_ORDER)}).fillna(99)
    all_sum = all_sum.sort_values(["_ro","Marca","Nome"]).drop(columns=["_ro"])

    st.markdown(f"**{len(all_sum)} produto(s)** encontrado(s)")
    for ret in RETAILER_ORDER:
        sub = all_sum[all_sum["Retalhista"]==ret]
        if sub.empty: continue
        color = RETAILER_COLORS.get(ret,"#333")
        st.markdown(f"#### {ret} &nbsp; <span style='font-size:.85rem;color:{color}'>{len(sub)} SKUs</span>", unsafe_allow_html=True)
        d = sub[["PID","Nome","Marca","Quantidade","Formato","Tipo_Preco","Preco_Atual","Preco_Min","Preco_Max","Prof_Promo","Alert_Label","Leituras"]].copy()
        d.columns = ["ID","Nome","Marca","Tamanho","Formato","Estratégia","Preço Atual €","Mín €","Máx €","Prof. Promo %","Alerta","Leituras"]
        d["Preço Atual €"] = d["Preço Atual €"].map("{:.2f}".format)
        d["Mín €"]         = d["Mín €"].map("{:.2f}".format)
        d["Máx €"]         = d["Máx €"].map("{:.2f}".format)
        d["Prof. Promo %"] = d["Prof. Promo %"].apply(lambda x: f"{x:.1f}%" if pd.notna(x) and x>0 else "—")
        d["Formato"]       = d["Formato"].fillna("—")
        d["Alerta"]        = d["Alerta"].apply(lambda x: ("⚡ "+x) if pd.notna(x) and x else "")
        st.dataframe(d, use_container_width=True, hide_index=True)

# ═══════════════════════════════════════════════════════════════════
# TAB 4 — EVOLUÇÃO DE PREÇOS (multi-SKU chart)
# ═══════════════════════════════════════════════════════════════════
with tab4:
    st.markdown('<div class="section-header">📊 Evolução de Preços</div>', unsafe_allow_html=True)
    st.markdown("Seleciona os filtros para visualizar a evolução histórica de múltiplos SKUs num único gráfico.")

    g1, g2, g3, g4, g5, g6 = st.columns(6)
    with g1:
        g_ret   = st.multiselect("Retalhista", retailers_sel, default=retailers_sel, key="g_ret")
    with g2:
        g_brand = st.multiselect("Marca", sorted(df["Marca"].dropna().unique()), key="g_brand")
    with g3:
        g_size  = st.multiselect("Tamanho", sorted(df["Quantidade"].dropna().astype(str).unique()), key="g_size")
    with g4:
        g_tipo  = st.multiselect("Estratégia", ["Preço Único","High-Low"], default=["Preço Único","High-Low"], key="g_tipo")
    with g6:
        g_fmts_avail = sorted(df_fmt_lookup["Formato"].dropna().unique()) if not df_fmt_lookup.empty else []
        g_fmt = st.multiselect("Formato", g_fmts_avail, key="g_fmt")
    with g5:
        g_period = st.date_input("Período", value=(min_date,max_date), min_value=min_date, max_value=max_date, key="g_period")
        gp_s, gp_e = (g_period[0],g_period[1]) if len(g_period)==2 else (min_date,max_date)

    g_search = st.text_input("🔎 Pesquisar por nome do produto", placeholder="ex: Magnum, Cornetto…", key="g_search")

    # Filter data
    dg = df[(df["Data"].dt.date>=gp_s)&(df["Data"].dt.date<=gp_e)].copy()
    if g_ret:    dg = dg[dg["Retalhista"].isin(g_ret)]
    if g_brand:  dg = dg[dg["Marca"].isin(g_brand)]
    if g_size:   dg = dg[dg["Quantidade"].astype(str).isin(g_size)]
    if g_search: dg = dg[dg["Nome"].str.contains(g_search, case=False, na=False)]
    # Merge Formato for tab4 filter
    dg["PID"] = dg["PID"].astype(str)
    dg = dg.merge(df_fmt_lookup, on=["PID","Retalhista"], how="left")
    if g_fmt: dg = dg[dg["Formato"].isin(g_fmt)]

    # Apply strategy filter via sku_cls
    if g_tipo:
        valid_skus = sku_cls[sku_cls["Tipo_Preco"].isin(g_tipo)][["PID","Retalhista"]]
        dg = dg.merge(valid_skus, on=["PID","Retalhista"])

    n_skus_g = dg.groupby(["PID","Retalhista"]).ngroups
    st.markdown(f"**{n_skus_g} SKU(s)** com os filtros aplicados.")

    MAX_LINES = 60
    if n_skus_g == 0:
        st.info("Nenhum SKU encontrado com os filtros aplicados.")
    elif n_skus_g > MAX_LINES:
        st.warning(f"Muitos SKUs ({n_skus_g}) para visualizar. Aplica mais filtros (sugestão: máx {MAX_LINES} linhas para boa leitura).")
    else:
        fig4 = go.Figure()
        palette = px.colors.qualitative.Dark24 + px.colors.qualitative.Light24
        sku_groups = list(dg.groupby(["PID","Retalhista","Nome","Marca"]))
        for i, ((pid,ret,nome,marca), grp) in enumerate(sku_groups):
            grp = grp.sort_values("Data")
            color = RETAILER_COLORS.get(ret, palette[i % len(palette)])
            dash = "solid" if ret=="Continente" else ("dash" if ret=="PingoDoce" else "dot")
            label = f"{nome[:30]} [{ret[:3]}]"
            fig4.add_trace(go.Scatter(
                x=grp["Data"], y=grp["Preco"],
                mode="lines+markers", name=label,
                line=dict(color=color, width=1.8, dash=dash),
                marker=dict(size=4),
                hovertemplate=f"<b>{nome}</b><br>{ret}<br>%{{x|%d/%m/%Y}}<br>%{{y:.2f}}€<extra></extra>",
            ))
        fig4.update_layout(
            height=550,
            template="plotly_white",
            yaxis_title="Preço (€)",
            xaxis_title="",
            hovermode="x unified",
            legend=dict(
                orientation="v", yanchor="top", y=1, xanchor="left", x=1.01,
                font=dict(size=10),
            ),
            margin=dict(t=20, b=20, l=10, r=10),
        )
        st.plotly_chart(fig4, use_container_width=True, key="chart_tab4_multi")


# ═══════════════════════════════════════════════════════════════════
# TAB 5 — SKUs NÃO CLASSIFICADOS
# ═══════════════════════════════════════════════════════════════════
with tab5:
    st.markdown('<div class="section-header">🏷️ Glossário de Formatos</div>', unsafe_allow_html=True)

    glossario = load_glossario()

    # ── Top toolbar: import / export / stats ─────────────────────────────────
    toolbar_l, toolbar_r = st.columns([2, 1])
    with toolbar_l:
        st.markdown(
            f"O glossário guarda a classificação de Formato de cada SKU de forma **persistente**. "
            f"Actualmente tem **{len(glossario)} classificações** guardadas."
        )
    with toolbar_r:
        if glossario:
            gl_rows = []
            for key_id, fmt in glossario.items():
                pid, ret = key_id.rsplit("_", 1)
                row_m = df_sku_list[(df_sku_list["PID"]==pid) & (df_sku_list["Retalhista"]==ret)]
                r = row_m.iloc[0] if not row_m.empty else None
                gl_rows.append({
                    "PID": pid, "Retalhista": ret,
                    "Nome": r["Nome"] if r is not None and pd.notna(r.get("Nome")) else "—",
                    "Marca": r["Marca"] if r is not None and pd.notna(r.get("Marca")) else "—",
                    "Quantidade": r["Quantidade"] if r is not None and pd.notna(r.get("Quantidade")) else "—",
                    "Formato": fmt,
                })
            df_gl_export = pd.DataFrame(gl_rows)
            csv_gl = df_gl_export.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Exportar glossário (CSV)", csv_gl,
                               file_name="glossario_formato.csv", mime="text/csv",
                               key="dl_glossario", use_container_width=True)

    # ── Import CSV ────────────────────────────────────────────────────────────
    with st.expander("📥 Importar glossário de ficheiro CSV"):
        st.markdown(
            "Carrega um CSV com colunas `PID`, `Retalhista`, `Formato`. "
            "As classificações importadas são **adicionadas** ao glossário existente."
        )
        csv_up = st.file_uploader("CSV do glossário", type=["csv"], key="csv_import")
        if csv_up:
            n_imp = import_glossario_csv(csv_up)
            if isinstance(n_imp, int):
                st.success(f"✅ {n_imp} classificações importadas!")
                glossario = load_glossario()
                st.rerun()
            else:
                st.error(n_imp)

    st.markdown("---")

    # ── Build full SKU table with glossário applied ───────────────────────────
    df_all_skus = df_sku_list.copy()
    df_all_skus["key_id"] = df_all_skus["PID"].astype(str) + "_" + df_all_skus["Retalhista"]
    df_all_skus["Formato"] = df_all_skus["key_id"].map(glossario)

    n_total      = len(df_all_skus)
    n_classified = df_all_skus["Formato"].notna().sum()
    n_missing    = n_total - n_classified
    pct = int(n_classified / n_total * 100) if n_total > 0 else 0
    bar_color = "#16a34a" if pct == 100 else "#2563eb"

    st.markdown(f"""
<div style="margin-bottom:1rem;">
  <div style="display:flex;justify-content:space-between;font-size:.82rem;color:#666;margin-bottom:.3rem;">
    <span>Classificações: <strong>{n_classified} / {n_total}</strong></span>
    <span><strong>{pct}%</strong> completo</span>
  </div>
  <div style="background:#e5e7eb;border-radius:8px;height:10px;overflow:hidden;">
    <div style="background:{bar_color};width:{pct}%;height:100%;border-radius:8px;"></div>
  </div>
</div>""", unsafe_allow_html=True)

    if n_missing == 0:
        st.success("✅ Todos os SKUs têm Formato classificado!")
    else:
        st.info(f"**{n_missing} SKU(s)** ainda sem classificação.")

    view_mode = st.radio("Mostrar:", ["Não classificados", "Todos os SKUs", "Apenas classificados"],
                          horizontal=True, key="tab5_view")
    uc_ret5 = st.multiselect("Filtrar por retalhista", retailers_sel,
                              default=retailers_sel, key="uc_ret5")

    if view_mode == "Não classificados":
        display_skus = df_all_skus[df_all_skus["Formato"].isna()]
    elif view_mode == "Apenas classificados":
        display_skus = df_all_skus[df_all_skus["Formato"].notna()]
    else:
        display_skus = df_all_skus.copy()

    display_skus = display_skus[display_skus["Retalhista"].isin(uc_ret5)]
    st.markdown(f"**{len(display_skus)} SKU(s)** com os filtros actuais.")
    st.markdown("---")

    SEL_OPTIONS = ["— seleccionar —"] + FORMATO_OPTIONS

    for ret in RETAILER_ORDER:
        sub_uc = display_skus[display_skus["Retalhista"]==ret].copy()
        if sub_uc.empty: continue
        color = RETAILER_COLORS.get(ret,"#333")
        st.markdown(
            f"#### {ret} &nbsp; <span style='font-size:.85rem;color:{color}'>{len(sub_uc)} SKUs</span>",
            unsafe_allow_html=True
        )
        for _, row in sub_uc.iterrows():
            key_id    = row["key_id"]
            current   = glossario.get(key_id, "— seleccionar —")
            nome_str  = str(row["Nome"])  if pd.notna(row.get("Nome"))       else f"(sem nome · PID {row['PID']})"
            marca_str = str(row["Marca"]) if pd.notna(row.get("Marca"))      else "—"
            qtd_str   = str(row["Quantidade"]) if pd.notna(row.get("Quantidade")) else "—"

            col_info, col_sel, col_status = st.columns([3, 1, 0.6])
            with col_info:
                st.markdown(
                    f"<strong>{nome_str}</strong><br>"
                    f"<span style='color:#888;font-size:.8rem'>Marca: {marca_str} · Qtd: {qtd_str} · PID: {row['PID']}</span>",
                    unsafe_allow_html=True
                )
            with col_sel:
                chosen = st.selectbox(
                    "Formato", SEL_OPTIONS,
                    index=SEL_OPTIONS.index(current) if current in SEL_OPTIONS else 0,
                    key=f"gls_{key_id}", label_visibility="collapsed",
                )
                if chosen != "— seleccionar —" and chosen != current:
                    glossario[key_id] = chosen
                    save_glossario(glossario)
                    st.rerun()
                elif chosen == "— seleccionar —" and current in FORMATO_OPTIONS:
                    del glossario[key_id]
                    save_glossario(glossario)
                    st.rerun()
            with col_status:
                if current in FORMATO_OPTIONS:
                    st.markdown(
                        f'<div style="padding-top:.4rem"><span class="tag" style="background:#dcfce7;color:#166534;font-size:.75rem">✔ {current}</span></div>',
                        unsafe_allow_html=True
                    )
            st.markdown("<hr style='margin:.3rem 0;border-color:#f1f5f9;'>", unsafe_allow_html=True)

    # ── Full glossário viewer ─────────────────────────────────────────────────
    if glossario:
        st.markdown("---")
        with st.expander(f"📖 Ver glossário completo ({len(glossario)} entradas)"):
            gl_view = []
            for key_id, fmt in sorted(glossario.items()):
                pid, ret = key_id.rsplit("_", 1)
                row_m = df_sku_list[(df_sku_list["PID"]==pid) & (df_sku_list["Retalhista"]==ret)]
                r = row_m.iloc[0] if not row_m.empty else None
                gl_view.append({
                    "PID": pid, "Retalhista": ret,
                    "Nome":   r["Nome"]   if r is not None and pd.notna(r.get("Nome"))   else "—",
                    "Marca":  r["Marca"]  if r is not None and pd.notna(r.get("Marca"))  else "—",
                    "Formato": fmt,
                })
            st.dataframe(pd.DataFrame(gl_view), use_container_width=True, hide_index=True)

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("<p style='text-align:center;color:#bbb;font-size:.78rem;'>Monitoramento de Preços IceCream Portugal · Actualizado automaticamente com o ficheiro Excel do scraper</p>", unsafe_allow_html=True)
