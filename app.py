"""
IA Market Analyzer — v5 con OpenStreetMap (sin billing)
Freemium SaaS: gratis (3 análisis/día) + PRO €29/mes (ilimitado + IA)
"""
import streamlit as st
import requests
import os
import time
import json
import hashlib
import sqlite3
import datetime
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
#  CONFIGURACIÓN DE PÁGINA
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="IA Market Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
  .main-title { font-size: 2.4rem; font-weight: 800; color: #1a1a2e; }
  .subtitle   { font-size: 1.05rem; color: #555; margin-bottom: 1.5rem; }
  .free-badge { background:#e8f5e9; color:#2e7d32; padding:2px 10px;
                border-radius:20px; font-size:.75rem; font-weight:bold; }
  .pro-badge  { background:#fff3e0; color:#e65100; padding:2px 10px;
                border-radius:20px; font-size:.75rem; font-weight:bold; }
  .auth-box   { background:#f8f9ff; border-radius:16px; padding:2rem;
                max-width:420px; margin:2rem auto; box-shadow:0 2px 16px #0001; }
  .hero-card  { background:linear-gradient(135deg,#1a1a2e,#16213e);
                color:white; border-radius:20px; padding:2.5rem; margin-bottom:2rem; }
  div[data-testid="metric-container"] { background:#f8f9ff; border-radius:10px; padding:10px; }
  .limit-bar  { background:#ffe0e0; border-left:4px solid #e53935;
                padding:.6rem 1rem; border-radius:6px; font-size:.9rem; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
#  BASE DE DATOS SQLite
# ─────────────────────────────────────────────
DB_PATH = "users.db"

def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            email    TEXT UNIQUE NOT NULL,
            name     TEXT NOT NULL,
            password TEXT NOT NULL,
            plan     TEXT DEFAULT 'free',
            created  TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usage (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date    TEXT NOT NULL,
            count   INTEGER DEFAULT 0,
            UNIQUE(user_id, date)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS analyses (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            nicho      TEXT,
            ubicacion  TEXT,
            result_json TEXT,
            created    TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.commit()
    con.close()

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def register_user(email: str, name: str, password: str) -> tuple[bool, str]:
    try:
        con = sqlite3.connect(DB_PATH)
        con.execute(
            "INSERT INTO users (email, name, password) VALUES (?,?,?)",
            (email.lower().strip(), name.strip(), hash_password(password))
        )
        con.commit()
        con.close()
        return True, "ok"
    except sqlite3.IntegrityError:
        return False, "Este email ya está registrado."
    except Exception as e:
        return False, str(e)

def login_user(email: str, password: str):
    con = sqlite3.connect(DB_PATH)
    row = con.execute(
        "SELECT id, name, plan FROM users WHERE email=? AND password=?",
        (email.lower().strip(), hash_password(password))
    ).fetchone()
    con.close()
    return row  # (id, name, plan) o None

def get_daily_usage(user_id: int) -> int:
    today = datetime.date.today().isoformat()
    con = sqlite3.connect(DB_PATH)
    row = con.execute(
        "SELECT count FROM usage WHERE user_id=? AND date=?", (user_id, today)
    ).fetchone()
    con.close()
    return row[0] if row else 0

def increment_usage(user_id: int):
    today = datetime.date.today().isoformat()
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        INSERT INTO usage (user_id, date, count) VALUES (?,?,1)
        ON CONFLICT(user_id, date) DO UPDATE SET count = count + 1
    """, (user_id, today))
    con.commit()
    con.close()

def save_analysis(user_id: int, nicho: str, ubicacion: str, result: dict):
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT INTO analyses (user_id, nicho, ubicacion, result_json) VALUES (?,?,?,?)",
        (user_id, nicho, ubicacion, json.dumps(result, ensure_ascii=False))
    )
    con.commit()
    con.close()

def get_user_history(user_id: int, limit=5) -> list:
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT nicho, ubicacion, result_json, created FROM analyses "
        "WHERE user_id=? ORDER BY created DESC LIMIT ?",
        (user_id, limit)
    ).fetchall()
    con.close()
    return rows

def upgrade_user(user_id: int):
    con = sqlite3.connect(DB_PATH)
    con.execute("UPDATE users SET plan='pro' WHERE id=?", (user_id,))
    con.commit()
    con.close()

init_db()

FREE_LIMIT = 3  # análisis gratis por día


# ─────────────────────────────────────────────
#  DATOS DEMO REALISTAS
# ─────────────────────────────────────────────
DEMO_BUSINESSES = [
    {"name": "Burger Gourmet Madrid", "rating": 4.6, "user_ratings_total": 892,
     "formatted_address": "Calle Gran Vía 45, Madrid", "place_id": "demo_1"},
    {"name": "La Hamburguesería del Centro", "rating": 4.2, "user_ratings_total": 523,
     "formatted_address": "Calle Alcalá 78, Madrid", "place_id": "demo_2"},
    {"name": "Smash Burgers Co.", "rating": 4.8, "user_ratings_total": 1203,
     "formatted_address": "Calle Fuencarral 12, Madrid", "place_id": "demo_3"},
    {"name": "Burguer Palace", "rating": 3.9, "user_ratings_total": 310,
     "formatted_address": "Av. de América 33, Madrid", "place_id": "demo_4"},
    {"name": "The American Burger", "rating": 4.4, "user_ratings_total": 748,
     "formatted_address": "Calle Serrano 90, Madrid", "place_id": "demo_5"},
]
DEMO_TRENDS = {
    "ene": 45, "feb": 48, "mar": 52, "abr": 58, "may": 62,
    "jun": 71, "jul": 68, "ago": 65, "sep": 70, "oct": 74,
    "nov": 78, "dic": 85
}
DEMO_KEYWORDS = [
    ("hamburguesa gourmet", 87), ("smash burger Madrid", 72),
    ("mejor hamburguesa", 65), ("hamburguesa casera", 54),
    ("burger vegetariana", 48), ("hamburguesa delivery", 61),
]


# ─────────────────────────────────────────────
#  MÓDULOS DE ANÁLISIS
# ─────────────────────────────────────────────


def _nominatim_queries(nicho: str, ubicacion: str) -> list[str]:
    """Genera 1-2 términos de búsqueda para Nominatim según el nicho."""
    n = nicho.lower()
    if any(w in n for w in ["restaurante", "comida", "comer", "gastro", "cocina"]):
        return [f"restaurante {ubicacion}", f"restaurant {ubicacion}"]
    elif any(w in n for w in ["café", "cafetería", "cafeteria", "coffee"]):
        return [f"café {ubicacion}", f"cafetería {ubicacion}"]
    elif any(w in n for w in ["bar", "tapas", "pub", "cervecería", "taberna"]):
        return [f"bar {ubicacion}", f"pub {ubicacion}"]
    elif any(w in n for w in ["hamburgues", "burger", "smash"]):
        return [f"hamburguesería {ubicacion}", f"fast food {ubicacion}"]
    elif any(w in n for w in ["pizza", "pizz"]):
        return [f"pizzería {ubicacion}"]
    elif any(w in n for w in ["gimnasio", "gym", "fitness", "crossfit"]):
        return [f"gimnasio {ubicacion}", f"gym {ubicacion}"]
    elif any(w in n for w in ["hotel", "hostal", "alojamiento"]):
        return [f"hotel {ubicacion}"]
    elif any(w in n for w in ["farmacia"]):
        return [f"farmacia {ubicacion}"]
    elif any(w in n for w in ["peluquería", "peluqueria", "barbería", "barberia"]):
        return [f"peluquería {ubicacion}", f"barbería {ubicacion}"]
    elif any(w in n for w in ["panadería", "panaderia", "pastelería"]):
        return [f"panadería {ubicacion}", f"pastelería {ubicacion}"]
    elif any(w in n for w in ["supermercado", "alimentación"]):
        return [f"supermercado {ubicacion}"]
    else:
        return [f"{nicho} {ubicacion}"]


def buscar_negocios(nicho: str, ubicacion: str) -> list:
    """Busca negocios via Nominatim (OpenStreetMap geocoder) — funciona desde cualquier IP."""
    queries = _nominatim_queries(nicho, ubicacion)
    negocios = []
    seen: set[str] = set()

    for q in queries:
        try:
            resp = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": q,
                    "format": "json",
                    "limit": 25,
                    "addressdetails": 1,
                    "extratags": 1,
                },
                headers={"User-Agent": "IA-Market-Analyzer/1.0 (icdvillar8@gmail.com)"},
                timeout=12
            )
            resp.raise_for_status()
            results = resp.json()

            for r in results:
                # El nombre del POI es la primera parte del display_name
                raw_name = r.get("display_name", "")
                name = raw_name.split(",")[0].strip()
                if not name or name in seen or len(name) < 3:
                    continue
                # Descartar si el nombre es simplemente la ciudad
                if name.lower() in [ubicacion.lower(), "spain", "españa"]:
                    continue
                seen.add(name)

                addr_d = r.get("address", {})
                street = addr_d.get("road", "")
                housenumber = addr_d.get("house_number", "")
                postcode = addr_d.get("postcode", "")
                city_r = addr_d.get("city", addr_d.get("town", addr_d.get("village", ubicacion)))

                if street:
                    addr = f"{street} {housenumber}".strip()
                    addr += f", {postcode + ' ' if postcode else ''}{city_r}"
                else:
                    addr = city_r

                negocios.append({
                    "name": name,
                    "vicinity": addr,
                    "formatted_address": addr,
                    "rating": None,
                    "user_ratings_total": 0,
                    "types": [nicho.lower()],
                    "place_id": f"nom_{r.get('osm_id', '')}",
                    "website": (r.get("extratags") or {}).get("website", ""),
                })

        except Exception:
            continue

        if len(negocios) >= 15:
            break

    if not negocios:
        st.warning(f"No se encontraron negocios de '{nicho}' en '{ubicacion}'. "
                   "Prueba con un término más genérico (ej: 'restaurante', 'bar').")
    return negocios[:20]


def obtener_tendencias(nicho, ubicacion):
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl='es', tz=360, timeout=(10, 25))
        geo_map = {"madrid": "ES-MD", "barcelona": "ES-CT", "sevilla": "ES-AN",
                   "valladolid": "ES-CL", "bilbao": "ES-PV", "zaragoza": "ES-AR",
                   "españa": "ES", "mexico": "MX", "colombia": "CO",
                   "argentina": "AR", "chile": "CL"}
        geo = next((v for k, v in geo_map.items() if k in ubicacion.lower()), "ES")
        pytrends.build_payload([nicho], cat=0, timeframe='today 12-m', geo=geo, gprop='')
        df = pytrends.interest_over_time()
        if df.empty:
            return None, None
        rel = pytrends.related_queries()
        keywords = []
        if nicho in rel and rel[nicho].get("top") is not None:
            top_df = rel[nicho]["top"]
            keywords = list(zip(top_df["query"].tolist(), top_df["value"].tolist()))[:8]
        return df[nicho], keywords
    except Exception:
        return None, []


def analizar_con_ia(client, nicho, ubicacion, negocios_list):
    """Analiza el mercado usando la lista de negocios encontrados."""
    nombres = [n["name"] for n in negocios_list[:15]]
    nombres_str = "\n".join(f"- {n}" for n in nombres) if nombres else "(sin datos)"

    prompt = f"""Analiza el mercado de '{nicho}' en {ubicacion}.

Competidores encontrados ({len(nombres)}):
{nombres_str}

Proporciona en español un análisis estratégico con:
1. PUNTOS DE DOLOR principales del sector (3 bullets)
2. OPORTUNIDADES DE MERCADO para un nuevo entrante (3 bullets)
3. RECOMENDACIÓN ESTRATÉGICA para diferenciarse (2-3 frases)

Sé específico para {ubicacion} y el sector {nicho}. Sé directo y accionable."""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"Error IA: {e}"


def calcular_scores(negocios):
    scores = []
    max_reviews = max((n.get("user_ratings_total", 0) or 0 for n in negocios), default=1) or 1
    for i, n in enumerate(negocios[:8]):
        r = n.get("rating") or 3.5     # Default razonable si OSM no tiene rating
        rev = n.get("user_ratings_total", 0) or 0
        scores.append({
            "name": n["name"][:25],
            "Calidad":      round(r * 20),
            "Popularidad":  round((rev / max_reviews) * 100) if max_reviews > 0 else 50,
            "Visibilidad":  min(100, 40 + i * 8),
            "Madurez":      min(100, 30 + rev // 20),
            "Servicio":     round((r - 1) / 4 * 100),
            "Amenaza":      round(((r * 20) + (rev / max_reviews * 100 if max_reviews > 0 else 50)) / 2),
        })
    return scores


def detectar_brechas(scores, trend_data):
    avg_scores = {k: sum(s[k] for s in scores) / len(scores)
                  for k in ["Calidad", "Servicio", "Popularidad"]}
    brechas = []
    if avg_scores["Servicio"] < 60:
        brechas.append("🟢 **Servicio al cliente**: La media del mercado es baja. Diferenciarte con atención excepcional es una ventaja clara.")
    if avg_scores["Calidad"] < 70:
        brechas.append("🟢 **Calidad del producto**: Hay margen para posicionarse como referente premium.")
    if avg_scores["Popularidad"] < 50:
        brechas.append("🟢 **Presencia online**: El mercado tiene poca visibilidad digital. Invertir en SEO local y reseñas puede generar ventaja competitiva rápida.")
    if trend_data and len(trend_data) > 6:
        vals = list(trend_data.values()) if isinstance(trend_data, dict) else list(trend_data)
        if vals[-1] > vals[0] * 1.1:
            brechas.append("📈 **Demanda creciente**: El interés de búsqueda sube. El mercado tiene viento a favor — buen momento para entrar.")
    if not brechas:
        brechas.append("⚡ Mercado competitivo y equilibrado. La clave es una propuesta de valor única y nicho específico.")
    return brechas


def generar_reporte_html(nicho, ubicacion, negocios, ai_text, trend_vals, brechas, keywords):
    rows = "".join(f"<tr><td>{n['name']}</td><td>⭐ {n.get('rating') or 'N/A'}</td>"
                   f"<td>{n.get('user_ratings_total', 0):,}</td>"
                   f"<td>{n.get('formatted_address', '')}</td></tr>"
                   for n in negocios[:10])
    brechas_html = "".join(f"<li>{b}</li>" for b in brechas)
    kw_html = "".join(f"<li>{k[0]} — {k[1]} pts</li>" for k in keywords[:6]) if keywords else "<li>N/D</li>"
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<title>Análisis: {nicho} en {ubicacion}</title>
<style>body{{font-family:Arial,sans-serif;max-width:900px;margin:auto;padding:2rem;color:#222}}
h1{{color:#1a1a2e}}h2{{color:#16213e;border-bottom:2px solid #eee;padding-bottom:.5rem}}
table{{width:100%;border-collapse:collapse;margin:1rem 0}}
th{{background:#1a1a2e;color:white;padding:.6rem}}td{{padding:.5rem;border-bottom:1px solid #eee}}
.brecha{{background:#e8f5e9;padding:1rem;border-radius:8px;margin:.5rem 0}}
.ia-box{{background:#f3e5f5;padding:1.2rem;border-radius:8px;white-space:pre-wrap}}</style>
</head><body>
<h1>📊 IA Market Analyzer</h1>
<p><strong>Nicho:</strong> {nicho} &nbsp;|&nbsp; <strong>Ubicación:</strong> {ubicacion}
&nbsp;|&nbsp; <strong>Fecha:</strong> {datetime.date.today()}</p>
<h2>🏢 Competidores (OpenStreetMap)</h2>
<table><tr><th>Nombre</th><th>Rating</th><th>Reseñas</th><th>Dirección</th></tr>{rows}</table>
<h2>🔍 Brechas de Mercado</h2><ul>{"".join(f'<li class=brecha>{b}</li>' for b in brechas)}</ul>
<h2>🔑 Keywords Relacionadas</h2><ul>{kw_html}</ul>
<h2>🤖 Análisis IA</h2><div class="ia-box">{ai_text or 'No disponible (plan PRO)'}</div>
</body></html>"""


# ─────────────────────────────────────────────
#  PÁGINAS DE AUTH (con st.form para fiabilidad)
# ─────────────────────────────────────────────

def pagina_login():
    st.markdown('<div class="auth-box">', unsafe_allow_html=True)
    st.markdown("## 🔐 Iniciar sesión")
    with st.form("login_form"):
        email = st.text_input("Email", placeholder="tu@email.com", key="li_email")
        password = st.text_input("Contraseña", type="password", key="li_pw")
        submitted = st.form_submit_button("Entrar", use_container_width=True, type="primary")
    if submitted:
        if not email or not password:
            st.error("Completa todos los campos.")
        else:
            row = login_user(email, password)
            if row:
                st.session_state.user_id = row[0]
                st.session_state.user_name = row[1]
                st.session_state.user_plan = row[2]
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("Email o contraseña incorrectos.")
    if st.button("Registrarme", use_container_width=True):
        st.session_state.auth_mode = "register"
        st.rerun()
    st.markdown("---")
    st.caption("¿Quieres probar sin registrarte?")
    if st.button("🎯 Entrar en modo Demo", use_container_width=True):
        st.session_state.user_id = 0
        st.session_state.user_name = "Demo"
        st.session_state.user_plan = "demo"
        st.session_state.logged_in = True
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


def pagina_registro():
    st.markdown('<div class="auth-box">', unsafe_allow_html=True)
    st.markdown("## 📝 Crear cuenta gratis")
    with st.form("register_form"):
        name = st.text_input("Nombre", placeholder="Tu nombre", key="reg_name")
        email = st.text_input("Email", placeholder="tu@email.com", key="reg_email")
        pw1 = st.text_input("Contraseña", type="password", key="reg_pw1")
        pw2 = st.text_input("Confirmar contraseña", type="password", key="reg_pw2")
        submitted = st.form_submit_button("Crear cuenta", use_container_width=True, type="primary")
    if submitted:
        if not all([name, email, pw1, pw2]):
            st.error("Completa todos los campos.")
        elif pw1 != pw2:
            st.error("Las contraseñas no coinciden.")
        elif len(pw1) < 6:
            st.error("La contraseña debe tener al menos 6 caracteres.")
        else:
            ok, msg = register_user(email, name, pw1)
            if ok:
                st.success("✅ Cuenta creada. Ya puedes iniciar sesión.")
                st.session_state.auth_mode = "login"
                st.rerun()
            else:
                st.error(msg)
    if st.button("← Volver al login"):
        st.session_state.auth_mode = "login"
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────
#  SIDEBAR
# ─────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        user = st.session_state.get("user_name", "")
        plan = st.session_state.get("user_plan", "free")
        badge = "🆓 Free" if plan == "free" else ("✨ PRO" if plan == "pro" else "🎯 Demo")
        st.markdown(f"### Hola, {user} {badge}")
        if plan == "free":
            used = get_daily_usage(st.session_state.user_id)
            remaining = max(0, FREE_LIMIT - used)
            st.progress(used / FREE_LIMIT if used < FREE_LIMIT else 1.0)
            st.caption(f"{remaining} análisis restantes hoy")
            if remaining == 0:
                st.warning("Límite diario alcanzado.")
        if plan != "pro" and plan != "demo":
            if st.button("⚡ Actualizar a PRO — €29/mes", use_container_width=True, type="primary"):
                st.session_state.show_upgrade = True
                st.rerun()
        st.markdown("---")
        st.markdown("**Fuentes de datos**")
        st.success("✅ OpenStreetMap (negocios)")
        o_key = os.getenv("OPENAI_API_KEY", "")
        st.success("✅ OpenAI API" if o_key else "❌ OpenAI API (no configurada)")
        try:
            from pytrends.request import TrendReq
            st.success("✅ Google Trends")
        except Exception:
            st.warning("⚠️ Google Trends (pytrends no disponible)")
        st.markdown("---")
        st.markdown("**Módulos**")
        mods = {
            "google_trends": st.toggle("📈 Google Trends", True),
            "analisis_ia":   st.toggle("🤖 Análisis IA", True),
            "competidores":  st.toggle("🏢 Competidores", True),
            "scoring":       st.toggle("📊 Matriz de Scores", True),
            "brechas":       st.toggle("🔍 Brechas de Mercado", True),
            "keywords":      st.toggle("🔑 Keywords", True),
        }
        st.markdown("---")
        if st.button("🚪 Cerrar sesión", use_container_width=True):
            for k in ["logged_in", "user_id", "user_name", "user_plan"]:
                st.session_state.pop(k, None)
            st.rerun()
    return mods


# ─────────────────────────────────────────────
#  PANTALLA DE UPGRADE
# ─────────────────────────────────────────────

def pantalla_upgrade():
    st.markdown("## ⚡ Pasa a PRO")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        ### Plan Gratuito
        - ✅ 3 análisis / día
        - ✅ Tabla de competidores
        - ✅ Gráfico básico
        - ❌ Análisis IA de reseñas
        - ❌ Keyword Engine
        - ❌ Historial ilimitado
        - ❌ Export PDF/HTML
        **€0/mes**
        """)
    with col2:
        st.markdown("""
        ### Plan PRO ✨
        - ✅ Análisis ilimitados
        - ✅ Tabla de competidores
        - ✅ Todos los gráficos
        - ✅ **Análisis IA de reseñas**
        - ✅ **Keyword Suggestion Engine**
        - ✅ **Historial completo**
        - ✅ **Export HTML report**
        - ✅ **Scoring Matrix radar**
        **€29/mes**
        """)
    st.markdown("---")
    st.info("💳 Sistema de pagos próximamente disponible vía Stripe. Por ahora activa tu PRO aquí:")
    col_a, col_b = st.columns(2)
    with col_a:
        code = st.text_input("Código de activación PRO", placeholder="PROACTIVATE2024")
        if st.button("Activar PRO", type="primary"):
            if code.strip().upper() in ["PROACTIVATE2024", "IAMARKET2024", "PRO2024"]:
                upgrade_user(st.session_state.user_id)
                st.session_state.user_plan = "pro"
                st.success("✅ ¡PRO activado! Recarga la página.")
                st.balloons()
            else:
                st.error("Código inválido.")
    with col_b:
        if st.button("← Volver"):
            st.session_state.show_upgrade = False
            st.rerun()


# ─────────────────────────────────────────────
#  TAB: BIENVENIDA
# ─────────────────────────────────────────────

def tab_bienvenida():
    plan = st.session_state.get("user_plan", "free")
    st.markdown("""
    <div class="hero-card">
      <h1 style="color:white;font-size:2.2rem;margin-bottom:.5rem">📊 IA Market Analyzer</h1>
      <p style="color:#aaa;font-size:1.1rem">Analiza cualquier nicho de mercado en segundos.<br>
      Datos reales de OpenStreetMap · Tendencias · Inteligencia Artificial.</p>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("🏢 Competidores", "Datos reales", "OpenStreetMap")
    c2.metric("📈 Tendencias", "12 meses", "Google Trends")
    c3.metric("🤖 IA", "GPT-4o-mini", "Análisis de mercado")

    st.markdown("---")
    st.markdown("### ¿Cómo funciona?")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("""**1️⃣ Define tu nicho**
Escribe el sector que quieres analizar y la ciudad objetivo.""")
    with col2:
        st.markdown("""**2️⃣ Lanzamos el análisis**
Cruzamos OpenStreetMap, Trends e IA en segundos.""")
    with col3:
        st.markdown("""**3️⃣ Obtén tu estrategia**
Detectamos brechas, keywords y oportunidades concretas.""")

    if plan == "free":
        st.info(f"🆓 Plan Free: {FREE_LIMIT} análisis gratis al día. Actualiza a PRO para acceso ilimitado + IA.")
    elif plan == "pro":
        st.success("✨ Plan PRO activo — Acceso ilimitado a todos los módulos.")


# ─────────────────────────────────────────────
#  TAB: HISTORIAL
# ─────────────────────────────────────────────

def tab_historial():
    uid = st.session_state.get("user_id", 0)
    plan = st.session_state.get("user_plan", "free")
    st.markdown("## 📋 Mi Historial")
    if uid == 0 or plan == "demo":
        st.info("El historial no está disponible en modo Demo. Regístrate gratis para guardarlo.")
        return
    rows = get_user_history(uid, limit=5 if plan == "free" else 20)
    if not rows:
        st.info("Todavía no tienes análisis guardados. Ve a la pestaña **Analizar** para empezar.")
        return
    for nicho, ubicacion, rjson, created in rows:
        with st.expander(f"📊 {nicho} en {ubicacion} — {created[:10]}"):
            try:
                data = json.loads(rjson)
                n = len(data.get("negocios", []))
                st.write(f"**Competidores encontrados:** {n}")
                if data.get("ai_text"):
                    st.markdown("**Análisis IA:**")
                    st.caption(data["ai_text"][:400] + "…")
            except Exception:
                st.write("Datos del análisis")


# ─────────────────────────────────────────────
#  TAB: ANALIZAR  (núcleo de la app)
# ─────────────────────────────────────────────

def tab_analizar(mods):
    plan = st.session_state.get("user_plan", "free")
    uid  = st.session_state.get("user_id", 0)
    demo = (plan == "demo")

    o_key = os.getenv("OPENAI_API_KEY", "")

    if plan == "free":
        used = get_daily_usage(uid)
        if used >= FREE_LIMIT:
            st.markdown(f'<div class="limit-bar">⛔ Has usado tus {FREE_LIMIT} análisis gratuitos de hoy. '
                        f'<a href="#">Actualiza a PRO</a> para continuar.</div>', unsafe_allow_html=True)
            if st.button("⚡ Ver planes PRO"):
                st.session_state.show_upgrade = True
                st.rerun()
            return

    with st.form("analisis_form"):
        col1, col2 = st.columns([2, 1])
        with col1:
            nicho = st.text_input("🎯 Nicho / Sector",
                                  placeholder="Ej: Restaurantes, Cafeterías, Gimnasios…")
        with col2:
            ubicacion = st.text_input("📍 Ciudad",
                                      placeholder="Valladolid, Madrid, Barcelona…")
        if demo:
            st.info("🎯 **Modo Demo** — mostrando datos de ejemplo. Regístrate gratis para análisis reales.")
        analizar = st.form_submit_button("🚀 Analizar Mercado", type="primary",
                                         use_container_width=True)

    if not analizar:
        return
    if not nicho or not ubicacion:
        st.warning("Escribe un nicho y una ciudad.")
        return

    ai_text = ""
    keywords = []
    trend_series = None
    kws = []

    # ── Buscar competidores ──────────────────────────
    with st.spinner("Buscando competidores en OpenStreetMap…"):
        negocios = DEMO_BUSINESSES if demo else buscar_negocios(nicho, ubicacion)
        if not negocios:
            st.error("No se encontraron resultados. Prueba con otro nicho o ciudad.")
            return

    # Incrementar uso SOLO cuando hay resultados reales
    if plan == "free" and uid > 0:
        increment_usage(uid)

    # ── Competidores ──────────────────────────
    if mods["competidores"]:
        st.markdown("### 🏢 Competidores encontrados")
        df = pd.DataFrame([{
            "Nombre":   n["name"],
            "Rating":   n.get("rating") or "—",
            "Reseñas":  n.get("user_ratings_total", 0) or 0,
            "Dirección": n.get("formatted_address", n.get("vicinity", "")),
        } for n in negocios[:10]])
        st.dataframe(df, use_container_width=True)

        # Solo mostrar gráfico de ratings si hay datos reales
        ratings_disponibles = [n for n in negocios if n.get("rating")]
        if ratings_disponibles:
            df_r = pd.DataFrame([{
                "Nombre": n["name"],
                "Rating": n["rating"],
            } for n in ratings_disponibles[:10]])
            fig = px.bar(df_r.sort_values("Rating"), x="Nombre", y="Rating",
                         color="Rating", color_continuous_scale="Blues",
                         title="Rating por competidor")
            fig.update_layout(xaxis_tickangle=-30)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info(f"📍 Se encontraron **{len(negocios)} establecimientos** en OpenStreetMap. "
                    "Los datos de rating no están disponibles en esta fuente.")

    # ── Google Trends ──────────────────────────
    if mods["google_trends"]:
        st.markdown("### 📈 Tendencia de búsqueda (12 meses)")
        with st.spinner("Consultando Google Trends…"):
            if demo:
                trend_series = DEMO_TRENDS
                keywords = DEMO_KEYWORDS
            else:
                trend_series, keywords = obtener_tendencias(nicho, ubicacion)

        if trend_series is not None:
            if isinstance(trend_series, dict):
                labels = list(trend_series.keys())
                values = list(trend_series.values())
            else:
                labels = [str(d)[:7] for d in trend_series.index]
                values = trend_series.values.tolist()

            fig2 = px.line(x=labels, y=values,
                           labels={"x": "Mes", "y": "Interés (0-100)"},
                           title=f"Interés de búsqueda: '{nicho}'",
                           markers=True)
            fig2.update_traces(line_color="#1a1a2e", line_width=2.5)
            st.plotly_chart(fig2, use_container_width=True)
            trend_delta = values[-1] - values[0] if len(values) > 1 else 0
            emoji = "📈" if trend_delta > 0 else "📉"
            st.metric("Cambio de interés (12 meses)", f"{trend_delta:+.0f} pts", delta=f"{emoji}")
        else:
            st.info("No se obtuvieron datos de tendencias para este nicho.")

    # ── Análisis IA ──────────────────────────
    if mods["analisis_ia"]:
        if plan not in ["pro", "demo"] and not o_key:
            st.warning("🔒 El análisis IA es exclusivo del plan PRO.")
        else:
            st.markdown("### 🤖 Análisis IA de Mercado")
            with st.spinner("Analizando mercado con IA…"):
                if demo:
                    ai_text = """PUNTOS DE DOLOR:
• Tiempos de espera excesivos (>20 min) sin comunicación proactiva al cliente
• Falta de opciones para dietas especiales (vegetariano, vegano, sin gluten)
• Relación calidad-precio cuestionada vs oferta de cadenas premium

OPORTUNIDADES DE MERCADO:
• Especialización en smash burgers artesanales con ingredientes locales
• Servicio rápido (<12 min) como propuesta de valor diferencial
• Menú flexible con opciones plant-based para ampliar público

RECOMENDACIÓN ESTRATÉGICA:
Posiciónate como la opción "fast-casual premium" con tiempos garantizados y opciones inclusivas. \
Un programa de fidelización digital desde el día 1 puede capturar la demanda insatisfecha que actualmente \
va a cadenas internacionales."""
                elif o_key:
                    client = OpenAI(api_key=o_key)
                    ai_text = analizar_con_ia(client, nicho, ubicacion, negocios)
                else:
                    ai_text = "Configura tu OpenAI API key en Streamlit Secrets para obtener el análisis IA."

            st.markdown(ai_text)

    # ── Competitor Scoring Matrix ──────────────────────────
    if mods["scoring"] and len(negocios) >= 2:
        st.markdown("### 📊 Competitor Scoring Matrix")
        scores = calcular_scores(negocios)
        dims = ["Calidad", "Popularidad", "Visibilidad", "Madurez", "Servicio", "Amenaza"]

        fig3 = go.Figure()
        for s in scores[:5]:
            fig3.add_trace(go.Scatterpolar(
                r=[s[d] for d in dims],
                theta=dims, fill='toself', name=s["name"], opacity=0.6
            ))
        fig3.update_layout(polar=dict(radialaxis=dict(range=[0, 100])),
                           title="Radar de Competidores", height=500)
        st.plotly_chart(fig3, use_container_width=True)

        heat_df = pd.DataFrame([{**{"Empresa": s["name"]}, **{d: s[d] for d in dims}}
                                 for s in scores]).set_index("Empresa")
        fig4 = px.imshow(heat_df, color_continuous_scale="RdYlGn",
                         aspect="auto", title="Heatmap de Scores")
        st.plotly_chart(fig4, use_container_width=True)

        st.markdown("#### 🏆 Podio de Competidores")
        sorted_s = sorted(scores, key=lambda x: x["Amenaza"], reverse=True)
        p1, p2, p3 = st.columns(3)
        if len(sorted_s) > 0: p1.metric("🥇 Líder",    sorted_s[0]["name"], f"Score: {sorted_s[0]['Amenaza']}")
        if len(sorted_s) > 1: p2.metric("🥈 2º puesto", sorted_s[1]["name"], f"Score: {sorted_s[1]['Amenaza']}")
        if len(sorted_s) > 2: p3.metric("🥉 3º puesto", sorted_s[2]["name"], f"Score: {sorted_s[2]['Amenaza']}")

    # ── Brechas de Mercado ──────────────────────────
    if mods["brechas"] and len(negocios) >= 2:
        st.markdown("### 🔍 Brechas de Mercado Detectadas")
        scores_b = calcular_scores(negocios)
        brechas = detectar_brechas(scores_b, DEMO_TRENDS if demo else (trend_series or {}))
        for b in brechas:
            st.markdown(f"- {b}")

    # ── Keyword Suggestion Engine ──────────────────────────
    if mods["keywords"]:
        st.markdown("### 🔑 Keyword Suggestion Engine")
        kws = keywords if keywords else DEMO_KEYWORDS
        if kws:
            kw_df = pd.DataFrame(kws, columns=["Keyword", "Interés"])
            kw_df = kw_df.sort_values("Interés", ascending=False)
            fig5 = px.bar(kw_df, x="Interés", y="Keyword", orientation="h",
                          color="Interés", color_continuous_scale="Teal",
                          title="Keywords relacionadas por volumen de búsqueda")
            st.plotly_chart(fig5, use_container_width=True)
            st.dataframe(kw_df, use_container_width=True)
        else:
            st.info("No se encontraron keywords relacionadas para este nicho.")

    # ── Guardar análisis ──────────────────────────
    if uid > 0 and plan != "demo":
        save_analysis(uid, nicho, ubicacion, {
            "negocios": negocios[:5],
            "ai_text": ai_text,
            "keywords": kws,
        })

    # ── Exportar HTML ──────────────────────────
    if plan in ["pro"] or demo:
        st.markdown("---")
        st.markdown("### 📥 Exportar Reporte")
        brechas_exp = detectar_brechas(calcular_scores(negocios),
                                       DEMO_TRENDS if demo else (trend_series or {}))
        html = generar_reporte_html(nicho, ubicacion, negocios, ai_text,
                                    DEMO_TRENDS if demo else (trend_series or {}),
                                    brechas_exp, kws)
        st.download_button("⬇️ Descargar Reporte HTML", html,
                           file_name=f"análisis_{nicho}_{ubicacion}.html",
                           mime="text/html")


# ─────────────────────────────────────────────
#  APP PRINCIPAL
# ─────────────────────────────────────────────

def main():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "auth_mode" not in st.session_state:
        st.session_state.auth_mode = "login"
    if "show_upgrade" not in st.session_state:
        st.session_state.show_upgrade = False

    if not st.session_state.logged_in:
        st.markdown('<div style="text-align:center;padding:2rem">'
                    '<h1>📊 IA Market Analyzer</h1>'
                    '<p style="color:#666">Inteligencia de mercado para emprendedores</p>'
                    '</div>', unsafe_allow_html=True)
        if st.session_state.auth_mode == "login":
            pagina_login()
        else:
            pagina_registro()
        return

    if st.session_state.show_upgrade and st.session_state.user_plan != "demo":
        mods = render_sidebar()
        pantalla_upgrade()
        return

    mods = render_sidebar()
    tab_b, tab_a, tab_h = st.tabs(["🏠 Bienvenida", "🔍 Analizar Mercado", "📋 Mi Historial"])
    with tab_b:
        tab_bienvenida()
    with tab_a:
        tab_analizar(mods)
    with tab_h:
        tab_historial()


if __name__ == "__main__":
    main()
