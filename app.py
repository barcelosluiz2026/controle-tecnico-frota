import os
import re
from datetime import datetime
from flask import Flask, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from collections import defaultdict
from zoneinfo import ZoneInfo
# ==================================================================================
from flask import send_file, request
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import styles
from reportlab.lib.units import inch
from reportlab.lib.pagesizes import A4
import io

def hora_br(dt):
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M")


app = Flask(__name__)
app.secret_key = "supersecretkey"

# ======================
# BANCO DE DADOS
# ======================

database_url = os.getenv("DATABASE_URL")

if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ======================
# MODELOS
# ======================


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(50), nullable=False)


class Aircraft(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    model = db.Column(db.String(50), nullable=False)
    prefix = db.Column(db.String(10), unique=True, nullable=False)
    photo_url = db.Column(db.String(500))


class Pane(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    aircraft_id = db.Column(db.Integer, db.ForeignKey("aircraft.id"), nullable=False)
    description = db.Column(db.Text, nullable=False)
    ata = db.Column(db.String(2), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)
    responsavel = db.Column(db.String(100), nullable=False)
    photo_url = db.Column(db.String(500))
    status = db.Column(db.String(50), default="Pane Lançada")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.String(100))
    aircraft = db.relationship("Aircraft", backref="panes")


class Step(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pane_id = db.Column(db.Integer, db.ForeignKey("pane.id"), nullable=False)
    description = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.String(100))
    pane = db.relationship("Pane", backref="steps")
    responsavel_info = db.Column(db.String(100), nullable=False)
    photo1 = db.Column(db.String(500))
    photo2 = db.Column(db.String(500))
    photo3 = db.Column(db.String(500))


class Pendencia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pane_id = db.Column(db.Integer, db.ForeignKey("pane.id"), nullable=False)
    tipo_item = db.Column(db.String(20), nullable=False)
    tipo_aquisicao = db.Column(db.String(20), nullable=False)
    descricao = db.Column(db.Text, nullable=False)
    pn = db.Column(db.String(50))
    sms_part_request = db.Column(db.String(20))
    task_card = db.Column(db.String(20))
    responsavel = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.String(100))
    pane = db.relationship("Pane", backref="pendencias")


# ======================
# LOGIN REQUIRED
# ======================

def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                return "Acesso negado", 403
            return f(*args, **kwargs)
        return wrapper
    return decorator

# ======================
# HOME
# ======================

