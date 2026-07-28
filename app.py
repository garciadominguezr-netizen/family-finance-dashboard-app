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
      .block-container {padding-top: 1.3rem; padding-bottom: 3rem;}
      [data-testid="stMetric"] {background: color-mix(in srgb, var(--secondary-background-color) 88%, transparent); padding: 1rem; border-radius: .75rem;}
      h1, h2, h3 {letter-spacing: -0.02em;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.caption("Reforma, gastos personales, ahorro y deuda · periodo configurable")

with st.sidebar:
    st.caption(f"Sesión: {display_name}")
    if person_key == "member_a":
        st.code(db_context["invite_code"], language=None)
        st.caption("Código privado para que el segundo miembro se una una sola vez.")
    st.header("Escenario")
    data["scenario"]["include_march_bonus"] = st.toggle(
        "Incluir bonus de marzo",
        value=bool(data["scenario"]["include_march_bonus"]),
        help="Activa los importes potenciales introducidos por ambos miembros.",
    )
    data[person_key]["march_bonus"] = st.number_input(f"Bonus marzo · {display_name}", min_value=0.0, value=float(data[person_key]["march_bonus"]), step=100.0)
    data["savings"]["annual_interest"] = st.number_input(
        "Interés anual de la cuenta",
        min_value=0.0,
        max_value=0.20,
        value=float(data["savings"]["annual_interest"]),
        step=0.001,
        format="%.3f",
    )
    data["debt"]["family_monthly_repayment"] = st.number_input(
        "Devolución mensual préstamo familiar",
        min_value=0.0,
        value=float(data["debt"].get("family_monthly_repayment", 0.0)),
        step=50.0,
    )


def person_editor(key: str, label: str) -> None:
    person = data[key]
    st.subheader(f"Parámetros de {label}")
    c1, c2, c3, c4 = st.columns(4)
    person["salary"] = c1.number_input("Nómina ordinaria", min_value=0.0, value=float(person["salary"]), step=50.0, key=f"salary_{key}")
    person["extra_amount"] = c2.number_input("Importe paga extra", min_value=0.0, value=float(person["extra_amount"]), step=50.0, key=f"extra_{key}")
    person["extra_months"][0] = c3.number_input("Mes de extra 1", min_value=1, max_value=12, value=int(person["extra_months"][0]), key=f"extra_m1_{key}")
    person["extra_months"][1] = c4.number_input("Mes de extra 2", min_value=1, max_value=12, value=int(person["extra_months"][1]), key=f"extra_m2_{key}")
    edited = st.data_editor(
        pd.DataFrame(person["expenses"]),
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "concept": st.column_config.TextColumn("Concepto", required=True),
            "category": st.column_config.TextColumn("Categoría", required=True),
            "monthly": st.column_config.NumberColumn("Importe mensual", min_value=0.0, step=1.0, format="%.2f €"),
        },
        key=f"expenses_{key}",
        hide_index=True,
    )
    person["expenses"] = normalize_records(edited.to_dict("records"), ["monthly"])


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


member_a_label = next(label for key, label in AUTHORIZED_USERS.values() if key == "member_a")
member_b_label = next(label for key, label in AUTHORIZED_USERS.values() if key == "member_b")
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

with tabs[0]:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Cash flow familiar", money(float(family["cumulative_cash_flow"].iloc[-1])))
    m2.metric("Ahorro acumulado", money(float(family["savings_balance"].iloc[-1])))
    m3.metric("Deuda John Deere", money(float(family["john_deere_balance"].iloc[-1])))
    m4.metric("Préstamo familiar", money(float(family["family_loan_balance"].iloc[-1])))
    st.altair_chart(
        time_chart(family, ["cumulative_cash_flow", "savings_balance", "john_deere_balance"], {
            "cumulative_cash_flow": "Cash flow familiar", "savings_balance": "Ahorro", "john_deere_balance": "John Deere"
        }),
        use_container_width=True,
    )
    monthly = family[["month", "income", "cash_flow"]].melt("month", var_name="series", value_name="amount")
    monthly["series"] = monthly["series"].map({"income": "Ingresos", "cash_flow": "Cash flow mensual"})
    bars = alt.Chart(monthly).mark_bar().encode(
        x=alt.X("month:T", title=None, axis=alt.Axis(format="%b %Y")),
        y=alt.Y("amount:Q", title="€"),
        color=alt.Color("series:N", title=None),
        xOffset="series:N",
        tooltip=[alt.Tooltip("month:T", format="%b %Y"), "series:N", alt.Tooltip("amount:Q", format=",.2f")],
    ).properties(height=300)
    st.altair_chart(bars, use_container_width=True)


def personal_dashboard(frame: pd.DataFrame, key: str, label: str) -> None:
    expenses = pd.DataFrame(data[key]["expenses"])
    total_personal = float(expenses["monthly"].sum()) if not expenses.empty else 0.0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ingresos del periodo", money(float(frame["income"].sum())))
    c2.metric("Gasto común", money(float(frame["common"].sum() + frame["reform_adjustment"].sum())))
    c3.metric("Gasto personal", money(float(frame["personal"].sum())))
    c4.metric("Neto acumulado", money(float(frame["cumulative_net"].iloc[-1])))
    left, right = st.columns([1.1, 1])
    with left:
        st.altair_chart(time_chart(frame, ["net", "cumulative_net"], {"net": "Neto mensual", "cumulative_net": "Neto acumulado"}), use_container_width=True)
    with right:
        if total_personal > 0:
            chart_data = expenses.groupby("concept", as_index=False)["monthly"].sum()
            donut = alt.Chart(chart_data).mark_arc(innerRadius=70).encode(
                theta=alt.Theta("monthly:Q"), color=alt.Color("concept:N", title=None),
                tooltip=[alt.Tooltip("concept:N", title="Concepto"), alt.Tooltip("monthly:Q", title="Mensual", format=",.2f")]
            ).properties(height=330, title=f"Gastos personales de {label}")
            st.altair_chart(donut, use_container_width=True)
    display = frame.copy()
    display["month"] = display["month"].dt.strftime("%b %Y")
    st.dataframe(display.rename(columns={"month":"Mes","income":"Ingresos","common":"Comunes","reform_adjustment":"Reforma","personal":"Personales","net":"Neto mensual","cumulative_net":"Neto acumulado"}), use_container_width=True, hide_index=True)


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
    c3.metric("Ajuste desde cash flow", money(result["reform_gap"]))
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
