"""
POSCOPE Teams 연동
MS Teams Incoming Webhook으로 프로젝트 카드 전송
"""

import json
import urllib.request
from urllib.error import URLError


def send_teams_message(webhook_url, project):
    if not webhook_url:
        return False, "Teams Webhook이 설정되지 않았습니다. config.json의 teams_webhook_url을 입력하세요."

    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "003087",
        "summary": project.get("title", "POSCOPE 알림"),
        "title": f"🔭 POSCOPE — {project.get('title', '')}",
        "sections": [
            {
                "facts": [
                    {"name": "국가", "value": project.get("region") or project.get("country") or "-"},
                    {"name": "발주처", "value": project.get("owner") or "-"},
                    {"name": "강재 품목", "value": project.get("steel") or "-"},
                    {"name": "예상 물량", "value": project.get("tons") or "-"},
                    {"name": "마감일", "value": project.get("deadline") or "-"},
                ],
                "text": project.get("aiSummary") or "",
            }
        ],
    }

    payload = json.dumps(card).encode("utf-8")
    req = urllib.request.Request(
        webhook_url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True, "Teams 채널에 공유되었습니다."
    except URLError as e:
        return False, f"Teams 전송 실패: {e}"
