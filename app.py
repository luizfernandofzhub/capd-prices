import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px
from io import BytesIO

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CAPD · Price Intelligence",import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px
from io import BytesIO

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CAPD · Price Intelligence",
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

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<h1 style='font-family:"DM Serif Display",serif; font-size:2.4rem; margin-bottom:.2rem;'>
    CAPD · Price Intelligence
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
tab1, tab2, tab3, tab4 = st.tabs([
    "🆕 Produtos Novos",
    "📈 Análise de Preços",
    "🏷️ Descontos Promocionais",
    "🔍 Produto Individual",
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

            display = sub[["Nome","Marca","Quantidade","Preco","Primeira_Leitura"]].copy()
            display.columns = ["Nome","Marca","Quantidade","Preço atual (€)","1ª Leitura"]
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
# TAB 2 — ANÁLISE DE PREÇOS
# ─────────────────────────────────────────────────────────────────
with tab2:
    st.markdown('<div class="section-header">📈 Análise de Preços por Produto</div>', unsafe_allow_html=True)

    # Per (PID, Retalhista) compute min / max / unique prices
    summary = (
        df_period.groupby(["PID","Retalhista","Nome","Marca","Quantidade"])["Preco"]
        .agg(
            Minimo="min",
            Maximo="max",
            Leituras="count",
            Precos_Distintos=lambda x: x.nunique(),
        )
        .reset_index()
    )
    summary["Variacao_Pct"] = ((summary["Maximo"] - summary["Minimo"]) / summary["Maximo"] * 100).round(1)
    summary["Houve_Alteracao"] = summary["Precos_Distintos"] > 1

    st.markdown(f"**{len(summary)} SKU × retalhista** no período seleccionado.")

    c1, c2 = st.columns([1, 2])
    with c1:
        show_changed = st.checkbox("🔴 Apenas com alteração de preço", value=False)
        brand_filter = st.multiselect("Filtrar por marca", sorted(summary["Marca"].unique()))
    with c2:
        search = st.text_input("🔎 Pesquisar por nome", placeholder="ex: Ben & Jerry's")

    filtered = summary.copy()
    if show_changed:
        filtered = filtered[filtered["Houve_Alteracao"]]
    if brand_filter:
        filtered = filtered[filtered["Marca"].isin(brand_filter)]
    if search:
        filtered = filtered[filtered["Nome"].str.contains(search, case=False, na=False)]

    filtered = filtered.sort_values("Variacao_Pct", ascending=False)

    # Display
    for _, row in filtered.head(100).iterrows():
        changed_html = (
            '<span class="tag tag-alert">⚠️ Alterou</span>'
            if row["Houve_Alteracao"]
            else '<span class="tag tag-new">✔ Estável</span>'
        )
        ret_html = badge(row["Retalhista"])
        with st.expander(f"{row['Nome']} — {row['Marca']}  |  {row['Retalhista']}"):
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Mínimo", f"{row['Minimo']:.2f} €")
            c2.metric("Máximo", f"{row['Maximo']:.2f} €")
            c3.metric("Variação", f"{row['Variacao_Pct']:.1f}%")
            c4.metric("Preços distintos", int(row["Precos_Distintos"]))
            c5.metric("Leituras", int(row["Leituras"]))

            # Price evolution chart for this product
            sub = df_period[(df_period["PID"] == row["PID"]) & (df_period["Retalhista"] == row["Retalhista"])]
            sub = sub.sort_values("Data")
            if len(sub) > 1:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=sub["Data"], y=sub["Preco"],
                    mode="lines+markers",
                    line=dict(color=RETAILER_COLORS.get(row["Retalhista"], "#333"), width=2),
                    marker=dict(size=6),
                    name="Preço",
                ))
                fig.update_layout(
                    height=200, margin=dict(t=10,b=10,l=10,r=10),
                    yaxis_title="€", xaxis_title="",
                    template="plotly_white",
                )
                st.plotly_chart(fig, use_container_width=True, key=f"chart_tab2_{row['PID']}_{row['Retalhista']}")

