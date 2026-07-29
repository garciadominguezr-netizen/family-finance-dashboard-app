from __future__ import annotations

import json
from copy import deepcopy

import altair as alt
import pandas as pd
import streamlit as st

from model import calculate, export_excel, money, normalize_records
from supabase_store import connect, create_household, join_household, load_data, save_data, sign_in, sign_out, sign_up


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

st.title(FAMILY_NAME)
st.markdown(
    """
    <style>
      :root {--ra-gold:#B48A2C;--ra-gold-dark:#896719;--ra-gold-soft:#F7F0DF;--ra-ink:#28241D;}
      .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {background:#FFFFFF;color:var(--ra-ink);}
      [data-testid="stSidebar"], [data-testid="stSidebar"] > div {background:#FCF9F2;}
      [data-testid="stSidebar"] {border-right:1px solid #E6D4A7;}
      h1,h2,h3,p,label,[data-testid="stCaptionContainer"] {color:var(--ra-ink);}
      h1 {color:var(--ra-gold-dark);}
      [data-baseweb="input"], [data-baseweb="input"] > div, [data-baseweb="base-input"],
      [data-baseweb="select"] > div, [data-baseweb="textarea"], [data-baseweb="textarea"] > div {
        background:#FFFFFF !important;border-color:#DCC587;color:var(--ra-ink);
      }
      input, textarea {background:#FFFFFF !important;color:var(--ra-ink) !important;}
      [data-testid="stForm"] {background:#FFFFFF;border-color:#E2CC94;}
      .stButton > button[kind="primary"], .stFormSubmitButton > button {
        background:var(--ra-gold);border-color:var(--ra-gold);color:#FFFFFF;
      }
      .stButton > button[kind="primary"]:hover, .stFormSubmitButton > button:hover {
        background:var(--ra-gold-dark);border-color:var(--ra-gold-dark);color:#FFFFFF;
      }
      [data-baseweb="radio"] div[aria-checked="true"] {background-color:var(--ra-gold);}
    </style>
    """,
    unsafe_allow_html=True,
)
if "signed_email" not in st.session_state:
    st.subheader("Acceso privado")
    mode = st.radio("", ["Iniciar sesión", "Crear mi contraseña"], horizontal=True, label_visibility="collapsed")
    with st.form("auth_form"):
        email = st.text_input("Correo electrónico").strip().lower()
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button(mode, type="primary", use_container_width=True)
    if submitted:
        if email not in AUTHORIZED_USERS:
            st.error("Este correo no está autorizado para esta familia.")
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
      }
      .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background: #FFFFFF;
        color: var(--ra-ink);
      }
      .block-container {padding-top: 1.3rem; padding-bottom: 3rem;}
      [data-testid="stSidebar"] {background: #FCF9F2; border-right: 1px solid #E6D4A7;}
      [data-testid="stSidebar"] > div {background: #FCF9F2;}
      h1, h2, h3 {letter-spacing: -0.02em; color: var(--ra-ink);}
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
      .stTabs [data-baseweb="tab-list"] {gap: .35rem; border-bottom: 1px solid #E6D4A7;}
      .stTabs [data-baseweb="tab"] {color: #64583F; border-radius: .55rem .55rem 0 0; padding-left: 1rem; padding-right: 1rem;}
      .stTabs [aria-selected="true"] {background: var(--ra-gold-soft); color: var(--ra-gold-dark); font-weight: 700;}
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
      [data-testid="stDataFrame"] {border: 1px solid #E2CC94; border-radius: .65rem; overflow: hidden;}
      hr {border-color: #E6D4A7;}
      a {color: var(--ra-gold-dark);}
    </style>
    """,
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
        k1.metric("Nómina mensual", money(float(person["salary"])))
        k2.metric("Gasto común mensual", money(common_monthly))
        k3.metric("Gastos personales mensuales", money(personal_monthly))
        k4.metric("Neto restante mensual", money(ordinary_net))


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


tabs = st.tabs(["Resumen familiar", member_a_label, member_b_label, "Gastos comunes", "Reforma y deudas"])

with tabs[1]:
    if person_key == "member_a":
        person_editor("member_a", member_a_label)
    else:
        st.info(f"Los gastos personales de {member_a_label} son privados. Solo se incorpora su aportación neta al cálculo familiar.")

with tabs[2]:
    if person_key == "member_b":
        person_editor("member_b", member_b_label)
    else:
        st.info(f"Los gastos personales de {member_b_label} son privados. Solo se incorpora su aportación neta al cálculo familiar.")

with tabs[3]:
    st.subheader("Gastos comunes")
    common_df = pd.DataFrame(data["common_expenses"])
    common_edited = st.data_editor(
        common_df,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
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

with tabs[4]:
    st.subheader("Presupuesto de reforma")
    reform_edited = st.data_editor(
        pd.DataFrame(data["reform"]), use_container_width=True, num_rows="dynamic", hide_index=True,
        column_config={
            "concept": st.column_config.TextColumn("Partida", required=True),
            "status": st.column_config.SelectboxColumn("Estado", options=["Presupuesto", "Estimación", "Pagado"]),
            "amount": st.column_config.NumberColumn("Importe", min_value=0.0, step=50.0, format="%.2f €"),
        }, key="reform_editor"
    )
    data["reform"] = normalize_records(reform_edited.to_dict("records"), ["amount"])
    st.caption(
        "El estimado general incluye además un ajuste no desglosado de "
        f"{money(float(data['savings'].get('reform_estimate_adjustment', 0.0)))}. "
        "Cada nueva partida se suma automáticamente al total."
    )
    if st.button("Guardar presupuesto de reforma", type="primary", use_container_width=True):
        try:
            save_data(client, data, db_context, person_key)
            st.session_state.finance_data = deepcopy(data)
            st.success("Presupuesto guardado y verificado en la base de datos.")
        except Exception as exc:
            st.error(f"No se ha podido guardar el presupuesto: {exc}")
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
    s1.metric("Ahorro familiar", money(float(current_status["savings_balance"])))
    s2.metric("Gasto estimado reforma", money(float(result["reform_total"])))
    d1, d2 = st.columns(2)
    d1.metric("Deuda John Deere", money(float(current_status["john_deere_balance"])))
    d2.metric("Préstamo familiar", money(float(current_status["family_loan_balance"])))

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
    st.subheader("Neto personal disponible mes a mes")
    cashflow_chart = (
        alt.Chart(frame)
        .mark_line(point=alt.OverlayMarkDef(filled=True, size=75), strokeWidth=3, color="#B48A2C")
        .encode(
            x=alt.X("month:T", title=None, axis=alt.Axis(format="%b %Y")),
            y=alt.Y("net:Q", title="Neto disponible (€)", scale=alt.Scale(zero=False)),
            tooltip=[
                alt.Tooltip("month:T", title="Mes", format="%b %Y"),
                alt.Tooltip("ordinary_salary:Q", title="Nómina ordinaria", format=",.2f"),
                alt.Tooltip("extra_personal_remainder:Q", title="Extra personal", format=",.2f"),
                alt.Tooltip("net:Q", title="Neto disponible", format=",.2f"),
            ],
        )
        .properties(height=340)
    )
    st.altair_chart(cashflow_chart, use_container_width=True)


with tabs[1]:
    if person_key == "member_a":
        st.divider()
        personal_dashboard(member_a, "member_a", member_a_label)

with tabs[2]:
    if person_key == "member_b":
        st.divider()
        personal_dashboard(member_b, "member_b", member_b_label)

with tabs[3]:
    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.metric("Total común mensual", money(result["common_total"]))
    c2.metric(f"Parte de {member_a_label}", money(result["member_a_common"]))
    c3.metric(f"Parte de {member_b_label}", money(result["member_b_common"]))
    category = result["common"].groupby("category", as_index=False)["monthly"].sum()
    category_chart = alt.Chart(category).mark_bar().encode(
        x=alt.X("monthly:Q", title="€ al mes"), y=alt.Y("category:N", title=None, sort="-x"),
        tooltip=[alt.Tooltip("category:N", title="Categoría"), alt.Tooltip("monthly:Q", title="Mensual", format=",.2f")]
    ).properties(height=360)
    st.altair_chart(category_chart, use_container_width=True)

with tabs[4]:
    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.metric("Coste de reforma", money(result["reform_total"]))
    c2.metric("Financiación prevista", money(result["funding_total"]))
    c3.metric("Diferencia de financiación", money(result["reform_gap"]))
    st.subheader("Aportaciones extraordinarias para la reforma")
    e1, e2 = st.columns(2)
    e1.metric(f"Aportado Extra {member_a_label}", money(float(data["savings"].get("member_a_extra", 0.0))))
    e2.metric(f"Aportado Extra {member_b_label}", money(float(data["savings"].get("member_b_extra", 0.0))))
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