@app.route("/")
@login_required()
def home():

    # ======================
    # DADOS DASHBOARD
    # ======================

    total_aeronaves = Aircraft.query.count()

    aeronaves_por_modelo = (
        db.session.query(
            Aircraft.model,
            func.count(Aircraft.id)
        )
        .group_by(Aircraft.model)
        .order_by(Aircraft.model)
        .all()
    )

    total_panes_abertas = (
        Pane.query
        .filter(Pane.status != "Finalizadas")
        .count()
    )

    panes_mecanico = (
        Pane.query
        .filter(
            Pane.status != "Finalizadas",
            Pane.tipo == "Mecânico"
        )
        .count()
    )

    panes_avionico = (
        Pane.query
        .filter(
            Pane.status != "Finalizadas",
            Pane.tipo == "Aviônico"
        )
        .count()
    )

    # ======================
    # LISTAGEM DE AERONAVES
    # ======================

    aircrafts = Aircraft.query.order_by(
        Aircraft.model,
        Aircraft.prefix
    ).all()

    grouped = {}

    for ac in aircrafts:
        grouped.setdefault(ac.model, []).append(ac)

    html = f"""
    <html>
    <head>
        <title>Controle Técnico</title>
        <style>
            body {{ font-family: Arial; background-color: #0f172a; color: white; padding: 20px; }}
            .dashboard {{ background:#1e293b; padding:20px; border-radius:10px; margin-bottom:40px; }}
            .dashboard-cards {{ display:flex; gap:20px; flex-wrap:wrap; margin-bottom:20px; }}
            .dash-card {{ background:#334155; padding:15px; border-radius:8px; flex:1; min-width:200px; text-align:center; }}
            .dash-card h3 {{ margin:0; font-size:14px; color:#38bdf8; }}
            .dash-card p {{ font-size:26px; font-weight:bold; margin:5px 0 0 0; }}
            .model-title {{ margin-top: 40px; font-size: 24px; border-bottom: 2px solid #1e293b; padding-bottom: 10px; }}
            .grid {{ display: grid; grid-template-columns: repeat(7, 1fr); gap: 15px; margin-top: 20px; }}
            .card {{ background: #1e293b; padding: 10px; border-radius: 8px; text-align: center; }}
            .card img {{ width: 100%; height: 100px; object-fit: cover; border-radius: 6px; }}
            .prefix {{ font-weight: bold; margin-top: 5px; }}
            .top-bar {{ display:flex; justify-content: space-between; }}
            a {{ color: #38bdf8; text-decoration: none; }}
        </style>
    </head>
    <body>

    <div class="top-bar">
        <h1>🚁 Controle Técnico de Frota</h1>
        <div>
            <a href="/add_aircraft">Cadastrar Helicóptero</a> |
            <a href="/logout">Sair</a>
        </div>
    </div>

    <div class="dashboard">
        <h2>📊 Dashboard Operacional</h2>

        <div class="dashboard-cards">
            <div class="dash-card">
                <h3>Total de Aeronaves</h3>
                <p>{total_aeronaves}</p>
            </div>

            <div class="dash-card">
                <h3>Panes em Aberto</h3>
                <p>{total_panes_abertas}</p>
            </div>

            <div class="dash-card">
                <h3>Mecânico</h3>
                <p>{panes_mecanico}</p>
            </div>

            <div class="dash-card">
                <h3>Aviônico</h3>
                <p>{panes_avionico}</p>
            </div>
        </div>

        <h3>Aeronaves por Modelo</h3>
    """

    for modelo, quantidade in aeronaves_por_modelo:
        html += f"<p>{modelo}: <strong>{quantidade}</strong></p>"

    html += "</div>"

    # ======================
    # GRID DE AERONAVES
    # ======================

    for model, items in grouped.items():

        html += f"<div class='model-title'>🚁 {model}</div>"
        html += "<div class='grid'>"

        for ac in items:
            html += f"""
            <div class='card'>
                <img src='{ac.photo_url}' alt='foto'>
                <div class='prefix'>
                    <a href='/aircraft/{ac.id}' style='color:white;text-decoration:none;'>
                        {ac.prefix}
                    </a>
                </div>
                {
                    "<a href='/delete_aircraft/" + str(ac.id) + "' style='color:#f87171;font-size:12px;'>Excluir</a>"
                    if session.get("role") == "Admin" else ""
                }
            </div>
            """

        html += "</div>"

    html += "</body></html>"

    return html


# ======================
# CADASTRAR AERONAVE
# ======================

@app.route("/add_aircraft", methods=["GET", "POST"])
@login_required("Admin")
def add_aircraft():

    if request.method == "POST":

        model = request.form["model"]
        prefix = request.form["prefix"].upper()
        photo_url = request.form.get("photo_url", "").strip() or None

        if not re.match(r"^[A-Z]{2}-[A-Z]{3}$", prefix):
            return "Prefixo inválido. Use formato PR-ABC"

        if Aircraft.query.filter_by(prefix=prefix).first():
            return "Aeronave já cadastrada"

        new_aircraft = Aircraft(
            model=model,
            prefix=prefix,
            photo_url=photo_url
        )

        db.session.add(new_aircraft)
        db.session.commit()

        return redirect(url_for("home"))

    return """
    <h2>Cadastrar Helicóptero 🚁</h2>
    <form method="POST">
        Modelo:
        <select name="model">
            <option>AW139</option>
            <option>EC175</option>
            <option>S-92A</option>
            <option>H160</option>
            <option>EC225</option>
        </select><br><br>

        Prefixo:
        <input name="prefix" placeholder="PR-ABC"><br><br>

        Link da Foto:
        <input name="photo_url" placeholder="https://..."><br><br>

        <button type="submit">Cadastrar</button>
    </form>
    """

# ======================
# EXCLUIR AERONAVE
# ======================

