"""
POSCOPE Flask 서버
- index.html 서빙
- /api/* REST API로 SQLite(db.py) 영속화, 크롤러 트리거, Teams/Salesforce 연동
"""

import json
import os

from flask import Flask, jsonify, request, send_from_directory

import db
import teams
import salesforce
import crawler

BASE_DIR = os.path.dirname(__file__)
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

app = Flask(__name__, static_folder=None)


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/static_libs/<path:filename>")
def static_libs(filename):
    return send_from_directory(os.path.join(BASE_DIR, "static_libs"), filename)


@app.route("/api/projects", methods=["GET"])
def api_list_projects():
    div_filter = request.args.get("div")
    return jsonify(db.list_projects(div_filter=div_filter))


@app.route("/api/stats", methods=["GET"])
def api_stats():
    return jsonify(db.get_stats())


@app.route("/api/projects", methods=["POST"])
def api_add_manual_project():
    body = request.get_json(force=True) or {}
    title = (body.get("title") or "").strip()
    if not title:
        return jsonify({"error": "PJT명을 입력하세요."}), 400

    deadline = body.get("deadline") or ""
    new_id = db.insert_project({
        "title": title,
        "div": body.get("div", "steel"),
        "sub_business": body.get("subBusiness") or "",
        "kind": body.get("kind") or "PJT",
        "manager": body.get("manager") or "",
        "country": body.get("country") or "미정",
        "region": body.get("country") or "미정",
        "owner": body.get("owner") or "-",
        "steel": body.get("item") or "-",
        "tons": body.get("tons") or "-",
        "size": body.get("size") or "-",
        "deadline": deadline or "-",
        "urgency": body.get("urgency", False),
        "is_auto": False,
        "is_new": True,
        "source": "수동입력",
        "source_date": body.get("sourceDate") or "",
        "memo": body.get("memo") or "",
        "ai_summary": "수동 입력 PJT.",
    }, sf_history=[])
    db.add_upload_history("manual", title, 1)
    return jsonify(db.get_project(new_id)), 201


@app.route("/api/projects/import", methods=["POST"])
def api_import_projects():
    body = request.get_json(force=True) or {}
    rows = body.get("rows") or []
    filename = body.get("filename") or "엑셀 업로드"
    created = []
    for row in rows:
        title = (row.get("title") or "").strip()
        if not title:
            continue
        new_id = db.insert_project({
            "title": title,
            "div": "steel",
            "country": row.get("country") or "",
            "region": row.get("country") or "",
            "owner": row.get("owner") or "-",
            "steel": row.get("item") or "-",
            "tons": row.get("tons") or "-",
            "size": row.get("amount") or "-",
            "deadline": "",
            "urgency": False,
            "is_auto": False,
            "is_new": True,
            "source": "엑셀 업로드",
            "source_date": "",
            "ai_summary": "",
        }, sf_history=[])
        created.append(db.get_project(new_id))
    if created:
        db.add_upload_history("excel", filename, len(created))
    return jsonify({"created": created, "count": len(created)}), 201


@app.route("/api/projects/import-poscope", methods=["POST"])
def api_import_poscope():
    from datetime import datetime as dt
    body = request.get_json(force=True) or {}
    rows = body.get("rows") or []
    filename = body.get("filename") or "POSCOPE 성약현황"
    contracted, pursuing, created = 0, 0, []
    for row in rows:
        title = (row.get("title") or "").strip()
        if not title:
            continue
        status = row.get("status") or "검토중"
        source_label = row.get("sourceLabel") or "성약현황 엑셀"
        new_id = db.insert_project({
            "title": title,
            "div": "steel",
            "country": row.get("country") or "국내",
            "region": row.get("country") or "국내",
            "owner": row.get("owner") or "",
            "steel": row.get("item") or "",
            "tons": str(row.get("tons") or ""),
            "size": "",
            "deadline": "",
            "urgency": False,
            "is_auto": False,
            "is_new": True,
            "source": source_label,
            "source_date": dt.now().strftime("%Y-%m-%d"),
            "memo": row.get("memo") or "",
            "ai_summary": "",
            "status": status,
        }, sf_history=[])
        created.append(db.get_project(new_id))
        if status == "수주":
            contracted += 1
        else:
            pursuing += 1
    if created:
        db.add_upload_history("excel", filename, len(created))
    return jsonify({"created": created, "count": len(created), "contracted": contracted, "pursuing": pursuing}), 201


