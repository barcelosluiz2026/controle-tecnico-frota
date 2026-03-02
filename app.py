import os
import re
from datetime import datetime
from flask import Flask, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from zoneinfo import ZoneInfo

# ======================
# HORA BRASIL
# ======================

def hora_br(dt):
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M")

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ======================
# BANCO
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
    responsavel_info = db.Column(db.String(100), nullable=False)
    photo1 = db.Column(db.String(500))
    photo2 = db.Column(db.String(500))
    photo3 = db.Column(db.String(500))
    pane = db.relationship("Pane", backref="steps")

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
# HOME (ORIGINAL)
# ======================

@app.route("/")
@login_required()
def home():

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

    total_panes_abertas = Pane.query.filter(Pane.status != "Finalizadas").count()
    panes_mecanico = Pane.query.filter(Pane.status != "Finalizadas", Pane.tipo == "Mecânico").count()
    panes_avionico = Pane.query.filter(Pane.status != "Finalizadas", Pane.tipo == "Aviônico").count()

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

            a {{ color: #38bdf8; text-decoration: none; }}
        </style>
    </head>
    <body>
        <h1>🚁 Controle Técnico de Frota</h1>
    """

    for model, items in grouped.items():
        html += f"<h2>{model}</h2><div class='grid'>"
        for ac in items:
            html += f"""
            <div class='card'>
                <img src='{ac.photo_url}'>
                <a href='/aircraft/{ac.id}'>{ac.prefix}</a>
            </div>
            """
        html += "</div>"

    html += "</body></html>"
    return html

# ======================
# PANE DETAIL CORRIGIDO
# ======================

@app.route("/pane/<int:id>", methods=["GET", "POST"])
@login_required()
def pane_detail(id):

    pane = Pane.query.get_or_404(id)

    total_fotos = 0
    for s in Step.query.filter_by(pane_id=pane.id).all():
        for f in [s.photo1, s.photo2, s.photo3]:
            if f:
                total_fotos += 1

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

            if pane.status == "Pane Lançada":
                pane.status = "In Progress Mec"

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

            if pend.tipo_item == "Ferramenta":
                pane.status = "Wait Tools"
            elif pend.tipo_aquisicao == "Compra":
                pane.status = "Wait Material"
            elif pend.tipo_aquisicao == "Transferência":
                pane.status = "Wait Transfer"

        elif action == "finalize":
            pane.status = "Finalizadas"

        db.session.commit()
        return redirect(url_for("pane_detail", id=pane.id))

    steps = Step.query.filter_by(pane_id=pane.id).order_by(Step.created_at.desc()).all()
    pendencias = Pendencia.query.filter_by(pane_id=pane.id).order_by(Pendencia.created_at.desc()).all()

    html = f"<h2>Pane #{pane.id}</h2><p>Status: {pane.status}</p>"

    for s in steps:
        html += f"<p>{s.description}</p>"

    return html

# ======================
# LOGIN
# ======================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form["username"]).first()
        if user and check_password_hash(user.password, request.form["password"]):
            session["user_id"] = user.id
            session["username"] = user.username
            session["role"] = user.role
            return redirect(url_for("home"))
        return "Login inválido"

    return """
    <form method="POST">
        <input name="username">
        <input type="password" name="password">
        <button>Entrar</button>
    </form>
    """

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ======================
# INIT
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