@app.route("/delete_aircraft/<int:id>", methods=["GET", "POST"])
@login_required("Admin")
def delete_aircraft(id):

    aircraft = Aircraft.query.get_or_404(id)

    if request.method == "POST":
        db.session.delete(aircraft)
        db.session.commit()
        return redirect(url_for("home"))

    return f"""
    <html>
    <head>
        <title>Confirmar Exclusão</title>
        <style>
            body {{ font-family: Arial; background-color: #0f172a; color: white; padding: 40px; text-align: center; }}
            .box {{ background: #1e293b; padding: 30px; border-radius: 10px; display: inline-block; }}
            button {{ padding: 10px 20px; margin: 10px; border: none; border-radius: 5px; cursor: pointer; }}
            .delete {{ background-color: #dc2626; color: white; }}
            .cancel {{ background-color: #475569; color: white; }}
            a {{ text-decoration: none; color: white; }}
        </style>
    </head>
    <body>
        <div class="box">
            <h2>⚠ Confirmar Exclusão</h2>
            <p>Deseja realmente excluir a aeronave:</p>
            <h3>{aircraft.prefix} - {aircraft.model}</h3>

            <form method="POST">
                <button type="submit" class="delete">Excluir</button>
                <a href="{url_for('home')}">
                    <button type="button" class="cancel">Cancelar</button>
                </a>
            </form>
        </div>
    </body>
    </html>
    """


# ======================
# PAGINA DA AERONAVE
# ======================

