from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from typing import Any

import pandas as pd


def money(value: float) -> str:
    return f"{value:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def normalize_records(records: list[dict[str, Any]], numeric: list[str]) -> list[dict[str, Any]]:
    clean = []
    for record in records:
        row = dict(record)
        for key in numeric:
            value = pd.to_numeric(row.get(key, 0), errors="coerce")
            row[key] = 0.0 if pd.isna(value) else float(value)
        clean.append(row)
    return clean


def mortgage_schedule(debt: dict[str, Any]) -> pd.DataFrame:
    initial = float(debt.get("mortgage_initial_principal", 460000.0))
    current = float(debt.get("mortgage_current_balance", initial))
    total_months = int(debt.get("mortgage_term_months", 360))
    actual_payments = int(debt.get("mortgage_actual_payments", 2))
    first_months = int(debt.get("mortgage_first_fixed_months", 6))
    second_months = int(debt.get("mortgage_second_fixed_months", 54))
    first_rate = float(debt.get("mortgage_first_fixed_rate", 1.4))
    second_rate = float(debt.get("mortgage_second_fixed_rate", 2.3))
    variable_rate = max(
        0.0,
        float(debt.get("mortgage_euribor_assumption", 2.0))
        + float(debt.get("mortgage_variable_spread", 1.35)),
    )
    first_payment = float(debt.get("mortgage_payment_first_period", 1565.84))
    start = pd.Timestamp(debt.get("mortgage_start", "2026-05-13")).replace(day=1)
    payment_dates = pd.date_range(
        pd.Timestamp(debt.get("mortgage_first_payment", "2026-06-01")).replace(day=1),
        periods=total_months,
        freq="MS",
    )

    def annuity(balance: float, annual_rate: float, periods_left: int) -> float:
        monthly_rate = annual_rate / 1200
        if periods_left <= 0:
            return balance
        if monthly_rate == 0:
            return balance / periods_left
        return balance * monthly_rate / (1 - (1 + monthly_rate) ** (-periods_left))

    rows = [{
        "month": start,
        "opening_balance": initial,
        "payment": 0.0,
        "interest": 0.0,
        "principal": 0.0,
        "balance": initial,
        "annual_rate": first_rate,
        "phase": "Apertura",
    }]
    balance = initial
    payment = first_payment
    for number, month in enumerate(payment_dates, 1):
        if number <= first_months:
            rate, phase = first_rate, "Fijo inicial"
        elif number <= first_months + second_months:
            rate, phase = second_rate, "Fijo segundo tramo"
        else:
            rate, phase = variable_rate, "Variable estimado"
        if number in (first_months + 1, first_months + second_months + 1):
            payment = annuity(balance, rate, total_months - number + 1)
        opening = balance
        interest = opening * rate / 1200
        principal = max(0.0, payment - interest)
        closing = max(0.0, opening - principal)
        if number == actual_payments:
            closing = current
            principal = max(0.0, opening - closing)
            interest = max(0.0, payment - principal)
        if principal > opening:
            principal = opening
            payment = principal + interest
            closing = 0.0
        balance = closing
        rows.append({
            "month": month,
            "opening_balance": opening,
            "payment": payment,
            "interest": interest,
            "principal": principal,
            "balance": closing,
            "annual_rate": rate,
            "phase": phase,
        })
    return pd.DataFrame(rows)


