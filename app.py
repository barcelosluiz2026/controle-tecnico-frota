import csv
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Text

BASE_DIR = Path(__file__).resolve().parent

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")


def build_database_uri() -> str:
    database_url = os.getenv("DATABASE_URL", "").strip()

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    if database_url:
        if "sslmode=" not in database_url:
            separator = "&" if "?" in database_url else "?"
            database_url = f"{database_url}{separator}sslmode=require"
        return database_url

    return f"sqlite:///{BASE_DIR / 'app.db'}"


app.config["SQLALCHEMY_DATABASE_URI"] = build_database_uri()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JSON_SORT_KEYS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}


db = SQLAlchemy(app)


class Record(db.Model):
    __tablename__ = "records"

    id = db.Column(db.String(120), primary_key=True)
    record_type = db.Column(db.String(50), nullable=True, index=True)
    data = db.Column(Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self) -> dict:
        payload = json.loads(self.data)
        if not isinstance(payload, dict):
            raise ValueError("Stored record is not a JSON object")
        if "id" not in payload:
            payload["id"] = self.id
        if "type" not in payload and self.record_type:
            payload["type"] = self.record_type
        return payload


class AccessLog(db.Model):
    __tablename__ = "access_logs"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), nullable=False, index=True)
    action = db.Column(db.String(50), nullable=False, index=True)
    result = db.Column(db.String(30), nullable=False, index=True)
    source = db.Column(db.String(50), nullable=False, default="panes")
    ip_address = db.Column(db.String(120), nullable=True)
    user_agent = db.Column(Text, nullable=True)
    details = db.Column(Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "action": self.action,
            "result": self.result,
            "source": self.source,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "details": self.details,
            "created_at": self.created_at.astimezone(timezone.utc).isoformat() if self.created_at else None,
        }


with app.app_context():
    db.create_all()


def parse_iso_datetime(value):
    if not value:
        return None

    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_tipo(value: str) -> str:
    text = str(value or "").strip().lower()
    if text in {"avionico", "aviônico"}:
        return "avionico"
    if text == "mecânico":
        return "mecanico"
    return text


def pane_status_aberta(status: str) -> bool:
    return normalize_tipo(status) != "finalizada" and str(status or "").strip().lower() != "finalizada"


def montar_ranking_panes(tipo: str | None = None, limit: int = 10):
    records = Record.query.order_by(Record.created_at.asc(), Record.id.asc()).all()

    aeronaves = {}
    panes = []

    for record in records:
        try:
            payload = record.to_dict()
        except Exception:
            continue

        record_type = str(payload.get("type") or record.record_type or "").strip().lower()

        if record_type == "aeronave":
            aeronaves[str(payload.get("id", "")).strip()] = payload
            continue

        if record_type != "pane":
            continue

        pane_tipo = normalize_tipo(payload.get("paneTipo"))
        pane_status = str(payload.get("paneStatus", "")).strip()

        if tipo and pane_tipo != normalize_tipo(tipo):
            continue

        if not pane_status_aberta(pane_status):
            continue

        criado_em = parse_iso_datetime(payload.get("criadoEm")) or record.created_at
        if not criado_em:
            continue

        agora = datetime.now(timezone.utc)
        delta = agora - criado_em
        horas = round(delta.total_seconds() / 3600, 1)
        dias = round(delta.total_seconds() / 86400, 1)

        aeronave_id = str(payload.get("aeronaveId", "")).strip()
        aeronave = aeronaves.get(aeronave_id, {})

        panes.append(
            {
                "id": str(payload.get("id", "")).strip(),
                "aeronaveId": aeronave_id,
                "prefixo": aeronave.get("prefixo"),
                "modelo": aeronave.get("modelo"),
                "descricao": payload.get("paneDescricao", ""),
                "ata": payload.get("paneAta"),
                "tipo": pane_tipo,
                "status": pane_status,
                "criadoEm": criado_em.isoformat(),
                "horasEmAberto": horas,
                "diasEmAberto": dias,
                "criadoPor": payload.get("criadoPor"),
            }
        )

    panes.sort(
        key=lambda item: (
            -item["horasEmAberto"],
            str(item.get("prefixo") or ""),
            str(item.get("descricao") or ""),
        )
    )
    return panes[:limit]