@app.route("/aircraft/<int:id>", methods=["GET", "POST"])
@login_required()
def aircraft_page(id):

    aircraft = Aircraft.query.get_or_404(id)

    # ======================
    # NOVA PANE
    # ======================

    if request.method == "POST":

        description = request.form["description"]
        ata = request.form["ata"]
        tipo = request.form["tipo"]
        responsavel = request.form["responsavel"]
        photo_url = request.form.get("photo_url", "").strip() or None

        new_pane = Pane(
            aircraft_id=aircraft.id,
            description=description,
            ata=ata,
            tipo=tipo,
            responsavel=responsavel,
            photo_url=photo_url,
            status="Pane Lançada",
            created_by=session.get("username")
        )

        db.session.add(new_pane)
        db.session.commit()

        return redirect(url_for("aircraft_page", id=aircraft.id))

    # ======================
    # LISTAGEM DE PANES
    # ======================

    panes = (
        Pane.query
        .filter_by(aircraft_id=aircraft.id)
        .order_by(Pane.created_at.desc())
        .all()
    )

    statuses = [
        "Pane Lançada",
        "In Progress Avi",
        "In Progress Mec",
        "Wait Material",
        "Wait Tools",
        "Wait Transfer",
        "Finalizadas"
    ]

    grouped_panes = {status: [] for status in statuses}

    for pane in panes:
        if pane.status in grouped_panes:
            grouped_panes[pane.status].append(pane)

    html = f"""
    <html>
    <head>
        <title>{aircraft.prefix} - {aircraft.model}</title>
        <style>
            body {{ font-family: 'Segoe UI', Arial, sans-serif; background-color: #0f172a; color: #f1f5f9; margin: 0; padding: 20px; }}
            h2, h3 {{ color: #38bdf8; }}
            .container {{ max-width: 98%; margin: 0 auto; }}

            .btn-add {{
                background: linear-gradient(90deg, #2563eb, #1d4ed8);
                color: white;
                border: none;
                padding: 12px 18px;
                border-radius: 8px;
                cursor: pointer;
                font-weight: bold;
                margin-bottom: 20px;
            }}

            .form-box {{
                background: #1e293b;
                padding: 30px;
                border-radius: 12px;
                box-shadow: 0 0 15px rgba(0,0,0,0.3);
                margin-bottom: 40px;
                display: none;
            }}

            form {{ display: grid; gap: 15px; }}

            textarea, input {{
                background: #0f172a;
                color: #f1f5f9;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 10px;
                width: 100%;
            }}

            .radio-group {{ display: flex; gap: 20px; align-items: center; }}

            .btn {{
                background: linear-gradient(90deg, #2563eb, #1d4ed8);
                color: white;
                border: none;
                padding: 12px;
                border-radius: 6px;
                cursor: pointer;
                font-weight: bold;
            }}

            .tabs {{ display:flex; gap:10px; margin-bottom:15px; flex-wrap:wrap; }}

            .tabs button {{
                padding:8px 15px;
                border:none;
                border-radius:6px;
                background:#334155;
                color:#38bdf8;
                cursor:pointer;
                transition:0.2s;
            }}

            .tabs button.active {{
                background:#2563eb;
                color:white;
                box-shadow:0 0 8px rgba(37,99,235,0.6);
            }}

            .column {{
                background: #1e293b;
                border-radius: 10px;
                padding: 15px;
                display: none;
                flex-direction: column;
            }}

            .column h4 {{
                text-align: center;
                background: #334155;
                padding: 10px;
                border-radius: 6px;
                margin-bottom: 15px;
                color: #38bdf8;
            }}

            .card {{
                background: #334155;
                padding: 12px;
                border-radius: 8px;
                margin-bottom: 10px;
            }}

            .card small {{ color: #94a3b8; }}
        </style>
    </head>
    <body>
        <div class="container">
            <a href="/" style="
                background:#334155;
                color:white;
                padding:6px 12px;
                border-radius:6px;
                text-decoration:none;
            ">
                ← Voltar
            </a>
            <h2>🚁 {aircraft.prefix} - {aircraft.model}</h2>

            <button class="btn-add" onclick="toggleForm()">➕ Adicionar Pane</button>

            <div class="form-box" id="formPane">
                <h3>Registrar Nova Pane</h3>
                <form method="POST">
                    <textarea name="description" placeholder="Descrição da Pane" required></textarea>

                    <div style="display:flex; gap:15px;">
                        <input name="ata" placeholder="ATA (2 dígitos)" required style="flex:1;">

                        <div class="radio-group">
                            <label><input type="radio" name="tipo" value="Mecânico" required> Mecânico</label>
                            <label><input type="radio" name="tipo" value="Aviônico" required> Aviônico</label>
                        </div>
                    </div>

                    <input name="responsavel" placeholder="Responsável" required>
                    <input name="photo_url" placeholder="URL da Foto (opcional)">

                    <button type="submit" class="btn">Salvar Pane</button>
                    <button type="button" class="btn" onclick="toggleForm()">Cancelar</button>
                </form>
            </div>

            <h3>Kanban de Panes</h3>
            <div class="tabs">
    """

    for status in statuses:
        quantidade = len(grouped_panes[status])
        html += f"<button onclick=\"abrirAba('{status}')\">{status} ({quantidade})</button>"

    html += "</div>"

    for status in statuses:

        quantidade = len(grouped_panes[status])

        html += f"<div class='column' id='col-{status}'>"
        html += f"<h4>{status} ({quantidade})</h4>"

        for pane in grouped_panes[status]:
            html += f"""
            <a href='/pane/{pane.id}' style='text-decoration:none;color:white;'>
                <div class='card'>
                    <strong>ATA {pane.ata}</strong><br>
                    <p>{pane.description}</p>
                    <small>Responsável: {pane.responsavel}</small><br>
                    <small>{hora_br(pane.created_at)} - {pane.created_by}</small>
                </div>
            </a>
            """

        html += "</div>"

    html += """
        </div>

        <script>
            function toggleForm() {
                const form = document.getElementById("formPane");
                form.style.display = form.style.display === "none" ? "block" : "none";
            }

            function abrirAba(status) {
                const colunas = document.querySelectorAll('.column');
                colunas.forEach(col => col.style.display = 'none');

                const botoes = document.querySelectorAll('.tabs button');
                botoes.forEach(btn => btn.classList.remove('active'));

                const ativa = document.getElementById('col-' + status);
                if (ativa) ativa.style.display = 'flex';

                botoes.forEach(btn => {
                    if (btn.innerText.startsWith(status)) {
                        btn.classList.add('active');
                    }
                });
            }

            window.onload = function() {
                abrirAba('Pane Lançada');
            }
        </script>
    </body>
    </html>
    """

    return html

# ======================
# DETALHES DA PANE
# ======================

