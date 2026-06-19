"""
POSCOPE Salesforce 연동
OAuth2 Username-Password flow + SOQL REST 조회로 거래선 미팅 이력을 가져온다.

config.json의 "salesforce" 항목에 아래 값을 채우면 동작한다:
  instance_url, client_id, client_secret, username, password, security_token
  (history_objects/what_name_field/date_field/owner_field/memo_field/subject_field/api_version은
   조직의 실제 객체·필드 구조에 맞춰 조정)

표준 Task/Event 객체는 거래선(Account)에 직접 연결된 필드가 없고, 둘 다 What이라는
polymorphic lookup으로 Account/Opportunity 등을 가리킨다. 그래서 기본값은
Account.Name이 아니라 What.Name이며, Task와 Event를 모두 조회해 병합한다.

자격증명이 비어 있으면 빈 리스트를 반환하여 화면에는 영향이 없도록 한다.
"""

import json
import urllib.parse
import urllib.request
from urllib.error import URLError, HTTPError

DEFAULTS = {
    "api_version": "v59.0",
    "history_objects": ["Task", "Event"],
    "what_name_field": "What.Name",
    "date_field": "ActivityDate",
    "owner_field": "Owner.Name",
    "memo_field": "Description",
    "subject_field": "Subject",
}

REQUIRED_FIELDS = ["instance_url", "client_id", "client_secret", "username", "password"]


def _is_configured(sf_cfg):
    return all(sf_cfg.get(f) for f in REQUIRED_FIELDS)


def _get_token(sf_cfg):
    payload = urllib.parse.urlencode({
        "grant_type": "password",
        "client_id": sf_cfg["client_id"],
        "client_secret": sf_cfg["client_secret"],
        "username": sf_cfg["username"],
        "password": sf_cfg["password"] + sf_cfg.get("security_token", ""),
    }).encode("utf-8")
    req = urllib.request.Request(
        sf_cfg["instance_url"].rstrip("/") + "/services/oauth2/token",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return data["access_token"], data["instance_url"]


def _dig(record, dotted_field):
    cur = record
    for part in dotted_field.split("."):
        if cur is None:
            return None
        cur = cur.get(part)
    return cur


def _query_object(instance_url, access_token, sf_obj, company_name, sf_cfg):
    escaped_name = company_name.replace("'", "\\'")
    fields = [sf_cfg["date_field"], sf_cfg["owner_field"], sf_cfg["memo_field"], sf_cfg["subject_field"]]
    soql = (
        f"SELECT {', '.join(fields)} FROM {sf_obj} "
        f"WHERE {sf_cfg['what_name_field']} = '{escaped_name}' "
        f"ORDER BY {sf_cfg['date_field']} DESC LIMIT 10"
    )
    query_url = (
        f"{instance_url}/services/data/{sf_cfg['api_version']}/query/"
        f"?q={urllib.parse.quote(soql)}"
    )
    req = urllib.request.Request(
        query_url, headers={"Authorization": f"Bearer {access_token}"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())

    history = []
    for rec in data.get("records", []):
        memo = _dig(rec, sf_cfg["memo_field"]) or _dig(rec, sf_cfg["subject_field"]) or ""
        history.append({
            "date": _dig(rec, sf_cfg["date_field"]) or "",
            "who": _dig(rec, sf_cfg["owner_field"]) or "",
            "memo": memo,
        })
    return history


def get_sf_history(company_name, config):
    sf_cfg = {**DEFAULTS, **(config.get("salesforce") or {})}
    if not _is_configured(sf_cfg):
        return [], "Salesforce 설정이 비어 있습니다. config.json의 salesforce 항목을 입력하세요."
    if not company_name:
        return [], "회사명이 없어 조회할 수 없습니다."

    try:
        access_token, instance_url = _get_token(sf_cfg)

        history = []
        errors = []
        for sf_obj in sf_cfg.get("history_objects", ["Task", "Event"]):
            try:
                history.extend(_query_object(instance_url, access_token, sf_obj, company_name, sf_cfg))
            except (HTTPError, URLError) as e:
                errors.append(f"{sf_obj}: {e}")

        history.sort(key=lambda h: h.get("date") or "", reverse=True)
        history = history[:10]

        if not history and errors:
            return [], f"Salesforce 조회 실패: {'; '.join(errors)}"
        return history, "ok"
    except HTTPError as e:
        return [], f"Salesforce API 오류: {e.code} {e.reason}"
    except URLError as e:
        return [], f"Salesforce 연결 실패: {e}"
    except Exception as e:
        return [], f"Salesforce 조회 실패: {e}"