# ─────────────────────────────────────────────────────────────────
# TAB 3 — DESCONTOS PROMOCIONAIS
# ─────────────────────────────────────────────────────────────────
with tab3:
    st.markdown('<div class="section-header">🏷️ Descontos Promocionais</div>', unsafe_allow_html=True)
    st.markdown("Percentual de desconto = **(Máximo − Mínimo) / Máximo × 100**. Só produtos com pelo menos 2 leituras e variação de preço.")

    promo = (
        df_period.groupby(["PID","Retalhista","Nome","Marca","Quantidade"])["Preco"]
        .agg(Minimo="min", Maximo="max", Leituras="count", Distintos=lambda x: x.nunique())
        .reset_index()
    )
    promo = promo[promo["Distintos"] > 1].copy()
    promo["Desconto_Pct"] = ((promo["Maximo"] - promo["Minimo"]) / promo["Maximo"] * 100).round(1)
    promo = promo.sort_values("Desconto_Pct", ascending=False)

    if promo.empty:
        st.info("Sem variação de preço no período seleccionado.")
    else:
        col_thresh, col_ret = st.columns(2)
        with col_thresh:
            min_disc = st.slider("Desconto mínimo (%)", 0, 50, 5)
        with col_ret:
            ret_filter = st.multiselect("Retalhista", retailers_sel, default=retailers_sel)

        promo_f = promo[(promo["Desconto_Pct"] >= min_disc) & (promo["Retalhista"].isin(ret_filter))]

        st.markdown(f"**{len(promo_f)} produto(s)** com desconto ≥ {min_disc}%")

        # Bar chart top 20
        top20 = promo_f.head(20)
        if not top20.empty:
            fig = px.bar(
                top20,
                x="Desconto_Pct",
                y=top20["Nome"].str[:40],
                color="Retalhista",
                color_discrete_map=RETAILER_COLORS,
                orientation="h",
                template="plotly_white",
                labels={"Desconto_Pct": "Desconto (%)", "y": ""},
                title="Top 20 maiores descontos observados",
            )
            fig.update_layout(height=500, margin=dict(t=40,b=10), legend_title_text="")
            st.plotly_chart(fig, use_container_width=True, key="chart_3")

        # Table
        display_promo = promo_f[["Nome","Marca","Retalhista","Minimo","Maximo","Desconto_Pct","Distintos","Leituras"]].copy()
        display_promo.columns = ["Nome","Marca","Retalhista","Mínimo €","Máximo €","Desconto %","Preços distintos","Leituras"]
        display_promo["Mínimo €"] = display_promo["Mínimo €"].map("{:.2f}".format)
        display_promo["Máximo €"] = display_promo["Máximo €"].map("{:.2f}".format)
        display_promo["Desconto %"] = display_promo["Desconto %"].map("{:.1f}".format)
        st.dataframe(display_promo, use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────────────
# TAB 4 — PRODUTO INDIVIDUAL
# ─────────────────────────────────────────────────────────────────
with tab4:
    st.markdown('<div class="section-header">🔍 Análise Individual de Produto</div>', unsafe_allow_html=True)
    st.markdown("Pesquisa um produto e compara-o nos 3 retalhistas.")

    search_prod = st.text_input("🔎 Nome do produto (ex: Häagen-Dazs, Ben & Jerry's, Cornetto…)")

    if search_prod:
        results = df[df["Nome"].str.contains(search_prod, case=False, na=False)]
        if results.empty:
            st.warning("Nenhum produto encontrado.")
        else:
            # Group by retailer
            groups = results.groupby(["Retalhista","PID","Nome","Marca","Quantidade"])

            # Show matches
            matches = results[["Retalhista","PID","Nome","Marca","Quantidade"]].drop_duplicates()
            st.markdown(f"**{len(matches)} SKU(s) encontrado(s):**")
            for _, m in matches.iterrows():
                st.markdown(f"- {badge(m['Retalhista'])} &nbsp; **{m['Nome']}** · {m['Marca']} · {m['Quantidade']}", unsafe_allow_html=True)

            st.markdown("#### Evolução de preço")
            fig = go.Figure()
            for (ret, pid, nome, marca, qtd), grp in groups:
                grp = grp.sort_values("Data")
                fig.add_trace(go.Scatter(
                    x=grp["Data"],
                    y=grp["Preco"],
                    mode="lines+markers",
                    name=f"{ret}: {nome[:35]}",
                    line=dict(color=RETAILER_COLORS.get(ret, "#333"), width=2),
                    marker=dict(size=6),
                ))
            fig.update_layout(
                height=380,
                template="plotly_white",
                yaxis_title="€",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                margin=dict(t=10,b=10),
            )
            st.plotly_chart(fig, use_container_width=True, key=f"chart_tab4_{id(fig)}")

            # Summary table
            summ = (
                results.groupby(["Retalhista","Nome","Marca"])["Preco"]
                .agg(Min="min", Max="max", Atual="last", N="count", Distintos="nunique")
                .reset_index()
            )
            summ["Desconto %"] = ((summ["Max"] - summ["Min"]) / summ["Max"] * 100).round(1)
            summ = summ.rename(columns={"Min":"Mín €","Max":"Máx €","Atual":"Preço atual €","N":"Leituras","Distintos":"Preços únicos"})
            st.dataframe(summ, use_container_width=True, hide_index=True)
    else:
        st.info("Escreve um nome de produto para começar a pesquisa.")

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<p style='text-align:center;color:#bbb;font-size:.8rem;'>"
    "CAPD Price Intelligence · Actualizado automaticamente com o ficheiro Excel do scraper"
    "</p>",
    unsafe_allow_html=True,
)

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

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<h1 style='font-family:"DM Serif Display",serif; font-size:2.4rem; margin-bottom:.2rem;'>
    CAPD · Price Intelligence
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
tab1, tab2, tab3, tab4 = st.tabs([
    "🆕 Produtos Novos",
    "📈 Análise de Preços",
    "🏷️ Descontos Promocionais",
    "🔍 Produto Individual",
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

            display = sub[["Nome","Marca","Quantidade","Preco","Primeira_Leitura"]].copy()
            display.columns = ["Nome","Marca","Quantidade","Preço atual (€)","1ª Leitura"]
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
        st.plotly_chart(fig, use_container_width=True)

# ─────────────────────────────────────────────────────────────────
# TAB 2 — ANÁLISE DE PREÇOS
# ─────────────────────────────────────────────────────────────────
with tab2:
    st.markdown('<div class="section-header">📈 Análise de Preços por Produto</div>', unsafe_allow_html=True)

    # Per (PID, Retalhista) compute min / max / unique prices
    summary = (
        df_period.groupby(["PID","Retalhista","Nome","Marca","Quantidade"])["Preco"]
        .agg(
            Minimo="min",
            Maximo="max",
            Leituras="count",
            Precos_Distintos=lambda x: x.nunique(),
        )
        .reset_index()
    )
    summary["Variacao_Pct"] = ((summary["Maximo"] - summary["Minimo"]) / summary["Maximo"] * 100).round(1)
    summary["Houve_Alteracao"] = summary["Precos_Distintos"] > 1

    st.markdown(f"**{len(summary)} SKU × retalhista** no período seleccionado.")

    c1, c2 = st.columns([1, 2])
    with c1:
        show_changed = st.checkbox("🔴 Apenas com alteração de preço", value=False)
        brand_filter = st.multiselect("Filtrar por marca", sorted(summary["Marca"].unique()))
    with c2:
        search = st.text_input("🔎 Pesquisar por nome", placeholder="ex: Ben & Jerry's")

    filtered = summary.copy()
    if show_changed:
        filtered = filtered[filtered["Houve_Alteracao"]]
    if brand_filter:
        filtered = filtered[filtered["Marca"].isin(brand_filter)]
    if search:
        filtered = filtered[filtered["Nome"].str.contains(search, case=False, na=False)]

    filtered = filtered.sort_values("Variacao_Pct", ascending=False)

    # Display
    for _, row in filtered.head(100).iterrows():
        changed_html = (
            '<span class="tag tag-alert">⚠️ Alterou</span>'
            if row["Houve_Alteracao"]
            else '<span class="tag tag-new">✔ Estável</span>'
        )
        ret_html = badge(row["Retalhista"])
        with st.expander(f"{row['Nome']} — {row['Marca']}  |  {row['Retalhista']}"):
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Mínimo", f"{row['Minimo']:.2f} €")
            c2.metric("Máximo", f"{row['Maximo']:.2f} €")
            c3.metric("Variação", f"{row['Variacao_Pct']:.1f}%")
            c4.metric("Preços distintos", int(row["Precos_Distintos"]))
            c5.metric("Leituras", int(row["Leituras"]))

            # Price evolution chart for this product
            sub = df_period[(df_period["PID"] == row["PID"]) & (df_period["Retalhista"] == row["Retalhista"])]
            sub = sub.sort_values("Data")
            if len(sub) > 1:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=sub["Data"], y=sub["Preco"],
                    mode="lines+markers",
                    line=dict(color=RETAILER_COLORS.get(row["Retalhista"], "#333"), width=2),
                    marker=dict(size=6),
                    name="Preço",
                ))
                fig.update_layout(
                    height=200, margin=dict(t=10,b=10,l=10,r=10),
                    yaxis_title="€", xaxis_title="",
                    template="plotly_white",
                )
                st.plotly_chart(fig, use_container_width=True)