@app.route("/pane/<int:id>", methods=["GET", "POST"])
@login_required()
def pane_detail(id):
    pane = Pane.query.get_or_404(id)

    steps_all = Step.query.filter_by(pane_id=pane.id).all()

    # Todas as fotos da pane (principal + etapas)
    todas_fotos = []
    if pane.photo_url:
        todas_fotos.append(pane.photo_url)
    for s in steps_all:
        for f in [s.photo1, s.photo2, s.photo3]:
            if f:
                todas_fotos.append(f)

    total_fotos = len(todas_fotos)

    # ======================
    # PROCESSAMENTO DE FORMULÁRIOS
    # ======================
    if request.method == "POST":
        action = request.form.get("action")

        # Bloqueia novas fotos se já houver 4
        if action == "add_step" and total_fotos >= 4:
            return f"""
            <html><body style='background:#0f172a;color:white;text-align:center;padding:40px;'>
            <h2>⚠ Limite de 4 fotos atingido para esta pane.</h2>
            <a href='{url_for('pane_detail', id=pane.id)}' style='color:#38bdf8;'>Voltar</a>
            </body></html>
            """

        if action == "add_step":
            descricao = request.form.get("step_desc", "").strip()
            responsavel_info = request.form.get("responsavel_info", "").strip()
            if not descricao or not responsavel_info:
                return redirect(url_for("pane_detail", id=pane.id))

            step = Step(
                pane_id=pane.id,
                description=descricao,
                responsavel_info=responsavel_info,
                created_by=session.get("username"),
                photo1=request.form.get("photo1"),
                photo2=request.form.get("photo2"),
                photo3=request.form.get("photo3")
            )
            db.session.add(step)
            pane.status = "In Progress Avi" if pane.tipo and pane.tipo.strip().lower() == "aviônico" else "In Progress Mec"

        elif action == "add_pendencia":
            pend = Pendencia(
                pane_id=pane.id,
                tipo_item=request.form.get("tipo_item"),
                tipo_aquisicao=request.form.get("tipo_aquisicao"),
                descricao=request.form.get(""),
                pn=request.form.get("pn"),
                sms_part_request=request.form.get("sms_part_request"),
                task_card=request.form.get("task_card"),
                responsavel=request.form.get("responsavel"),
                created_by=session.get("username")
            )
            db.session.add(pend)
            if pend.tipo_item == "Ferramenta":
                pane.status = "Wait Tools"
            elif pend.tipo_item == "Material":
                if pend.tipo_aquisicao == "Compra":
                    pane.status = "Wait Material"
                elif pend.tipo_aquisicao == "Transferência":
                    pane.status = "Wait Transfer"

        elif action == "finalize":
            pane.status = "Finalizadas"

        db.session.commit()
        return redirect(url_for("pane_detail", id=pane.id))

    # ======================
    # CONSULTAS
    # ======================
    steps = Step.query.filter_by(pane_id=pane.id).order_by(Step.created_at.desc()).all()
    pendencias = Pendencia.query.filter_by(pane_id=pane.id).order_by(Pendencia.created_at.desc()).all()

    # ======================
    # HTML
    # ======================
    html = f"""
    <html>
    <head>
    <style>
    body {{ background:#0f172a; color:#f1f5f9; font-family:Segoe UI; padding:40px; }}
    .card {{ background:#1e293b; padding:20px; border-radius:10px; margin-bottom:25px; }}
    textarea, input {{
        width:100%; padding:10px; margin-top:8px;
        background:#0f172a; color:white; border:1px solid #334155; border-radius:6px;
    }}
    .btn {{ background:#2563eb; color:white; border:none; padding:10px 18px; border-radius:6px; cursor:pointer; }}
    .btn-green {{ background:#16a34a; }}
    .btn-red {{ background:#ef4444; }}
    .top-actions {{ display:flex; gap:15px; margin-bottom:25px; flex-wrap:wrap; }}
    .contador {{ background:#334155; padding:8px 12px; border-radius:6px; display:inline-block; margin-bottom:20px; }}
    .modal {{
        display:none; position:fixed; top:0; left:0; width:100%; height:100%;
        background:rgba(0,0,0,0.6); justify-content:center; align-items:center;
        z-index:1000;
    }}
    .modal-content {{
        background:#1e293b; padding:25px; border-radius:10px; width:90%; max-width:500px;
        box-shadow:0 0 20px rgba(0,0,0,0.4);
    }}
    .modal-large {{
        max-width: 700px;
    }}

    .form-group {{
        margin-bottom: 15px;
    }}

    .form-grid {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 15px;
        margin-top: 15px;
    }}

    .form-grid label {{
        font-size: 13px;
        color: #94a3b8;
        display: block;
        margin-bottom: 4px;
    }}

    .radio-group {{
        margin-bottom: 18px;
    }}

    .radio-title {{
        font-weight: 600;
        display: block;
        margin-bottom: 8px;
    }}

    .radio-row {{
        display: flex;
        gap: 15px;
    }}

    .radio-card {{
        background: #1e293b;
        padding: 10px 14px;
        border-radius: 8px;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 8px;
        border: 1px solid #334155;
    }}

    .radio-card input {{
        margin-right: 6px;
    }}

    .modal-actions {{
        margin-top: 25px;
        display: flex;
        justify-content: flex-end;
        gap: 12px;
    }}
    </style>
    </head>
    <body>
        <div class="container">
        <a href="/aircraft/{pane.aircraft_id}"style="
            background:#334155;
            color:white;
            padding:6px 12px;
            border-radius:6px;
            text-decoration:none;
        ">
            ← Voltar
        </a>
    <h2>Pane: {pane.description} - ATA {pane.ata}</h2>
    <small>Criado por: {pane.created_by} - Em: {hora_br(pane.created_at)}</small><br>
    <div class="contador">📸 Fotos utilizadas: {total_fotos} / 4</div>

    <div class="card">
        <strong>{pane.description}</strong><br>
        <small>Status: {pane.status}</small>
    """

    # Exibe fotos com botão de exclusão
    if todas_fotos:
        html += "<div style='margin-top:15px; display:flex; gap:12px; flex-wrap:wrap;'>"
        for foto in todas_fotos:
            html += f"""
            <div style="position:relative;display:inline-block;">
                <img src="{foto}"
                     style="width:110px;height:110px;object-fit:cover;border-radius:8px;cursor:pointer;border:1px solid #475569;"
                     onclick="openImage('{foto}')">
                <form method="POST" action="/delete_photo/{pane.id}" style="position:absolute;top:4px;right:4px;">
                    <input type="hidden" name="foto_url" value="{foto}">
                    <button type="submit" onclick="return confirm('Excluir esta foto?')" 
                            style="background:#ef4444;border:none;color:white;border-radius:50%;width:22px;height:22px;cursor:pointer;">×</button>
                </form>
            </div>
            """
        html += "</div>"

    html += "</div>"

    html += """
    <div class="top-actions">
        <button class="btn" onclick="openModal('modalStep')">➕ Adicionar Etapa</button>
        <button class="btn" onclick="openModal('modalPend')">➕ Registrar Pendência</button>
        <button class="btn btn-green" onclick="confirmarFinalizacao()">✅ Finalizar Pane</button>
    </div>
    """

    html += "<div class='card'><h3>Etapas</h3>"
    for step in steps:
        html += f"""
        <div style="background:#334155;padding:12px;border-radius:8px;margin-bottom:12px;">
        🛠 {step.description}<br>
        <small>{step.responsavel_info}<br>{hora_br(step.created_at)} - {step.created_by}</small>
        </div>
        """
    html += "</div>"

    html += "<div class='card'><h3>Pendências</h3>"
    for p in pendencias:
        html += f"""
        <div style="background:#334155;padding:12px;border-radius:8px;margin-bottom:12px;">
        <strong>{p.tipo_item}</strong> - {p.descricao}<br>
        <small>
        Aquisição: {p.tipo_aquisicao}<br>
        P/N: {p.pn or '-'}<br>
        SMS/Part: {p.sms_part_request or '-'}<br>
        Task Card: {p.task_card or '-'}<br>
        Responsável: {p.responsavel}<br>
        {hora_br(p.created_at)} - {p.created_by}
        </small>
        </div>
        """
    html += "</div>"

    html += """
    <!-- MODAL ETAPA -->
    <div id="modalStep" class="modal">
        <div class="modal-content">
            <h3>Nova Etapa</h3>
            <form method="POST">
                <input type="hidden" name="action" value="add_step">
                <textarea name="step_desc" placeholder="Descreva a etapa" required></textarea>
                <input name="responsavel_info" placeholder="Responsável pela informação" required>
                <label>📷 Fotos (até 3)</label>
                <input name="photo1" placeholder="https://exemplo.com/foto1.jpg">
                <input name="photo2" placeholder="https://exemplo.com/foto2.jpg">
                <input name="photo3" placeholder="https://exemplo.com/foto3.jpg">
                <div style="margin-top:15px;">
                    <button type="submit" class="btn">Salvar</button>
                    <button type="button" class="btn btn-red" onclick="closeModal('modalStep')">Cancelar</button>
                </div>
            </form>
        </div>
    </div>

    <!-- MODAL PENDÊNCIA -->
    <div id="modalPend" class="modal">
    <div class="modal-content">
        <h3>Nova Pendência</h3>
        <form method="POST">
            <input type="hidden" name="action" value="add_pendencia">

            <div class="radio-group">
                <span class="radio-title">Tipo de Item *</span>
                <div class="radio-row">
                    <label><input type="radio" name="tipo_item" value="Ferramenta" required> 🔧 Ferramenta</label>
                    <label><input type="radio" name="tipo_item" value="Material" required> 📋 Material</label>
                </div>
            </div>

            <div class="radio-group">
                <span class="radio-title">Tipo de Aquisição *</span>
                <div class="radio-row">
                    <label><input type="radio" name="tipo_aquisicao" value="Transferência" required> 🔄 Transferência</label>
                    <label><input type="radio" name="tipo_aquisicao" value="Compra" required> 🛒 Compra</label>
                </div>
            </div>

            <input name="descricao" placeholder="Descrição" required>

            <div class="form-grid">
                <input name="pn" placeholder="P/N">
                <input name="sms_part_request" placeholder="SMS/Part Request">
                <input name="task_card" placeholder="Task Card">
                <input name="responsavel" placeholder="Responsável" required>
            </div>

            <div style="margin-top:15px; display:flex; gap:12px;">
                <button type="submit" class="btn">Salvar</button>
                <button type="button" class="btn btn-red" onclick="closeModal('modalPend')">Cancelar</button>
            </div>
        </form>
    </div>
</div>

    <form method="POST" id="formFinalize">
        <input type="hidden" name="action" value="finalize">
    </form>

    <div id="imageModal" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.85);justify-content:center;align-items:center;z-index:2000;">
        <img id="zoomedImage" style="max-width:90%;max-height:90%;border-radius:10px;box-shadow:0 0 40px rgba(0,0,0,0.7);">
    </div>

    <script>
    function openModal(id) {{ document.getElementById(id).style.display = "flex"; }}
    function closeModal(id) {{ document.getElementById(id).style.display = "none"; }}
    function confirmarFinalizacao() {{
        if (confirm("Tem certeza que deseja finalizar esta pane?")) {{
            document.getElementById("formFinalize").submit();
        }}
    }}
    function openImage(src) {{
        document.getElementById("zoomedImage").src = src;
        document.getElementById("imageModal").style.display = "flex";
    }}
    document.getElementById("imageModal").addEventListener("click", function() {{
        this.style.display = "none";
    }});
    document.addEventListener("keydown", function(e) {{
        if (e.key === "Escape") {{
            closeModal("modalStep");
            closeModal("modalPend");
            document.getElementById("imageModal").style.display = "none";
        }}
    }});
    </script>

    </body>
    </html>
    """

    return html