@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin", "*")
    response.headers["Access-Control-Allow-Origin"] = origin if origin else "*"
    response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return response


@app.route("/api/<path:_>", methods=["OPTIONS"])
@app.route("/<path:_>", methods=["OPTIONS"])
def options_handler(_):
    return ("", 204)


def get_client_ip() -> str | None:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or None
    real_ip = request.headers.get("X-Real-IP", "").strip()
    if real_ip:
        return real_ip
    return request.remote_addr


def create_access_log(username: str, action: str, result: str, source: str = "panes", details: str | None = None):
    log = AccessLog(
        username=str(username or "desconhecido")[:120],
        action=str(action or "unknown")[:50],
        result=str(result or "unknown")[:30],
        source=str(source or "panes")[:50],
        ip_address=(get_client_ip() or "")[:120] or None,
        user_agent=(request.headers.get("User-Agent", "") or "")[:2000] or None,
        details=(str(details)[:4000] if details else None),
    )
    db.session.add(log)
    db.session.commit()
    return log




def apply_access_log_filters(query):
    username = str(request.args.get("username", "")).strip()
    action = str(request.args.get("action", "")).strip()
    result = str(request.args.get("result", "")).strip()
    text = str(request.args.get("q", "")).strip()
    date_from = parse_iso_datetime(request.args.get("date_from"))
    date_to = parse_iso_datetime(request.args.get("date_to"))

    if username:
        query = query.filter(AccessLog.username.ilike(f"%{username}%"))
    if action:
        query = query.filter(AccessLog.action == action)
    if result:
        query = query.filter(AccessLog.result == result)
    if date_from:
        query = query.filter(AccessLog.created_at >= date_from)
    if date_to:
        query = query.filter(AccessLog.created_at <= date_to)

    if text:
        from sqlalchemy import or_
        query = query.filter(
            or_(
                AccessLog.username.ilike(f"%{text}%"),
                AccessLog.details.ilike(f"%{text}%"),
                AccessLog.ip_address.ilike(f"%{text}%"),
            )
        )

    return query


def build_csv_response(rows, filename: str):
    output = io.StringIO()
    if rows:
        fieldnames = list(rows[0].keys())
    else:
        fieldnames = ["message"]
        rows = [{"message": "Sem registros"}]

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "controle-panes-api"})


@app.post("/api/access-log")
def create_access_log_endpoint():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON inválido"}), 400

    username = str(payload.get("username", "")).strip() or "desconhecido"
    action = str(payload.get("action", "")).strip() or "unknown"
    result = str(payload.get("result", "")).strip() or "unknown"
    source = str(payload.get("source", "panes")).strip() or "panes"
    details = str(payload.get("details", "")).strip() or None

    log = create_access_log(username=username, action=action, result=result, source=source, details=details)
    return jsonify({"ok": True, "item": log.to_dict()}), 201


@app.get("/api/access-log")
def list_access_logs():
    limit = request.args.get("limit", default=200, type=int)
    if limit is None or limit < 1:
        limit = 200
    if limit > 1000:
        limit = 1000

    query = AccessLog.query.order_by(AccessLog.created_at.desc(), AccessLog.id.desc())
    query = apply_access_log_filters(query)
    logs = query.limit(limit).all()
    return jsonify([log.to_dict() for log in logs])


@app.get("/api/access-log/export")
def export_access_logs():
    query = AccessLog.query.order_by(AccessLog.created_at.desc(), AccessLog.id.desc())
    query = apply_access_log_filters(query)
    logs = query.limit(5000).all()
    return build_csv_response([log.to_dict() for log in logs], "auditoria_acesso.csv")


@app.get("/api/records")
def list_records():
    records = Record.query.order_by(Record.created_at.asc(), Record.id.asc()).all()
    return jsonify([record.to_dict() for record in records])


