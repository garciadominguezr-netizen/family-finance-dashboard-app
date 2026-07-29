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

    itemized_reform_total = sum(float(item["amount"]) for item in data["reform"])
    reform_total = itemized_reform_total + float(data["savings"].get("reform_estimate_adjustment", 0.0))
    funding_total = sum(float(item["amount"]) for item in data["funding"])
    reform_gap = max(0.0, reform_total - funding_total)

    def person_frame(key: str, common_share: float) -> pd.DataFrame:
        person = data[key]
        personal_total = sum(float(item["monthly"]) for item in person["expenses"])
        rows = []
        for index, month in enumerate(periods):
            income = float(person["salary"])
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
        total_contribution = savings_monthly + float(extra_contribution)
        savings_balance = savings_balance * (1 + monthly_rate) + total_contribution
        if index == 0 and savings_checkpoint < month:
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

    return {
        "data": data,
        "member_a": member_a,
        "member_b": member_b,
        "family": family,
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
    return output.getvalue()