# ======================
# EXCLUIR FOTOS
# ======================
@app.route("/delete_photo/<int:pane_id>", methods=["POST"])
@login_required()
def delete_photo(pane_id):
    pane = Pane.query.get_or_404(pane_id)
    foto_url = request.form.get("foto_url")

    # Remove se for a foto principal
    if pane.photo_url == foto_url:
        pane.photo_url = None

    # Remove se for de alguma etapa
    steps = Step.query.filter_by(pane_id=pane.id).all()
    for s in steps:
        for attr in ["photo1", "photo2", "photo3"]:
            if getattr(s, attr) == foto_url:
                setattr(s, attr, None)

    db.session.commit()
    return redirect(url_for("pane_detail", id=pane.id))

# ======================
# RELATÓRIO PENDENCIAS
# ======================

@app.route("/relatorio/pendencias/modelo/pdf")
@login_required()
def relatorio_pendencias_modelo_pdf():

    modelo = request.args.get("modelo")
    prefixo = request.args.get("prefixo")

    query = (
        Pendencia.query
        .join(Pane)
        .join(Aircraft)
    )

    if modelo and modelo != "todos":
        query = query.filter(Aircraft.model == modelo)

    if prefixo and prefixo != "todos":
        query = query.filter(Aircraft.prefix == prefixo)

    pendencias = query.order_by(Aircraft.model, Aircraft.prefix).all()

    # Agrupar por modelo
    agrupado = {}

    for pend in pendencias:
        model_name = pend.pane.aircraft.model
        if model_name not in agrupado:
            agrupado[model_name] = []
        agrupado[model_name].append(pend)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []

    styles_default = styles.getSampleStyleSheet()

    # Título
    elements.append(
        Paragraph("<b>RELATÓRIO DE PENDÊNCIAS POR MODELO</b>",
                  styles_default["Title"])
    )
    elements.append(Spacer(1, 20))

    elements.append(
        Paragraph(
            f"Data de emissão: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            styles_default["Normal"]
        )
    )
    elements.append(Spacer(1, 20))

    # Para cada modelo
    for model_name, lista in agrupado.items():

        elements.append(
            Paragraph(f"<b>Modelo: {model_name}</b>",
                      styles_default["Heading2"])
        )
        elements.append(Spacer(1, 12))

        data_table = [[
            "Prefixo",
            "Pane",
            "Descrição",
            "Tipo",
            "Aquisição",
            "Responsável",
            "PN",
            "SMS/Part",
            "Task Card"
        ]]

        for pend in lista:

            mostrar_extra = (
                pend.tipo_item == "Material"
                and pend.tipo_aquisicao == "Compra"
            )

            data_table.append([
                pend.pane.aircraft.prefix,
                str(pend.pane_id),
                pend.descricao or "",
                pend.tipo_item or "",
                pend.tipo_aquisicao or "",
                pend.responsavel or "",
                pend.pn if mostrar_extra else "",
                pend.sms_part_request if mostrar_extra else "",
                pend.task_card if mostrar_extra else ""
            ])

        tabela = Table(data_table, repeatRows=1)

        tabela.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))

        elements.append(tabela)
        elements.append(Spacer(1, 25))

    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="relatorio_pendencias_modelo.pdf",
        mimetype="application/pdf"
    )

