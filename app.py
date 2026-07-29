from __future__ import annotations

import json
from copy import deepcopy
from html import escape

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from model import calculate, export_excel, money, normalize_records
from supabase_store import connect, create_household, join_household, load_data, open_recovery_session, request_password_reset, save_data, sign_in, sign_out, sign_up, update_password


st.set_page_config(page_title="Control financiero familiar", page_icon="🏠", layout="wide")


try:
    supabase_url = st.secrets["supabase"]["url"]
    supabase_key = st.secrets["supabase"]["publishable_key"]
    FAMILY_NAME = st.secrets["app"]["family_name"]
    AUTHORIZED_USERS = {
        email.lower(): tuple(value.split("|", 1))
        for email, value in st.secrets["authorized_users"].items()
    }
    defaults = json.loads(st.secrets["initial_data_json"])
except (KeyError, FileNotFoundError):
    st.error("Falta configurar la conexión privada de la aplicación.")
    st.stop()

if "supabase" not in st.session_state:
    st.session_state.supabase = connect(supabase_url, supabase_key)
client = st.session_state.supabase
APP_URL = "https://garcia-bouayach-family-finances.streamlit.app/"  # Recovery callback

components.html(
    """
    <script>
      const hash = window.parent.location.hash;
      if (hash && hash.includes("type=recovery")) {
        const values = new URLSearchParams(hash.slice(1));
        const access = values.get("access_token");
        const refresh = values.get("refresh_token");
        if (access && refresh) {
          const target = new URL(window.parent.location.href);
          target.hash = "";
          target.searchParams.set("recovery", "1");
          target.searchParams.set("access_token", access);
          target.searchParams.set("refresh_token", refresh);
          window.parent.location.replace(target.toString());
        }
      }
    </script>
    """,
    height=0,
)

if st.query_params.get("recovery") == "1" and not st.session_state.get("password_recovery"):
    access_token = st.query_params.get("access_token", "")
    refresh_token = st.query_params.get("refresh_token", "")
    if access_token and refresh_token:
        try:
            open_recovery_session(client, access_token, refresh_token)
            st.session_state.password_recovery = True
            st.query_params.clear()
            st.rerun()
        except Exception:
            st.query_params.clear()
            st.error("El enlace de recuperación ha caducado o ya se ha utilizado. Solicita uno nuevo.")

if st.session_state.get("password_recovery"):
    st.subheader("Crear una contraseña nueva")
    with st.form("new_password_form"):
        new_password = st.text_input("Nueva contraseña", type="password")
        repeated_password = st.text_input("Repite la contraseña", type="password")
        password_submitted = st.form_submit_button("Guardar contraseña nueva", type="primary", use_container_width=True)
    if password_submitted:
        if len(new_password) < 8:
            st.error("La contraseña debe tener al menos 8 caracteres.")
        elif new_password != repeated_password:
            st.error("Las dos contraseñas no coinciden.")
        else:
            try:
                update_password(client, new_password)
                sign_out(client)
                st.session_state.pop("password_recovery", None)
                st.success("Contraseña actualizada. Ya puedes iniciar sesión desde el móvil y el Mac.")
            except Exception as exc:
                st.error(f"No ha sido posible actualizar la contraseña: {exc}")
    st.stop()