def calculate(data: dict[str, Any]) -> dict[str, Any]:
    data = deepcopy(data)
    start = pd.Timestamp(data["period"]["start"])
    periods = pd.date_range(start=start, periods=int(data["period"]["months"]), freq="MS")

    common = pd.DataFrame(data["common_expenses"])
    common["monthly"] = pd.to_numeric(common["monthly"], errors="coerce").fillna(0.0)
    common["member_a_share"] = pd.to_numeric(common["member_a_share"], errors="coerce").fillna(0.5)
    common_total = float(common["monthly"].sum())
    member_a_common = float((common["monthly"] * common["member_a_share"]).sum())
    member_b_common = common_total - member_a_common
    savings_monthly = float(common.loc[common["category"] == "Ahorro", "monthly"].sum())

    itemized_reform_total = sum(
        float(item.get("total_amount", item.get("amount", 0.0)))
        for item in data["reform"]
    )
    reform_total = itemized_reform_total + float(data["savings"].get("reform_estimate_adjustment", 0.0))
    funding_total = sum(float(item["amount"]) for item in data["funding"])
    reform_gap = max(0.0, reform_total - funding_total)

    def person_frame(key: str, common_share: float) -> pd.DataFrame:
        person = data[key]
        personal_total = sum(float(item["monthly"]) for item in person["expenses"])
        projected_salary = float(person["salary"])
        january_raise_pct = float(person.get("january_raise_pct", 0.0))
        rows = []
        for index, month in enumerate(periods):
            if month.month == 1 and month > start:
                projected_salary *= 1 + january_raise_pct / 100
            income = projected_salary
            extra_income = 0.0
            extra_to_savings = 0.0
            if month.month in [int(x) for x in person["extra_months"]]:
                extra_income = float(person["extra_amount"])
                income += extra_income
                configured_contribution = float(
                    data["savings"].get(f"{key}_extra_pay_contribution", 0.0)
                )
                extra_to_savings = min(extra_income, configured_contribution)
            if data["scenario"]["include_march_bonus"] and month.month == 3:
                income += float(person.get("march_bonus", 0.0))
            reform_adjustment = reform_gap / 2 if index == 0 else 0.0
            net = income - common_share - reform_adjustment - personal_total - extra_to_savings
            rows.append({
                "month": month,
                "ordinary_salary": projected_salary,
                "income": income,
                "extra_income": extra_income,
                "extra_to_savings": extra_to_savings,
                "extra_personal_remainder": extra_income - extra_to_savings,
                "common": common_share,
                "reform_adjustment": reform_adjustment,
                "personal": personal_total,
                "net": net,
            })
        frame = pd.DataFrame(rows)
        frame["cumulative_net"] = frame["net"].cumsum()
        return frame

    member_a = person_frame("member_a", member_a_common)
    member_b = person_frame("member_b", member_b_common)

    family = pd.DataFrame({
        "month": periods,
        "income": member_a["income"] + member_b["income"],
        "common": common_total,
        "member_a_personal": member_a["personal"],
        "member_b_personal": member_b["personal"],
        "cash_flow": member_a["net"] + member_b["net"],
        "extra_to_savings": member_a["extra_to_savings"] + member_b["extra_to_savings"],
    })

    family_payment = float(data["debt"].get("family_monthly_repayment", 0.0))
    family_debt = float(data["debt"]["family_loan"])
    family_debt_values = []
    adjusted_cash = []
    for cash in family["cash_flow"]:
        payment = min(family_payment, family_debt, max(0.0, float(cash)))
        family_debt -= payment
        family_debt_values.append(family_debt)
        adjusted_cash.append(float(cash) - payment)
    family["family_loan_balance"] = family_debt_values
    family["cash_flow"] = adjusted_cash
    family["cumulative_cash_flow"] = family["cash_flow"].cumsum()

    savings_config = data["savings"]
    base_savings = float(savings_config.get("base_balance", savings_config.get("initial_balance", 0.0)))
    member_a_extra = float(savings_config.get("member_a_extra", 0.0))
    member_b_extra = float(savings_config.get("member_b_extra", 0.0))
    legacy_initial_savings = base_savings + member_a_extra + member_b_extra
    initial_savings = float(savings_config.get("actual_savings_amount", legacy_initial_savings))
    savings_checkpoint = pd.Timestamp(
        savings_config.get("actual_savings_month", periods[0] - pd.offsets.MonthBegin(1))
    ).replace(day=1)
    monthly_rate = (1 + float(savings_config["annual_interest"])) ** (1 / 12) - 1
    savings_balance = initial_savings
    savings_values = []
    savings_contributions = []
    vacation_amount = float(savings_config.get("vacation_amount", 0.0))
    vacation_month = pd.Timestamp(savings_config.get("vacation_month", periods[-1])).strftime("%Y-%m")
    reform_payment_month = pd.Timestamp(
        savings_config.get("reform_payment_month", periods[0])
    ).strftime("%Y-%m")
    march_extra_contribution = float(savings_config.get("march_extra_contribution", 0.0))
    vacation_outflows = []
    for index, (month, extra_contribution) in enumerate(zip(periods, family["extra_to_savings"])):
        if month < savings_checkpoint:
            savings_values.append(float("nan"))
            savings_contributions.append(0.0)
            vacation_outflows.append(0.0)
            continue
        if month == savings_checkpoint:
            savings_values.append(savings_balance)
            savings_contributions.append(0.0)
            vacation_outflows.append(0.0)
            continue
        march_contribution = (
            march_extra_contribution
            if data["scenario"]["include_march_bonus"] and month.month == 3
            else 0.0
        )
        total_contribution = savings_monthly + float(extra_contribution) + march_contribution
        savings_balance = savings_balance * (1 + monthly_rate) + total_contribution
        if month.strftime("%Y-%m") == reform_payment_month and savings_checkpoint < month:
            savings_balance -= reform_total
        vacation_outflow = vacation_amount if month.strftime("%Y-%m") == vacation_month else 0.0
        savings_balance -= vacation_outflow
        savings_values.append(savings_balance)
        savings_contributions.append(total_contribution)
        vacation_outflows.append(vacation_outflow)
    family["savings_contribution"] = savings_contributions
    family["vacation_outflow"] = vacation_outflows
    family["savings_balance"] = savings_values

    jd_principal = float(data["debt"]["john_deere_principal"])
    jd_months = max(1, int(data["debt"]["john_deere_months"]))
    jd_payment = jd_principal / jd_months
    balance = jd_principal
    jd_balances, jd_payments = [], []
    for _ in periods:
        payment = min(jd_payment, balance)
        balance = max(0.0, balance - payment)
        jd_payments.append(payment)
        jd_balances.append(balance)
    family["john_deere_payment"] = jd_payments
    family["john_deere_balance"] = jd_balances
    mortgage = mortgage_schedule(data["debt"])

    return {
        "data": data,
        "member_a": member_a,
        "member_b": member_b,
        "family": family,
        "mortgage": mortgage,
        "common": common,
        "common_total": common_total,
        "member_a_common": member_a_common,
        "member_b_common": member_b_common,
        "savings_monthly": savings_monthly,
        "initial_savings": initial_savings,
        "savings_checkpoint_month": savings_checkpoint,
        "reform_total": reform_total,
        "itemized_reform_total": itemized_reform_total,
        "funding_total": funding_total,
        "reform_gap": reform_gap,
    }


def export_excel(result: dict[str, Any]) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        result["member_a"].to_excel(writer, sheet_name="Miembro A", index=False)
        result["member_b"].to_excel(writer, sheet_name="Miembro B", index=False)
        result["family"].drop(
            columns=["cash_flow", "cumulative_cash_flow"], errors="ignore"
        ).to_excel(writer, sheet_name="Evolución familiar", index=False)
        result["common"].to_excel(writer, sheet_name="Gastos comunes", index=False)
        pd.DataFrame(result["data"]["reform"]).to_excel(writer, sheet_name="Reforma", index=False)
        pd.DataFrame(result["data"]["funding"]).to_excel(writer, sheet_name="Financiación", index=False)
        result["mortgage"].to_excel(writer, sheet_name="Hipoteca", index=False)
    return output.getvalue()