# ======================
# LOGIN
# ======================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form["username"]
        password = generate_password_hash(request.form["password"])
        role = request.form["role"]

        if User.query.filter_by(username=username).first():
            return "Usuário já existe"

        new_user = User(
            username=username,
            password=password,
            role=role
        )

        db.session.add(new_user)
        db.session.commit()

        return redirect(url_for("login"))

    return """
    <h2>Cadastrar Usuário</h2>
    <form method="POST">
        Usuário: <input name="username"><br>
        Senha: <input type="password" name="password"><br>
        Perfil:
        <select name="role">
            <option value="Admin">Admin</option>
            <option value="Tecnico">Técnico</option>
            <option value="Inspetor">Inspetor</option>
            <option value="Visualizador">Visualizador</option>
        </select><br><br>
        <button type="submit">Cadastrar</button>
    </form>
    """


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session["user_id"] = user.id
            session["username"] = user.username
            session["role"] = user.role
            return redirect(url_for("home"))

        return "Login inválido"

    return """
    <h2>Login</h2>
    <form method="POST">
        <input name="username" placeholder="Usuário">
        <input type="password" name="password" placeholder="Senha">
        <button type="submit">Entrar</button>
    </form>
    """


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ======================
# CRIAR TABELAS
# ======================

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run()

# ======================
# RESET BANCO
# ======================

@app.route("/reset_db")
def reset_db():
    db.drop_all()
    db.create_all()
    return "Banco recriado com sucesso!"


