@app.post("/api/records")
def create_record():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON inválido"}), 400

    record_id = str(payload.get("id", "")).strip()
    if not record_id:
        return jsonify({"error": "Campo 'id' é obrigatório"}), 400

    existing = db.session.get(Record, record_id)
    if existing is not None:
        return jsonify({"error": "Já existe um registro com este id"}), 409

    record = Record(
        id=record_id,
        record_type=str(payload.get("type", "")).strip() or None,
        data=json.dumps(payload, ensure_ascii=False),
    )
    db.session.add(record)
    db.session.commit()
    return jsonify({"isOk": True, "item": record.to_dict()}), 201


@app.put("/api/records/<record_id>")
def update_record(record_id: str):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON inválido"}), 400

    record = db.session.get(Record, record_id)
    if record is None:
        return jsonify({"error": "Registro não encontrado"}), 404

    payload["id"] = record_id
    record.record_type = str(payload.get("type", "")).strip() or None
    record.data = json.dumps(payload, ensure_ascii=False)
    record.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({"isOk": True, "item": record.to_dict()})


@app.delete("/api/records/<record_id>")
def delete_record(record_id: str):
    record = db.session.get(Record, record_id)
    if record is None:
        return jsonify({"error": "Registro não encontrado"}), 404

    db.session.delete(record)
    db.session.commit()
    return jsonify({"isOk": True, "deletedId": record_id})


@app.delete("/api/records")
def delete_record_from_body():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON inválido"}), 400

    record_id = str(payload.get("id", "")).strip()
    if not record_id:
        return jsonify({"error": "Campo 'id' é obrigatório"}), 400
    return delete_record(record_id)




@app.get("/api/ranking-panes")
def ranking_panes():
    tipo = request.args.get("tipo")
    limit = request.args.get("limit", default=10, type=int)

    if limit is None or limit < 1:
        limit = 10
    if limit > 50:
        limit = 50

    ranking = montar_ranking_panes(tipo=tipo, limit=limit)
    return jsonify(ranking)

@app.get("/")
def index():
    candidates = [
        "codigo_render_api.html",
        "index.html",
        "codigo completo.html",
    ]
    for filename in candidates:
        file_path = BASE_DIR / filename
        if file_path.exists():
            return send_from_directory(BASE_DIR, filename)
    return jsonify(
        {
            "ok": True,
            "message": "API online. Coloque seu HTML no mesmo diretório do app.py com o nome 'codigo_render_api.html' ou 'index.html'.",
        }
    )


# =========================
# ROD END - HELPERS
# =========================

RODEND_ALLOWED_TYPES = {"rodend_user", "rodend_aircraft", "rodend_component"}


def is_rodend_type(value: str) -> bool:
    return str(value or "").strip().lower() in RODEND_ALLOWED_TYPES


def get_rodend_records():
    records = Record.query.order_by(Record.created_at.asc(), Record.id.asc()).all()
    items = []

    for record in records:
        try:
            payload = record.to_dict()
        except Exception:
            continue

        record_type = str(payload.get("type") or record.record_type or "").strip().lower()
        if is_rodend_type(record_type):
            items.append(payload)

    return items


def get_rodend_users():
    return [item for item in get_rodend_records() if str(item.get("type", "")).strip().lower() == "rodend_user"]


def sanitize_rodend_payload(payload: dict, record_id: str | None = None):
    if not isinstance(payload, dict):
        return None, ("JSON inválido", 400)

    payload_type = str(payload.get("type", "")).strip().lower()
    if not is_rodend_type(payload_type):
        return None, ("Tipo inválido para módulo ROD END", 400)

    if record_id:
        payload["id"] = record_id

    final_id = str(payload.get("id", "")).strip()
    if not final_id:
        return None, ("Campo 'id' é obrigatório", 400)

    # Reforça prefixos para evitar colisão com o sistema atual
    if payload_type == "rodend_user" and not final_id.startswith("roduser_"):
        return None, ("ID de usuário ROD END deve começar com 'roduser_'", 400)

    if payload_type == "rodend_aircraft" and not final_id.startswith("rodair_"):
        return None, ("ID de aeronave ROD END deve começar com 'rodair_'", 400)

    if payload_type == "rodend_component" and not final_id.startswith("rodcomp_"):
        return None, ("ID de componente ROD END deve começar com 'rodcomp_'", 400)

    payload["id"] = final_id
    payload["type"] = payload_type

    return payload, None


