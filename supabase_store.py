from __future__ import annotations

from copy import deepcopy
from typing import Any

from supabase import Client, create_client


def connect(url: str, key: str) -> Client:
    return create_client(url, key)


def sign_in(client: Client, email: str, password: str):
    return client.auth.sign_in_with_password({"email": email, "password": password})


def sign_up(client: Client, email: str, password: str):
    return client.auth.sign_up({"email": email, "password": password})


def sign_out(client: Client) -> None:
    client.auth.sign_out()


def current_user(client: Client):
    return client.auth.get_user().user


def membership(client: Client) -> dict[str, Any] | None:
    user = current_user(client)
    rows = client.table("household_members").select("household_id,display_name").eq("user_id", user.id).execute().data
    return rows[0] if rows else None


def create_household(client: Client, name: str, display_name: str) -> dict[str, Any]:
    rows = client.rpc("create_financial_household", {"household_name": name, "member_name": display_name}).execute().data
    return rows[0]


def join_household(client: Client, code: str, display_name: str) -> str:
    return client.rpc("join_financial_household", {"code": code, "member_name": display_name}).execute().data


def load_data(client: Client, defaults: dict[str, Any], person_key: str) -> tuple[dict[str, Any], dict[str, Any]]:
    user = current_user(client)
    member = membership(client)
    if not member:
        raise RuntimeError("El usuario todavía no pertenece a una familia.")
    household_id = member["household_id"]
    result = deepcopy(defaults)

    profile_rows = client.table("personal_profiles").select("*").eq("user_id", user.id).execute().data
    if profile_rows:
        p = profile_rows[0]
        result[person_key].update({
            "salary": float(p["salary"]), "extra_amount": float(p["extra_amount"]),
            "extra_months": [int(p["extra_month_1"]), int(p["extra_month_2"])],
            "march_bonus": float(p["march_bonus"]),
        })

    expenses = client.table("expenses").select("id,concept,category,monthly_amount,scope,owner_share").eq("household_id", household_id).execute().data
    result[person_key]["expenses"] = [
        {"id": x["id"], "concept": x["concept"], "category": x["category"], "monthly": float(x["monthly_amount"])}
        for x in expenses if x["scope"] == "personal" and x.get("id")
    ]
    result["common_expenses"] = [
        {"id": x["id"], "concept": x["concept"], "category": x["category"], "monthly": float(x["monthly_amount"]), "member_a_share": float(x["owner_share"])}
        for x in expenses if x["scope"] == "common"
    ] or result["common_expenses"]

    config = client.table("shared_config").select("*").eq("household_id", household_id).single().execute().data
    if config:
        result["period"] = {"start": config["period_start"], "months": int(config["period_months"])}
        for key in ("reform", "funding", "debt", "savings"):
            result[key] = config[key]

    summaries = client.rpc("get_household_member_summaries", {"target_household": household_id}).execute().data
    other_key = "member_b" if person_key == "member_a" else "member_a"
    other = next((x for x in summaries if x["user_id"] != user.id), None)
    if other:
        ordinary = float(other["ordinary_available"])
        extra_available = float(other["extra_available"])
        result[other_key].update({
            "salary": ordinary,
            "extra_amount": max(0.0, extra_available - ordinary),
            "extra_months": [int(other["extra_month_1"]), int(other["extra_month_2"])],
            "march_bonus": max(0.0, float(other["march_bonus_available"]) - ordinary),
            "expenses": [],
        })
    household = client.table("households").select("name,invite_code").eq("id", household_id).single().execute().data
    return result, {
        "household_id": household_id, "display_name": member["display_name"], "user_id": user.id,
        "household_name": household["name"], "invite_code": household["invite_code"],
    }


def _replace_expenses(client: Client, household_id: str, user_id: str, scope: str, records: list[dict], owner_key: str) -> None:
    existing = client.table("expenses").select("id").eq("household_id", household_id).eq("scope", scope)
    if scope == "personal":
        existing = existing.eq("owner_id", user_id)
    old_ids = {x["id"] for x in existing.execute().data}
    kept = set()
    for row in records:
        payload = {
            "household_id": household_id, "owner_id": user_id, "scope": scope,
            "visibility": "private" if scope == "personal" else "shared",
            "concept": row["concept"], "category": row["category"],
            "monthly_amount": float(row["monthly"]), "owner_share": float(row.get(owner_key, .5)), "active": True,
        }
        row_id = row.get("id")
        if row_id in old_ids:
            client.table("expenses").update(payload).eq("id", row_id).execute(); kept.add(row_id)
        else:
            inserted = client.table("expenses").insert(payload).execute().data
            if inserted: kept.add(inserted[0]["id"])
    for row_id in old_ids - kept:
        client.table("expenses").delete().eq("id", row_id).execute()


def save_data(client: Client, data: dict[str, Any], context: dict[str, Any], person_key: str) -> None:
    hid, uid = context["household_id"], context["user_id"]
    person = data[person_key]
    client.table("personal_profiles").update({
        "salary": person["salary"], "extra_amount": person["extra_amount"],
        "extra_month_1": person["extra_months"][0], "extra_month_2": person["extra_months"][1],
        "march_bonus": person.get("march_bonus", 0),
    }).eq("user_id", uid).execute()
    _replace_expenses(client, hid, uid, "personal", person["expenses"], "owner_share")
    _replace_expenses(client, hid, uid, "common", data["common_expenses"], "member_a_share")
    client.table("shared_config").update({
        "period_start": data["period"]["start"], "period_months": data["period"]["months"],
        "reform": data["reform"], "funding": data["funding"], "debt": data["debt"],
        "savings": data["savings"], "updated_by": uid,
    }).eq("household_id", hid).execute()