# ─────────────────────────────────────────────────────────────────
# TAB 3 — DESCONTOS PROMOCIONAIS
# ─────────────────────────────────────────────────────────────────
with tab3:
    st.markdown('<div class="section-header">🏷️ Descontos Promocionais</div>', unsafe_allow_html=True)
    st.markdown("Percentual de desconto = **(Máximo − Mínimo) / Máximo × 100**. Só produtos com pelo menos 2 leituras e variação de preço.")

    promo = (
        df_period.groupby(["PID","Retalhista","Nome","Marca","Quantidade"])["Preco"]
        .agg(Minimo="min", Maximo="max", Leituras="count", Distintos=lambda x: x.nunique())
        .reset_index()
    )
    promo = promo[promo["Distintos"] > 1].copy()
    promo["Desconto_Pct"] = ((promo["Maximo"] - promo["Minimo"]) / promo["Maximo"] * 100).round(1)
    promo = promo.sort_values("Desconto_Pct", ascending=False)

    if promo.empty:
        st.info("Sem variação de preço no período seleccionado.")
    else:
        col_thresh, col_ret = st.columns(2)
        with col_thresh:
            min_disc = st.slider("Desconto mínimo (%)", 0, 50, 5)
        with col_ret:
            ret_filter = st.multiselect("Retalhista", retailers_sel, default=retailers_sel)

        promo_f = promo[(promo["Desconto_Pct"] >= min_disc) & (promo["Retalhista"].isin(ret_filter))]

        st.markdown(f"**{len(promo_f)} produto(s)** com desconto ≥ {min_disc}%")

        # Bar chart top 20
        top20 = promo_f.head(20)
        if not top20.empty:
            fig = px.bar(
                top20,
                x="Desconto_Pct",
                y=top20["Nome"].str[:40],
                color="Retalhista",
                color_discrete_map=RETAILER_COLORS,
                orientation="h",
                template="plotly_white",
                labels={"Desconto_Pct": "Desconto (%)", "y": ""},
                title="Top 20 maiores descontos observados",
            )
            fig.update_layout(height=500, margin=dict(t=40,b=10), legend_title_text="")
            st.plotly_chart(fig, use_container_width=True)

        # Table
        display_promo = promo_f[["Nome","Marca","Retalhista","Minimo","Maximo","Desconto_Pct","Distintos","Leituras"]].copy()
        display_promo.columns = ["Nome","Marca","Retalhista","Mínimo €","Máximo €","Desconto %","Preços distintos","Leituras"]
        display_promo["Mínimo €"] = display_promo["Mínimo €"].map("{:.2f}".format)
        display_promo["Máximo €"] = display_promo["Máximo €"].map("{:.2f}".format)
        display_promo["Desconto %"] = display_promo["Desconto %"].map("{:.1f}".format)
        st.dataframe(display_promo, use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────────────
# TAB 4 — PRODUTO INDIVIDUAL
# ─────────────────────────────────────────────────────────────────
with tab4:
    st.markdown('<div class="section-header">🔍 Análise Individual de Produto</div>', unsafe_allow_html=True)
    st.markdown("Pesquisa um produto e compara-o nos 3 retalhistas.")

    search_prod = st.text_input("🔎 Nome do produto (ex: Häagen-Dazs, Ben & Jerry's, Cornetto…)")

    if search_prod:
        results = df[df["Nome"].str.contains(search_prod, case=False, na=False)]
        if results.empty:
            st.warning("Nenhum produto encontrado.")
        else:
            # Group by retailer
            groups = results.groupby(["Retalhista","PID","Nome","Marca","Quantidade"])

            # Show matches
            matches = results[["Retalhista","PID","Nome","Marca","Quantidade"]].drop_duplicates()
            st.markdown(f"**{len(matches)} SKU(s) encontrado(s):**")
            for _, m in matches.iterrows():
                st.markdown(f"- {badge(m['Retalhista'])} &nbsp; **{m['Nome']}** · {m['Marca']} · {m['Quantidade']}", unsafe_allow_html=True)

            st.markdown("#### Evolução de preço")
            fig = go.Figure()
            for (ret, pid, nome, marca, qtd), grp in groups:
                grp = grp.sort_values("Data")
                fig.add_trace(go.Scatter(
                    x=grp["Data"],
                    y=grp["Preco"],
                    mode="lines+markers",
                    name=f"{ret}: {nome[:35]}",
                    line=dict(color=RETAILER_COLORS.get(ret, "#333"), width=2),
                    marker=dict(size=6),
                ))
            fig.update_layout(
                height=380,
                template="plotly_white",
                yaxis_title="€",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                margin=dict(t=10,b=10),
            )
            st.plotly_chart(fig, use_container_width=True)

            # Summary table
            summ = (
                results.groupby(["Retalhista","Nome","Marca"])["Preco"]
                .agg(Min="min", Max="max", Atual="last", N="count", Distintos="nunique")
                .reset_index()
            )
            summ["Desconto %"] = ((summ["Max"] - summ["Min"]) / summ["Max"] * 100).round(1)
            summ = summ.rename(columns={"Min":"Mín €","Max":"Máx €","Atual":"Preço atual €","N":"Leituras","Distintos":"Preços únicos"})
            st.dataframe(summ, use_container_width=True, hide_index=True)
    else:
        st.info("Escreve um nome de produto para começar a pesquisa.")

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<p style='text-align:center;color:#bbb;font-size:.8rem;'>"
    "CAPD Price Intelligence · Actualizado automaticamente com o ficheiro Excel do scraper"
    "</p>",
    unsafe_allow_html=True,
)
