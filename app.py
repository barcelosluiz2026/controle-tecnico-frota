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
    return dt.astimezone(
        ZoneInfo("America/Sao_Paulo")
    ).strftime("%d/%m/%Y %H:%M")


app = Flask(__name__)
app.secret_key = "supersecretkey"

# ======================
# BANCO DE DADOS
# ======================

database_url = os.getenv("DATABASE_URL")

if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace(
        "postgres://", "postgresql://", 1
    )

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ======================
# MODELOS
# ======================


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(
        db.String(100), unique=True, nullable=False
    )
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(50), nullable=False)


class Aircraft(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    model = db.Column(db.String(50), nullable=False)
    prefix = db.Column(
        db.String(10), unique=True, nullable=False
    )
    photo_url = db.Column(db.String(500))


class Pane(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    aircraft_id = db.Column(
        db.Integer,
        db.ForeignKey("aircraft.id"),
        nullable=False,
    )
    description = db.Column(db.Text, nullable=False)
    ata = db.Column(db.String(2), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)
    responsavel = db.Column(
        db.String(100), nullable=False
    )
    photo_url = db.Column(db.String(500))
    status = db.Column(
        db.String(50), default="Pane Lançada"
    )
    created_at = db.Column(
        db.DateTime, default=datetime.utcnow
    )
    created_by = db.Column(db.String(100))

    aircraft = db.relationship(
        "Aircraft", backref="panes"
    )


class Step(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pane_id = db.Column(
        db.Integer,
        db.ForeignKey("pane.id"),
        nullable=False,
    )
    description = db.Column(
        db.Text, nullable=False
    )
    created_at = db.Column(
        db.DateTime, default=datetime.utcnow
    )
    created_by = db.Column(db.String(100))
    responsavel_info = db.Column(
        db.String(100), nullable=False
    )
    photo1 = db.Column(db.String(500))
    photo2 = db.Column(db.String(500))
    photo3 = db.Column(db.String(500))

    pane = db.relationship(
        "Pane", backref="steps"
    )


class Pendencia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pane_id = db.Column(
        db.Integer,
        db.ForeignKey("pane.id"),
        nullable=False,
    )
    tipo_item = db.Column(
        db.String(20), nullable=False
    )
    tipo_aquisicao = db.Column(
        db.String(20), nullable=False
    )
    descricao = db.Column(
        db.Text, nullable=False
    )
    pn = db.Column(db.String(50))
    sms_part_request = db.Column(db.String(20))
    task_card = db.Column(db.String(20))
    responsavel = db.Column(db.String(100))
    created_at = db.Column(
        db.DateTime, default=datetime.utcnow
    )
    created_by = db.Column(db.String(100))

    pane = db.relationship(
        "Pane", backref="pendencias"
    )

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
    # LISTAGEM AERONAVES
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
                margin-top:40px;
                font-size:24px;
                border-bottom:2px solid #1e293b;
                padding-bottom:10px;
            }}
            .grid {{
                display:grid;
                grid-template-columns: repeat(7, 1fr);
                gap:15px;
                margin-top:20px;
            }}
            .card {{
                background:#1e293b;
                padding:10px;
                border-radius:8px;
                text-align:center;
            }}
            .card img {{
                width:100%;
                height:100px;
                object-fit:cover;
                border-radius:6px;
            }}
            .prefix {{
                font-weight:bold;
                margin-top:5px;
            }}
            .top-bar {{
                display:flex;
                justify-content:space-between;
            }}
            a {{
                color:#38bdf8;
                text-decoration:none;
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
    # GRID AERONAVES
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
    <body style="background:#0f172a;color:white;padding:40px;text-align:center;">
        <h2>Confirmar Exclusão</h2>
        <p>Deseja excluir {aircraft.prefix} - {aircraft.model}?</p>
        <form method="POST">
            <button type="submit">Excluir</button>
            <a href="{url_for('home')}">Cancelar</a>
        </form>
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

    panes = Pane.query.filter_by(
        aircraft_id=aircraft.id
    ).order_by(
        Pane.created_at.desc()
    ).all()

    html = f"""
    <html>
    <body style="background:#0f172a;color:white;padding:40px;">
        <a href="/">← Voltar</a>
        <h2>{aircraft.prefix} - {aircraft.model}</h2>
    """

    for pane in panes:
        html += f"""
        <div style="background:#1e293b;padding:15px;margin-bottom:10px;border-radius:8px;">
            <strong>ATA {pane.ata}</strong><br>
            {pane.description}<br>
            Status: {pane.status}<br>
            <a href="/pane/{pane.id}">Abrir</a>
        </div>
        """

    html += "</body></html>"

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

        if action == "add_step":

            step = Step(
                pane_id=pane.id,
                description=request.form.get("step_desc"),
                responsavel_info=request.form.get("responsavel_info"),
                photo1=request.form.get("photo1"),
                photo2=request.form.get("photo2"),
                photo3=request.form.get("photo3"),
                created_by=session.get("username")
            )

            db.session.add(step)

        elif action == "add_pendencia":

            pend = Pendencia(
                pane_id=pane.id,
                tipo_item=request.form["tipo_item"],
                tipo_aquisicao=request.form["tipo_aquisicao"],
                descricao=request.form["descricao"],
                pn=request.form.get("pn"),
                sms_part_request=request.form.get("sms_part_request"),
                task_card=request.form.get("task_card"),
                responsavel=request.form["responsavel"],
                created_by=session.get("username")
            )

            db.session.add(pend)

        elif action == "finalize":
            pane.status = "Finalizadas"

        db.session.commit()
        return redirect(url_for("pane_detail", id=pane.id))

    steps = Step.query.filter_by(
        pane_id=pane.id
    ).order_by(
        Step.created_at.desc()
    ).all()

    pendencias = Pendencia.query.filter_by(
        pane_id=pane.id
    ).order_by(
        Pendencia.created_at.desc()
    ).all()

    html = f"""
    <html>
    <body style="background:#0f172a;color:white;padding:40px;">
        <a href="/aircraft/{pane.aircraft_id}">← Voltar</a>
        <h2>Pane #{pane.id} - ATA {pane.ata}</h2>
        <div style="background:#1e293b;padding:20px;border-radius:10px;margin-bottom:20px;">
            {pane.description}<br>
            Status: {pane.status}
        </div>
    """

    for step in steps:
        html += f"""
        <div style="background:#334155;padding:15px;margin-bottom:10px;border-radius:8px;">
            {step.description}<br>
            Info: {step.responsavel_info}
        </div>
        """

    html += "</body></html>"

    return html


# ======================
# REGISTER
# ======================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form["username"]
        password = generate_password_hash(
            request.form["password"]
        )
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
            <option value="Tecnico">Tecnico</option>
            <option value="Inspetor">Inspetor</option>
            <option value="Visualizador">Visualizador</option>
        </select><br><br>
        <button type="submit">Cadastrar</button>
    </form>
    """


# ======================
# LOGIN
# ======================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(
            username=username
        ).first()

        if user and check_password_hash(user.password, password):
            session["user_id"] = user.id
            session["username"] = user.username
            session["role"] = user.role
            return redirect(url_for("home"))

        return "Login inválido"

    return """
    <h2>Controle Técnico de Frota 🚁</h2>
    <form method="POST">
        <input name="username" placeholder="Usuário"><br>
        <input type="password" name="password" placeholder="Senha"><br>
        <button type="submit">Entrar</button>
    </form>
    """


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ======================
# RESET DB
# ======================

@app.route("/reset_db")
def reset_db():
    db.drop_all()
    db.create_all()
    return "Banco recriado com sucesso!"