st.markdown(
    f"""
    <div class="brand-lockup">
      <div class="brand-mark">R&amp;A</div>
      <div>
        <div class="brand-name">{escape(FAMILY_NAME)}</div>
        <div class="brand-tagline">Private financial dashboard</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.markdown(
    """
    <style>
      :root {--ra-gold:#B48A2C;--ra-gold-dark:#896719;--ra-gold-soft:#F7F0DF;--ra-ink:#28241D;}
      .stApp, [data-testid="stAppViewContainer"] {
        background:
          radial-gradient(circle at 88% 0%, rgba(207,169,79,.22), transparent 29rem),
          radial-gradient(circle at 4% 84%, rgba(22,138,87,.11), transparent 34rem),
          linear-gradient(rgba(180,138,44,.035) 1px, transparent 1px),
          linear-gradient(90deg, rgba(180,138,44,.035) 1px, transparent 1px),
          linear-gradient(135deg,#FFFDF8 0%,#F7F1E4 52%,#FAFCF8 100%);
        background-size:auto,auto,32px 32px,32px 32px,auto;
        background-attachment:fixed;
        color:var(--ra-ink);
      }
      [data-testid="stHeader"] {background:rgba(255,255,255,.82);backdrop-filter:blur(12px);}
      [data-testid="stSidebar"], [data-testid="stSidebar"] > div {background:#FCF9F2;}
      [data-testid="stSidebar"] {border-right:1px solid #E6D4A7;}
      h1,h2,h3,p,label,[data-testid="stCaptionContainer"] {color:var(--ra-ink);}
      h1 {color:var(--ra-gold-dark);}
      [data-baseweb="input"], [data-baseweb="input"] > div, [data-baseweb="base-input"],
      [data-baseweb="select"] > div, [data-baseweb="textarea"], [data-baseweb="textarea"] > div {
        background:#FFFFFF !important;border-color:#DCC587;color:var(--ra-ink);
      }
      input, textarea {background:#FFFFFF !important;color:var(--ra-ink) !important;}
      [data-testid="stForm"] {background:rgba(255,255,255,.78);backdrop-filter:blur(18px);border:1px solid #E2CC94;border-radius:20px;box-shadow:0 20px 55px rgba(89,69,28,.10);}
      .stButton > button[kind="primary"], .stFormSubmitButton > button {
        background:var(--ra-gold);border-color:var(--ra-gold);color:#FFFFFF;
      }
      .stButton > button[kind="primary"]:hover, .stFormSubmitButton > button:hover {
        background:var(--ra-gold-dark);border-color:var(--ra-gold-dark);color:#FFFFFF;
      }
      [data-baseweb="radio"] div[aria-checked="true"] {background-color:var(--ra-gold);}
      .brand-lockup {display:flex;align-items:center;gap:14px;padding:13px 18px;margin:2px 0 20px;background:rgba(255,255,255,.60);backdrop-filter:blur(18px);border:1px solid rgba(180,138,44,.28);border-radius:20px;box-shadow:0 12px 38px rgba(89,69,28,.08);}
      .brand-mark {width:54px;height:54px;border-radius:17px;display:flex;align-items:center;justify-content:center;background:linear-gradient(145deg,#E4C981,#9A741E);color:#FFF;font-weight:800;font-size:1rem;letter-spacing:-.04em;box-shadow:0 10px 25px rgba(137,103,25,.26),inset 0 1px 0 rgba(255,255,255,.52);}
      .brand-name {font-size:1.85rem;line-height:1.05;font-weight:760;letter-spacing:-.045em;color:#28241D;}
      .brand-tagline {font-size:.72rem;text-transform:uppercase;letter-spacing:.16em;color:#8A7450;margin-top:5px;font-weight:650;}
    </style>
    """,
    unsafe_allow_html=True,
)
if "signed_email" not in st.session_state:
    st.subheader("Acceso privado")
    mode = st.radio("", ["Iniciar sesión", "Crear mi contraseña", "Recuperar contraseña"], horizontal=True, label_visibility="collapsed")
    with st.form("auth_form"):
        email = st.text_input("Correo electrónico").strip().lower()
        password = st.text_input("Contraseña", type="password", disabled=mode == "Recuperar contraseña")
        submitted = st.form_submit_button(mode, type="primary", use_container_width=True)
    if submitted:
        if email not in AUTHORIZED_USERS:
            st.error("Este correo no está autorizado para esta familia.")
        elif mode == "Recuperar contraseña":
            try:
                request_password_reset(client, email, APP_URL)
                st.success("Te hemos enviado un enlace. Revisa también la carpeta de correo no deseado.")
            except Exception as exc:
                st.error(f"No ha sido posible enviar el enlace de recuperación: {exc}")
        elif len(password) < 8:
            st.error("La contraseña debe tener al menos 8 caracteres.")
        else:
            try:
                response = sign_in(client, email, password) if mode == "Iniciar sesión" else sign_up(client, email, password)
                if response.session:
                    st.session_state.signed_email = email
                    st.rerun()
                else:
                    st.success("Cuenta creada. Revisa tu correo para confirmarla y después inicia sesión.")
            except Exception as exc:
                st.error(f"No ha sido posible completar el acceso: {exc}")
    st.caption("Solo los miembros autorizados pueden acceder. Cada contraseña es privada y no se guarda en la aplicación.")
    st.stop()

signed_email = st.session_state.signed_email
person_key, display_name = AUTHORIZED_USERS[signed_email]

try:
    data, db_context = load_data(client, defaults, person_key)
except RuntimeError:
    st.subheader("Unir la cuenta familiar")
    if person_key == "member_a":
        st.write("Crea el espacio familiar. Después aparecerá un código para que el segundo miembro pueda unirse.")
        if st.button("Crear espacio familiar", type="primary"):
            created = create_household(client, FAMILY_NAME, display_name)
            _, initial_context = load_data(client, defaults, person_key)
            save_data(client, defaults, initial_context, person_key)
            st.session_state.invite_code = created["invite_code"]
            st.session_state.finance_data = defaults
            st.rerun()
    else:
        invite = st.text_input("Código de invitación proporcionado por el primer miembro")
        if st.button("Unirme a la familia", type="primary") and invite:
            join_household(client, invite, display_name)
            loaded, initial_context = load_data(client, defaults, person_key)
            loaded[person_key] = defaults[person_key]
            save_data(client, loaded, initial_context, person_key)
            st.session_state.finance_data = loaded
            st.rerun()
    if "invite_code" in st.session_state:
        st.success(f"Código para el segundo miembro: {st.session_state.invite_code}")
    st.stop()

if "finance_data" not in st.session_state:
    st.session_state.finance_data = data
else:
    data = st.session_state.finance_data

st.markdown(
    """
    <style>
      :root {
        --ra-gold: #B48A2C;
        --ra-gold-dark: #896719;
        --ra-gold-soft: #F7F0DF;
        --ra-ink: #28241D;
        --ra-positive: #168A57;
        --ra-negative: #C63D3D;
      }
      .stApp, [data-testid="stAppViewContainer"] {
        background:
          radial-gradient(circle at 90% 3%, rgba(207,169,79,.20), transparent 30rem),
          radial-gradient(circle at 5% 88%, rgba(22,138,87,.09), transparent 36rem),
          linear-gradient(rgba(180,138,44,.032) 1px, transparent 1px),
          linear-gradient(90deg, rgba(180,138,44,.032) 1px, transparent 1px),
          linear-gradient(135deg,#FFFDF8 0%,#F8F2E7 48%,#F9FCF8 100%);
        background-size:auto,auto,34px 34px,34px 34px,auto;
        background-attachment:fixed;
        color: var(--ra-ink);
      }
      [data-testid="stHeader"] {background:rgba(255,253,248,.62);backdrop-filter:blur(18px);border-bottom:1px solid rgba(180,138,44,.10);}
      .block-container {padding-top: 1.3rem;padding-bottom:3rem;}
      [data-testid="stSidebar"] {background:linear-gradient(180deg,rgba(248,240,221,.94) 0%,rgba(255,255,255,.82) 72%);backdrop-filter:blur(20px);border-right:1px solid #E6D4A7;box-shadow:8px 0 32px rgba(89,69,28,.045);}
      [data-testid="stSidebar"] > div {background:transparent;}
      html, body, [class*="css"] {font-family: Inter, "SF Pro Display", "Segoe UI", sans-serif;}
      h1, h2, h3 {letter-spacing: -0.035em; color: var(--ra-ink); font-weight: 650;}
      h1 {color: var(--ra-gold-dark);}
      [data-testid="stMetric"] {
        background: linear-gradient(145deg, #FFFFFF 35%, #FBF6EA 100%);
        padding: 1rem;
        border: 1px solid #D8BA73;
        border-top: 4px solid var(--ra-gold);
        border-radius: .85rem;
        box-shadow: 0 5px 18px rgba(137, 103, 25, .08);
      }
      [data-testid="stMetricLabel"] {color: var(--ra-gold-dark); font-weight: 700;}
      [data-testid="stMetricValue"] {color: var(--ra-ink);}
      .stTabs [data-baseweb="tab-list"] {gap:.35rem;border:1px solid rgba(180,138,44,.20);background:rgba(255,255,255,.55);backdrop-filter:blur(14px);padding:6px;border-radius:15px;box-shadow:0 8px 28px rgba(89,69,28,.055);}
      .stTabs [data-baseweb="tab"] {color:#64583F;border-radius:9px;padding-left:1rem;padding-right:1rem;}
      .stTabs [aria-selected="true"] {background:linear-gradient(145deg,#FFF,#F8EBCB);color:var(--ra-gold-dark);font-weight:700;box-shadow:0 5px 16px rgba(89,69,28,.12);}
      .stTabs [data-baseweb="tab-highlight"] {background-color: var(--ra-gold);}
      .stButton > button[kind="primary"], .stFormSubmitButton > button {
        background: var(--ra-gold);
        border-color: var(--ra-gold);
        color: #FFFFFF;
      }
      .stButton > button[kind="primary"]:hover, .stFormSubmitButton > button:hover {
        background: var(--ra-gold-dark);
        border-color: var(--ra-gold-dark);
        color: #FFFFFF;
      }
      .stButton > button:not([kind="primary"]), .stDownloadButton > button {
        border-color: #C9A955;
        color: var(--ra-gold-dark);
      }
      [data-baseweb="input"] > div, [data-baseweb="select"] > div, [data-baseweb="textarea"] > div {
        background: #FFFFFF;
        border-color: #DCC587;
      }
      [data-testid="stDataFrame"] {background:rgba(255,255,255,.90);border:1px solid #E2CC94;border-radius:16px;overflow:hidden;box-shadow:0 12px 34px rgba(89,69,28,.07);}
      hr {border-color: #E6D4A7;}
      a {color: var(--ra-gold-dark);}
      .finance-card {background:linear-gradient(145deg,rgba(255,255,255,.94),rgba(249,241,221,.72));backdrop-filter:blur(14px);border:1px solid #D8BA73;border-top:4px solid var(--ra-gold);border-radius:18px;padding:15px 19px 17px;min-height:104px;box-shadow:0 12px 34px rgba(89,69,28,.09),inset 0 1px 0 rgba(255,255,255,.9);transition:transform .18s ease,box-shadow .18s ease;}
      .finance-card:hover {transform:translateY(-3px);box-shadow:0 18px 40px rgba(89,69,28,.13);}
      .finance-card .finance-label {font-size:.82rem;font-weight:700;color:var(--ra-gold-dark);margin-bottom:8px;letter-spacing:.01em;}
      .finance-card .finance-value {font-size:1.72rem; line-height:1.15; font-weight:720; letter-spacing:-.035em; color:var(--ra-ink);}
      .finance-card.positive .finance-value {color:var(--ra-positive);}
      .finance-card.negative .finance-value {color:var(--ra-negative);}
      .finance-breakdown {display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:4px;}
      .finance-breakdown.items-4 {grid-template-columns:repeat(4,1fr);}
      .finance-breakdown-item {padding-right:12px;border-right:1px solid rgba(180,138,44,.24);}
      .finance-breakdown-item:last-child {border-right:0;padding-right:0;}
      .finance-breakdown-name {font-size:.72rem;text-transform:uppercase;letter-spacing:.08em;color:#8A7450;font-weight:700;margin-bottom:4px;}
      .finance-breakdown-value {font-size:1.48rem;line-height:1.15;font-weight:730;letter-spacing:-.035em;color:var(--ra-ink);}
      .finance-breakdown-value.positive {color:var(--ra-positive);}
      .finance-breakdown-value.negative {color:var(--ra-negative);}
      [data-testid="stVegaLiteChart"] {background:linear-gradient(145deg,rgba(255,255,255,.94),rgba(255,252,245,.84));backdrop-filter:blur(14px);border:1px solid #D8BA73;border-radius:20px;padding:16px 18px 10px;box-shadow:0 14px 38px rgba(89,69,28,.09),inset 0 1px 0 rgba(255,255,255,.9);overflow:hidden;}
    </style>
    """,
    unsafe_allow_html=True,
)

def financial_metric(container, label: str, value: str, tone: str = "neutral") -> None:
    container.markdown(
        f'<div class="finance-card {tone}"><div class="finance-label">{escape(label)}</div>'
        f'<div class="finance-value">{escape(value)}</div></div>',
        unsafe_allow_html=True,
    )


def financial_breakdown_metric(container, label: str, items: list[tuple[str, str, str]]) -> None:
    parts = "".join(
        f'<div class="finance-breakdown-item"><div class="finance-breakdown-name">{escape(name)}</div>'
        f'<div class="finance-breakdown-value {tone}">{escape(value)}</div></div>'
        for name, value, tone in items
    )
    container.markdown(
        f'<div class="finance-card"><div class="finance-label">{escape(label)}</div>'
        f'<div class="finance-breakdown items-{len(items)}">{parts}</div></div>',
        unsafe_allow_html=True,
    )

st.caption("Reforma, gastos personales, ahorro y deuda · periodo configurable")

member_a_label = next(label for key, label in AUTHORIZED_USERS.values() if key == "member_a")
member_b_label = next(label for key, label in AUTHORIZED_USERS.values() if key == "member_b")

with st.sidebar:
    st.caption(f"Sesión: {display_name}")
    if person_key == "member_a":
        st.code(db_context["invite_code"], language=None)
        st.caption("Código privado para que el segundo miembro se una una sola vez.")
    st.header("Escenario")
    data["scenario"]["include_march_bonus"] = st.toggle(
        "Incluir bonus de marzo",
        value=bool(data["scenario"]["include_march_bonus"]),
        help="Añade al ahorro familiar el importe extraordinario indicado para marzo.",
    )
    stored_march_extra = float(data["savings"].get("march_extra_contribution", 0.0))
    march_extra_input = st.number_input(
        "Aportación extra familiar en marzo",
        min_value=0.0,
        value=stored_march_extra if stored_march_extra > 0 else None,
        step=100.0,
        placeholder="Introduce el importe",
        disabled=not data["scenario"]["include_march_bonus"],
    )
    data["savings"]["march_extra_contribution"] = 0.0 if march_extra_input is None else float(march_extra_input)
    st.subheader("Punto de partida del ahorro")
    savings_periods = pd.date_range(
        start=pd.Timestamp(data["period"]["start"]),
        periods=int(data["period"]["months"]),
        freq="MS",
    )
    savings_checkpoint_months = [savings_periods[0] - pd.offsets.MonthBegin(1), *savings_periods]
    savings_checkpoint_options = [month.strftime("%Y-%m-%d") for month in savings_checkpoint_months]
    stored_checkpoint_month = str(data["savings"].get("actual_savings_month", savings_checkpoint_options[0]))
    checkpoint_index = savings_checkpoint_options.index(stored_checkpoint_month) if stored_checkpoint_month in savings_checkpoint_options else 0
    data["savings"]["actual_savings_month"] = st.selectbox(
        "Mes del ahorro real",
        options=savings_checkpoint_options,
        index=checkpoint_index,
        format_func=lambda value: pd.Timestamp(value).strftime("%m/%Y"),
    )
    data["savings"]["actual_savings_amount"] = st.number_input(
        "Ahorro real en ese mes",
        min_value=0.0,
        value=float(data["savings"].get("actual_savings_amount", data["savings"].get("initial_balance", 0.0))),
        step=100.0,
    )
    data["savings"]["member_a_extra"] = st.number_input(
        f"Aportado extra · {member_a_label}",
        min_value=0.0,
        value=float(data["savings"].get("member_a_extra", 0.0)),
        step=100.0,
    )
    data["savings"]["member_b_extra"] = st.number_input(
        f"Aportado extra · {member_b_label}",
        min_value=0.0,
        value=float(data["savings"].get("member_b_extra", 0.0)),
        step=100.0,
    )
    st.subheader("Pagas extra al ahorro")
    data["savings"]["member_a_extra_pay_contribution"] = st.number_input(
        f"Aportación por paga extra · {member_a_label}",
        min_value=0.0,
        value=float(data["savings"].get("member_a_extra_pay_contribution", 3000.0)),
        step=100.0,
    )
    data["savings"]["member_b_extra_pay_contribution"] = st.number_input(
        f"Aportación por paga extra · {member_b_label}",
        min_value=0.0,
        value=float(data["savings"].get("member_b_extra_pay_contribution", 3000.0)),
        step=100.0,
    )
    st.subheader("Vacaciones")
    data["savings"]["vacation_amount"] = st.slider(
        "Dinero destinado a vacaciones",
        min_value=0,
        max_value=20000,
        value=int(data["savings"].get("vacation_amount", 0.0)),
        step=100,
        format="%d €",
    )
    vacation_months = pd.date_range(
        start=pd.Timestamp(data["period"]["start"]),
        periods=int(data["period"]["months"]),
        freq="MS",
    )
    vacation_options = [month.strftime("%Y-%m-%d") for month in vacation_months]
    stored_vacation_month = str(data["savings"].get("vacation_month", vacation_options[-1]))
    vacation_index = vacation_options.index(stored_vacation_month) if stored_vacation_month in vacation_options else len(vacation_options) - 1
    selected_vacation_month = st.selectbox(
        "Mes de las vacaciones",
        options=vacation_options,
        index=vacation_index,
        format_func=lambda value: pd.Timestamp(value).strftime("%m/%Y"),
    )
    data["savings"]["vacation_month"] = selected_vacation_month
    data["debt"]["family_monthly_repayment"] = st.number_input(
        "Devolución mensual préstamo familiar",
        min_value=0.0,
        value=float(data["debt"].get("family_monthly_repayment", 0.0)),
        step=50.0,
    )


def person_editor(key: str, label: str) -> None:
    person = data[key]
    metrics = st.container()
    st.subheader(f"Parámetros de {label}")
    c1, c2, c3, c4 = st.columns(4)
    person["salary"] = c1.number_input("Nómina ordinaria", min_value=0.0, value=float(person["salary"]), step=50.0, key=f"salary_{key}")
    person["extra_amount"] = c2.number_input("Importe paga extra", min_value=0.0, value=float(person["extra_amount"]), step=50.0, key=f"extra_{key}")
    person["extra_months"][0] = c3.number_input("Mes de extra 1", min_value=1, max_value=12, value=int(person["extra_months"][0]), key=f"extra_m1_{key}")
    person["extra_months"][1] = c4.number_input("Mes de extra 2", min_value=1, max_value=12, value=int(person["extra_months"][1]), key=f"extra_m2_{key}")
    person["january_raise_pct"] = st.number_input(
        "Subida salarial anual en enero (%)",
        min_value=0.0,
        max_value=30.0,
        value=float(person.get("january_raise_pct", 0.0)),
        step=0.5,
        key=f"january_raise_{key}",
        help="Se aplica a partir de enero y se acumula cada año de la simulación.",
    )
    edited = st.data_editor(
        pd.DataFrame(person["expenses"]),
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "id": None,
            "concept": st.column_config.TextColumn("Concepto", required=True),
            "category": st.column_config.TextColumn("Categoría", required=True),
            "monthly": st.column_config.NumberColumn("Importe mensual", min_value=0.0, step=1.0, format="%.2f €"),
        },
        key=f"expenses_{key}",
        hide_index=True,
    )
    person["expenses"] = normalize_records(edited.to_dict("records"), ["monthly"])
    common_monthly = sum(
        float(item["monthly"])
        * (float(item.get("member_a_share", 0.5)) if key == "member_a" else 1 - float(item.get("member_a_share", 0.5)))
        for item in data["common_expenses"]
    )
    personal_monthly = sum(float(item["monthly"]) for item in person["expenses"])
    ordinary_net = float(person["salary"]) - common_monthly - personal_monthly
    with metrics:
        k1, k2, k3, k4 = st.columns(4)
        financial_metric(k1, "Nómina mensual", money(float(person["salary"])))
        financial_metric(k2, "Gasto común mensual", money(common_monthly))
        financial_metric(k3, "Gastos personales mensuales", money(personal_monthly))
        financial_metric(k4, "Neto restante mensual", money(ordinary_net), "positive" if ordinary_net >= 0 else "negative")


def time_chart(frame: pd.DataFrame, fields: list[str], names: dict[str, str], colors: list[str] | None = None):
    melted = frame[["month", *fields]].melt("month", var_name="series", value_name="amount")
    melted["series"] = melted["series"].map(names)
    encoding = alt.Color("series:N", title=None)
    if colors:
        encoding = alt.Color("series:N", title=None, scale=alt.Scale(range=colors))
    return (
        alt.Chart(melted)
        .mark_line(point=True, strokeWidth=2.5)
        .encode(
            x=alt.X("month:T", title=None, axis=alt.Axis(format="%b %Y")),
            y=alt.Y("amount:Q", title="€"),
            color=encoding,
            tooltip=[alt.Tooltip("month:T", title="Mes", format="%b %Y"), alt.Tooltip("series:N", title="Serie"), alt.Tooltip("amount:Q", title="Importe", format=",.2f")],
        )
        .properties(height=330)
    )


PHOTO_REFORM_ROWS = [
    ("Cocina", "Reserva", 500.0, 0.0, "Pagado"),
    ("Cocina", "Fabricación", 7960.0, 0.0, "Pagado"),
    ("Cocina", "Pago 2 · Entrega muebles", 2530.0, 0.0, "No pagado"),
    ("Cocina", "Pago 3 · Montaje", 2000.0, 0.0, "No pagado"),
    ("Reforma", "1.ª factura reforma", 17100.64, 3591.13, "Pagado"),
    ("Reforma", "2.ª factura reforma", 11130.40, 2337.38, "Pagado"),
    ("Reforma", "3.er pago efectivo", 11130.40, 0.0, "No pagado"),
    ("Reforma", "Baños", 9098.04, 0.0, "No pagado"),
    ("Reforma", "4.º pago", 13543.636, 2844.16356, "No pagado"),
    ("Reforma", "5.º pago efectivo", 16719.54, 0.0, "No pagado"),
    ("Materiales", "Tarima", 5460.77, 1146.76, "Pagado"),
    ("Materiales", "Peldaños tarima", 1653.30, 347.19, "Pagado"),
    ("Materiales", "Cocina y aseo", 1719.16, 361.02, "Pagado"),
    ("Materiales", "Suelo/pared y pared baños planta superior", 1664.98, 349.65, "Pagado"),
    ("Materiales", "Suelo baño planta superior", 700.0, 147.0, "No pagado"),
    ("Placas solares", "1.er pago placas", 2576.81, 541.1301, "Pagado"),
    ("Placas solares", "2.º pago placas", 2576.81, 541.1301, "No pagado"),
    ("Aerotermia", "Aerotermia", 11576.50, 2431.065, "No pagado"),
]

PREVIOUS_PENDING_ROWS = [
    ("Cocina", "Presupuesto pendiente cocina", 4530.0),
    ("Reforma", "Presupuesto pendiente reforma", 41861.0),
    ("Placas solares", "Presupuesto pendiente placas solares", 3117.94),
    ("Aerotermia", "Presupuesto pendiente aerotermia", 7018.7825),
    ("Equipamiento casa", "Muebles de baño", 1800.0),
    ("Materiales", "Material suelo baño", 500.0),
    ("Equipamiento casa", "Sofás", 2400.0),
    ("Electrodomésticos", "Frigorífico", 949.0),
    ("Electrodomésticos", "Placa vitrocerámica", 1279.0),
    ("Electrodomésticos", "Instalación vitrocerámica", 150.0),
    ("Electrodomésticos", "Horno", 600.0),
    ("Reforma", "Ajuste del presupuesto anterior", 550.9975),
]


def detailed_reform_row(partida: str, description: str, base: float, vat: float, status: str) -> dict:
    total = float(base) + float(vat)
    return {
        "partida": partida,
        "description": description,
        "base_amount": float(base),
        "vat_amount": float(vat),
        "with_vat": float(vat) > 0,
        "total_amount": total,
        "payment_status": status,
        "paid_amount": total if status == "Pagado" else 0.0,
        "payment_date": "",
    }


def upgrade_reform_records(records: list[dict]) -> tuple[list[dict], bool]:
    paid_photo = [detailed_reform_row(*row) for row in PHOTO_REFORM_ROWS if row[4] == "Pagado"]
    if records and all("partida" in row for row in records):
        rejected_photo_descriptions = {
            description.casefold() for _, description, _, _, status in PHOTO_REFORM_ROWS if status != "Pagado"
        }
        cleaned = [
            row for row in records
            if str(row.get("description", "")).casefold() not in rejected_photo_descriptions
        ]
        existing = {str(row.get("description", "")).casefold() for row in cleaned}
        for partida, description, amount in PREVIOUS_PENDING_ROWS:
            if description.casefold() not in existing:
                pending = detailed_reform_row(partida, description, amount, 0.0, "No pagado")
                pending["with_vat"] = True
                cleaned.append(pending)
        changed = len(cleaned) != len(records) or any(
            description.casefold() not in {str(row.get("description", "")).casefold() for row in records}
            for _, description, _ in PREVIOUS_PENDING_ROWS
        )
        return cleaned, changed
    detailed = paid_photo
    appliance_terms = {"frigorífico", "placa vitrocerámica", "instalación vitrocerámica", "horno", "electrodomésticos"}
    for old in records:
        concept = str(old.get("concept", "")).strip()
        if not concept:
            continue
        folded = concept.casefold()
        if folded == "cocina":
            partida, concept = "Cocina", "Presupuesto pendiente cocina"
        elif folded == "reforma":
            partida, concept = "Reforma", "Presupuesto pendiente reforma"
        elif folded == "placas solares":
            partida, concept = "Placas solares", "Presupuesto pendiente placas solares"
        elif folded in {"aerotermia pendiente", "aerotermia"}:
            partida, concept = "Aerotermia", "Presupuesto pendiente aerotermia"
        elif folded in appliance_terms:
            partida = "Electrodomésticos"
        elif "material" in folded or "suelo" in folded:
            partida = "Materiales"
        else:
            partida = "Equipamiento casa"
        pending = detailed_reform_row(partida, concept, float(old.get("amount", 0.0)), 0.0, "No pagado")
        pending["with_vat"] = True
        detailed.append(pending)
    if not any(str(row.get("description", "")).casefold() == "ajuste del presupuesto anterior" for row in detailed):
        adjustment = detailed_reform_row("Reforma", "Ajuste del presupuesto anterior", 550.9975, 0.0, "No pagado")
        adjustment["with_vat"] = True
        detailed.append(adjustment)
    return detailed, True


tabs = st.tabs(["Resumen familiar", "Gastos comunes", "Financiación", "Reforma", member_b_label, member_a_label])

with tabs[5]:
    if person_key == "member_a":
        person_editor("member_a", member_a_label)
    else:
        st.info(f"Los gastos personales de {member_a_label} son privados. Solo se incorpora su aportación neta al cálculo familiar.")

with tabs[4]:
    if person_key == "member_b":
        person_editor("member_b", member_b_label)
    else:
        st.info(f"Los gastos personales de {member_b_label} son privados. Solo se incorpora su aportación neta al cálculo familiar.")

with tabs[1]:
    common_metrics = st.container()
    st.subheader("Gastos comunes")
    common_df = pd.DataFrame(data["common_expenses"])
    common_edited = st.data_editor(
        common_df,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "id": None,
            "concept": st.column_config.TextColumn("Concepto", required=True),
            "category": st.column_config.TextColumn("Categoría", required=True),
            "monthly": st.column_config.NumberColumn("Total mensual", min_value=0.0, step=1.0, format="%.2f €"),
            "member_a_share": st.column_config.NumberColumn(f"Proporción de {member_a_label} (0-1)", min_value=0.0, max_value=1.0, step=0.05, format="%.2f"),
        },
        key="common_editor",
        hide_index=True,
    )
    data["common_expenses"] = normalize_records(common_edited.to_dict("records"), ["monthly", "member_a_share"])
    st.info("Los 65 € por persona para IBI, ecotasa y seguro de hogar están incluidos dentro del ahorro familiar.")

with tabs[3]:
    data["reform"], reform_was_upgraded = upgrade_reform_records(data["reform"])
    if reform_was_upgraded:
        data["savings"]["reform_estimate_adjustment"] = 0.0
    reform_metrics = st.container()
    st.subheader("Histórico detallado de la reforma")
    st.caption("Edita importes, IVA, estado y fecha. Los totales y cantidades pendientes se recalculan automáticamente.")
    reform_df = pd.DataFrame(data["reform"])
    for numeric_column in ("base_amount", "vat_amount", "total_amount", "paid_amount"):
        reform_df[numeric_column] = pd.to_numeric(reform_df.get(numeric_column, 0.0), errors="coerce").fillna(0.0)
    reform_df["total_amount"] = reform_df["base_amount"] + reform_df["vat_amount"]
    reform_df["pending_amount"] = (reform_df["total_amount"] - reform_df["paid_amount"]).clip(lower=0.0)
    reform_edited = st.data_editor(
        reform_df, use_container_width=True, num_rows="dynamic", hide_index=True,
        column_config={
            "id": None,
            "partida": st.column_config.TextColumn("Partida", required=True),
            "description": st.column_config.TextColumn("Concepto / pago", required=True),
            "base_amount": st.column_config.NumberColumn("Base", min_value=0.0, step=50.0, format="%.2f €"),
            "with_vat": st.column_config.CheckboxColumn("Con IVA"),
            "vat_amount": st.column_config.NumberColumn("IVA", min_value=0.0, step=10.0, format="%.2f €"),
            "total_amount": st.column_config.NumberColumn("Total real", format="%.2f €"),
            "payment_status": st.column_config.SelectboxColumn("Estado", options=["Pagado", "Parcial", "No pagado"], required=True),
            "paid_amount": st.column_config.NumberColumn("Pagado", min_value=0.0, step=50.0, format="%.2f €"),
            "pending_amount": st.column_config.NumberColumn("Pendiente", format="%.2f €"),
            "payment_date": st.column_config.TextColumn("Fecha de pago", help="Formato recomendado: AAAA-MM-DD"),
        },
        disabled=["total_amount", "pending_amount"],
        column_order=["partida", "description", "base_amount", "with_vat", "vat_amount", "total_amount", "payment_status", "paid_amount", "pending_amount", "payment_date"],
        key="reform_editor",
    )
    clean_reform = normalize_records(
        reform_edited.to_dict("records"),
        ["base_amount", "vat_amount", "total_amount", "paid_amount", "pending_amount"],
    )
    for row in clean_reform:
        row["partida"] = str(row.get("partida", "Sin clasificar"))
        row["description"] = str(row.get("description", "Nuevo concepto"))
        row["payment_date"] = "" if pd.isna(row.get("payment_date")) else str(row.get("payment_date", ""))
        row["total_amount"] = row["base_amount"] + row["vat_amount"]
        status = row.get("payment_status") or "No pagado"
        row["payment_status"] = status
        if status == "Pagado":
            row["paid_amount"] = row["total_amount"]
        elif status == "No pagado":
            row["paid_amount"] = 0.0
        else:
            row["paid_amount"] = min(row["total_amount"], max(0.0, row["paid_amount"]))
        row["pending_amount"] = max(0.0, row["total_amount"] - row["paid_amount"])
        row["with_vat"] = bool(row.get("with_vat", row["vat_amount"] > 0))
    data["reform"] = clean_reform
    if st.button("Guardar histórico de reforma", type="primary", use_container_width=True):
        try:
            save_data(client, data, db_context, person_key)
            st.session_state.finance_data = deepcopy(data)
            st.success("Histórico de reforma guardado y verificado en la base de datos.")
        except Exception as exc:
            st.error(f"No se ha podido guardar el histórico: {exc}")
with tabs[2]:
    st.subheader("Financiación")
    funding_edited = st.data_editor(
        pd.DataFrame(data["funding"]), use_container_width=True, num_rows="dynamic", hide_index=True,
        column_config={
            "source": st.column_config.TextColumn("Fuente", required=True),
            "type": st.column_config.TextColumn("Tipo", required=True),
            "amount": st.column_config.NumberColumn("Importe", min_value=0.0, step=100.0, format="%.2f €"),
        }, key="funding_editor"
    )
    data["funding"] = normalize_records(funding_edited.to_dict("records"), ["amount"])
    d1, d2, d3 = st.columns(3)
    data["debt"]["john_deere_principal"] = d1.number_input("Capital John Deere", min_value=0.0, value=float(data["debt"]["john_deere_principal"]), step=500.0)
    data["debt"]["john_deere_months"] = d2.number_input("Plazo John Deere (meses)", min_value=1, value=int(data["debt"]["john_deere_months"]), step=1)
    data["debt"]["family_loan"] = d3.number_input("Préstamo familiar", min_value=0.0, value=float(data["debt"]["family_loan"]), step=100.0)


result = calculate(data)
family, member_a, member_b = result["family"], result["member_a"], result["member_b"]


def current_family_status(frame: pd.DataFrame) -> tuple[dict[str, float], str]:
    """Return the latest completed monthly status, or the opening position."""
    today = pd.Timestamp.now(tz="Europe/Madrid").tz_localize(None).normalize()
    current_month = today.replace(day=1)
    first_month = frame["month"].iloc[0]
    if current_month < first_month:
        return {
            "savings_balance": float(result["initial_savings"]),
            "john_deere_balance": float(data["debt"]["john_deere_principal"]),
            "family_loan_balance": float(data["debt"]["family_loan"]),
        }, f"Situación actual · {today.strftime('%d/%m/%Y')} · antes del inicio de la proyección"

    eligible = frame.loc[(frame["month"] <= current_month) & frame["savings_balance"].notna()]
    if eligible.empty:
        return {
            "savings_balance": float(result["initial_savings"]),
            "john_deere_balance": float(data["debt"]["john_deere_principal"]),
            "family_loan_balance": float(data["debt"]["family_loan"]),
        }, f"Saldo real indicado para {pd.Timestamp(result['savings_checkpoint_month']).strftime('%m/%Y')}"
    row = eligible.iloc[-1]
    status_month = row["month"].strftime("%m/%Y")
    return row.to_dict(), f"Situación actual estimada · mes {status_month}"


with tabs[0]:
    current_status, current_status_label = current_family_status(family)
    st.caption(current_status_label)
    s1, s2 = st.columns(2)
    financial_metric(s1, "Ahorro familiar", money(float(current_status["savings_balance"])), "positive")
    financial_metric(s2, "Gasto estimado reforma", money(float(result["reform_total"])))
    d1, d2 = st.columns(2)
    financial_metric(d1, "Deuda John Deere", money(float(current_status["john_deere_balance"])), "negative")
    financial_metric(d2, "Préstamo familiar", money(float(current_status["family_loan_balance"])), "negative")

    st.subheader("Evolución del ahorro familiar tras pagar la reforma")
    savings_history = family[["month", "savings_balance"]].dropna().copy()
    savings_min = min(-1000.0, float(savings_history["savings_balance"].min()) * 1.15)
    savings_max = max(1000.0, float(savings_history["savings_balance"].max()) * 1.10)
    savings_line = alt.Chart(savings_history).mark_line(point=True, strokeWidth=2.8, color="#22A06B").encode(
        x=alt.X("month:T", title=None, axis=alt.Axis(format="%b %Y")),
        y=alt.Y(
            "savings_balance:Q",
            title="€",
            scale=alt.Scale(domain=[savings_min, savings_max], zero=True),
        ),
        tooltip=[
            alt.Tooltip("month:T", title="Mes", format="%b %Y"),
            alt.Tooltip("savings_balance:Q", title="Ahorro", format=",.2f"),
        ],
    ).properties(height=330)
    negative_points = alt.Chart(savings_history).mark_point(size=95, color="#E45756", filled=True).transform_filter(
        alt.datum.savings_balance < 0
    ).encode(x="month:T", y="savings_balance:Q")
    zero_line = alt.Chart(pd.DataFrame({"zero": [0]})).mark_rule(
        color="#E45756", strokeDash=[6, 4], strokeWidth=1.5
    ).encode(y="zero:Q")
    st.altair_chart(savings_line + negative_points + zero_line, use_container_width=True)
    st.caption(
        f"Saldo real de partida: {money(result['initial_savings'])} en "
        f"{pd.Timestamp(result['savings_checkpoint_month']).strftime('%m/%Y')}. "
        "La simulación aplica únicamente los movimientos posteriores a ese mes. "
        "Cada punto muestra el saldo al cierre mensual; la reforma se paga al final de agosto de 2026."
    )
    if float(data["savings"].get("vacation_amount", 0.0)) > 0:
        st.info(
            "Vacaciones: se descontarán "
            f"{money(float(data['savings']['vacation_amount']))} en "
            f"{pd.Timestamp(data['savings']['vacation_month']).strftime('%m/%Y')}."
        )

    st.subheader("Evolución de las deudas")
    st.altair_chart(
        time_chart(
            family,
            ["john_deere_balance", "family_loan_balance"],
            {
                "john_deere_balance": "Deuda John Deere",
                "family_loan_balance": "Préstamo familiar",
            },
            ["#E45756", "#F2A541"],
        ),
        use_container_width=True,
    )


def personal_dashboard(frame: pd.DataFrame, key: str, label: str) -> None:
    expenses = pd.DataFrame(data[key]["expenses"])
    total_personal = float(expenses["monthly"].sum()) if not expenses.empty else 0.0
    if total_personal > 0:
        chart_data = expenses.groupby("concept", as_index=False)["monthly"].sum().sort_values("monthly", ascending=False)
        donut = alt.Chart(chart_data).mark_arc(innerRadius=70).encode(
            theta=alt.Theta("monthly:Q"), color=alt.Color("concept:N", title=None),
            order=alt.Order("monthly:Q", sort="descending"),
            tooltip=[
                alt.Tooltip("concept:N", title="Concepto"),
                alt.Tooltip("monthly:Q", title="Mensual", format=",.2f"),
            ],
        ).properties(height=330, title=f"Gastos personales de {label}")
        st.altair_chart(donut, use_container_width=True)
    st.subheader("Capacidad de ahorro")
    cashflow_chart = (
        alt.Chart(frame)
        .mark_line(point=alt.OverlayMarkDef(filled=True, size=75), strokeWidth=3, color="#168A57")
        .encode(
            x=alt.X("month:T", title=None, axis=alt.Axis(format="%b %Y")),
            y=alt.Y("cumulative_net:Q", title="Capacidad de ahorro acumulada (€)", scale=alt.Scale(zero=True)),
            tooltip=[
                alt.Tooltip("month:T", title="Mes", format="%b %Y"),
                alt.Tooltip("ordinary_salary:Q", title="Nómina ordinaria", format=",.2f"),
                alt.Tooltip("extra_personal_remainder:Q", title="Extra personal", format=",.2f"),
                alt.Tooltip("net:Q", title="Neto del mes", format=",.2f"),
                alt.Tooltip("cumulative_net:Q", title="Capacidad de ahorro", format=",.2f"),
            ],
        )
        .properties(height=340)
    )
    st.altair_chart(cashflow_chart, use_container_width=True)


with tabs[5]:
    if person_key == "member_a":
        st.divider()
        personal_dashboard(member_a, "member_a", member_a_label)

with tabs[4]:
    if person_key == "member_b":
        st.divider()
        personal_dashboard(member_b, "member_b", member_b_label)

with tabs[1]:
    with common_metrics:
        c1, c2, c3 = st.columns(3)
        financial_metric(c1, "Total común mensual", money(result["common_total"]))
        financial_metric(c2, f"Parte de {member_a_label}", money(result["member_a_common"]))
        financial_metric(c3, f"Parte de {member_b_label}", money(result["member_b_common"]))
    st.divider()
    common_chart_data = result["common"].copy()
    category_order = (
        common_chart_data.groupby("category")["monthly"]
        .sum()
        .sort_values(ascending=False)
        .index.tolist()
    )
    category_chart = alt.Chart(common_chart_data).mark_bar().encode(
        x=alt.X("monthly:Q", title="€ al mes", stack="zero"),
        y=alt.Y("category:N", title=None, sort=category_order),
        color=alt.Color("concept:N", title="Concepto", scale=alt.Scale(scheme="tableau20")),
        order=alt.Order("monthly:Q", sort="descending"),
        tooltip=[
            alt.Tooltip("category:N", title="Categoría"),
            alt.Tooltip("concept:N", title="Concepto"),
            alt.Tooltip("monthly:Q", title="Mensual", format=",.2f"),
        ],
    ).properties(height=360)
    st.altair_chart(category_chart, use_container_width=True)

with tabs[3]:
    reform_status = pd.DataFrame(data["reform"])
    reform_base_total = float(reform_status["base_amount"].sum())
    reform_vat_total = float(reform_status["vat_amount"].sum())
    reform_paid_total = float(reform_status["paid_amount"].sum())
    reform_pending_total = float(reform_status["pending_amount"].sum())
    reform_partida = reform_status["partida"].astype(str).str.casefold()
    energy_mask = reform_partida.str.contains("placas|aerotermia", regex=True)
    appliances_mask = reform_partida.str.contains("electrodomésticos|electrodomesticos", regex=True)
    kitchen_mask = reform_partida.str.contains("cocina", regex=False)
    energy_total = float(reform_status.loc[energy_mask, "total_amount"].sum())
    appliances_total = float(reform_status.loc[appliances_mask, "total_amount"].sum())
    kitchen_total = float(reform_status.loc[kitchen_mask, "total_amount"].sum())
    house_reform_total = float(
        reform_status.loc[~energy_mask & ~appliances_mask & ~kitchen_mask, "total_amount"].sum()
    )
    with reform_metrics:
        financial_breakdown_metric(
            st.container(),
            "Estado económico de la reforma",
            [
                ("Pagado", money(reform_paid_total), "positive"),
                ("Pendiente", money(reform_pending_total), "negative"),
                ("Total", money(result["reform_total"]), "neutral"),
            ],
        )
        st.write("")
        financial_breakdown_metric(
            st.container(),
            "Distribución del coste de la reforma",
            [
                ("Reforma y casa", money(house_reform_total), "neutral"),
                ("Cocina", money(kitchen_total), "neutral"),
                ("Electrodomésticos", money(appliances_total), "neutral"),
                ("Placas + aerotermia", money(energy_total), "neutral"),
            ],
        )
    st.divider()
    st.subheader("Pagado y pendiente por partida")
    reform_by_partida = reform_status.groupby("partida", as_index=False).agg(
        Pagado=("paid_amount", "sum"),
        Pendiente=("pending_amount", "sum"),
    )
    reform_payment_chart = alt.Chart(
        reform_by_partida.melt("partida", var_name="situacion", value_name="importe")
    ).mark_bar(cornerRadiusEnd=4).encode(
        x=alt.X("importe:Q", title="Importe (€)", stack="zero"),
        y=alt.Y("partida:N", title=None, sort="-x"),
        color=alt.Color(
            "situacion:N",
            title=None,
            scale=alt.Scale(domain=["Pagado", "Pendiente"], range=["#168A57", "#C63D3D"]),
        ),
        tooltip=[
            alt.Tooltip("partida:N", title="Partida"),
            alt.Tooltip("situacion:N", title="Situación"),
            alt.Tooltip("importe:Q", title="Importe", format=",.2f"),
        ],
    ).properties(height=max(340, len(reform_by_partida) * 42))
    st.altair_chart(reform_payment_chart, use_container_width=True)
    st.subheader("Conceptos de mayor coste")
    expensive_concepts = reform_status.nlargest(12, "total_amount")
    expensive_chart = alt.Chart(expensive_concepts).mark_bar(color="#B48A2C", cornerRadiusEnd=5).encode(
        x=alt.X("total_amount:Q", title="Coste real (€)"),
        y=alt.Y("description:N", title=None, sort="-x"),
        tooltip=[
            alt.Tooltip("partida:N", title="Partida"),
            alt.Tooltip("description:N", title="Concepto"),
            alt.Tooltip("base_amount:Q", title="Base", format=",.2f"),
            alt.Tooltip("vat_amount:Q", title="IVA", format=",.2f"),
            alt.Tooltip("total_amount:Q", title="Total", format=",.2f"),
        ],
    ).properties(height=max(380, len(expensive_concepts) * 32))
    st.altair_chart(expensive_chart, use_container_width=True)
    st.caption(f"Base acumulada: {money(reform_base_total)} · IVA acumulado: {money(reform_vat_total)}")

with tabs[2]:
    st.divider()
    c1, c2, c3 = st.columns(3)
    financial_metric(c1, "Coste de reforma", money(result["reform_total"]))
    financial_metric(c2, "Financiación prevista", money(result["funding_total"]), "positive")
    financial_metric(c3, "Diferencia de financiación", money(result["reform_gap"]), "negative" if result["reform_gap"] > 0 else "positive")
    st.subheader("Aportaciones extraordinarias para la reforma")
    e1, e2 = st.columns(2)
    financial_metric(e1, f"Aportado Extra {member_a_label}", money(float(data["savings"].get("member_a_extra", 0.0))), "positive")
    financial_metric(e2, f"Aportado Extra {member_b_label}", money(float(data["savings"].get("member_b_extra", 0.0))), "positive")
    st.altair_chart(time_chart(family, ["john_deere_balance", "family_loan_balance"], {"john_deere_balance":"John Deere", "family_loan_balance":"Préstamo familiar"}), use_container_width=True)


with st.sidebar:
    st.divider()
    if st.button("Guardar cambios", type="primary", use_container_width=True):
        try:
            save_data(client, data, db_context, person_key)
            st.success("Cambios sincronizados para ambos dispositivos")
        except Exception as exc:
            st.error(f"No se han podido guardar los cambios: {exc}")
    st.download_button(
        "Descargar Excel actualizado",
        data=export_excel(result),
        file_name="control_financiero_actualizado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    if st.button("Cerrar sesión", use_container_width=True):
        sign_out(client)
        for key in ("signed_email", "finance_data", "supabase"):
            st.session_state.pop(key, None)
        st.rerun()

st.session_state.finance_data = deepcopy(data)