# =========================
# ROD END - ROTAS HTML
# =========================

@app.get("/rodend")
def rodend_index():
    candidates = [
        "rodend.html",
        "Rod End Control Ultima Versao 24-03-2026.html",
    ]
    for filename in candidates:
        file_path = BASE_DIR / filename
        if file_path.exists():
            return send_from_directory(BASE_DIR, filename)

    return jsonify(
        {
            "ok": False,
            "message": "Arquivo do módulo ROD END não encontrado. Use 'rodend.html' no mesmo diretório do app.py.",
        }
    ), 404


# =========================
# ROD END - API
# =========================

@app.post("/api/rodend/login")
def rodend_login():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "JSON inválido"}), 400

    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", "")).strip()

    if not username or not password:
        return jsonify({"ok": False, "error": "Usuário e senha são obrigatórios"}), 400

    # admin fixo do módulo ROD END
    if username == "admin" and password == "Omni0320!":
        return jsonify(
            {
                "ok": True,
                "user": {
                    "id": "roduser_admin",
                    "username": "admin",
                    "type": "rodend_user",
                    "isAdmin": True,
                    "needsPasswordChange": False,
                }
            }
        )

    users = get_rodend_users()
    user = next((u for u in users if str(u.get("username", "")).strip() == username), None)

    if not user or str(user.get("password", "")).strip() != password:
        return jsonify({"ok": False, "error": "Usuário ou senha incorretos"}), 401

    return jsonify(
        {
            "ok": True,
            "user": {
                "id": user.get("id"),
                "username": user.get("username"),
                "type": "rodend_user",
                "isAdmin": False,
                "needsPasswordChange": bool(user.get("needs_password_change", False)),
            }
        }
    )


@app.get("/api/rodend/records")
def rodend_list_records():
    return jsonify(get_rodend_records())


@app.post("/api/rodend/records")
def rodend_create_record():
    payload = request.get_json(silent=True)
    payload, error = sanitize_rodend_payload(payload)

    if error:
        return jsonify({"error": error[0]}), error[1]

    existing = db.session.get(Record, payload["id"])
    if existing is not None:
        return jsonify({"error": "Já existe um registro com este id"}), 409

    record = Record(
        id=payload["id"],
        record_type=payload["type"],
        data=json.dumps(payload, ensure_ascii=False),
    )
    db.session.add(record)
    db.session.commit()

    return jsonify({"isOk": True, "item": record.to_dict()}), 201


@app.put("/api/rodend/records/<record_id>")
def rodend_update_record(record_id: str):
    payload = request.get_json(silent=True)
    payload, error = sanitize_rodend_payload(payload, record_id=record_id)

    if error:
        return jsonify({"error": error[0]}), error[1]

    record = db.session.get(Record, record_id)
    if record is None:
        return jsonify({"error": "Registro não encontrado"}), 404

    current_type = str(record.record_type or "").strip().lower()
    if not is_rodend_type(current_type):
        return jsonify({"error": "Registro não pertence ao módulo ROD END"}), 400

    record.record_type = payload["type"]
    record.data = json.dumps(payload, ensure_ascii=False)
    record.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({"isOk": True, "item": record.to_dict()})


@app.delete("/api/rodend/records/<record_id>")
def rodend_delete_record(record_id: str):
    record = db.session.get(Record, record_id)
    if record is None:
        return jsonify({"error": "Registro não encontrado"}), 404

    current_type = str(record.record_type or "").strip().lower()
    if not is_rodend_type(current_type):
        return jsonify({"error": "Registro não pertence ao módulo ROD END"}), 400

    db.session.delete(record)
    db.session.commit()
    return jsonify({"isOk": True, "deletedId": record_id})

@app.get("/<path:filename>")
def serve_static(filename: str):
    file_path = BASE_DIR / filename
    if file_path.exists() and file_path.is_file():
        return send_from_directory(BASE_DIR, filename)
    return jsonify({"error": "Arquivo não encontrado"}), 404

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
