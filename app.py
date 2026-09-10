import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px
from io import BytesIO
from collections import Counter as _Counter, defaultdict as _defaultdict
import re as _re
import unicodedata as _unicodedata
import hashlib
from rapidfuzz import fuzz as _fuzz

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

/* ── Sidebar collapse/expand control — fixed contrast, not only on hover ──
   Confirmed by inspecting the real rendered DOM: the icon itself is a
   Material Symbols ligature inside a [data-testid="stIconMaterial"] span,
   not an <svg>, so it needs a `color` override rather than `fill`. Two
   different testids cover the expanded-sidebar button and the
   collapsed-sidebar (re-expand) button. */
[data-testid="stSidebarCollapseButton"] button,
[data-testid="stExpandSidebarButton"] {
    background: #1a1a1a !important;
    border-radius: 6px !important;
    opacity: 1 !important;
}
[data-testid="stSidebarCollapseButton"] button [data-testid="stIconMaterial"],
[data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"] {
    color: #f7f5f0 !important;
}
[data-testid="stSidebarCollapseButton"] button:hover,
[data-testid="stExpandSidebarButton"]:hover {
    background: #333 !important;
}
</style>
""", unsafe_allow_html=True)

RETAILER_COLORS = {"Continente":"#2563eb","Auchan":"#7c3aed","PingoDoce":"#db2777"}
RETAILER_ORDER  = ["Continente","PingoDoce","Auchan"]

def badge(retailer):
    color = RETAILER_COLORS.get(retailer,"#666")
    return f'<span class="retailer-badge" style="background:{color}22;color:{color}">{retailer}</span>'

# ── Weekly collapse (Dia -> Semana) ─────────────────────────────────────────────
# Scraping runs daily (Mon-Fri) via Task Scheduler, but every analysis in this
# app only ever considers one reading per week — the week's minimum price.
# Dia_para_Weeks.csv (Dia;Semana, e.g. '37´26') maps each calendar day to its
# week label; load_data() uses it to collapse daily readings down to one row
# per PID+Retalhista+Semana (the row with the lowest Preco that week).
_WEEK_LABEL_RE        = _re.compile(r"^W(\d{1,2})´(\d{2})$")
_WEEK_LABEL_NO_SEP_RE  = _re.compile(r"^W(\d{1,3})(\d{2})$")  # repairs a missing ´ separator

def _normalize_week_label(raw):
    """Normalise a week label from Dia_para_Weeks.csv. Handles the expected
    'W<semana>´<aa>' format and repairs the occasional typo where the ´
    separator is missing (e.g. 'W1025' -> 'W10´25' — the last two digits are
    always the 2-digit year)."""
    s = str(raw).strip()
    if _WEEK_LABEL_RE.match(s):
        return s
    m = _WEEK_LABEL_NO_SEP_RE.match(s)
    if m:
        return f"W{m.group(1)}´{m.group(2)}"
    return s


@st.cache_data(ttl=300)
def load_dia_para_weeks():
    """Load the Dia -> Semana mapping from Dia_para_Weeks.csv.
    Returns a dict {datetime.date: week_label_str}, e.g. {date(2026,9,10):
    "W37´26"}. Returns an empty dict (graceful no-op — load_data() then
    skips the weekly collapse) if the file can't be found or parsed.
    """
    for fname in ["Dia_para_Weeks.csv", "Dia para Weeks.csv"]:
        for enc in ["cp1252", "latin-1"]:
            try:
                df_w = pd.read_csv(fname, sep=";", encoding=enc, header=0)
            except Exception:
                continue
            if df_w.shape[1] < 2:
                continue
            df_w = df_w.iloc[:, :2]
            df_w.columns = ["Dia", "Semana"]
            df_w["Dia"] = pd.to_datetime(df_w["Dia"], format="%d/%m/%Y", errors="coerce").dt.date
            df_w = df_w.dropna(subset=["Dia"])
            df_w["Semana"] = df_w["Semana"].apply(_normalize_week_label)
            return dict(zip(df_w["Dia"], df_w["Semana"]))
    return {}


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

    # ── Weekly collapse: one row per PID+Retalhista+Semana, keeping the
    # reading with the lowest Preco that week. A date missing from the
    # mapping falls back to being its own single-day "week" rather than
    # being silently dropped, so nothing disappears if the mapping file
    # doesn't yet cover a given date.
    week_map = load_dia_para_weeks()
    if week_map:
        df_all["Semana"] = df_all["Data"].dt.date.map(week_map)
        df_all["Semana"] = df_all["Semana"].fillna("D_" + df_all["Data"].dt.strftime("%Y-%m-%d"))
        idx_min = df_all.groupby(["PID","Retalhista","Semana"])["Preco"].idxmin()
        df_all = df_all.loc[idx_min].reset_index(drop=True)
        df_all = df_all.sort_values("Data").reset_index(drop=True)
    else:
        df_all["Semana"] = None

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

@st.cache_data(ttl=60)
def load_glossario_mestre():
    """Load the master glossary from glossario_mestre.csv.
    Returns a DataFrame indexed by PID+Retalhista with:
      - Formato: product format (Pints, Sticks, etc.) — manually curated.
    (Marca_Padronizada / Grupo_ID / Nome_Padronizado are no longer used —
    replaced by the automatic Nome Agregador / Marca Agregadora engine.)
    Falls back gracefully to legacy files if glossario_mestre.csv is absent.
    """
    _empty = pd.DataFrame(columns=["PID","Retalhista","Nome","Marca","Quantidade","Formato"])
    # Priority order: new master > legacy glossario_retalhistas > legacy glossario_formato
    for fname in ["glossario_mestre.csv", "glossario_retalhistas.csv", "glossario_formato.csv"]:
        try:
            df_gl = pd.read_csv(fname, encoding="utf-8-sig")
            df_gl["PID"] = df_gl["PID"].astype(str)
            if "Formato" not in df_gl.columns:
                df_gl["Formato"] = None
            return df_gl
        except Exception:
            continue
    return _empty


# ── Fixed config (no user-facing controls: file, retailers and date range are
#    always the full dataset) ──────────────────────────────────────────────────
data_source   = "precos_CAPD.xlsx"
retailers_sel = ["Continente", "Auchan", "PingoDoce"]

try:
    df = load_data(data_source)
except Exception as e:
    st.error(f"Erro ao carregar dados: {e}"); st.stop()
if df.empty:
    st.warning("Sem dados para apresentar."); st.stop()

df = df[df["Retalhista"].isin(retailers_sel)]
min_date = df["Data"].min().date()
max_date = df["Data"].max().date()

# (Sidebar navigation now built with st.navigation/st.Page below the data
#  load — see the bottom of this file. No custom CSS needed: Streamlit
#  renders and themes this menu itself.)

# ── Load master glossary and enrich df ───────────────────────────────────────
# Single source of truth: glossario_mestre.csv
# Contains: Formato for all SKUs (manually curated — kept as-is), and
# Marca_Padronizada (manually curated — used for the Histórico de Preços tab's
# brand filter, to avoid spelling-variant duplicates like "Ben & Jerry's" /
# "BEN & JERRY'S" / "Ben & Jerrys" all showing up as separate brands).
# Grupo_ID / Nome_Padronizado are still NOT used: cross-retailer product
# matching is handled by the automatic Nome Agregador / Marca Agregadora
# engine below, which doesn't require manual glossary upkeep as new SKUs
# appear.
df_gl_full = load_glossario_mestre()
df_gl_full["PID"] = df_gl_full["PID"].astype(str)

# Enrich main df with Formato + Marca_Padronizada from glossary
df["PID"] = df["PID"].astype(str)
if "Formato" in df.columns:
    df = df.drop(columns=["Formato"])

_gl_cols = ["PID","Retalhista","Formato"]
if "Marca_Padronizada" in df_gl_full.columns:
    _gl_cols.append("Marca_Padronizada")

df = df.merge(
    df_gl_full[_gl_cols].drop_duplicates(subset=["PID","Retalhista"]),
    on=["PID","Retalhista"], how="left"
)

# Marca_Padronizada: fallback to the raw Marca for any SKU not (yet) in the
# glossary, then apply small corrections on top of the curated column
# (case-insensitively, since the curation itself has a couple of leftover
# case-variant gaps — e.g. "FERRERO ROCHER" was never folded into the
# Title-Case "Ferrero Rocher" used everywhere else):
#  - "Ferrero"/"Ferrero Rocher" (any case) folded into "Ferrero" (same
#    brand family)
#  - "Carte DOr" (missing apostrophe) folded into "Carte D'Or"
if "Marca_Padronizada" not in df.columns:
    df["Marca_Padronizada"] = df["Marca"]
else:
    df["Marca_Padronizada"] = df["Marca_Padronizada"].fillna(df["Marca"])
_MARCA_PADRONIZADA_OVERRIDES = {
    "ferrero rocher": "Ferrero",
    "carte dor": "Carte D'Or",
}
def _apply_marca_override(v):
    if not isinstance(v, str):
        return v
    return _MARCA_PADRONIZADA_OVERRIDES.get(v.strip().lower(), v)
df["Marca_Padronizada"] = df["Marca_Padronizada"].apply(_apply_marca_override)

# Treat SKUs with a purely-numeric (garbage) raw Marca as noise: force them
# unclassified (no Formato) so they're excluded wherever the app already
# skips formatless SKUs (the matching engine, Produtos Novos, etc.) — e.g.
# PID 4013230 "CUBOS GELO EM COPO 528 130G", where "528" ended up in the
# Marca field instead of being a real brand.
_numeric_marca_mask = df["Marca"].astype(str).str.fullmatch(r"\d+")
df.loc[_numeric_marca_mask, "Formato"] = None

# df_fmt_lookup: simple PID+Retalhista → Formato table (used by several tabs)
df_fmt_lookup = df[["PID","Retalhista","Formato"]].drop_duplicates()

# ═══════════════════════════════════════════════════════════════════════════
# NOME AGREGADOR / MARCA AGREGADORA — automatic cross-retailer product
# matching engine. Replaces the old manually-curated Marca_Padronizada /
# Grupo_ID / Nome_Padronizado glossary fields.
#
# How it works (see project notes for full rationale):
#   1. Own-brand (marca própria) SKUs are detected via retailer-name aliases
#      and are NEVER matched across retailers — they always stay standalone.
#   2. SKUs without a Formato are excluded from matching entirely.
#   3. Candidates are compared only within the same Formato, with brand
#      (normalised) and size (parsed to a common unit, with tolerance) as
#      hard filters — only then is a fuzzy name-similarity score computed.
#   4. Pairs scoring ≥ HIGH_THRESHOLD are auto-grouped into one cluster,
#      sharing a single Nome Agregador / Marca Agregadora.
#   5. Pairs scoring between LOW_THRESHOLD and HIGH_THRESHOLD are NOT
#      grouped (each SKU stays standalone) but are surfaced in the "Notas"
#      tab as an open question for manual review.
#   6. Nothing is persisted — this recomputes in memory on every load.
# ═══════════════════════════════════════════════════════════════════════════

_RETAILER_BRAND_ALIASES = {
    "Continente": {"continente"},
    "Auchan":     {"auchan", "auchan collection"},
    "PingoDoce":  {"pingo doce", "pingodoce"},
}
_GENERIC_BRAND_SUFFIXES = [" gelados", " ice cream", " icecream"]
_PACK_WORDS = ["emb.", "embalagem", "un.", "unidades", "unidade", "multipack",
               "minicups", "pack", "the",
               "quantidade nao disponivel", "quantidade não disponível"]

# Words Luiz reviewed and authorized (2026-09-09, CAPD_auditoria_palavras_matching.xlsx)
# as SAFE TO IGNORE when comparing two product names across retailers — i.e. one
# retailer's title including this word and another's omitting it does NOT mean
# they're different products (confirmed case-by-case, e.g. "Memories" is a
# truncated-title artifact, not a real naming difference). These are blanket-
# stripped in _core_name, same as "Gelado"/"Tarte" always were.
_SAFE_FILLER_WORDS = [
    "1", "bem", "collection", "cone", "cream", "creamy", "de", "e", "gelada",
    "geldo", "kids", "max", "memories", "pint", "roma", "sticks", "utopia",
]
_GENERIC_FILLER_WORDS = ["gelado", "gelados", "sobremesa", "sobremesas",
                          "tarte", "tarte gelada"] + _SAFE_FILLER_WORDS

# Words Luiz reviewed and marked SABOR — NUNCA IGNORAR in the same review: if
# either of two product names has one of these and the other doesn't, they are
# DIFFERENT products/variants, even when the text is otherwise near-identical
# and would score high by pure edit distance (e.g. "Chocolate Clássico" vs
# "Mini Chocolate Clássico" scores 87.8 on text alone — well above the 84
# auto-merge line — even though Luiz confirmed "Mini" marks a genuinely
# different, differently-priced multipack SKU, not the same product renamed).
# Sub-brands sold under the Olá umbrella (Luiz confirmed 2026-09-09): kept as
# INDEPENDENT brands (never collapsed into "Olá") for reporting/analysis, but
# bridged with "Olá" for cross-retailer matching — see _brands_compatible and
# _pick_canonical.
_OLA_SUBBRANDS = {"calippo", "cornetto", "solero", "viennetta", "feast"}

_NEVER_IGNORE_WORDS = {
    "almond", "caramel", "cheesecake", "chocolate", "classico", "crackable",
    "double", "frac", "mini", "nozes", "praline", "speculoos", "strawberry",
    "white",
}

_UNIT_TO_G = {"ml": 1, "l": 1000, "g": 1, "kg": 1000}
# Raw unit spellings actually seen in the scraped text that the previous
# regex silently missed (confirmed against the live data: 2 159 Continente
# readings write grams as "gr" — e.g. "emb. 300 gr (6 un)" — and 1 760
# Continente readings write liters as "lt" — e.g. "emb. 1,3 lt"; 12 PingoDoce
# readings use "Grm"). Missing these sent the parser straight to the bare
# "N un" fallback (or to no size at all), which is the root cause of
# Histórico rows that looked like duplicates of the same product at another
# retailer purely because Continente's size was invisible to the parser.
_UNIT_ALIASES = {
    "ml": "ml",
    "l": "l", "lt": "l", "litro": "l", "litros": "l",
    "g": "g", "gr": "g", "grs": "g", "grm": "g", "grama": "g", "gramas": "g",
    "kg": "kg",
}
_UNITS_PATTERN = "|".join(sorted(_UNIT_ALIASES.keys(), key=len, reverse=True))


def _canon_unit(u):
    """Map a raw unit spelling (ml/l/lt/g/gr/grm/kg/...) to its canonical
    form (ml/l/g/kg) before any lookup — never invents a unit, just
    recognizes the spelling variants actually present in the source data."""
    return _UNIT_ALIASES.get(str(u).lower(), str(u).lower())


_MULTIPACK_RE = _re.compile(rf"(\d+)\s*[xX]\s*(\d+[.,]?\d*)\s*({_UNITS_PATTERN})\b", _re.IGNORECASE)
_SINGLE_QTY_RE = _re.compile(rf"(\d+[.,]?\d*)\s*({_UNITS_PATTERN})\b", _re.IGNORECASE)
_PAREN_UN_RE = _re.compile(r"\((\d+)\s*un\)", _re.IGNORECASE)

_AGG_HIGH_THRESHOLD = 84   # name-similarity score at/above which SKUs auto-group
_AGG_LOW_THRESHOLD  = 60   # below this, not even shown as a Nota
_AGG_SIZE_TOLERANCE = 0.15  # 15%

# PT -> EN flavour synonyms, applied only inside _core_name for scoring/matching
# purposes (never for the displayed Nome Agregador). Keys are post-_norm_text
# (accent-stripped, lowercase) tokens.
FLAVOR_SYNONYMS = {
    "negro": "dark", "preto": "dark",
    "branco": "white",
    "amendoa": "almond", "amendoas": "almond",
    "caramelo": "caramel",
    "choco": "chocolate",   # common abbreviation seen in Auchan titles (e.g.
                             # "CHOCO FUDGE BROWNIE") — same word, not a flavour
    "salgado": "salted",
    "morango": "strawberry",
    "baunilha": "vanilla",
    "cereja": "cherry",
    "avela": "hazelnut",
    "pistacio": "pistachio", "pistacho": "pistachio",
    "leite": "milk",
    "manga": "mango",
    "framboesa": "raspberry",
    "mel": "honey",
    "coco": "coconut",
    "canela": "cinnamon",
    "limao": "lemon",
    "manteiga": "butter",
    "amendoim": "peanut",
}

# Leading filler/preposition stripping for canonical display names.
_LEADING_FILLER_RE = _re.compile(r"^\s*(gelados?|tarte\s+gelada|tarte)\s+", _re.IGNORECASE)
_LEADING_PREP_RE    = _re.compile(r"^\s*(de|do|da)\s+", _re.IGNORECASE)


def _strip_accents(s):
    if s is None:
        return ""
    nfkd = _unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in nfkd if not _unicodedata.combining(c))


def _norm_text(s):
    s = _strip_accents(s).lower().strip()
    # Apostrophes are dropped entirely (not turned into a space) so that a
    # possessive/contraction normalizes the same whether or not the source
    # kept the apostrophe — confirmed against real data: Continente's raw
    # Marca field writes "Ben & Jerrys" (no apostrophe) while Auchan/
    # PingoDoce write "Ben & Jerry's". Turning "'" into a space produced
    # "jerry s" (2 tokens) vs "jerrys" (1 token) — never equal — which
    # silently blocked Continente's SKUs from matching either of the other
    # two retailers in build_agregadores' brand-compatibility check, before
    # the name-similarity score was even computed.
    s = s.replace("'", "").replace("\u2019", "")
    s = _re.sub(r"[^\w\s]", " ", s)
    s = _re.sub(r"\s+", " ", s).strip()
    return s


def _normalize_brand(marca):
    m = _norm_text(marca)
    for suf in _GENERIC_BRAND_SUFFIXES:
        if m.endswith(suf.strip()):
            m = m[: -len(suf.strip())].strip()
    return m


def _is_private_label(marca, retalhista):
    m = _norm_text(marca)
    aliases = _RETAILER_BRAND_ALIASES.get(retalhista, set())
    return m in aliases


def _parse_total_qty(nome, quantidade, retalhista):
    """Return total pack quantity in a grams/ml-equivalent unit, or None."""
    nome = str(nome or "")
    quant = str(quantidade or "")
    search_space = f"{nome} {quant}"

    m = _MULTIPACK_RE.search(search_space)
    if m:
        mult = float(m.group(1))
        val = float(m.group(2).replace(",", "."))
        unit = _canon_unit(m.group(3))
        return mult * val * _UNIT_TO_G.get(unit, 1)

    if "|" in quant:
        quant = quant.split("|")[0].strip()

    single = _SINGLE_QTY_RE.search(quant)
    if single:
        val = float(single.group(1).replace(",", "."))
        unit = _canon_unit(single.group(2))
        return val * _UNIT_TO_G.get(unit, 1)

    single2 = _SINGLE_QTY_RE.search(nome)
    if single2:
        val = float(single2.group(1).replace(",", "."))
        unit = _canon_unit(single2.group(2))
        return val * _UNIT_TO_G.get(unit, 1)

    return None


# Display unit for each raw unit token: ml/l -> "ml", g/kg -> "g" (always
# whole numbers, always base units — per user decision).
_QTY_DISPLAY_UNIT = {"ml": "ml", "l": "ml", "g": "g", "kg": "g"}
_BARE_UN_RE = _re.compile(r"(\d+)\s*un\b", _re.IGNORECASE)

def _format_qty_padronizada(nome, quantidade):
    """Standardized display quantity for the Histórico de Preços table —
    reuses the same parsing cascade as _parse_total_qty (including its
    Nome-field fallback, which recovers the correct value even when the
    scraped Quantidade is truncated for some Auchan SKUs, e.g. '41.8G' ->
    '8G'), but keeps track of whether the unit is volume or weight so it can
    be displayed correctly ('465 ml' / '300 g' — never mg, never L/Kg, never
    decimals). Falls back to a bare unit count ('6 un') when no ml/g/l/kg
    size is present anywhere; returns None when nothing at all is derivable
    (never invents a size)."""
    nome = str(nome or "")
    quant = str(quantidade or "")
    search_space = f"{nome} {quant}"

    m = _MULTIPACK_RE.search(search_space)
    if m:
        mult = float(m.group(1))
        val = float(m.group(2).replace(",", "."))
        unit = _canon_unit(m.group(3))
        total = mult * val * _UNIT_TO_G.get(unit, 1)
        return f"{round(total)} {_QTY_DISPLAY_UNIT.get(unit,'ml')}"

    q = quant
    if "|" in q:
        q = q.split("|")[0].strip()

    single = _SINGLE_QTY_RE.search(q)
    if single:
        val = float(single.group(1).replace(",", "."))
        unit = _canon_unit(single.group(2))
        total = val * _UNIT_TO_G.get(unit, 1)
        return f"{round(total)} {_QTY_DISPLAY_UNIT.get(unit,'ml')}"

    single2 = _SINGLE_QTY_RE.search(nome)
    if single2:
        val = float(single2.group(1).replace(",", "."))
        unit = _canon_unit(single2.group(2))
        total = val * _UNIT_TO_G.get(unit, 1)
        return f"{round(total)} {_QTY_DISPLAY_UNIT.get(unit,'ml')}"

    un = _BARE_UN_RE.search(search_space)
    if un:
        return f"{un.group(1)} un"

    return None


# Retailer/brand marketing nicknames that don't literally describe the
# flavour, found case-by-case during matching review and confirmed with
# Luiz (2026-09-09: "vamos sempre ter que fazer inferências manuais com o
# tempo — junte o que der"). Manual by nature; grows as more cases surface.
# Applied as a phrase-level substitution before any other stripping.
_MARKETING_ALIASES = {
    "la pistache": "pistachio chocolate",   # Magnum (Auchan naming)
    "euphoria": "pink lemonade",            # Magnum Mini (Auchan naming)
    "churrifically churros y": "churros",   # Ben & Jerry's official flavour name
    "tropical": "mango vanilla",            # Cornetto Max (Auchan naming) — broadest
                                             # of these aliases; scoped only to this
                                             # exact word, revisit if it ever collides
                                             # with an unrelated "tropical" flavour.
}


def _core_name(nome, marca):
    """Strip brand/quantity/packaging tokens from Nome, leaving the
    descriptive 'core' of the product name for fuzzy matching."""
    n = _norm_text(nome)
    for phrase, repl in sorted(_MARKETING_ALIASES.items(), key=lambda x: -len(x[0])):
        n = _re.sub(rf"\b{_re.escape(phrase)}\b", repl, n)
    for w in _PACK_WORDS:
        # Whole-word replace, not substring — a naive .replace() here turned
        # "un" (from "un." after normalization) into a substring match that
        # corrupted any word CONTAINING "un", e.g. "baunilha" -> "ba ilha".
        # Confirmed against real data: this silently hurt the match score
        # for every vanilla-flavoured product in the catalog.
        n = _re.sub(rf"\b{_re.escape(_norm_text(w))}\b", " ", n)
    n = _MULTIPACK_RE.sub(" ", n)
    n = _SINGLE_QTY_RE.sub(" ", n)
    n = _PAREN_UN_RE.sub(" ", n)
    # "N un" without parentheses (e.g. "8UN", "4 UN") — the paren-only regex
    # above missed these; confirmed against real data (rows with residual
    # "8un"/"4un" tokens surviving into the matched text).
    n = _re.sub(r"\b\d+\s*un\b", " ", n)
    brand_token_list = _normalize_brand(marca).split()
    brand_tokens = set(brand_token_list)
    if _normalize_brand(marca) in ({"ola"} | _OLA_SUBBRANDS):
        # Olá-family bridging (see _brands_compatible): a retailer may record
        # this SKU's Marca as generic "Olá" while the sub-brand name (e.g.
        # "Calippo") still appears in the Nome text, or vice-versa. Strip the
        # whole family's tokens either way so both sides of a bridged pair
        # end up with the SAME residual text regardless of which specific
        # label that retailer happened to use in the Marca field.
        brand_tokens |= {"ola"} | _OLA_SUBBRANDS
    for tok in brand_tokens:
        n = _re.sub(rf"\b{_re.escape(tok)}\b", " ", n)
    if len(brand_token_list) >= 2:
        # Retailers sometimes abbreviate a multi-word brand to its initials
        # (confirmed: Auchan writes "B&J" for "Ben & Jerry's" — after
        # normalisation "&" becomes a space, leaving "b j" as two adjacent
        # single-letter tokens). Strip that derived-initials sequence too;
        # requires the letters to appear ADJACENT as separate tokens, so
        # this shouldn't false-trigger on unrelated short words.
        initials = " ".join(w[0] for w in brand_token_list if w)
        n = _re.sub(rf"\b{_re.escape(initials)}\b", " ", n)
    for w in _GENERIC_FILLER_WORDS:
        n = _re.sub(rf"\b{_re.escape(w)}\b", " ", n)
    # translate PT flavour terms to EN so cross-language variants score as
    # matches (scoring/matching only — never affects the displayed name)
    n = " ".join(FLAVOR_SYNONYMS.get(tok, tok) for tok in n.split())
    # PT plural/singular packaging-word variant seen in the data
    # ("Bombons" vs "Bombom") — same word, not a flavour difference.
    n = _re.sub(r"\bbombons\b", "bombom", n)
    # Any standalone number left over at this point (e.g. "Pack 4", or a
    # digit stranded by the "un"/pack stripping above) is packaging count,
    # never a flavour identifier in this catalog — safe to drop.
    n = _re.sub(r"\b\d{1,3}\b", " ", n)
    n = _re.sub(r"\s+", " ", n).strip()
    return n


def _brands_compatible(marca_a, marca_b):
    ba, bb = _normalize_brand(marca_a), _normalize_brand(marca_b)
    if not ba or not bb:
        return False
    if ba == bb or ba in bb or bb in ba:
        return True
    # Sub-brands sold under the Olá umbrella (Luiz confirmed 2026-09-09):
    # a retailer may label the SAME product "Olá" or with the sub-brand name
    # directly (e.g. Calippo shows as "Olá" at one retailer, "Calippo" at
    # another). Bridge sub-brand <-> generic "Olá" only — NOT sub-brand <->
    # sub-brand (Calippo and Cornetto are different product families and
    # must never cross-match each other).
    if ba == "ola" and bb in _OLA_SUBBRANDS:
        return True
    if bb == "ola" and ba in _OLA_SUBBRANDS:
        return True
    return False


def _sizes_compatible(qa, qb):
    if not qa or not qb:
        return True
    return abs(qa - qb) / max(qa, qb) <= _AGG_SIZE_TOLERANCE


def _name_score(nome_a, marca_a, nome_b, marca_b):
    ca = _core_name(nome_a, marca_a)
    cb = _core_name(nome_b, marca_b)
    base = _fuzz.token_sort_ratio(ca, cb)
    ta, tb = set(ca.split()), set(cb.split())
    diff_words = ta ^ tb  # words present on only one side, post-stripping
    if diff_words & _NEVER_IGNORE_WORDS:
        # At least one authorized "never merge" word (Luiz's review) is part
        # of what separates these two names. Text similarity alone is not
        # trustworthy here — e.g. "Chocolate Clássico" vs "Mini Chocolate
        # Clássico" scores 87.8 by edit distance alone (already above the 84
        # auto-merge line) even though "Mini" marks a genuinely different,
        # differently-priced multipack SKU. Cap below even the gray-zone
        # floor: these are confirmed-different, not merely ambiguous, so
        # they shouldn't clutter Notas as if they needed manual review.
        return min(base, _AGG_LOW_THRESHOLD - 1)
    return base


def _pick_canonical(names_or_brands):
    """Pick the 'nicest' display string from a list of variants: prefer
    natural casing (not ALL CAPS) and, among those, the shortest (closer to
    the bare product/brand name without redundant pack info).
    Brand-specific override (Luiz, 2026-09-09): when a cluster mixes the
    generic "Olá" label with one of its sub-brands (Calippo, Cornetto,
    Solero, Viennetta, Feast — bridged for matching in _brands_compatible),
    the sub-brand name wins even though "Olá" is shorter — the sub-brand is
    the more specific, more useful label for analysis."""
    vals = [v for v in names_or_brands if v and str(v).strip()]
    if not vals:
        return None
    sub_brand_vals = [v for v in vals if _normalize_brand(v) in _OLA_SUBBRANDS]
    if sub_brand_vals and any(_normalize_brand(v) == "ola" for v in vals):
        vals = sub_brand_vals
    non_caps = [v for v in vals if not str(v).isupper()]
    pool = non_caps if non_caps else vals
    return min(pool, key=len)


def _pick_canonical_name(names, marca_agg):
    """Pick the canonical display Nome Agregador, always prefixed with the
    aggregated brand (e.g. 'Magnum Chocolate Clássico' instead of 'Gelado de
    Chocolate Clássico'):
      1. pick the 'nicest' variant the same way _pick_canonical does;
      2. strip a leading 'Gelado(s) '/'Tarte Gelada '/'Tarte ' filler;
      3. strip one remaining leading 'de '/'do '/'da ' preposition;
      4. strip brand tokens already present in the middle of the text, so
         the brand isn't duplicated once prefixed;
      5. prefix with marca_agg.
    """
    vals = [v for v in names if v and str(v).strip()]
    if not vals:
        return None
    non_caps = [v for v in vals if not str(v).isupper()]
    pool = non_caps if non_caps else vals
    base = str(min(pool, key=len)).strip()

    core = _LEADING_FILLER_RE.sub("", base).strip()
    core = _LEADING_PREP_RE.sub("", core).strip()
    core_after_filler = core  # non-brand-stripped fallback

    if marca_agg:
        for tok in str(marca_agg).split():
            core = _re.sub(rf"\b{_re.escape(tok)}\b", "", core, flags=_re.IGNORECASE)
        core = _re.sub(r"\s+", " ", core).strip(" -")

    if not core:
        # If brand-token removal is what emptied it (e.g. the product name IS
        # the brand name, like "Gelado Nutella"), the brand alone is the
        # correct canonical name — don't reintroduce it and duplicate.
        # Only fall back to the raw base if filler-stripping alone already
        # left nothing (e.g. name was just "Gelado").
        core = base if not core_after_filler else ""

    return f"{marca_agg} {core}".strip() if marca_agg else core


@st.cache_data(ttl=300)
def build_agregadores(df_sku):
    """Compute Nome Agregador / Marca Agregadora for every PID+Retalhista,
    plus a list of gray-zone (ambiguous) pairs for the Notas tab.
    df_sku must have one row per PID+Retalhista with Nome, Marca, Quantidade,
    Retalhista, Formato.
    """
    recs = df_sku.to_dict("records")
    for r in recs:
        r["_key"] = f"{r['PID']}_{r['Retalhista']}"
        r["_qty"] = _parse_total_qty(r["Nome"], r["Quantidade"], r["Retalhista"])
        r["_priv"] = _is_private_label(r["Marca"], r["Retalhista"])

    parent = {r["_key"]: r["_key"] for r in recs}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    gray_notes = []

    eligible = [r for r in recs if not r["_priv"] and pd.notna(r.get("Formato"))]
    by_fmt = _defaultdict(list)
    for r in eligible:
        by_fmt[r["Formato"]].append(r)

    for fmt, group in by_fmt.items():
        n = len(group)
        for i in range(n):
            a = group[i]
            for j in range(i + 1, n):
                b = group[j]
                if a["Retalhista"] == b["Retalhista"]:
                    continue
                if not _brands_compatible(a["Marca"], b["Marca"]):
                    continue
                if not _sizes_compatible(a["_qty"], b["_qty"]):
                    continue
                score = _name_score(a["Nome"], a["Marca"], b["Nome"], b["Marca"])
                if score >= _AGG_HIGH_THRESHOLD:
                    union(a["_key"], b["_key"])
                elif score >= _AGG_LOW_THRESHOLD:
                    gray_notes.append({
                        "PID_A": a["PID"], "Retalhista_A": a["Retalhista"], "Nome_A": a["Nome"],
                        "PID_B": b["PID"], "Retalhista_B": b["Retalhista"], "Nome_B": b["Nome"],
                        "Score": round(score, 1),
                    })

    clusters = _defaultdict(list)
    for r in recs:
        clusters[find(r["_key"])].append(r)

    out_rows = []
    for root, members in clusters.items():
        if len(members) > 1:
            marca_agg = _pick_canonical([m["Marca"] for m in members])
            nome_agg = _pick_canonical_name([m["Nome"] for m in members], marca_agg)
        else:
            nome_agg = members[0]["Nome"]
            marca_agg = _normalize_brand(members[0]["Marca"]).title() if members[0]["Marca"] else members[0]["Marca"]
            marca_agg = members[0]["Marca"]  # standalone: keep own brand as-is
        for m in members:
            out_rows.append({
                "PID": m["PID"], "Retalhista": m["Retalhista"],
                "Nome_Agregador": nome_agg, "Marca_Agregadora": marca_agg,
            })

    df_agg = pd.DataFrame(out_rows)
    df_notas = pd.DataFrame(gray_notes).sort_values("Score", ascending=False) if gray_notes else pd.DataFrame(
        columns=["PID_A","Retalhista_A","Nome_A","PID_B","Retalhista_B","Nome_B","Score"])
    return df_agg, df_notas


_df_sku_for_agg = df.sort_values("Data").drop_duplicates(subset=["PID","Retalhista"], keep="last")[
    ["PID","Retalhista","Nome","Marca","Quantidade","Formato"]].copy()
df_agregadores, df_notas_grouping = build_agregadores(_df_sku_for_agg)

df = df.merge(df_agregadores, on=["PID","Retalhista"], how="left")
df["Nome_Agregador"] = df["Nome_Agregador"].fillna(df["Nome"])
df["Marca_Agregadora"] = df["Marca_Agregadora"].fillna(df["Marca"])

# Quantidade_Padronizada: standardized pack size ("465 ml" / "300 g" / a bare
# "6 un" when no size at all is derivable — never invented). Computed once
# per unique (Nome, Quantidade) pair for speed, then mapped back onto df.
_qty_pairs = df[["Nome","Quantidade"]].drop_duplicates()
_qty_pairs["Quantidade_Padronizada"] = _qty_pairs.apply(
    lambda r: _format_qty_padronizada(r["Nome"], r["Quantidade"]), axis=1)
df = df.merge(_qty_pairs, on=["Nome","Quantidade"], how="left")


def _harmonize_ml_over_g(df_all):
    """De-duplication pass (per Luiz's decision): within the SAME aggregated
    product as the Histórico de Preços tab groups it — Nome_Agregador +
    Marca_Padronizada (the curated brand column that tab actually filters/
    groups by, not Marca_Agregadora) — if one retailer's size is written in
    grams and another retailer's size is written in ml but the NUMBER is
    identical (e.g. Danonino '300 g' at Continente vs '300 ml' at Auchan/
    PingoDoce — same pack, just weighed vs measured), relabel the gram
    reading to ml so both collapse into a single Histórico row. ml is the
    preferred/primary unit for this merge.
    Does NOT touch a SKU that's in only one unit everywhere (all-g or
    all-ml stays exactly as-is), and does NOT touch sizes that don't have a
    matching number in the other unit (e.g. '456 g' with no '456 ml'
    anywhere) — no value is invented or converted, only re-labelled when an
    exact numeric match already exists in ml for that same product."""
    q = df_all["Quantidade_Padronizada"]
    is_gml = q.notna() & q.str.match(r"^\d+ (ml|g)$")
    if not is_gml.any():
        return df_all

    sub = df_all.loc[is_gml, ["Nome_Agregador", "Marca_Padronizada", "Quantidade_Padronizada"]].copy()
    sub["_val"] = sub["Quantidade_Padronizada"].str.extract(r"^(\d+)")[0].astype(int)
    sub["_unit"] = sub["Quantidade_Padronizada"].str[-2:].str.strip()

    units_per_key = (sub.drop_duplicates(["Nome_Agregador", "Marca_Padronizada", "_val", "_unit"])
                         .groupby(["Nome_Agregador", "Marca_Padronizada", "_val"])["_unit"].agg(set))
    swap_keys = set(units_per_key[units_per_key.apply(lambda s: {"ml", "g"} <= s)].index)
    if not swap_keys:
        return df_all

    def _swap(row):
        if row["_unit"] != "g":
            return row["Quantidade_Padronizada"]
        key = (row["Nome_Agregador"], row["Marca_Padronizada"], row["_val"])
        return f'{row["_val"]} ml' if key in swap_keys else row["Quantidade_Padronizada"]

    sub["_new"] = sub.apply(_swap, axis=1)
    df_all.loc[is_gml, "Quantidade_Padronizada"] = sub["_new"].values
    return df_all


df = _harmonize_ml_over_g(df)

# ── Header ─────────────────────────────────────────────────────────────────────
_last_update_str = pd.Timestamp(max_date).strftime("%d/%m/%Y")
st.markdown(f"""
<div style='background:#1a1a1a;color:#d4d4d4;font-size:.78rem;text-align:center;
            padding:.42rem 1rem;border-radius:6px;margin:3rem 0 .6rem;letter-spacing:.04em;'>
  🕒 <strong>Última atualização em:</strong> {_last_update_str}
</div>""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════
# TAB 1 — NOVOS PRODUTOS
# ═══════════════════════════════════════════════════════════════════
def page_novos():
    st.markdown('<div class="section-header">🆕 Produtos Novos</div>', unsafe_allow_html=True)

    # ── Days selector (moved above the retailer boxes) ────────────────────────
    new_prod_days = st.slider("Nos últimos X dias",
                               min_value=3, max_value=90, value=7, step=1,
                               key="new_prod_days_slider")
    st.markdown(f"Produtos cuja **primeira leitura** ocorreu nos últimos **{new_prod_days} dias** (a contar de {max_date}).")

    # ── Exclude SKUs present on the very first date (launch SKUs) ─────────────
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
    new_products = new_products[new_products["Retalhista"].isin(retailers_sel)]

    # ── Only keep SKUs with a classified Formato — unclassified means the
    # classification logic deliberately excluded them, so they shouldn't
    # show up here at all ─────────────────────────────────────────────────
    new_products["PID"] = new_products["PID"].astype(str)
    new_products = new_products.merge(df_fmt_lookup, on=["PID","Retalhista"], how="left")
    new_products = new_products[new_products["Formato"].notna()]

    # ── 3 retailer boxes: new products per retailer in this period ────────────
    counts_by_ret = new_products["Retalhista"].value_counts()
    boxes_html = ""
    for ret in RETAILER_ORDER:
        cnt = int(counts_by_ret.get(ret, 0))
        color = RETAILER_COLORS.get(ret, "#1a1a1a")
        logo = LOGOS.get(ret)
        logo_html = (f'<img src="{logo}" style="height:20px;vertical-align:middle;margin-right:6px;">'
                     if logo else "")
        boxes_html += (f'<div class="kpi-item" style="border-color:{color}">'
                       f'<h4>{logo_html}{ret}</h4><p>{cnt}</p></div>')
    st.markdown(f'<div class="kpi-bar">{boxes_html}</div>', unsafe_allow_html=True)

    if new_products.empty:
        st.info(f"Nenhum produto novo nos últimos {new_prod_days} dias.")
    else:
        # Get latest price + price history min/max (FIX 3)
        price_stats = (df.groupby(["PID","Retalhista"])["Preco"]
                       .agg(Preco_Atual="last", Preco_Min="min", Preco_Max="max")
                       .reset_index())
        meta_cols = df.sort_values("Data").groupby(["PID","Retalhista"]).last()[["Nome","Marca","Quantidade"]].reset_index()
        price_stats = price_stats.merge(meta_cols, on=["PID","Retalhista"])

        price_stats["PID"]  = price_stats["PID"].astype(str)
        new_products = new_products.merge(price_stats, on=["PID","Retalhista"])
        new_products = new_products.sort_values(["Primeira_Leitura","Retalhista"], ascending=[False,True])

        for ret in RETAILER_ORDER:
            sub = new_products[new_products["Retalhista"]==ret].copy()
            if sub.empty: continue

            # FIX 6: larger green badge
            count_badge = (f'<span style="font-size:1.05rem;font-weight:700;color:#84cc16;'
                           f'background:#1a2e05;padding:2px 12px;border-radius:20px;">' +
                           f'{len(sub)} novos</span>')
            # FIX 2: retailer header with logo
            st.markdown(retailer_header(ret, count_badge), unsafe_allow_html=True)

            d = sub[["PID","Nome","Marca","Quantidade","Formato","Preco_Atual","Preco_Min","Preco_Max","Primeira_Leitura"]].copy()
            d.columns = ["ID","Nome","Marca","Quantidade","Formato","Preço Atual €","Mín €","Máx €","1ª Leitura"]
            d["Preço Atual €"] = d["Preço Atual €"].map("{:.2f}".format)
            d["Mín €"]         = d["Mín €"].map("{:.2f}".format)
            d["Máx €"]         = d["Máx €"].map("{:.2f}".format)
            d["1ª Leitura"]    = d["1ª Leitura"].dt.strftime("%d/%m/%Y")
            st.dataframe(d, use_container_width=True, hide_index=True)

# ═══════════════════════════════════════════════════════════════════
# TAB 2 — HISTÓRICO DE PREÇOS
# ═══════════════════════════════════════════════════════════════════
def page_historico():
    st.markdown('<div class="section-header">📈 Histórico de Preços</div>', unsafe_allow_html=True)
    st.markdown(
        '<style>'
        '.hist-filter-label{font-size:.72rem;color:#666;font-weight:600;margin:.6rem 0 .2rem;'
        'text-transform:uppercase;letter-spacing:.04em;}'
        # Cap Marca/Formato multiselects to a fixed height — extra chips
        # scroll inside the box instead of pushing the page down.
        'div[data-testid="stMultiSelect"] div[data-baseweb="select"] > div{'
        'max-height:2.5rem;overflow-y:auto;}'
        '</style>',
        unsafe_allow_html=True
    )

    # ── Período: De / Até + atalhos ──────────────────────────────────────────
    if "hist_start" not in st.session_state:
        st.session_state["hist_start"] = min_date
    if "hist_end" not in st.session_state:
        st.session_state["hist_end"] = max_date

    def _set_period(start, end):
        # Must run BEFORE the date_input widgets below are instantiated —
        # Streamlit forbids writing to session_state[key] once the widget
        # with that key exists for this run. The three columns are created
        # upfront as placeholders, then filled out of visual order so the
        # buttons (which may mutate state) always execute first.
        st.session_state["hist_start"] = start
        st.session_state["hist_end"] = end

    ytd_start = max(min_date, max_date.replace(month=1, day=1))
    l3m_start = max(min_date, max_date - timedelta(days=90))
    _cur_start, _cur_end = st.session_state["hist_start"], st.session_state["hist_end"]
    _active_css = ""
    for _key, _match in (("hist_ytd", _cur_start == ytd_start and _cur_end == max_date),
                          ("hist_l3m", _cur_start == l3m_start and _cur_end == max_date),
                          ("hist_total", _cur_start == min_date and _cur_end == max_date)):
        if _match:
            _active_css += (f'.st-key-{_key} button{{background:#1a1a1a!important;'
                             f'color:#f7f5f0!important;border-color:#1a1a1a!important;}}')
    if _active_css:
        st.markdown(f"<style>{_active_css}</style>", unsafe_allow_html=True)

    pc1, pc2, pc3, pc4, pc5 = st.columns([1.3, 1.3, 0.7, 0.7, 0.8])
    with pc3:
        st.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
        if st.button("YTD", key="hist_ytd", use_container_width=True, help="Do início do ano até hoje"):
            _set_period(ytd_start, max_date)
    with pc4:
        st.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
        if st.button("L3M", key="hist_l3m", use_container_width=True, help="Últimos 90 dias"):
            _set_period(l3m_start, max_date)
    with pc5:
        st.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
        if st.button("Total", key="hist_total", use_container_width=True, help="Todo o período disponível"):
            _set_period(min_date, max_date)
    with pc1:
        st.date_input("De", min_value=min_date, max_value=max_date, key="hist_start")
    with pc2:
        st.date_input("Até", min_value=min_date, max_value=max_date, key="hist_end")

    h_start, h_end = st.session_state["hist_start"], st.session_state["hist_end"]
    if h_start > h_end:
        h_start, h_end = h_end, h_start

    # ── Retalhista: botões fixos (pills), nunca cresce ───────────────────────
    st.markdown('<div class="hist-filter-label">Retalhista</div>', unsafe_allow_html=True)
    ret_h = st.pills("Retalhista", retailers_sel, selection_mode="multi",
                      default=retailers_sel, key="hist_ret", label_visibility="collapsed")

    # Base pool: selected period + retailers, classified SKUs only (SKUs
    # without a Formato — e.g. data-quality noise like a stray numeric code
    # in the Marca field — are excluded here just like elsewhere in the app).
    _hp = df[(df["Data"].dt.date >= h_start) & (df["Data"].dt.date <= h_end)
             & df["Retalhista"].isin(ret_h or retailers_sel)
             & df["Formato"].notna()].copy()

    # ── Marca: seletor direto (sem etapa extra de popover), altura fixa ─────
    st.markdown('<div class="hist-filter-label">Marca</div>', unsafe_allow_html=True)
    _marca_opts_h = sorted(_hp["Marca_Padronizada"].dropna().unique())
    marca_prev = [m for m in st.session_state.get("hist_marca", []) if m in _marca_opts_h]
    marca_h = st.multiselect("Marca", _marca_opts_h, default=marca_prev,
                              key="hist_marca", label_visibility="collapsed")
    if marca_h:
        st.caption(f"{len(marca_h)} marca(s) selecionada(s)")

    _hp1 = _hp[_hp["Marca_Padronizada"].isin(marca_h)] if marca_h else _hp

    # ── Formato: idem Marca ──────────────────────────────────────────────────
    st.markdown('<div class="hist-filter-label">Formato</div>', unsafe_allow_html=True)
    _fmt_opts_h = sorted(_hp1["Formato"].dropna().unique())
    fmt_prev = [f for f in st.session_state.get("hist_fmt", []) if f in _fmt_opts_h]
    fmt_h = st.multiselect("Formato", _fmt_opts_h, default=fmt_prev,
                            key="hist_fmt", label_visibility="collapsed")
    if fmt_h:
        st.caption(f"{len(fmt_h)} formato(s) selecionado(s)")

    search_h = st.text_input("🔎 Nome", placeholder="ex: Ben & Jerry's", key="hist_search")

    # ── Apply all filters ────────────────────────────────────────────────────
    hf = _hp1[_hp1["Formato"].isin(fmt_h)] if fmt_h else _hp1
    if search_h:
        hf = hf[hf["Nome_Agregador"].str.contains(search_h, case=False, na=False)]

    if hf.empty:
        st.info("Sem SKUs com os filtros selecionados.")
        return

    # ── Group into one row per (produto, marca, tamanho) — no duplicates ────
    # A bare numeric key won't exist for ungrouped Quantidade (None), so use
    # a stable placeholder for grouping purposes only.
    hf = hf.copy()
    hf["_qtd_key"] = hf["Quantidade_Padronizada"].fillna("—")

    groups = []
    for (nome_agg, marca_pad, qtd_key), g in hf.groupby(["Nome_Agregador", "Marca_Padronizada", "_qtd_key"]):
        formato = g["Formato"].dropna().iloc[0] if g["Formato"].notna().any() else "—"
        preco_min = g["Preco"].min()
        preco_max = g["Preco"].max()
        detail = []
        for ret, sub in g.groupby("Retalhista"):
            nome_orig = sub.sort_values("Data")["Nome"].iloc[-1]
            detail.append({
                "retalhista": ret, "nome_orig": nome_orig,
                "min": sub["Preco"].min(), "max": sub["Preco"].max(),
            })
        detail.sort(key=lambda d: RETAILER_ORDER.index(d["retalhista"]) if d["retalhista"] in RETAILER_ORDER else 99)
        groups.append({
            "key": (nome_agg, marca_pad, qtd_key),
            "Formato": formato, "Marca": marca_pad, "Nome": nome_agg,
            "Quantidade": qtd_key, "min": preco_min, "max": preco_max,
            "detail": detail,
        })
    groups.sort(key=lambda r: (r["Marca"], r["Nome"], r["Quantidade"]))

    # Read the SKU table's previous selection (from before this run) so the
    # chart — placed above the table — reflects the current pick immediately.
    _prev_sel = st.session_state.get("hist_table")
    _prev_rows = list(_prev_sel["selection"]["rows"]) if _prev_sel else []
    selected_groups = [groups[i] for i in _prev_rows if i < len(groups)]

    # ── Chart: one line per (produto+tamanho selecionado, retalhista) ───────
    st.markdown("#### Gráfico de evolução")
    if not selected_groups:
        st.info("← Marca uma ou mais linhas na tabela abaixo para ver a evolução de preço.")
    else:
        line_specs = []  # (nome_agg, qtd_key, retalhista)
        for row in selected_groups:
            for d in row["detail"]:
                line_specs.append((row["Nome"], row["Quantidade"], d["retalhista"]))
        line_specs = list(dict.fromkeys(line_specs))  # de-dupe, keep order
        n_lines_h = len(line_specs)

        MAX_LINES_H = 60
        if n_lines_h > MAX_LINES_H:
            st.warning(f"Muitas linhas ({n_lines_h}) para uma leitura clara. "
                        f"Reduz a seleção de produtos (sugestão: máx {MAX_LINES_H} linhas).")
        else:
            # All-solid lines, differentiated purely by a large, high-contrast
            # basic-color palette (Dark24 + Light24 ≈ 48 distinct hues) — one
            # color per line, no reliance on dash style to tell lines apart.
            _BASIC_PALETTE = px.colors.qualitative.Dark24 + px.colors.qualitative.Light24
            color_by_line = {spec: _BASIC_PALETTE[i % len(_BASIC_PALETTE)]
                              for i, spec in enumerate(line_specs)}

            fig_h = go.Figure()
            for nome_agg, qtd_key, ret in line_specs:
                grp = hf[(hf["Nome_Agregador"] == nome_agg) & (hf["_qtd_key"] == qtd_key) & (hf["Retalhista"] == ret)]
                grp = grp.sort_values("Data")
                if grp.empty:
                    continue
                label = f"{nome_agg} ({qtd_key}) — {ret}"
                fig_h.add_trace(go.Scatter(
                    x=grp["Data"], y=grp["Preco"], mode="lines+markers",
                    name=label,
                    line=dict(color=color_by_line[(nome_agg, qtd_key, ret)], width=2.4,
                              shape="spline", smoothing=0.3),
                    marker=dict(size=4, opacity=.85, line=dict(width=.5, color="white")),
                    hovertemplate=(
                        f"<b>{nome_agg}</b> ({qtd_key})<br>"
                        f"<span style='color:#888'>{ret}</span><br>"
                        "%{x|%d %b %Y}<br>"
                        "<b>%{y:.2f} €</b>"
                        "<extra></extra>"
                    ),
                ))
            fig_h.update_layout(
                height=560,
                template="plotly_white",
                plot_bgcolor="#fdfcfa",
                paper_bgcolor="rgba(0,0,0,0)",
                title=dict(
                    text=f"Evolução de Preços — {n_lines_h} linha(s)",
                    font=dict(family="'DM Serif Display', serif", size=18, color="#1a1a1a"),
                    x=0, xanchor="left",
                ),
                yaxis_title="Preço (€)", xaxis_title="",
                hovermode="x unified",
                hoverlabel=dict(bgcolor="white", font_size=12, bordercolor="#ddd"),
                legend=dict(
                    orientation="v", yanchor="top", y=1, xanchor="left", x=1.02,
                    font=dict(size=10.5), bgcolor="rgba(255,255,255,.92)",
                    bordercolor="#e5e5e5", borderwidth=1,
                ),
                margin=dict(t=55, b=40, l=50, r=170),
                xaxis=dict(showgrid=False, showspikes=True, spikemode="across",
                           spikedash="dot", spikecolor="#999", spikethickness=1),
                yaxis=dict(showgrid=True, gridcolor="#ececec", zeroline=False),
            )
            fig_h.update_xaxes(rangeslider=dict(visible=True, thickness=.06,
                                                 bgcolor="#f1efe9", bordercolor="#ddd"),
                                type="date")
            st.plotly_chart(fig_h, use_container_width=True, key="chart_hist_multi")

    st.markdown("---")

    # ── SKU list — native selectable table, same widget/style as the         ─
    # "Produtos Novos" tab (st.dataframe), so the two tabs look consistent.
    st.markdown(f"**{len(groups)} produto(s)** com os filtros atuais &nbsp;·&nbsp; "
                f"<span style='color:#888;font-size:.8rem'>marca as linhas para comparar no gráfico acima</span>",
                unsafe_allow_html=True)

    table_rows = []
    for row in groups:
        retalhistas = ", ".join(d["retalhista"] for d in row["detail"])
        table_rows.append({
            "Formato": row["Formato"], "Marca": row["Marca"], "Nome": row["Nome"],
            "Quantidade": row["Quantidade"], "Retalhistas": retalhistas,
            "Mín €": row["min"], "Máx €": row["max"],
        })
    d_table = pd.DataFrame(table_rows)
    d_table["Mín €"] = d_table["Mín €"].map("{:.2f}".format)
    d_table["Máx €"] = d_table["Máx €"].map("{:.2f}".format)

    st.dataframe(d_table, use_container_width=True, hide_index=True,
                 on_select="rerun", selection_mode="multi-row", key="hist_table")

# ═══════════════════════════════════════════════════════════════════
# TAB 3 — ANÁLISE DE CLUSTERS (Beta)
# ═══════════════════════════════════════════════════════════════════
def page_clusters():
    st.markdown('<div class="section-header">🔬 Análise de Clusters <span style="font-size:.75rem;color:#888;font-family:DM Sans,sans-serif">(Beta)</span></div>', unsafe_allow_html=True)
    st.markdown("Agrupa SKUs por padrão de preço (Baseline + Low dentro de ±0.05 €). Hierarquia: **Retalhista → Marca → Formato → Cluster**.")

    # ── Cascading filters ─────────────────────────────────────────────────────
    # Build SKU summary first (needed for cascade)
    @st.cache_data(ttl=300)
    def build_sku_summary_cached(df_input):
        """Build SKU price summary (Baseline, Low) with Marca_Agregadora and Formato.
        df_input must already have Marca_Agregadora and Formato columns (from startup merge)."""
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
            # Marca_Agregadora and Formato already in df_input from startup merge
            row0 = grp.iloc[0]
            marca = row0.get("Marca_Agregadora") if pd.notna(row0.get("Marca_Agregadora")) else row0["Marca"]
            fmt   = row0.get("Formato") if pd.notna(row0.get("Formato")) else None
            qtd   = row0.get("Quantidade") if pd.notna(row0.get("Quantidade")) else ""
            records.append({"PID": str(pid), "Retalhista": ret,
                            "Nome": row0["Nome"], "Marca": str(marca),
                            "Formato": fmt, "Quantidade": str(qtd),
                            "Baseline": bl, "Low": low if low else bl})
        return pd.DataFrame(records)

    df_sku_sum_cl = build_sku_summary_cached(df)

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
# TAB 4 — PREÇO AGORA
# ═══════════════════════════════════════════════════════════════════
def page_agora():
    st.markdown('<div class="section-header">🔍 Preço Agora</div>', unsafe_allow_html=True)
    st.markdown("Preço **da semana mais recente** (mínimo registado) de cada SKU por retalhista. Passe o cursor sobre um preço para ver Mín/Máx dos últimos 30 dias.")

    # ── Build "now" dataset ───────────────────────────────────────────────────
    # df already has Nome_Agregador, Marca_Agregadora and Formato from the startup merge
    _src_cols = ["PID","Retalhista","Nome","Marca","Nome_Agregador","Marca_Agregadora","Quantidade","Formato","Preco","Data","Semana"]
    _src_cols = [c for c in _src_cols if c in df.columns]

    _now_latest = (df[_src_cols].sort_values("Data")
                   .groupby(["PID","Retalhista"], as_index=False).last())
    _now_latest.rename(columns={"Preco":"Preco_Atual","Data":"Data_Leitura"}, inplace=True)
    _now_latest["PID"] = _now_latest["PID"].astype(str)

    # Ensure Marca_Agregadora column exists with fallback
    if "Marca_Agregadora" not in _now_latest.columns:
        _now_latest["Marca_Agregadora"] = _now_latest["Marca"]
    else:
        _now_latest["Marca_Agregadora"] = _now_latest["Marca_Agregadora"].fillna(_now_latest["Marca"])

    if "Formato" not in _now_latest.columns:
        _now_latest["Formato"] = None

    _now_marca_col = "Marca_Agregadora"

    _cutoff_30 = pd.Timestamp(max_date) - timedelta(days=30)
    _df_30 = df[df["Data"] >= _cutoff_30].copy()
    _df_30["PID"] = _df_30["PID"].astype(str)
    _stats_30 = (_df_30.groupby(["PID","Retalhista"])["Preco"]
                 .agg(Min_30d="min", Max_30d="max").reset_index())

    _now_full = _now_latest.merge(_stats_30, on=["PID","Retalhista"], how="left")

    # ── Layout: filters left, table right ────────────────────────────────────
    left_f, right_tbl = st.columns([1, 3])

    with left_f:
        st.markdown("#### Filtros")

        # ── Cascading pool (we derive all options from _now_full, cascading down) ──
        # Note: no Retalhista filter here on purpose — this table always shows
        # every retailer side by side as comparison columns, so filtering by
        # retailer would just hide columns rather than narrow the product list.
        # Step 1: Marca (aggregated — Marca_Agregadora)
        _np1 = _now_full.copy()
        _now_marca_opts = sorted(_np1[_now_marca_col].dropna().unique())
        now_marca = st.multiselect("Marca", _now_marca_opts, key="now_marca")

        # Step 2: Formato — filtered by Marca
        _np2 = _np1[_np1[_now_marca_col].isin(now_marca)] if now_marca else _np1.copy()
        _now_fmt_opts = sorted(_np2["Formato"].dropna().unique()) if "Formato" in _np2.columns else []
        now_fmt = st.multiselect("Formato", _now_fmt_opts, key="now_fmt")

        # Step 3: Tamanho — filtered by above
        _np3 = _np2[_np2["Formato"].isin(now_fmt)] if now_fmt else _np2.copy()
        _now_size_opts = sorted(_np3["Quantidade"].dropna().astype(str).unique())
        now_size = st.multiselect("Tamanho", _now_size_opts, key="now_size")

        # Step 4: SKU (aggregated — Nome_Agregador) — filtered by above, shows
        # consolidated names (always populated — falls back to the SKU's own
        # Nome when it isn't part of a cross-retailer group)
        _np4 = _np3[_np3["Quantidade"].astype(str).isin(now_size)] if now_size else _np3.copy()
        _now_sku_display = sorted(set(_np4["Nome_Agregador"].dropna()))
        now_sku = st.multiselect("SKU", _now_sku_display, key="now_sku")

        # Free-text search → click-to-add
        st.markdown("---")
        st.markdown("**Pesquisa rápida por nome**")
        now_search = st.text_input("", placeholder="ex: Magnum, Cornetto…",
                                    key="now_search", label_visibility="collapsed")
        if now_search:
            _sm = sorted([n for n in _now_sku_display if now_search.lower() in n.lower()])[:25]
            if _sm:
                st.caption(f"{len(_sm)} resultado(s) — clica para adicionar à selecção:")
                _to_add = st.multiselect("", _sm, key="now_search_add", label_visibility="collapsed")
                if _to_add:
                    _combined = list(dict.fromkeys((now_sku or []) + _to_add))
                    st.session_state["now_sku"] = _combined
                    now_sku = _combined
            else:
                st.caption("Sem resultados.")

    # ── Apply all filters ─────────────────────────────────────────────────────
    _nf = _now_full.copy()
    if now_marca:  _nf = _nf[_nf[_now_marca_col].isin(now_marca)]
    if now_fmt and "Formato" in _nf.columns:
                   _nf = _nf[_nf["Formato"].isin(now_fmt)]
    if now_size:   _nf = _nf[_nf["Quantidade"].astype(str).isin(now_size)]
    # now_sku contains Nome_Agregador display names
    if now_sku:
        _nf = _nf[_nf["Nome_Agregador"].isin(now_sku)]
    elif now_search:
        _nf = _nf[_nf["Nome"].str.contains(now_search, case=False, na=False)]

    # ── Build consolidation key ────────────────────────────────────────────────
    # Nome_Agregador + Marca_Agregadora together identify a cross-retailer
    # product cluster from the automatic matching engine (build_agregadores).
    # A SKU not part of any cluster keeps its own Nome/Marca as the "group",
    # so it naturally shows on its own row.
    _nf["_group_key"] = "G_" + _nf["Nome_Agregador"].astype(str) + "_" + _nf["Marca_Agregadora"].astype(str)

    def _best_display_name(grp):
        return grp["Nome_Agregador"].iloc[0]

    with right_tbl:
        n_groups = _nf["_group_key"].nunique()
        n_skus_now = len(_nf)
        st.markdown(f"**{n_groups} produto(s)** encontrado(s) &nbsp;·&nbsp; "
                    f"<span style='color:#888;font-size:.82rem'>{n_skus_now} SKUs de {_nf['Retalhista'].nunique()} retalhistas consolidados</span>",
                    unsafe_allow_html=True)

        if _nf.empty:
            st.info("Sem SKUs com os filtros seleccionados.")
        else:
            RC = RETAILER_COLORS

            # ── One row per group ─────────────────────────────────────────────
            _pivot_rows = []
            for gkey, grp in _nf.groupby("_group_key", sort=False):
                display_name = _best_display_name(grp)
                mp_v  = str(grp[_now_marca_col].iloc[0]) if pd.notna(grp[_now_marca_col].iloc[0]) else "—"
                fmt_v = str(grp["Formato"].iloc[0]) if ("Formato" in grp.columns and pd.notna(grp["Formato"].iloc[0])) else "—"
                row_d = {"Nome": display_name, "Marca": mp_v, "Formato": fmt_v}
                for ret_v in RETAILER_ORDER:
                    sub_r = grp[grp["Retalhista"] == ret_v]
                    if sub_r.empty:
                        row_d[ret_v] = None
                    else:
                        # If multiple SKUs from same retailer in same group, show lowest price
                        r = sub_r.sort_values("Preco_Atual").iloc[0]
                        row_d[ret_v] = {
                            "atual": r["Preco_Atual"],
                            "min":   r["Min_30d"] if pd.notna(r.get("Min_30d")) else None,
                            "max":   r["Max_30d"] if pd.notna(r.get("Max_30d")) else None,
                            "data":  r["Data_Leitura"].strftime("%d/%m/%Y") if pd.notna(r.get("Data_Leitura")) else "—",
                            "semana": str(r["Semana"]) if pd.notna(r.get("Semana")) else "—",
                            "nome_orig": str(r["Nome"]),
                        }
                _pivot_rows.append(row_d)

            # Sort: by Marca then Nome
            _pivot_rows.sort(key=lambda r: (r["Marca"], r["Nome"]))

            # ── Build HTML table ──────────────────────────────────────────────
            ret_headers = "".join(
                f'<th style="background:{RC[r]}18;color:{RC[r]};min-width:90px;text-align:center;padding:6px 10px;">{r}</th>'
                for r in RETAILER_ORDER
            )
            html_rows = ""
            for rd in _pivot_rows:
                cells = ""
                for ret_v in RETAILER_ORDER:
                    v = rd[ret_v]
                    color = RC.get(ret_v, "#333")
                    if v is None:
                        cells += '<td style="text-align:center;color:#ccc;padding:5px 10px;">—</td>'
                    else:
                        preco_str = f"{v['atual']:.2f} €"
                        mn = f"{v['min']:.2f} €" if v["min"] is not None else "—"
                        mx = f"{v['max']:.2f} €" if v["max"] is not None else "—"
                        tooltip = f"{v['nome_orig']}&#10;Semana: {v['semana']} ({v['data']})&#10;Mín 30d: {mn}&#10;Máx 30d: {mx}"
                        cells += (
                            f'<td style="text-align:center;padding:5px 10px;" title="{tooltip}">'
                            f'<span style="background:{color}15;color:{color};font-weight:700;'
                            f'padding:3px 10px;border-radius:5px;cursor:help;font-size:.88rem;">'
                            f'{preco_str}</span></td>'
                        )
                safe_nome = rd["Nome"].replace('"', '&quot;').replace('<','&lt;')
                html_rows += (
                    f'<tr style="border-bottom:1px solid #f1f5f9;">'
                    f'<td style="padding:5px 10px;font-size:.82rem;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="{safe_nome}">{safe_nome}</td>'
                    f'<td style="padding:5px 10px;font-size:.78rem;color:#666;">{rd["Marca"]}</td>'
                    f'<td style="padding:5px 10px;font-size:.78rem;color:#888;">{rd["Formato"]}</td>'
                    f'{cells}'
                    f'</tr>'
                )

            table_html = f"""
<div style="overflow-x:auto;border-radius:8px;border:1px solid #e5e7eb;">
<table style="width:100%;border-collapse:collapse;font-family:'DM Sans',sans-serif;font-size:.83rem;">
<thead>
<tr style="background:#f8fafc;border-bottom:2px solid #e5e7eb;">
  <th style="text-align:left;padding:7px 10px;min-width:220px;">Nome</th>
  <th style="text-align:left;padding:7px 10px;">Marca</th>
  <th style="text-align:left;padding:7px 10px;">Formato</th>
  {ret_headers}
</tr>
</thead>
<tbody>
{html_rows}
</tbody>
</table>
</div>
<p style="font-size:.72rem;color:#aaa;margin-top:.4rem;">
  💡 Passe o cursor sobre um preço para ver o nome original, a semana e Mín/Máx dos últimos 30 dias.
  Produtos comuns a vários retalhistas estão consolidados numa só linha.
</p>
"""
            st.markdown(table_html, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════
# TAB 5 — NOTAS
# ═══════════════════════════════════════════════════════════════════
def page_notas():
    st.markdown('<div class="section-header">📝 Notas</div>', unsafe_allow_html=True)
    st.markdown(
        "Questões em aberto que o motor de agrupamento automático (Nome Agregador / "
        "Marca Agregadora) encontrou mas não teve confiança suficiente para resolver sozinho. "
        "Nestes casos, cada SKU envolvido continua a aparecer separadamente na app até haver revisão."
    )

    if df_notas_grouping.empty:
        st.success("Sem questões em aberto no momento.")
        return

    st.markdown(f"**{len(df_notas_grouping)} caso(s)** — ordenados por probabilidade de serem o mesmo produto.")

    for _, r in df_notas_grouping.iterrows():
        with st.container():
            st.markdown(f"""
<div style="background:#fdf9ee;border-left:3px solid #d4a017;border-radius:6px;
            padding:.7rem 1rem;margin-bottom:.6rem;">
  <div style="font-size:.72rem;color:#92400e;font-weight:700;text-transform:uppercase;letter-spacing:.05em;margin-bottom:.35rem;">
    Possível produto duplicado &nbsp;·&nbsp; confiança {r['Score']:.0f}%
  </div>
  <div style="font-size:.9rem;margin-bottom:.15rem;">
    <strong>SKU {r['PID_A']}</strong> ({r['Retalhista_A']}) — {r['Nome_A']}
  </div>
  <div style="font-size:.9rem;margin-bottom:.4rem;">
    <strong>SKU {r['PID_B']}</strong> ({r['Retalhista_B']}) — {r['Nome_B']}
  </div>
  <div style="font-size:.8rem;color:#666;">
    💡 Sugestão: comparar os dois produtos manualmente. Se forem o mesmo, nenhuma acção é
    necessária na app — o agrupamento é automático; se forem produtos diferentes, também
    não é preciso fazer nada. Esta nota existe apenas porque a semelhança de nome/marca/tamanho
    não foi suficientemente alta para o sistema decidir sozinho.
  </div>
</div>
""", unsafe_allow_html=True)

# ── Sidebar navigation (native Streamlit — no custom CSS needed) ───────────────
pg = st.navigation([
    st.Page(page_novos,       title="Produtos Novos",              icon="🆕", url_path="novos",       default=True),
    st.Page(page_historico,   title="Histórico de Preços",         icon="📈", url_path="historico"),
    st.Page(page_clusters,    title="Análise de Clusters (Beta)",  icon="🔬", url_path="clusters"),
    st.Page(page_agora,       title="Preço Agora",                 icon="🔍", url_path="agora"),
    st.Page(page_notas,       title="Notas",                       icon="📝", url_path="notas"),
])
pg.run()

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("<p style='text-align:center;color:#bbb;font-size:.78rem;'>Monitoramento de Preços IceCream Portugal · Actualizado automaticamente com o ficheiro Excel do scraper</p>", unsafe_allow_html=True)
