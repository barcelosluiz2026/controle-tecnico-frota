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

class Pendencia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pane_id = db.Column(db.Integer, db.ForeignKey("pane.id"), nullable=False)
    tipo_item = db.Column(db.String(20), nullable=False)  # Ferramenta ou Material
    tipo_aquisicao = db.Column(db.String(20), nullable=False)  # Transferência ou Compra
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

    aircrafts = Aircraft.query.order_by(Aircraft.model, Aircraft.prefix).all()

    grouped = {}
    for ac in aircrafts:
        grouped.setdefault(ac.model, []).append(ac)

    html = f"""
    <html>
    <head>
        <title>Controle Técnico</title>
        <style>
            body {{
                font-family: Arial;
                background-color: #0f172a;
                color: white;
                padding: 20px;
            }}

            .dashboard {{
                background:#1e293b;
                padding:20px;
                border-radius:10px;
                margin-bottom:40px;
            }}

            .dashboard-cards {{
                display:flex;
                gap:20px;
                flex-wrap:wrap;
                margin-bottom:20px;
            }}

            .dash-card {{
                background:#334155;
                padding:15px;
                border-radius:8px;
                flex:1;
                min-width:200px;
                text-align:center;
            }}

            .dash-card h3 {{
                margin:0;
                font-size:14px;
                color:#38bdf8;
            }}

            .dash-card p {{
                font-size:26px;
                font-weight:bold;
                margin:5px 0 0 0;
            }}

            .model-title {{
                margin-top: 40px;
                font-size: 24px;
                border-bottom: 2px solid #1e293b;
                padding-bottom: 10px;
            }}

            .grid {{
                display: grid;
                grid-template-columns: repeat(7, 1fr);
                gap: 15px;
                margin-top: 20px;
            }}

            .card {{
                background: #1e293b;
                padding: 10px;
                border-radius: 8px;
                text-align: center;
            }}

            .card img {{
                width: 100%;
                height: 100px;
                object-fit: cover;
                border-radius: 6px;
            }}

            .prefix {{
                font-weight: bold;
                margin-top: 5px;
            }}

            .top-bar {{
                display:flex;
                justify-content: space-between;
            }}

            a {{
                color: #38bdf8;
                text-decoration: none;
            }}
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
                {"<a href='/delete_aircraft/" + str(ac.id) + "' style='color:#f87171;font-size:12px;'>Excluir</a>" if session.get("role") == "Admin" else ""}
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
        photo_url = request.form["photo_url"]
        
        if not re.match(r"^[A-Z]{2}-[A-Z]{3}$", prefix):
            return "Prefixo inválido. Use formato PR-ABC"

        if Aircraft.query.filter_by(prefix=prefix).first():
            return "Aeronave já cadastrada"

        new_aircraft = Aircraft(
            model=model,
            prefix=prefix,
            photo_url=photo_url,
           
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
            body {{
                font-family: Arial;
                background-color: #0f172a;
                color: white;
                padding: 40px;
                text-align: center;
            }}

            .box {{
                background: #1e293b;
                padding: 30px;
                border-radius: 10px;
                display: inline-block;
            }}

            button {{
                padding: 10px 20px;
                margin: 10px;
                border: none;
                border-radius: 5px;
                cursor: pointer;
            }}

            .delete {{
                background-color: #dc2626;
                color: white;
            }}

            .cancel {{
                background-color: #475569;
                color: white;
            }}

            a {{
                text-decoration: none;
                color: white;
            }}
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

    if request.method == "POST":
        description = request.form["description"]
        ata = request.form["ata"]
        tipo = request.form["tipo"]
        responsavel = request.form["responsavel"]
        photo_url = request.form.get("photo_url")

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

    panes = Pane.query.order_by(Pane.created_at.desc()).all()
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
        grouped_panes[pane.status].append(pane)

    html = f"""
    <html>
    <head>
        <title>{aircraft.prefix} - {aircraft.model}</title>
        <style>
            body {{
                font-family: 'Segoe UI', Arial, sans-serif;
                background-color: #0f172a;
                color: #f1f5f9;
                margin: 0;
                padding: 20px;
                overflow-x: hidden;
            }}

            h2, h3 {{
                color: #38bdf8;
            }}

            .container {{
                max-width: 98%;
                margin: 0 auto;
            }}

            .form-box {{
                background: #1e293b;
                padding: 30px;
                border-radius: 12px;
                box-shadow: 0 0 15px rgba(0,0,0,0.3);
                margin-bottom: 40px;
            }}

            form {{
                display: grid;
                gap: 15px;
            }}

            textarea, input, select {{
                background: #0f172a;
                color: #f1f5f9;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 10px;
                font-size: 14px;
                width: 100%;
                box-sizing: border-box;
                transition: border-color 0.3s;
            }}

            textarea:focus, input:focus, select:focus {{
                border-color: #38bdf8;
                outline: none;
            }}

            .radio-group {{
                display: flex;
                gap: 20px;
                align-items: center;
            }}

            .btn {{
                background: linear-gradient(90deg, #2563eb, #1d4ed8);
                color: white;
                border: none;
                padding: 12px;
                border-radius: 6px;
                cursor: pointer;
                font-weight: bold;
                transition: background 0.3s;
            }}

            .btn:hover {{
                background: linear-gradient(90deg, #1d4ed8, #2563eb);
            }}

            /* ===== KANBAN ===== */
            .kanban {{
                display: grid;
                grid-template-columns: repeat(7, 1fr);
                gap: 20px;
                margin-top: 30px;
                width: 100%;
                height: calc(100vh - 300px);
            }}

            .column {{
                background: #1e293b;
                border-radius: 10px;
                padding: 10px;
                display: flex;
                flex-direction: column;
                overflow-y: auto;
                box-shadow: 0 0 10px rgba(0,0,0,0.2);
            }}

            .column h4 {{
                text-align: center;
                background: #334155;
                padding: 10px;
                border-radius: 6px;
                margin-bottom: 10px;
                color: #38bdf8;
                font-size: 15px;
                position: sticky;
                top: 0;
                z-index: 1;
            }}

            .card {{
                background: #334155;
                padding: 12px;
                border-radius: 8px;
                margin-bottom: 10px;
                transition: transform 0.2s;
            }}

            .card:hover {{
                transform: scale(1.02);
            }}

            .card small {{
                color: #94a3b8;
            }}

            a {{
                color: #38bdf8;
                text-decoration: none;
            }}

            /* Scrollbar personalizada */
            .column::-webkit-scrollbar {{
                width: 6px;
            }}
            .column::-webkit-scrollbar-thumb {{
                background-color: #475569;
                border-radius: 10px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <a href="/">← Voltar</a>
            <h2>🚁 {aircraft.prefix} - {aircraft.model}</h2>

            <div class="form-box">
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
                </form>
            </div>

            <h3>Kanban de Panes</h3>
            <div class="kanban">
    """

    for status in statuses:
        html += f"<div class='column'><h4>{status}</h4>"
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
        </div>
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

    if request.method == "POST":
        action = request.form.get("action")

        # Adicionar etapa
        if action == "add_step":
            step = Step(
                pane_id=pane.id,
                description=request.form["step_desc"],
                created_by=session.get("username")
            )
            db.session.add(step)
            if pane.tipo == "Aviônico":
                pane.status = "In Progress Avi"
            elif pane.tipo == "Mecânico":
                pane.status = "In Progress Mec"

        # Adicionar pendência
        elif action == "add_pendency":
            pend = Pendencia(
                pane_id=pane.id,
                tipo_item=request.form["tipo_item"],
                tipo_aquisicao=request.form["tipo_aquisicao"],
                descricao=request.form["descricao"],
                pn=request.form["pn"],
                sms_part_request=request.form["sms_part_request"],
                task_card=request.form["task_card"],
                responsavel=request.form["responsavel"],
                created_by=session.get("username")
            )
            db.session.add(pend)
            if pend.tipo_aquisicao == "Compra":
                pane.status = "Wait Material"
            elif pend.tipo_aquisicao == "Transferência":
                pane.status = "Wait Transfer"

        # Finalizar pane
        elif action == "finalize":
            pane.status = "Finalizadas"

        db.session.commit()
        return redirect(url_for("aircraft_page", id=pane.aircraft_id))

    steps = Step.query.filter_by(pane_id=pane.id).order_by(Step.created_at.desc()).all()
    pendencias = Pendencia.query.filter_by(pane_id=pane.id).order_by(Pendencia.created_at.desc()).all()

    html = f"""
    <html>
    <head>
        <title>Pane {pane.id}</title>
        <style>
            body {{
                font-family: 'Segoe UI', Arial, sans-serif;
                background-color: #0f172a;
                color: #f1f5f9;
                padding: 40px;
            }}
            .card {{
                background: #1e293b;
                padding: 25px;
                border-radius: 12px;
                margin-bottom: 25px;
                box-shadow: 0 0 10px rgba(0,0,0,0.3);
            }}
            textarea, input, select {{
                background: #0f172a;
                color: #f1f5f9;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 10px;
                width: 100%;
                box-sizing: border-box;
                margin-top: 8px;
                transition: border-color 0.3s;
            }}
            textarea:focus, input:focus, select:focus {{
                border-color: #38bdf8;
                outline: none;
            }}
            .btn {{
                background: linear-gradient(90deg, #2563eb, #1d4ed8);
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                cursor: pointer;
                font-weight: bold;
                transition: background 0.3s;
            }}
            .btn:hover {{
                background: linear-gradient(90deg, #1d4ed8, #2563eb);
            }}
            h3 {{ color: #38bdf8; }}
            small {{ color: #94a3b8; }}
            .radio-section {{ margin-bottom: 20px; }}
            .radio-group {{
                display: flex;
                gap: 20px;
                margin-top: 10px;
            }}
            .radio-option {{
                background: #334155;
                padding: 10px 15px;
                border-radius: 8px;
                display: flex;
                align-items: center;
                gap: 8px;
                cursor: pointer;
                transition: background 0.3s, transform 0.2s;
            }}
            .radio-option:hover {{
                background: #475569;
                transform: scale(1.03);
            }}
            .radio-option input[type="radio"] {{
                accent-color: #38bdf8;
                transform: scale(1.2);
            }}
            .pane-header {{
                display: flex;
                align-items: flex-start;
                gap: 20px;
            }}
            .pane-photo {{
                width: 180px;
                height: 120px;
                border-radius: 8px;
                object-fit: cover;
                cursor: pointer;
                transition: transform 0.3s;
            }}
            .pane-photo:hover {{
                transform: scale(1.05);
            }}
            .modal {{
                display: none;
                position: fixed;
                z-index: 1000;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0, 0, 0, 0.8);
                justify-content: center;
                align-items: center;
            }}
            .modal img {{
                max-width: 90%;
                max-height: 90%;
                border-radius: 10px;
                box-shadow: 0 0 20px rgba(0,0,0,0.5);
            }}
            .close {{
                position: absolute;
                top: 30px;
                right: 50px;
                color: white;
                font-size: 30px;
                text-decoration: none;
                font-weight: bold;
                cursor: pointer;
            }}
        </style>
    </head>
    <body>
        <a href="/aircraft/{pane.aircraft_id}">← Voltar</a>
        <h2>Pane #{pane.id} - ATA {pane.ata}</h2>

        <div class="card">
            <div class="pane-header">
                <div style="flex:1;">
                    <strong>Descrição:</strong> {pane.description}<br>
                    <small>Responsável: {pane.responsavel}</small><br>
                    <small>Status atual: {pane.status}</small>
                </div>
                {"<img src='"+pane.photo_url+"' class='pane-photo' alt='foto da pane' onclick='openZoom()'>" if pane.photo_url else ""}
            </div>
        </div>

        {"<div id='zoomModal' class='modal'><span class='close' onclick='closeZoom()'>&times;</span><img src='"+pane.photo_url+"' alt='Zoom da foto'></div>" if pane.photo_url else ""}

        <div class="card">
            <h3>Etapas</h3>
    """

    for step in steps:
        html += f"<p>🛠 {step.description}<br><small>{hora_br(step.created_at)} - {step.created_by}</small></p>"

    html += """
            <form method="POST">
                <textarea name="step_desc" placeholder="Descreva a etapa" required></textarea>
                <button type="submit" name="action" value="add_step" class="btn">Salvar Etapa</button>
            </form>
        </div>

        <div class="card">
            <h3>Registrar Pendência</h3>
            <form method="POST">
                <div class="radio-section">
                    <label>Tipo do Item:</label>
                    <div class="radio-group">
                        <label class="radio-option">
                            <input type="radio" name="tipo_item" value="Ferramenta" required>
                            <span>🔧 Ferramenta</span>
                        </label>
                        <label class="radio-option">
                            <input type="radio" name="tipo_item" value="Material" required>
                            <span>📦 Material</span>
                        </label>
                    </div>
                </div>
                <div class="radio-section">
                    <label>Tipo de Aquisição:</label>
                    <div class="radio-group">
                        <label class="radio-option">
                            <input type="radio" name="tipo_aquisicao" value="Transferência" required>
                            <span>🔁 Transferência</span>
                        </label>
                        <label class="radio-option">
                            <input type="radio" name="tipo_aquisicao" value="Compra" required>
                            <span>💰 Compra</span>
                        </label>
                    </div>
                </div>
                <input name="descricao" placeholder="Descrição" required>
                <input name="pn" placeholder="P/N">
                <input name="sms_part_request" placeholder="SMS/Part Request (números e ponto)" pattern="[0-9.]+">
                <input name="task_card" placeholder="Task Card (números e hífen)" pattern="[0-9-]+">
                <input name="responsavel" placeholder="Responsável" required>
                <button type="submit" name="action" value="add_pendency" class="btn" style="background:#f59e0b;">Salvar Pendência</button>
            </form>
        </div>

        <div class="card">
            <h3>Pendências</h3>
    """

    for p in pendencias:
        html += f"<p>📦 {p.tipo_item} - {p.descricao}<br><small>{hora_br(p.created_at)} - {p.created_by}</small></p>"
    html += """
        </div>

        <form method="POST" style="text-align:center;">
            <button type="submit" name="action" value="finalize" class="btn" style="background:#16a34a;">Finalizar Pane</button>
        </form>

        <script>
        function openZoom() {
            const modal = document.getElementById('zoomModal');
            if (modal) modal.style.display = 'flex';
        }
        function closeZoom() {
            const modal = document.getElementById('zoomModal');
            if (modal) modal.style.display = 'none';
        }
        window.addEventListener('click', function(event) {
            const modal = document.getElementById('zoomModal');
            if (event.target === modal) {
                modal.style.display = 'none';
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

        new_user = User(username=username, password=password, role=role)
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
    <html>
    <head>
        <title>Login - Controle Técnico</title>
        <style>
            body {
                margin: 0;
                font-family: Arial, sans-serif;
                background: url('/static/fundo.jpg') no-repeat center center fixed;
                background-size: cover;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100%;
            }

            .login-box {
                background: rgba(0, 0, 0, 0.75);
                padding: 40px;
                border-radius: 10px;
                color: white;
                width: 300px;
                text-align: center;
                box-shadow: 0 0 20px rgba(0,0,0,0.5);
            }

            input {
                width: 100%;
                padding: 10px;
                margin: 10px 0;
                border: none;
                border-radius: 5px;
            }

            button {
                width: 100%;
                padding: 10px;
                background: #007bff;
                color: white;
                border: none;
                border-radius: 5px;
                cursor: pointer;
            }

            button:hover {
                background: #0056b3;
            }

            h2 {
                margin-bottom: 20px;
            }
        </style>
    </head>
    <body>
        <div class="login-box">
            <h2>Controle Técnico de Frota 🚁</h2>
            <form method="POST">
                <input name="username" placeholder="Usuário">
                <input type="password" name="password" placeholder="Senha">
                <button type="submit">Entrar</button>
            </form>
        </div>
    </body>
    </html>
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

# =========================
# RESETE DO BANCO DE DADOS
# =========================

@app.route("/reset_db")
def reset_db():
    db.drop_all()
    db.create_all()
    return "Banco recriado com sucesso!"













