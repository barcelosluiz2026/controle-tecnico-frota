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
            <a href="/">← Voltar</a>
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

    # =========================
    # MONTAGEM DAS FOTOS
    # =========================
    todas_fotos = []

    # Foto principal da pane
    if pane.photo_url:
        todas_fotos.append(pane.photo_url)

    # Fotos das etapas
    for s in steps_all:
        for f in [s.photo1, s.photo2, s.photo3]:
            if f:
                todas_fotos.append(f)

    MAX_FOTOS = 4
    if len(todas_fotos) > MAX_FOTOS:
        todas_fotos = todas_fotos[:MAX_FOTOS]

    total_fotos = len(todas_fotos)

    # =========================
    # POST
    # =========================
    if request.method == "POST":
        action = request.form.get("action")

        if action == "add_step":

            if len(todas_fotos) >= 4:
                return redirect(url_for("pane_detail", id=pane.id))

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
                descricao=request.form.get("descricao"),
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

        elif action == "edit_step":

            step_id = request.form.get("step_id")
            step = Step.query.get(step_id)

            if step and step.pane_id == pane.id:
                step.description = request.form.get("step_desc")
                step.responsavel_info = request.form.get("responsavel_info")

        elif action == "delete_photo":

            photo = request.form.get("photo")

            if pane.photo_url == photo:
                pane.photo_url = None

            for s in steps_all:
                if s.photo1 == photo:
                    s.photo1 = None
                if s.photo2 == photo:
                    s.photo2 = None
                if s.photo3 == photo:
                    s.photo3 = None

        elif action == "finalize":
            pane.status = "Finalizadas"

        db.session.commit()
        return redirect(url_for("pane_detail", id=pane.id))

    steps = Step.query.filter_by(pane_id=pane.id).order_by(Step.created_at.desc()).all()
    pendencias = Pendencia.query.filter_by(pane_id=pane.id).order_by(Pendencia.created_at.desc()).all()

    # =========================
    # HTML
    # =========================
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
    </style>
    </head>
    <body>

    <a href="/aircraft/{pane.aircraft_id}">← Voltar</a>
    <h2>Pane #{pane.id} - ATA {pane.ata}</h2>

    <div class="contador">📸 Fotos utilizadas: {total_fotos}/4</div>

    <div class="card">
        <strong>{pane.description}</strong><br>
        <small>Status: {pane.status}</small>
    """

    if todas_fotos:
        html += "<div style='margin-top:15px; display:flex; gap:12px; flex-wrap:wrap;'>"
        for foto in todas_fotos:
            html += f"""
            <div style="position:relative;">
                <img draggable="true"
                     src="{foto}"
                     style="width:110px;height:110px;object-fit:cover;border-radius:8px;cursor:pointer;border:1px solid #475569;"
                     onclick="openImage('{foto}')">

                <form method="POST" style="position:absolute;top:-6px;right:-6px;">
                    <input type="hidden" name="action" value="delete_photo">
                    <input type="hidden" name="photo" value="{foto}">
                    <button style="
                        background:#ef4444;
                        border:none;
                        color:white;
                        width:22px;
                        height:22px;
                        border-radius:50%;
                        cursor:pointer;
                        font-size:12px;">✕</button>
                </form>
            </div>
            """
        html += "</div>"

    html += "</div>"

    html += "<div class='card'><h3>Etapas</h3>"

    for step in steps:
        html += f"""
        <div style="background:#334155;padding:12px;border-radius:8px;margin-bottom:12px;">
            <form method="POST">
                <input type="hidden" name="action" value="edit_step">
                <input type="hidden" name="step_id" value="{step.id}">

                <textarea name="step_desc">{step.description}</textarea>
                <input name="responsavel_info" value="{step.responsavel_info}">

                <button class="btn" style="margin-top:8px;">Salvar Alteração</button>
            </form>

            <small>{hora_br(step.created_at)} - {step.created_by}</small>
        </div>
        """
    html += "</div>"

    html += """
    <script>
    let dragged;

    document.addEventListener("dragstart", function(e) {
        dragged = e.target.closest("div");
    });

    document.addEventListener("dragover", function(e) {
        e.preventDefault();
    });

    document.addEventListener("drop", function(e) {
        e.preventDefault();
        if (e.target.tagName === "IMG") {
            let container = e.target.closest("div").parentNode;
            container.insertBefore(dragged, e.target.closest("div"));
        }
    });
    </script>

    </body>
    </html>
    """

    return html

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










