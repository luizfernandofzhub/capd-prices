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

_LAST_UPDATE = "29/Maio/2026"

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
    background:#e8e8e8; border-radius:8px;
    padding:.55rem 1.1rem; flex:1;
    border-left:3px solid #1a1a1a;
    box-shadow:0 1px 3px rgba(0,0,0,.06);
}
.kpi-item h4 { margin:0; font-size:.72rem; color:#444; letter-spacing:.07em; text-transform:uppercase; font-weight:600; }
.kpi-item p  { margin:.15rem 0 0; font-size:1.45rem; font-weight:700; color:#1a1a1a; }

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
    df_all["PID"] = df_all["PID"].astype(str)  # normalise PID type
    df_all = df_all.sort_values("Data").drop_duplicates(subset=["PID","Retalhista","Data"], keep="last")
    return df_all

import base64, os

def get_logo_b64(filename):
    """Load a logo PNG from the repo root and return a base64 data URI."""
    try:
        with open(filename, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        return f"data:image/png;base64,{data}"
    except Exception:
        return None

LOGOS = {
    "Continente": get_logo_b64("logo_continente.png"),
    "PingoDoce":  get_logo_b64("logo_pingodoce.png"),
    "Auchan":     get_logo_b64("logo_auchan.png"),
}

def retailer_header(ret, count_html=""):
    """Render a retailer section header with logo + name + optional count badge."""
    logo = LOGOS.get(ret)
    logo_html = f'<img src="{logo}" style="height:28px;vertical-align:middle;margin-right:8px;">' if logo else ""
    color = RETAILER_COLORS.get(ret, "#333")
    return (
        f'<div style="display:flex;align-items:center;gap:.5rem;margin:1.2rem 0 .6rem;">' +
        logo_html +
        f'<span style="font-family:DM Serif Display,serif;font-size:1.4rem;font-weight:600;">{ret}</span>' +
        (f'&nbsp;{count_html}' if count_html else "") +
        "</div>"
    )

GLOSSARIO_KEY = "glossario_formato_v1"
FORMATO_OPTIONS = ["Bars","Bites","Bites - PromoPack","Cakes","Cones","Cups",
                   "Frozen Fruits","Other","Pints","Pints - PromoPack",
                   "Pots","Sandwich","Sticks","Tubs"]

@st.cache_data(ttl=60)
def load_glossario_csv_from_github():
    """Try to load glossario_formato.csv from the same repo as the app.
    Returns a dict or empty dict if file not found."""
    try:
        df_csv = pd.read_csv("glossario_formato.csv")
        df_csv["PID"] = df_csv["PID"].astype(str)
        result = {}
        for _, row in df_csv.iterrows():
            if pd.notna(row.get("Formato")) and str(row.get("Formato","")) not in ("","nan"):
                key = f"{row['PID']}_{row['Retalhista']}"
                result[key] = str(row["Formato"])
        return result
    except Exception:
        return {}
    except Exception:
        return {}

def load_glossario():
    """Load glossário from session_state. On first load, seeds from GitHub CSV."""
    if GLOSSARIO_KEY not in st.session_state:
        # Seed from the CSV file in the repo (if it exists)
        seed = load_glossario_csv_from_github()
        st.session_state[GLOSSARIO_KEY] = seed
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

@st.cache_data(ttl=60)
def load_glossario_df():
    """Load the full glossario CSV including Marca Padronizada."""
    try:
        df_gl = pd.read_csv("glossario_formato.csv")
        df_gl["PID"] = df_gl["PID"].astype(str)
        if "Marca Padronizada" not in df_gl.columns:
            df_gl["Marca Padronizada"] = df_gl.get("Marca", None)
        return df_gl
    except Exception:
        return pd.DataFrame(columns=["PID","Retalhista","Nome","Marca","Marca Padronizada","Quantidade","Formato"])

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
def classify_sku(price_series_with_dates, outlier_min_count=3, outlier_min_pct=5.0):
    """Accepts list of (date, price) tuples sorted chronologically."""
    if not price_series_with_dates:
        return {"tipo":"Sem dados","preco_high":None,"preco_low":None,"prof_promo":0.0,"alerta":None}

    dated = [(d, float(p)) for d, p in price_series_with_dates if pd.notna(p)]
    if not dated:
        return {"tipo":"Sem dados","preco_high":None,"preco_low":None,"prof_promo":0.0,"alerta":None}

    prices = [p for _, p in dated]
    n = len(prices)
    cnt = _Counter(prices)
    unique_prices = sorted(cnt.keys())

    most_common_count = cnt.most_common(1)[0][1]
    if most_common_count/n >= 0.90 or len(unique_prices) == 1:
        return {"tipo":"Preço Único","preco_high":max(prices),"preco_low":None,"prof_promo":0.0,"alerta":None}

    # Top-2 most frequent = established Baseline / Low pair
    top2 = sorted(cnt.keys(), key=lambda p: -cnt[p])[:2]
    est_baseline = max(top2)
    est_low      = min(top2)
    known = {est_baseline, est_low}
    prof = (1 - est_low/est_baseline)*100 if est_baseline > 0 else 0.0

    # First-seen date for each price (chronological direction)
    first_seen_date = {}
    for date, price in dated:
        if price not in first_seen_date:
            first_seen_date[price] = date
    bl_first  = first_seen_date.get(est_baseline)
    low_first = first_seen_date.get(est_low)

    alerts = []
    for np_ in unique_prices:
        if np_ in known: continue
        cnt_p = cnt[np_]
        pct_p = cnt_p/n*100
        if cnt_p < outlier_min_count or pct_p < outlier_min_pct: continue

        np_first = first_seen_date.get(np_)
        dist_b = abs(np_ - est_baseline)
        dist_l = abs(np_ - est_low)

        if np_ > est_baseline:
            if np_first < bl_first:
                kind="Novo Baseline ↑"; old_v=np_; new_v=est_baseline
                new_prof=(1-est_low/est_baseline)*100
            else:
                kind="Novo Baseline ↑"; old_v=est_baseline; new_v=np_
                new_prof=(1-est_low/np_)*100
        elif np_ < est_low:
            if np_first < low_first:
                kind="Novo Low ↓"; old_v=np_; new_v=est_low
                new_prof=(1-est_low/est_baseline)*100
            else:
                kind="Novo Low ↓"; old_v=est_low; new_v=np_
                new_prof=(1-np_/est_baseline)*100
        elif dist_l <= dist_b:
            if np_first < low_first:
                kind="Novo Low ↓"; old_v=np_; new_v=est_low
                new_prof=(1-est_low/est_baseline)*100
            else:
                kind="Novo Low ↓"; old_v=est_low; new_v=np_
                new_prof=(1-np_/est_baseline)*100
        else:
            if np_first < bl_first:
                kind="Novo Baseline ↑"; old_v=np_; new_v=est_baseline
                new_prof=(1-est_low/est_baseline)*100
            else:
                kind="Novo Baseline ↑"; old_v=est_baseline; new_v=np_
                new_prof=(1-est_low/np_)*100

        alerts.append({"tipo":kind,"preco_anterior":round(old_v,2),"preco_novo":round(new_v,2),
                        "prof_anterior":round(prof,1),"prof_nova":round(new_prof,1),
                        "n_leituras":cnt_p,"pct_leituras":round(pct_p,1)})

    return {"tipo":"High-Low","preco_high":est_baseline,"preco_low":est_low,
            "prof_promo":round(prof,1),"alerta":alerts if alerts else None}

@st.cache_data(ttl=300)
def build_classifications(df_input):
    records = []
    for (pid, ret), grp in df_input.groupby(["PID","Retalhista"]):
        grp = grp.sort_values("Data")
        cls = classify_sku(list(zip(grp["Data"].tolist(), grp["Preco"].tolist())))
        m = grp.iloc[0]
        pid = str(pid)  # normalise to str
        has_bl  = cls["alerta"] and any("Baseline" in a["tipo"] for a in cls["alerta"])
        has_low = cls["alerta"] and any("Low"      in a["tipo"] for a in cls["alerta"])
        alert_label = None
        if has_bl and has_low: alert_label = "NB+NL"
        elif has_bl:           alert_label = "NB"
        elif has_low:          alert_label = "NL"
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

df_period = df[(df["Data"].dt.date >= d_start) & (df["Data"].dt.date <= d_end)]
sku_cls   = build_classifications(df)
sku_cls["PID"] = sku_cls["PID"].astype(str)  # normalise PID type throughout

# ── Formato lookup — built from glossário + SKU list ─────────────────────
df_sku_list   = load_sku_list_from_excel(data_source)
_glossario    = load_glossario()
df_fmt_lookup = build_formato_lookup(_glossario, df_sku_list)
# Load Marca Padronizada from glossario CSV
df_gl_full    = load_glossario_df()
# Merge Marca Padronizada into df and df_sku_list
if not df_gl_full.empty and "Marca Padronizada" in df_gl_full.columns:
    mp_map = df_gl_full[["PID","Retalhista","Marca Padronizada"]].drop_duplicates()
    df["PID"] = df["PID"].astype(str)
    if "Marca Padronizada" in df.columns:
        df = df.drop(columns=["Marca Padronizada"])
    df = df.merge(mp_map, on=["PID","Retalhista"], how="left")
    df_sku_list["PID"] = df_sku_list["PID"].astype(str)
    if "Marca Padronizada" in df_sku_list.columns:
        df_sku_list = df_sku_list.drop(columns=["Marca Padronizada"])
    df_sku_list = df_sku_list.merge(mp_map, on=["PID","Retalhista"], how="left")

# ── SKU static metadata (one row per PID×Retalhista, with Formato) ──────
df_sku_meta = (df.sort_values("Data")
               .drop_duplicates(subset=["PID","Retalhista"], keep="last")
               [["PID","Retalhista","Nome","Marca","Quantidade","Formato"]])

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style='background:#1a1a1a;color:#d4d4d4;font-size:.78rem;text-align:center;
            padding:.42rem 1rem;border-radius:6px;margin-bottom:.6rem;letter-spacing:.04em;'>
  🕒 <strong>Última atualização em:</strong> {{_LAST_UPDATE}}
</div>
<h1 style='font-family:"DM Serif Display",serif;font-size:2.2rem;margin-bottom:.1rem;'>
    Monitoramento de Preços | IceCream Portugal
</h1>
<p style='color:#888;font-size:.88rem;margin-bottom:.8rem;'>
    Monitorização de preços · Continente · Auchan · Pingo Doce
</p>""", unsafe_allow_html=True)

# ── Tabs first ─────────────────────────────────────────────────────────────────
tab1, tab2, tab4, tab5, tab6, tab_now = st.tabs([
    "🆕 Produtos Novos",
    "📣 Alerta de Mudança de Preço",
    "📊 Montar Gráficos",
    "🏷️ Classificar SKUs",
    "🔬 Análise de Clusters (Beta)",
    "🔍 Preço Agora",
])

# ── Slim KPI bar (below tabs) ───────────────────────────────────────────────────
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

# ═══════════════════════════════════════════════════════════════════
# TAB 1 — NOVOS PRODUTOS
# ═══════════════════════════════════════════════════════════════════
with tab1:
    st.markdown('<div class="section-header">🆕 Produtos Novos</div>', unsafe_allow_html=True)

    # ── Filter: days selector at top of tab (FIX 1) ──────────────────────────
    t1a, t1b = st.columns([1, 3])
    with t1a:
        new_prod_days = st.slider("Primeiros dados nos últimos N dias",
                                   min_value=3, max_value=90, value=7, step=1,
                                   key="new_prod_days_slider")
    with t1b:
        st.markdown("")  # spacer

    # ── FIX 5: exclude SKUs present on the very first date (launch SKUs) ─────
    first_date_global = df["Data"].min()
    launch_skus = set(
        df[df["Data"] == first_date_global]
        .apply(lambda r: f"{r['PID']}_{r['Retalhista']}", axis=1)
    )

    cutoff = pd.Timestamp(max_date) - timedelta(days=new_prod_days)
    first_seen = (df.groupby(["PID","Retalhista"])["Data"].min()
                  .reset_index().rename(columns={"Data":"Primeira_Leitura"}))

    # Exclude launch-day SKUs from "new products"
    first_seen["key"] = first_seen["PID"].astype(str) + "_" + first_seen["Retalhista"]
    first_seen_filtered = first_seen[~first_seen["key"].isin(launch_skus)].drop(columns=["key"])

    new_products = first_seen_filtered[first_seen_filtered["Primeira_Leitura"] >= cutoff].copy()

    st.markdown(f"Produtos cuja **primeira leitura** ocorreu nos últimos **{new_prod_days} dias** (a contar de {max_date}).")

    if new_products.empty:
        st.info(f"Nenhum produto novo nos últimos {new_prod_days} dias.")
    else:
        # Get latest price + price history min/max (FIX 3)
        price_stats = (df.groupby(["PID","Retalhista"])["Preco"]
                       .agg(Preco_Atual="last", Preco_Min="min", Preco_Max="max")
                       .reset_index())
        meta_cols = df.sort_values("Data").groupby(["PID","Retalhista"]).last()[["Nome","Marca","Quantidade"]].reset_index()
        price_stats = price_stats.merge(meta_cols, on=["PID","Retalhista"])

        new_products["PID"] = new_products["PID"].astype(str)
        price_stats["PID"]  = price_stats["PID"].astype(str)
        new_products = new_products.merge(price_stats, on=["PID","Retalhista"])
        new_products = new_products[new_products["Retalhista"].isin(retailers_sel)]
        new_products = new_products.sort_values(["Primeira_Leitura","Retalhista"], ascending=[False,True])
        new_products = new_products.merge(df_fmt_lookup, on=["PID","Retalhista"], how="left")

        st.markdown(f"**{len(new_products)} produto(s) encontrado(s)**")

        glossario = load_glossario()

        for ret in RETAILER_ORDER:
            sub = new_products[new_products["Retalhista"]==ret].copy()
            if sub.empty: continue

            # FIX 6: larger green badge
            count_badge = (f'<span style="font-size:1.05rem;font-weight:700;color:#84cc16;'
                           f'background:#1a2e05;padding:2px 12px;border-radius:20px;">' +
                           f'{len(sub)} novos</span>')
            # FIX 2: retailer header with logo
            st.markdown(retailer_header(ret, count_badge), unsafe_allow_html=True)

            # FIX 4: inline Formato classification for unclassified SKUs
            # Build display with selectbox for unclassified
            display_rows = []
            changed = False
            for _, row in sub.iterrows():
                key_id  = f"{row['PID']}_{ret}"
                fmt_val = glossario.get(key_id)
                if fmt_val is None:
                    fmt_val = None  # will show selectbox
                display_rows.append((row, key_id, fmt_val))

            # Check if any need classification
            needs_cls = any(fv is None for _, _, fv in display_rows)

            # Build table for rows with Formato already classified
            d = sub[["PID","Nome","Marca","Quantidade","Formato","Preco_Atual","Preco_Min","Preco_Max","Primeira_Leitura"]].copy()
            d["Formato"] = d.apply(
                lambda r: glossario.get(f"{r['PID']}_{ret}", r["Formato"]), axis=1
            )
            d["Formato"] = d["Formato"].fillna("—")
            d.columns = ["ID","Nome","Marca","Quantidade","Formato","Preço Atual €","Mín €","Máx €","1ª Leitura"]
            d["Preço Atual €"] = d["Preço Atual €"].map("{:.2f}".format)
            d["Mín €"]         = d["Mín €"].map("{:.2f}".format)
            d["Máx €"]         = d["Máx €"].map("{:.2f}".format)
            d["1ª Leitura"]    = d["1ª Leitura"].dt.strftime("%d/%m/%Y")
            st.dataframe(d, use_container_width=True, hide_index=True)

            # FIX 4: show inline selectboxes for unclassified SKUs
            unclassified = [(row, key_id) for row, key_id, fv in display_rows if fv is None and row["Formato"] == "—" or (fv is None and pd.isna(row.get("Formato","")))]
            unclassified = [(row, key_id) for row, key_id, fv in display_rows
                            if fv is None and (pd.isna(row.get("Formato")) or str(row.get("Formato","")) in ("nan","None","—",""))]
            if unclassified:
                st.markdown(f"**{len(unclassified)} SKU(s) sem Formato** — classifica abaixo:")
                SEL_OPTS = ["— seleccionar —"] + FORMATO_OPTIONS
                for row, key_id in unclassified:
                    c_name, c_sel = st.columns([3,1])
                    with c_name:
                        st.markdown(f"<small style='color:#888'>{row['Nome']} · {row['Marca']}</small>",
                                    unsafe_allow_html=True)
                    with c_sel:
                        chosen = st.selectbox("Formato", SEL_OPTS, key=f"t1_fmt_{key_id}",
                                              label_visibility="collapsed")
                        if chosen != "— seleccionar —":
                            glossario[key_id] = chosen
                            save_glossario(glossario)
                            st.rerun()

    # ── FIX 5: Timeline chart excluding launch SKUs ───────────────────────────
    if not first_seen_filtered.empty:
        st.markdown("#### Histórico de entrada de novos produtos")
        st.caption(f"Nota: SKUs presentes desde o início da base ({first_date_global.strftime('%d/%m/%Y')}) foram excluídos.")
        tl = first_seen_filtered.copy()
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
    st.markdown('<div class="section-header">📣 Alerta de Mudança de Preço</div>', unsafe_allow_html=True)

    # ── Filters ──
    # ── Row 1: main filters ───────────────────────────────────────────────────
    r1a, r1b, r1c, r1d = st.columns([1, 1, 1, 1])
    with r1a:
        period2 = st.date_input("Período", value=(min_date, max_date),
                                 min_value=min_date, max_value=max_date, key="period2")
        p2_start, p2_end = (period2[0], period2[1]) if len(period2)==2 else (min_date, max_date)
    with r1b:
        ret2   = st.multiselect("Retalhista", retailers_sel, default=retailers_sel, key="ret2")
    with r1c:
        mp_opts2 = sorted(df["Marca Padronizada"].dropna().unique()) if "Marca Padronizada" in df.columns else sorted(df["Marca"].dropna().unique())
        brand2 = st.multiselect("Marca", mp_opts2, key="brand2")
    with r1d:
        search2 = st.text_input("🔎 Nome", placeholder="ex: Ben & Jerry's", key="search2")

    # ── Row 2: secondary filters (sem filtro tipo alerta) ─────────────────────
    r2a, r2b, r2c, r2d = st.columns([1.4, 1, 1, 1])
    with r2a:
        st.markdown('<div style="background:#fff3f3;border:2px solid #dc2626;border-radius:10px;padding:.55rem .9rem;margin-top:.25rem;">', unsafe_allow_html=True)
        only_alerts2 = st.checkbox("🚨 Apenas SKUs com alertas", value=True, key="chk_alerts2")
        st.markdown("</div>", unsafe_allow_html=True)
    with r2b:
        tipo2  = st.multiselect("Estratégia", ["Preço Único","High-Low"], default=["Preço Único","High-Low"], key="tipo2")
    with r2c:
        fmt2_opts = sorted(df_fmt_lookup["Formato"].dropna().unique()) if (not df_fmt_lookup.empty and "Formato" in df_fmt_lookup.columns) else []
        fmt2 = st.multiselect("Formato", fmt2_opts, key="fmt2")
    with r2d:
        st.caption("ℹ️ O período seleccionado afecta todos os cálculos de alertas e o gráfico.")

    # ── Recompute classifications for selected period ─────────────────────────
    df_period2 = df[(df["Data"].dt.date >= p2_start) & (df["Data"].dt.date <= p2_end)]
    sku_cls2   = build_classifications(df_period2)
    sku_cls2["PID"] = sku_cls2["PID"].astype(str)

    # ── Filter ──
    cf = sku_cls2[sku_cls2["Retalhista"].isin(ret2 or retailers_sel)].copy()
    if brand2:
        if "Marca Padronizada" in cf.columns:
            cf = cf.merge(df[["PID","Retalhista","Marca Padronizada"]].drop_duplicates(), on=["PID","Retalhista"], how="left", suffixes=("","_mp"))
            mp_col = "Marca Padronizada_mp" if "Marca Padronizada_mp" in cf.columns else "Marca Padronizada"
            cf = cf[cf[mp_col].isin(brand2)]
        else:
            cf = cf[cf["Marca"].isin(brand2)]
    if tipo2:   cf = cf[cf["Tipo_Preco"].isin(tipo2)]
    if search2: cf = cf[cf["Nome"].str.contains(search2, case=False, na=False)]
    if only_alerts2: cf = cf[cf["Alert_Label"].notna()]
    if fmt2 and "Formato" in cf.columns: cf = cf[cf["Formato"].isin(fmt2)]
    cf["_ro"] = cf["Retalhista"].map({r:i for i,r in enumerate(RETAILER_ORDER)}).fillna(99)
    cf = cf.sort_values(["_ro","Marca","Nome"]).drop(columns=["_ro"])
    # Ensure Formato is in cf (always merge from static lookup)
    cf["PID"] = cf["PID"].astype(str)
    if "Formato" in cf.columns:
        cf = cf.drop(columns=["Formato"])
    cf = cf.merge(df_fmt_lookup, on=["PID","Retalhista"], how="left")

    # ── Brand summary table ──
    for ret in RETAILER_ORDER:
        sub_ret = cf[cf["Retalhista"]==ret]
        if sub_ret.empty: continue
        st.markdown(retailer_header(ret), unsafe_allow_html=True)

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

        # FIX 6: legend
        st.markdown(
            '<div style="font-size:.78rem;margin-bottom:.5rem;">' +
            '<span style="color:#888">Alertas: </span>' +
            '🟠 <span style="color:#ea580c;font-weight:600">Novo Baseline</span> &nbsp;&nbsp;' +
            '🟣 <span style="color:#7c3aed;font-weight:600">Novo Low</span> &nbsp;&nbsp;' +
            '🟠🟣 <span style="color:#888;font-weight:600">Novo Baseline + Novo Low</span> &nbsp;&nbsp;' +
            '<span style="color:#888;margin-left:1rem">↑ superior ao anterior &nbsp; ↓ inferior ao anterior</span>' +
            '</div>', unsafe_allow_html=True
        )
        # ── Main table + detail ──
        sub_sorted = sub_ret.copy()
        # Build display rows
        rows_display = []
        for _, row in sub_sorted.iterrows():
            al = row["Alert_Label"]
            if al == "NB+NL": alert_icon = "🟠🟣"
            elif al == "NB":   alert_icon = "🟠"
            elif al == "NL":   alert_icon = "🟣"
            else:              alert_icon = ""
            alert_pill = alert_icon  # keep compat

            if row["Tipo_Preco"] == "Preço Único":
                high_str  = f'{row["Preco_High"]:.2f} €' if row["Preco_High"] else "—"
                low_str   = "—"; prof_str = "—"
                new_h_str = "—"; new_l_str = "—"; new_prof_str = "—"
            else:
                # FIX 6: no emoji icons, orange for baseline, purple for low
                high_str  = f'{row["Preco_High"]:.2f} €' if row["Preco_High"] else "—"
                low_str   = f'{row["Preco_Low"]:.2f} €'  if row["Preco_Low"]  else "—"
                prof_str  = f'{row["Prof_Promo"]:.1f}%'  if row["Prof_Promo"] else "—"
                als = row["Alertas"] or []
                new_highs = [a for a in als if "Baseline" in a["tipo"]]
                new_lows  = [a for a in als if "Low" in a["tipo"]]
                # FIX 7: only new price; FIX 6: direction arrows
                def fmt_new_bl(a):
                    arrow = "↑" if a["preco_novo"] > a["preco_anterior"] else "↓"
                    return f'{arrow} {a["preco_novo"]:.2f} €'
                def fmt_new_low(a):
                    arrow = "↑" if a["preco_novo"] > a["preco_anterior"] else "↓"
                    return f'{arrow} {a["preco_novo"]:.2f} €'
                new_h_str  = " | ".join(fmt_new_bl(a)  for a in new_highs) or "—"
                new_l_str  = " | ".join(fmt_new_low(a) for a in new_lows)  or "—"
                all_als = new_highs + new_lows
                new_prof_str = f'{all_als[-1]["prof_nova"]:.1f}%' if all_als else "—"

            _fv = row.get("Formato","") if hasattr(row,"get") else (row["Formato"] if "Formato" in row.index else "")
            fmt_val = str(_fv) if (_fv is not None and str(_fv) not in ("nan","<NA>","None","")) else "—"
            # FIX 4: new column order
            # Track arrow direction for cell styling
            nb_up  = any(a["preco_novo"] > a["preco_anterior"] for a in new_highs) if new_highs else None
            nl_up  = any(a["preco_novo"] > a["preco_anterior"] for a in new_lows)  if new_lows  else None
            rows_display.append({
                "⚑":     alert_icon,
                "Formato": fmt_val,
                "Marca":   row["Marca"],
                "Nome":    row["Nome"],
                "Qtd":     row["Quantidade"],
                "Baseline €": high_str,
                "Low €":      low_str,
                "Prof.%":     prof_str,
                "Novo Baseline €": new_h_str,
                "Novo Low €":      new_l_str,
                "Nova Prof.%":     new_prof_str,
                "ID":      row["PID"],
                "_nb_up":  nb_up,   # True=up, False=down, None=no alert
                "_nl_up":  nl_up,
            })

        df_display = pd.DataFrame(rows_display)

        # ── Apply conditional cell styling via Styler ─────────────────────────
        COLS_SHOW = ["⚑","Formato","Marca","Nome","Qtd",
                     "Baseline €","Low €","Prof.%",
                     "Novo Baseline €","Novo Low €","Nova Prof.%","ID"]
        df_show = df_display[COLS_SHOW].copy()

        def style_alert_cells(df_s):
            styles = pd.DataFrame("", index=df_s.index, columns=df_s.columns)
            for i in df_show.index:
                nb_up = df_display.loc[i, "_nb_up"]
                nl_up = df_display.loc[i, "_nl_up"]
                if nb_up is True:
                    styles.loc[i, "Novo Baseline €"] = (
                        "background-color:rgba(34,197,94,0.18);"
                        "color:#16a34a;font-weight:700")
                elif nb_up is False:
                    styles.loc[i, "Novo Baseline €"] = (
                        "background-color:rgba(239,68,68,0.18);"
                        "color:#dc2626;font-weight:700")
                if nl_up is True:
                    styles.loc[i, "Novo Low €"] = (
                        "background-color:rgba(34,197,94,0.18);"
                        "color:#16a34a;font-weight:700")
                elif nl_up is False:
                    styles.loc[i, "Novo Low €"] = (
                        "background-color:rgba(239,68,68,0.18);"
                        "color:#dc2626;font-weight:700")
            return styles

        styled = df_show.style.apply(style_alert_cells, axis=None)

        # Show table + on-select graph
        left_col, right_col = st.columns([3,2])
        with left_col:
            sel = st.dataframe(
                styled,
                use_container_width=True, hide_index=True,
                on_select="rerun", selection_mode="single-row",
                key=f"tbl_{ret}",
                column_config={
                    "⚑":             st.column_config.TextColumn("⚑",             width="small"),
                    "Qtd":            st.column_config.TextColumn("Qtd",            width="small"),
                    "Prof.%":         st.column_config.TextColumn("Prof.%",         width="small"),
                    "Nova Prof.%":    st.column_config.TextColumn("Nova Prof.%",    width="small"),
                    "Baseline €":     st.column_config.TextColumn("Baseline €",     width="small"),
                    "Low €":          st.column_config.TextColumn("Low €",          width="small"),
                    "Novo Baseline €":st.column_config.TextColumn("Novo Baseline €",width="small"),
                    "Novo Low €":     st.column_config.TextColumn("Novo Low €",     width="small"),
                    "ID":             st.column_config.TextColumn("ID",             width="small"),
                },
            )
        with right_col:
            selected_rows = sel.selection.rows if sel.selection.rows else []
            if selected_rows:
                idx = selected_rows[0]
                row = sub_sorted.iloc[idx]
                sub_hist = df[(df["PID"]==row["PID"]) & (df["Retalhista"]==row["Retalhista"]) & (df["Data"].dt.date >= p2_start) & (df["Data"].dt.date <= p2_end)].sort_values("Data")
                st.markdown(f"**{row['Nome']}**  \n_{row['Marca']} · {row['Quantidade']}_")
                fig2 = go.Figure()
                if row["Tipo_Preco"]=="High-Low" and row["Preco_High"] and row["Preco_Low"]:
                    fig2.add_hrect(y0=row["Preco_Low"]*0.99, y1=row["Preco_High"]*1.01,
                                   fillcolor="rgba(234,179,8,0.06)", line_width=0)
                    fig2.add_hline(y=row["Preco_High"], line_dash="dot", line_color="rgba(220,38,38,0.6)",
                                   annotation_text=f"Baseline {row['Preco_High']:.2f}€", annotation_position="top right")
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
# TAB 4 — MONTAR GRÁFICOS
# ═══════════════════════════════════════════════════════════════════
with tab4:
    st.markdown('<div class="section-header">📊 Montar Gráficos</div>', unsafe_allow_html=True)
    st.markdown("Seleciona os filtros para visualizar a evolução histórica de múltiplos SKUs num único gráfico.")

    g1, g2, g3, g4, g5 = st.columns(5)
    with g1:
        g_ret   = st.multiselect("Retalhista", retailers_sel, default=retailers_sel, key="g_ret")

    # Cascading: Marca options depend on selected Retalhistas
    _dg_pool = df.copy()
    if g_ret:
        _dg_pool = _dg_pool[_dg_pool["Retalhista"].isin(g_ret)]
    if "Marca Padronizada" in _dg_pool.columns:
        _marca_opts4 = sorted(_dg_pool["Marca Padronizada"].dropna().unique())
    else:
        _marca_opts4 = sorted(_dg_pool["Marca"].dropna().unique())

    with g2:
        g_brand = st.multiselect("Marca", _marca_opts4, key="g_brand")

    # Cascading: Formato options depend on Retalhista + Marca
    if g_brand:
        _dg_pool2 = _dg_pool.copy()
        if "Marca Padronizada" in _dg_pool2.columns:
            _dg_pool2 = _dg_pool2[_dg_pool2["Marca Padronizada"].isin(g_brand)]
        else:
            _dg_pool2 = _dg_pool2[_dg_pool2["Marca"].isin(g_brand)]
    else:
        _dg_pool2 = _dg_pool.copy()
    _dg_pool2["PID"] = _dg_pool2["PID"].astype(str)
    _pool2_fmt = _dg_pool2.merge(df_fmt_lookup, on=["PID","Retalhista"], how="left")
    _fmt_opts4 = sorted(_pool2_fmt["Formato"].dropna().unique()) if (not _pool2_fmt.empty and "Formato" in _pool2_fmt.columns) else []

    with g3:
        g_fmt = st.multiselect("Formato", _fmt_opts4, key="g_fmt")

    # Cascading: Tamanho depends on Retalhista + Marca + Formato
    if g_fmt:
        _dg_pool3 = _pool2_fmt[_pool2_fmt["Formato"].isin(g_fmt)]
    else:
        _dg_pool3 = _pool2_fmt.copy()
    _size_opts4 = sorted(_dg_pool3["Quantidade"].dropna().astype(str).unique())

    with g4:
        g_size  = st.multiselect("Tamanho", _size_opts4, key="g_size")
    with g5:
        g_period = st.date_input("Período", value=(min_date,max_date), min_value=min_date, max_value=max_date, key="g_period")
        gp_s, gp_e = (g_period[0],g_period[1]) if len(g_period)==2 else (min_date,max_date)

    g_search = st.text_input("🔎 Pesquisar por nome do produto", placeholder="ex: Magnum, Cornetto…", key="g_search")

    # Filter data
    dg = df[(df["Data"].dt.date>=gp_s)&(df["Data"].dt.date<=gp_e)].copy()
    if g_ret:    dg = dg[dg["Retalhista"].isin(g_ret)]
    if g_brand:  dg = dg[dg["Marca Padronizada"].isin(g_brand)] if "Marca Padronizada" in dg.columns else dg[dg["Marca"].isin(g_brand)]
    if g_size:   dg = dg[dg["Quantidade"].astype(str).isin(g_size)]
    if g_search: dg = dg[dg["Nome"].str.contains(g_search, case=False, na=False)]
    # Merge Formato for tab4 filter
    dg["PID"] = dg["PID"].astype(str)
    # Build lookup from live session glossario
    live_glossario = load_glossario()
    live_fmt = build_formato_lookup(live_glossario, df_sku_list)
    # Drop Formato col if already present from a previous merge
    if "Formato" in dg.columns:
        dg = dg.drop(columns=["Formato"])
    if not live_fmt.empty and live_fmt["Formato"].notna().any():
        dg = dg.merge(live_fmt, on=["PID","Retalhista"], how="left")
    else:
        # Fallback: try to read glossario_formato.csv directly
        try:
            gl_csv = pd.read_csv("glossario_formato.csv")
            gl_csv["PID"] = gl_csv["PID"].astype(str)
            gl_csv = gl_csv[["PID","Retalhista","Formato"]].dropna(subset=["Formato"])
            if not gl_csv.empty:
                dg = dg.merge(gl_csv, on=["PID","Retalhista"], how="left")
            else:
                dg["Formato"] = None
        except Exception:
            dg["Formato"] = None
    if g_fmt:
        if "Formato" not in dg.columns or dg["Formato"].isna().all():
            st.warning("⚠️ O filtro Formato requer o ficheiro `glossario_formato.csv` no GitHub com classificações preenchidas.")
        else:
            dg = dg[dg["Formato"].isin(g_fmt)]

    n_skus_g = dg.groupby(["PID","Retalhista"]).ngroups
    st.markdown(f"**{n_skus_g} SKU(s)** com os filtros aplicados.")

    MAX_LINES = 60
    if n_skus_g == 0:
        st.info("Nenhum SKU encontrado com os filtros aplicados.")
    elif n_skus_g > MAX_LINES:
        st.warning(f"Muitos SKUs ({n_skus_g}) para visualizar. Aplica mais filtros (sugestão: máx {MAX_LINES} linhas para boa leitura).")
    else:
        # ── Colour palette: evenly spaced hues, good contrast on dark bg ──────
        import colorsys
        n_lines = len(list(dg.groupby(["PID","Retalhista"])))
        def hsl_palette(n):
            colors = []
            for i in range(n):
                h = i / max(n, 1)
                # Avoid yellow-green (0.20–0.35) which looks bad on dark bg
                if 0.20 <= h <= 0.35: h = h + 0.15
                r, g, b = colorsys.hls_to_rgb(h % 1.0, 0.65, 0.85)
                colors.append(f"rgb({int(r*255)},{int(g*255)},{int(b*255)})")
            return colors
        PALETTE = hsl_palette(max(n_lines, 1))

        DASHES = {"Continente":"solid","PingoDoce":"dash","Auchan":"dot"}
        sku_groups = list(dg.groupby(["PID","Retalhista","Nome","Marca"]))

        fig4 = go.Figure()
        for i, ((pid,ret,nome,marca), grp) in enumerate(sku_groups):
            grp   = grp.sort_values("Data")
            color = PALETTE[i % len(PALETTE)]
            dash  = DASHES.get(ret, "solid")
            # Short label for legend
            short = nome[:32] + ("…" if len(nome) > 32 else "")
            fig4.add_trace(go.Scatter(
                x=grp["Data"], y=grp["Preco"],
                mode="lines",          # no markers — cleaner look
                name=short,
                line=dict(color=color, width=1.8, dash=dash),
                hovertemplate=(
                    f"<b>{nome}</b><br>"
                    f"<span style='color:#aaa'>{ret}</span><br>"
                    "%{x|%d %b %Y}<br>"
                    "<b>%{y:.2f} €</b>"
                    "<extra></extra>"
                ),
            ))

        fig4.update_layout(
            height=560,
            template="plotly_dark",
            yaxis_title="Preço (€)",
            xaxis_title="",
            hovermode="x unified",
            hoverlabel=dict(bgcolor="#1e293b", font_size=12, font_color="white"),
            legend=dict(
                orientation="v",
                yanchor="top", y=1,
                xanchor="left", x=1.01,
                font=dict(size=10.5, color="#e2e8f0"),
                bgcolor="rgba(15,23,42,0.7)",
                bordercolor="#334155", borderwidth=1,
                itemsizing="constant",
            ),
            plot_bgcolor="#0f172a",
            paper_bgcolor="#0f172a",
            xaxis=dict(
                showgrid=True, gridcolor="#1e293b", gridwidth=1,
                zeroline=False, color="#94a3b8",
            ),
            yaxis=dict(
                showgrid=True, gridcolor="#1e293b", gridwidth=1,
                zeroline=False, color="#94a3b8",
            ),
            margin=dict(t=20, b=40, l=50, r=20),
            font=dict(color="#e2e8f0"),
        )
        fig4.add_annotation(
            text="— Continente &nbsp;&nbsp; - - PingoDoce &nbsp;&nbsp; · · · Auchan",
            xref="paper", yref="paper", x=0.01, y=-0.07,
            showarrow=False, font=dict(size=10, color="#64748b"),
            align="left",
        )
        st.plotly_chart(fig4, use_container_width=True, key="chart_tab4_multi")

        # ── Summary table below chart ─────────────────────────────────────────
        st.markdown("#### Tabela de SKUs no gráfico")
        # Build summary from sku_cls
        pids_in_chart = dg[["PID","Retalhista"]].drop_duplicates()
        tbl4 = pids_in_chart.merge(
            sku_cls[["PID","Retalhista","Tipo_Preco","Preco_High","Preco_Low","Alert_Label","Alertas"]],
            on=["PID","Retalhista"], how="left"
        )
        tbl4 = tbl4.merge(
            df_sku_list[["PID","Retalhista","Nome","Marca","Quantidade"]],
            on=["PID","Retalhista"], how="left"
        )
        tbl4 = tbl4.merge(df_fmt_lookup, on=["PID","Retalhista"], how="left")

        # Get new baseline/low from alerts
        def get_new_bl(alertas):
            if not alertas: return "—"
            nbs = [a for a in alertas if "Baseline" in a["tipo"]]
            return f"{nbs[-1]['preco_novo']:.2f} €" if nbs else "—"
        def get_new_low(alertas):
            if not alertas: return "—"
            nls = [a for a in alertas if "Low" in a["tipo"]]
            return f"{nls[-1]['preco_novo']:.2f} €" if nls else "—"

        tbl4["Baseline €"]     = tbl4["Preco_High"].apply(lambda x: f"{x:.2f} €" if pd.notna(x) else "—")
        tbl4["Low €"]          = tbl4["Preco_Low"].apply(lambda x: f"{x:.2f} €" if pd.notna(x) else "—")
        tbl4["Novo Baseline €"]= tbl4["Alertas"].apply(lambda x: get_new_bl(x) if x else "—")
        tbl4["Novo Low €"]     = tbl4["Alertas"].apply(lambda x: get_new_low(x) if x else "—")
        tbl4["Alerta"]         = tbl4["Alert_Label"].fillna("")

        disp4 = tbl4[["Formato","Marca","Nome","Quantidade","Baseline €","Low €","Novo Baseline €","Novo Low €"]].copy()
        disp4 = disp4.sort_values(["Formato","Marca","Nome"])
        st.dataframe(disp4, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════
# TAB 5 — SKUs NÃO CLASSIFICADOS
# ═══════════════════════════════════════════════════════════════════
with tab5:
    st.markdown('<div class="section-header">🏷️ Classificar SKUs</div>', unsafe_allow_html=True)

    glossario = load_glossario()

    # ── Build export CSV (always, even if empty) ─────────────────────────────
    # Export = ALL SKUs from df_sku_list, with Formato from glossario (or blank if unclassified)
    gl_rows = []
    for _, sku_row in df_sku_list.iterrows():
        key_id = f"{sku_row['PID']}_{sku_row['Retalhista']}"
        fmt = glossario.get(key_id, None)
        gl_rows.append({
            "PID":        sku_row["PID"],
            "Retalhista": sku_row["Retalhista"],
            "Nome":       str(sku_row["Nome"])       if pd.notna(sku_row.get("Nome"))       else "",
            "Marca":      str(sku_row["Marca"])      if pd.notna(sku_row.get("Marca"))      else "",
            "Quantidade": str(sku_row["Quantidade"]) if pd.notna(sku_row.get("Quantidade")) else "",
            "Formato":    fmt if fmt else "",
        })
    df_gl_export = pd.DataFrame(gl_rows)
    csv_gl = df_gl_export.to_csv(index=False).encode("utf-8")

    # ── Top bar ───────────────────────────────────────────────────────────────
    st.markdown(
        "Classifica os SKUs abaixo e clica no botão **Descarregar glossário** para guardar o CSV. "
        "Faz depois o upload desse ficheiro para o GitHub com o nome exacto **`glossario_formato.csv`** "
        "— o app carrega-o automaticamente ao arrancar."
    )
    st.markdown(f"Actualmente tem **{len(glossario)} classificações** no glossário desta sessão.")

    dl_col, reload_col = st.columns([3, 1])
    with dl_col:
        st.download_button(
            label="⬇️ Descarregar glossário (glossario_formato.csv)",
            data=csv_gl,
            file_name="glossario_formato.csv",
            mime="text/csv",
            key="dl_glossario",
            use_container_width=True,
            type="primary",
        )
    with reload_col:
        if st.button("🔄 Forçar recarga do GitHub", use_container_width=True, key="force_reload"):
            load_glossario_csv_from_github.clear()
            load_glossario_df.clear()
            # Also reset session state glossario so it re-seeds from GitHub
            if GLOSSARIO_KEY in st.session_state:
                del st.session_state[GLOSSARIO_KEY]
            st.success("Cache limpo! A recarregar...")
            st.rerun()
    st.caption("ℹ️ Após fazer upload para o GitHub, clica em **Forçar recarga** para ver as alterações imediatamente.")

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

    f5a, f5b, f5c = st.columns([1, 1, 2])
    with f5a:
        view_mode = st.radio("Mostrar:", ["Não classificados", "Todos os SKUs", "Apenas classificados"],
                              horizontal=False, key="tab5_view")
    with f5b:
        uc_ret5 = st.multiselect("Retalhista", retailers_sel,
                                  default=retailers_sel, key="uc_ret5")
    with f5c:
        uc_search5 = st.text_input("🔎 Pesquisar por nome ou PID",
                                    placeholder="ex: Magnum, Cookie Dough, 8240610…",
                                    key="uc_search5")

    if view_mode == "Não classificados":
        display_skus = df_all_skus[df_all_skus["Formato"].isna()]
    elif view_mode == "Apenas classificados":
        display_skus = df_all_skus[df_all_skus["Formato"].notna()]
    else:
        display_skus = df_all_skus.copy()

    display_skus = display_skus[display_skus["Retalhista"].isin(uc_ret5)]

    if uc_search5:
        mask = (
            display_skus["Nome"].str.contains(uc_search5, case=False, na=False) |
            display_skus["PID"].astype(str).str.contains(uc_search5, case=False, na=False) |
            display_skus.get("Marca", pd.Series(dtype=str)).str.contains(uc_search5, case=False, na=False)
        )
        display_skus = display_skus[mask]

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


# ═══════════════════════════════════════════════════════════════════
# TAB 6 — ANÁLISE DE CLUSTERS (Beta)
# ═══════════════════════════════════════════════════════════════════
with tab6:
    st.markdown('<div class="section-header">🔬 Análise de Clusters <span style="font-size:.75rem;color:#888;font-family:DM Sans,sans-serif">(Beta)</span></div>', unsafe_allow_html=True)
    st.markdown("Agrupa SKUs por padrão de preço (Baseline + Low dentro de ±0.05 €). Hierarquia: **Retalhista → Marca → Formato → Cluster**.")

    # ── Cascading filters ─────────────────────────────────────────────────────
    # Build SKU summary first (needed for cascade)
    @st.cache_data(ttl=300)
    def build_sku_summary_cached(df_input, df_gl):
        from collections import Counter as _C
        records = []
        for (pid, ret), grp in df_input.groupby(["PID","Retalhista"]):
            grp = grp.sort_values("Data")
            prices = grp["Preco"].tolist()
            cnt = _C(prices)
            n = len(prices)
            if n == 0: continue
            most_freq_pct = cnt.most_common(1)[0][1] / n
            if most_freq_pct >= 0.90 or len(set(prices)) == 1:
                bl, low = max(prices), None
            else:
                top2 = sorted(cnt.keys(), key=lambda p: -cnt[p])[:2]
                bl, low = max(top2), min(top2)
            gl_r = df_gl[df_gl["PID"]==pid] if not df_gl.empty else pd.DataFrame()
            fmt   = gl_r["Formato"].iloc[0]           if not gl_r.empty and pd.notna(gl_r["Formato"].iloc[0]) else None
            marca = gl_r["Marca Padronizada"].iloc[0]  if not gl_r.empty and "Marca Padronizada" in gl_r.columns and pd.notna(gl_r["Marca Padronizada"].iloc[0]) else grp["Marca"].iloc[0]
            qtd   = gl_r["Quantidade"].iloc[0]         if not gl_r.empty and pd.notna(gl_r["Quantidade"].iloc[0]) else grp["Quantidade"].iloc[0]
            records.append({"PID":pid,"Retalhista":ret,"Nome":grp["Nome"].iloc[0],
                            "Marca":marca,"Formato":fmt,"Quantidade":str(qtd),
                            "Baseline":bl,"Low":low if low else bl})
        return pd.DataFrame(records)

    df_sku_sum_cl = build_sku_summary_cached(df, df_gl_full if not df_gl_full.empty else pd.DataFrame())

    cl_a, cl_b, cl_c, cl_d = st.columns(4)
    with cl_a:
        cl_ret = st.multiselect("Retalhista", retailers_sel, default=retailers_sel[:1], key="cl_ret")

    # Formato options: only those present in selected retailers
    if cl_ret:
        fmt_pool = df_sku_sum_cl[df_sku_sum_cl["Retalhista"].isin(cl_ret)]
    else:
        fmt_pool = df_sku_sum_cl.copy()
    cl_fmt_opts = sorted(fmt_pool["Formato"].dropna().unique())

    with cl_b:
        cl_fmt = st.multiselect("Formato", cl_fmt_opts,
                                default=cl_fmt_opts[:1] if cl_fmt_opts else [],
                                key="cl_fmt")

    # Marca options: only those present in selected retailers × formats
    if cl_fmt:
        marca_pool = fmt_pool[fmt_pool["Formato"].isin(cl_fmt)]
    else:
        marca_pool = fmt_pool.copy()
    cl_marca_opts = sorted(marca_pool["Marca"].dropna().unique())

    with cl_c:
        cl_marca = st.multiselect("Marca", cl_marca_opts, key="cl_marca")

    with cl_d:
        cl_tol = st.slider("Tolerância (€)", min_value=0.01, max_value=0.20, value=0.05, step=0.01, key="cl_tol")

    st.markdown("---")

    # Apply filters (using df_sku_sum_cl built above)
    cl_filtered = df_sku_sum_cl.copy()
    if cl_ret:   cl_filtered = cl_filtered[cl_filtered["Retalhista"].isin(cl_ret)]
    if cl_fmt:   cl_filtered = cl_filtered[cl_filtered["Formato"].isin(cl_fmt)]
    if cl_marca: cl_filtered = cl_filtered[cl_filtered["Marca"].isin(cl_marca)]
    cl_filtered = cl_filtered.dropna(subset=["Baseline"])

    if cl_filtered.empty:
        st.info("Nenhum SKU com os filtros seleccionados.")
    else:
        # ── Cluster algorithm ─────────────────────────────────────────────────
        TOLERANCE = cl_tol
        cluster_rows = []   # for table
        chart_rows   = []   # for chart

        # Group by Retalhista → Marca → Formato
        for (ret, marca, fmt), grp in cl_filtered.groupby(["Retalhista","Marca","Formato"]):
            grp = grp.sort_values(["Baseline","Low"])
            clusters = []
            for _, row in grp.iterrows():
                placed = False
                for cl_obj in clusters:
                    if (abs(row["Baseline"] - cl_obj["bl"]) <= TOLERANCE and
                        abs(row["Low"]      - cl_obj["low"]) <= TOLERANCE):
                        cl_obj["members"].append(row)
                        placed = True; break
                if not placed:
                    clusters.append({"bl":row["Baseline"],"low":row["Low"],"members":[row]})

            for i, cl_obj in enumerate(clusters):
                letter = chr(65 + i)
                cl_label = f"{marca} — Cluster {letter}"
                members = cl_obj["members"]
                # Aggregate: use median of members for the bar
                bl_val  = round(np.median([m["Baseline"] for m in members]), 2)
                low_val = round(np.median([m["Low"]      for m in members]), 2)
                prof    = round((1 - low_val/bl_val)*100, 1) if bl_val > 0 else 0
                nomes   = "<br>".join(f"• {m['Nome'][:55]}" for m in members)
                qtds    = ", ".join(set(m["Quantidade"] for m in members if m["Quantidade"]))

                chart_rows.append({
                    "Retalhista": ret, "Marca": marca, "Formato": fmt,
                    "Cluster":    cl_label, "Cluster_Letter": letter,
                    "Baseline":   bl_val, "Low": low_val,
                    "Prof_%":     prof, "N_SKUs": len(members),
                    "Produtos":   nomes,
                })
                for m in members:
                    cluster_rows.append({
                        "Retalhista": ret, "Marca": marca, "Formato": fmt,
                        "Cluster": f"Cluster {letter}",
                        "Nome": m["Nome"], "Quantidade": m["Quantidade"],
                        "Baseline €": f"{m['Baseline']:.2f}",
                        "Low €": f"{m['Low']:.2f}",
                        "Prof.%": f"{round((1-m['Low']/m['Baseline'])*100,1)}%" if m['Baseline']>0 else "—",
                    })

        df_chart = pd.DataFrame(chart_rows)
        df_table = pd.DataFrame(cluster_rows)

        if df_chart.empty:
            st.info("Sem clusters para mostrar.")
        else:
            # ── KPIs ──────────────────────────────────────────────────────────
            n_clusters = len(df_chart)
            n_skus_cl  = len(df_table)
            n_marcas   = df_chart["Marca"].nunique()
            k1,k2,k3 = st.columns(3)
            k1.markdown(f'<div class="kpi-item"><h4>Marcas</h4><p>{n_marcas}</p></div>', unsafe_allow_html=True)
            k2.markdown(f'<div class="kpi-item"><h4>Clusters</h4><p>{n_clusters}</p></div>', unsafe_allow_html=True)
            k3.markdown(f'<div class="kpi-item"><h4>SKUs</h4><p>{n_skus_cl}</p></div>', unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

            # ── Chart: horizontal range bars ─────────────────────────────────
            st.markdown("#### Mapa de Preços por Cluster")
            st.caption("Cada barra mostra o intervalo Low → Baseline. Passa o cursor para ver os produtos.")

            # Sort by Marca then Baseline
            df_chart = df_chart.sort_values(["Marca","Baseline","Low"], ascending=[True,False,False])

            fig_cl = go.Figure()

            # One trace per cluster = horizontal bar from Low to Baseline
            colors_cl = px.colors.qualitative.Bold + px.colors.qualitative.Pastel
            marca_colors = {m: colors_cl[i % len(colors_cl)]
                            for i, m in enumerate(df_chart["Marca"].unique())}

            for _, row in df_chart.iterrows():
                color = marca_colors.get(row["Marca"], "#888")
                hover = (
                    f"<b>{row['Cluster']}</b><br>"
                    f"Formato: {row['Formato']}<br>"
                    f"Baseline: <b>{row['Baseline']:.2f} €</b><br>"
                    f"Low: <b>{row['Low']:.2f} €</b><br>"
                    f"Prof.: <b>{row['Prof_%']:.1f}%</b><br>"
                    f"SKUs ({row['N_SKUs']}):<br>{row['Produtos']}"
                )
                # Bar: from Low to Baseline
                fig_cl.add_trace(go.Bar(
                    x=[row["Baseline"] - row["Low"]],
                    y=[row["Cluster"]],
                    base=[row["Low"]],
                    orientation="h",
                    name=row["Marca"],
                    marker=dict(color=color, opacity=0.85,
                                line=dict(color=color, width=1.5)),
                    hovertemplate=hover + "<extra></extra>",
                    showlegend=row["Cluster"].endswith("Cluster A"),  # one legend per marca
                ))
                # Dot at Low
                fig_cl.add_trace(go.Scatter(
                    x=[row["Low"]], y=[row["Cluster"]],
                    mode="markers", marker=dict(color=color, size=8, symbol="circle"),
                    hoverinfo="skip", showlegend=False,
                ))
                # Dot at Baseline
                fig_cl.add_trace(go.Scatter(
                    x=[row["Baseline"]], y=[row["Cluster"]],
                    mode="markers", marker=dict(color=color, size=8, symbol="diamond"),
                    hoverinfo="skip", showlegend=False,
                ))

            fig_cl.update_layout(
                height=max(350, n_clusters * 38),
                barmode="overlay",
                template="plotly_white",
                xaxis=dict(title="Preço (€)", showgrid=True, gridcolor="#e5e7eb"),
                yaxis=dict(title="", autorange="reversed",
                           tickfont=dict(size=11)),
                legend=dict(title="Marca", orientation="v",
                            yanchor="top", y=1, xanchor="left", x=1.01,
                            font=dict(size=10)),
                margin=dict(t=20, b=40, l=10, r=150),
                hovermode="closest",
            )
            st.plotly_chart(fig_cl, use_container_width=True, key="chart_clusters")

            # ── Table ─────────────────────────────────────────────────────────
            st.markdown("#### Tabela de Clusters")
            for ret_val in sorted(df_table["Retalhista"].unique()):
                st.markdown(retailer_header(ret_val), unsafe_allow_html=True)
                sub_t = df_table[df_table["Retalhista"]==ret_val].copy()
                sub_t = sub_t[["Marca","Formato","Cluster","Nome","Quantidade","Baseline €","Low €","Prof.%"]]
                sub_t = sub_t.sort_values(["Marca","Formato","Cluster","Nome"])
                st.dataframe(sub_t, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════
# TAB NOW — PREÇO AGORA
# ═══════════════════════════════════════════════════════════════════
with tab_now:
    st.markdown('<div class="section-header">🔍 Preço Agora</div>', unsafe_allow_html=True)
    st.markdown("Consulta o **preço mais recente** de cada SKU em cada retalhista, com o Máximo e Mínimo dos últimos 30 dias.")

    # ── Build "now" dataset ───────────────────────────────────────────────────
    # Latest price per PID × Retalhista
    _now_latest = (df.sort_values("Data")
                   .groupby(["PID","Retalhista"]).last()
                   .reset_index()
                   [["PID","Retalhista","Nome","Marca","Quantidade","Preco","Data"]])
    _now_latest.rename(columns={"Preco":"Preco_Atual","Data":"Data_Leitura"}, inplace=True)

    # Min/Max last 30 days
    _cutoff_30 = pd.Timestamp(max_date) - timedelta(days=30)
    _df_30 = df[df["Data"] >= _cutoff_30]
    _stats_30 = (_df_30.groupby(["PID","Retalhista"])["Preco"]
                 .agg(Min_30d="min", Max_30d="max")
                 .reset_index())

    _now_full = _now_latest.merge(_stats_30, on=["PID","Retalhista"], how="left")

    # Merge Marca Padronizada
    if not df_gl_full.empty and "Marca Padronizada" in df_gl_full.columns:
        _mp = df_gl_full[["PID","Retalhista","Marca Padronizada"]].drop_duplicates()
        _now_full = _now_full.merge(_mp, on=["PID","Retalhista"], how="left")
        _marca_col = "Marca Padronizada"
    else:
        _marca_col = "Marca"

    # Merge Formato
    _now_full["PID"] = _now_full["PID"].astype(str)
    if "Formato" in _now_full.columns:
        _now_full = _now_full.drop(columns=["Formato"])
    if not df_fmt_lookup.empty:
        _now_full = _now_full.merge(df_fmt_lookup, on=["PID","Retalhista"], how="left")
    if "Formato" not in _now_full.columns:
        _now_full["Formato"] = None

    # ── Left sidebar-style filters (columns layout) ───────────────────────────
    left_f, right_tbl = st.columns([1, 3])

    with left_f:
        st.markdown("#### Filtros")

        # Retalhista
        _now_ret_opts = sorted(_now_full["Retalhista"].dropna().unique())
        now_ret = st.multiselect("Retalhista", _now_ret_opts, default=_now_ret_opts, key="now_ret")

        # Cascading: Marca
        _now_pool = _now_full.copy()
        if now_ret:
            _now_pool = _now_pool[_now_pool["Retalhista"].isin(now_ret)]
        _now_marca_opts = sorted(_now_pool[_marca_col].dropna().unique())
        now_marca = st.multiselect("Marca", _now_marca_opts, key="now_marca")

        # Cascading: Formato
        if now_marca:
            _now_pool2 = _now_pool[_now_pool[_marca_col].isin(now_marca)]
        else:
            _now_pool2 = _now_pool.copy()
        _now_fmt_opts = sorted(_now_pool2["Formato"].dropna().unique()) if "Formato" in _now_pool2.columns else []
        now_fmt = st.multiselect("Formato", _now_fmt_opts, key="now_fmt")

        # Cascading: Tamanho
        if now_fmt:
            _now_pool3 = _now_pool2[_now_pool2["Formato"].isin(now_fmt)]
        else:
            _now_pool3 = _now_pool2.copy()
        _now_size_opts = sorted(_now_pool3["Quantidade"].dropna().astype(str).unique())
        now_size = st.multiselect("Tamanho", _now_size_opts, key="now_size")

        # Cascading: SKU
        if now_size:
            _now_pool4 = _now_pool3[_now_pool3["Quantidade"].astype(str).isin(now_size)]
        else:
            _now_pool4 = _now_pool3.copy()
        _now_sku_opts = sorted(_now_pool4["Nome"].dropna().unique())
        now_sku = st.multiselect("SKU", _now_sku_opts, key="now_sku")

        # Free-text search with dropdown feel
        st.markdown("---")
        st.markdown("**Pesquisa por nome**")
        now_search = st.text_input("", placeholder="ex: Magnum, Cornetto…",
                                    key="now_search", label_visibility="collapsed")
        if now_search:
            _search_matches = sorted([n for n in _now_sku_opts
                                       if now_search.lower() in n.lower()])[:20]
            if _search_matches:
                st.caption(f"{len(_search_matches)} resultado(s) — selecciona abaixo para adicionar:")
                _to_add = st.multiselect("Adicionar à selecção", _search_matches,
                                          key="now_search_add", label_visibility="collapsed")
                if _to_add:
                    # Merge search additions into now_sku session
                    _combined = list(set((now_sku or []) + _to_add))
                    st.session_state["now_sku"] = _combined
                    now_sku = _combined

    # ── Apply filters ─────────────────────────────────────────────────────────
    _now_filtered = _now_full.copy()
    if now_ret:    _now_filtered = _now_filtered[_now_filtered["Retalhista"].isin(now_ret)]
    if now_marca:  _now_filtered = _now_filtered[_now_filtered[_marca_col].isin(now_marca)]
    if now_fmt:    _now_filtered = _now_filtered[_now_filtered["Formato"].isin(now_fmt)]
    if now_size:   _now_filtered = _now_filtered[_now_filtered["Quantidade"].astype(str).isin(now_size)]
    if now_sku:    _now_filtered = _now_filtered[_now_filtered["Nome"].isin(now_sku)]
    if now_search and not now_sku:
        _now_filtered = _now_filtered[_now_filtered["Nome"].str.contains(now_search, case=False, na=False)]

    with right_tbl:
        st.markdown(f"**{_now_filtered['Nome'].nunique()} SKU(s)** encontrado(s) · "
                    f"**{len(_now_filtered)}** combinações produto × retalhista")

        if _now_filtered.empty:
            st.info("Sem SKUs com os filtros seleccionados.")
        else:
            # ── Pivot: one row per SKU, columns per retailer ───────────────────
            # Build wide table: SKU info + for each retailer: Preço Atual, Min 30d, Max 30d
            _pivot_rows = []
            _sku_groups = _now_filtered.groupby("Nome")

            for nome, grp in _sku_groups:
                marca_v = grp[_marca_col].iloc[0] if _marca_col in grp.columns else grp["Marca"].iloc[0]
                qtd_v   = str(grp["Quantidade"].iloc[0]) if pd.notna(grp["Quantidade"].iloc[0]) else "—"
                fmt_v   = str(grp["Formato"].iloc[0]) if ("Formato" in grp.columns and pd.notna(grp["Formato"].iloc[0])) else "—"
                row_d   = {"Nome": nome, "Marca": marca_v, "Formato": fmt_v, "Qtd": qtd_v}
                for ret_v in RETAILER_ORDER:
                    sub_r = grp[grp["Retalhista"]==ret_v]
                    if sub_r.empty:
                        row_d[f"{ret_v} €"]    = "—"
                        row_d[f"{ret_v} Min"]  = "—"
                        row_d[f"{ret_v} Máx"]  = "—"
                    else:
                        r = sub_r.iloc[0]
                        row_d[f"{ret_v} €"]   = f"{r['Preco_Atual']:.2f}"
                        row_d[f"{ret_v} Min"]  = f"{r['Min_30d']:.2f}" if pd.notna(r.get('Min_30d')) else "—"
                        row_d[f"{ret_v} Máx"]  = f"{r['Max_30d']:.2f}" if pd.notna(r.get('Max_30d')) else "—"
                _pivot_rows.append(row_d)

            df_pivot = pd.DataFrame(_pivot_rows).sort_values(["Marca","Nome"])

            # Style: highlight current price cells
            def style_now(df_s):
                styles = pd.DataFrame("", index=df_s.index, columns=df_s.columns)
                for ret_v in RETAILER_ORDER:
                    col_now = f"{ret_v} €"
                    if col_now in df_s.columns:
                        color = RETAILER_COLORS.get(ret_v, "#333")
                        for i in df_s.index:
                            if df_s.loc[i, col_now] != "—":
                                styles.loc[i, col_now] = (
                                    f"background-color:{color}18;"
                                    f"color:{color};"
                                    "font-weight:700;"
                                )
                return styles

            st.dataframe(
                df_pivot.style.apply(style_now, axis=None),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Nome":  st.column_config.TextColumn("Nome", width="large"),
                    "Marca": st.column_config.TextColumn("Marca", width="medium"),
                    **{f"{r} €":   st.column_config.TextColumn(f"{r} Atual €", width="small")  for r in RETAILER_ORDER},
                    **{f"{r} Min": st.column_config.TextColumn(f"{r} Mín 30d", width="small")  for r in RETAILER_ORDER},
                    **{f"{r} Máx": st.column_config.TextColumn(f"{r} Máx 30d", width="small")  for r in RETAILER_ORDER},
                },
            )

            # ── Last read date info ────────────────────────────────────────────
            st.caption(
                f"Preço Atual = última leitura disponível. "
                f"Mín/Máx = intervalo dos últimos 30 dias (desde {_cutoff_30.strftime('%d/%m/%Y')})."
            )

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("<p style='text-align:center;color:#bbb;font-size:.78rem;'>Monitoramento de Preços IceCream Portugal · Actualizado automaticamente com o ficheiro Excel do scraper</p>", unsafe_allow_html=True)