@app.route("/api/upload-history", methods=["GET"])
def api_upload_history():
    return jsonify(db.list_upload_history())


@app.route("/api/contractors", methods=["GET"])
def api_list_contractors():
    return jsonify(db.list_contractors())


@app.route("/api/contractors", methods=["POST"])
def api_upsert_contractor():
    body = request.get_json(force=True) or {}
    name = db.upsert_contractor(body)
    if not name:
        return jsonify({"error": "업체명을 입력하세요."}), 400
    return jsonify({"ok": True, "name": name}), 201


@app.route("/api/projects/<int:project_id>", methods=["PUT"])
def api_update_project(project_id):
    body = request.get_json(force=True) or {}
    updated = db.update_project(project_id, body)
    if not updated:
        return jsonify({"error": "프로젝트를 찾을 수 없습니다."}), 404
    return jsonify(updated)


@app.route("/api/projects/<int:project_id>", methods=["DELETE"])
def api_delete_project(project_id):
    if not db.get_project(project_id):
        return jsonify({"error": "프로젝트를 찾을 수 없습니다."}), 404
    db.delete_project(project_id)
    return jsonify({"ok": True})


@app.route("/api/projects/<int:project_id>/status", methods=["PATCH"])
def api_update_status(project_id):
    body = request.get_json(force=True) or {}
    status = (body.get("status") or "").strip()
    if not status:
        return jsonify({"error": "상태 값이 필요합니다."}), 400
    updated = db.update_project(project_id, {"status": status})
    if not updated:
        return jsonify({"error": "프로젝트를 찾을 수 없습니다."}), 404
    return jsonify(updated)


@app.route("/api/projects/<int:project_id>/progress", methods=["POST"])
def api_add_progress(project_id):
    body = request.get_json(force=True) or {}
    author = (body.get("author") or "").strip()
    note = (body.get("note") or "").strip()
    if not author or not note:
        return jsonify({"error": "담당자명과 업데이트 내용을 입력하세요."}), 400
    updated = db.add_progress_log(project_id, author, note, status=body.get("status"))
    if not updated:
        return jsonify({"error": "프로젝트를 찾을 수 없습니다."}), 404
    return jsonify(updated)


@app.route("/dept/<div_name>")
def dept_page(div_name):
    if div_name not in ["steel", "materials", "energy", "gas"]:
        return "Not found", 404
    return send_from_directory(BASE_DIR, "dept.html")


@app.route("/api/crawl", methods=["POST"])
def api_crawl():
    try:
        added, total_analyzed = crawler.collect_and_save()
        return jsonify({"added": added, "analyzed": total_analyzed})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/projects/<int:project_id>/teams-share", methods=["POST"])
def api_teams_share(project_id):
    project = db.get_project(project_id)
    if not project:
        return jsonify({"ok": False, "message": "프로젝트를 찾을 수 없습니다."}), 404
    config = load_config()
    ok, message = teams.send_teams_message(config.get("teams_webhook_url", ""), project)
    return jsonify({"ok": ok, "message": message})


@app.route("/api/projects/<int:project_id>/sf-history", methods=["GET"])
def api_sf_history(project_id):
    project = db.get_project(project_id)
    if not project:
        return jsonify({"ok": False, "message": "프로젝트를 찾을 수 없습니다."}), 404
    config = load_config()
    history, message = salesforce.get_sf_history(project.get("owner", ""), config)
    if history:
        merged = project["sfHistory"] + [h for h in history if h not in project["sfHistory"]]
        db.update_sf_history(project_id, merged)
        return jsonify({"ok": True, "sfHistory": merged, "message": message})
    return jsonify({"ok": False, "sfHistory": project["sfHistory"], "message": message})


if __name__ == "__main__":
    db.init_db()
    print("POSCOPE 서버 시작 - http://0.0.0.0:5000 (사내망에서 PC의 IP로 접속 가능)")
    app.run(host="0.0.0.0", port=5000, debug=False)
