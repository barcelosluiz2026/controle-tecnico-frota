import os
import re
from datetime import datetime
from flask import Flask, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
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
# PANE DETAIL CORRIGIDO
# ======================

@app.route("/pane/<int:id>", methods=["GET", "POST"])
@login_required()
def pane_detail(id):

    pane = Pane.query.get_or_404(id)

    # Contar fotos totais
    total_fotos = 0
    for s in Step.query.filter_by(pane_id=pane.id).all():
        for f in [s.photo1, s.photo2, s.photo3]:
            if f:
                total_fotos += 1

    # ======================
    # POST
    # ======================
    if request.method == "POST":

        action = request.form.get("action")

        # NOVA ETAPA
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

        # NOVA PENDÊNCIA
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

        # FINALIZAR
        elif action == "finalize":
            pane.status = "Finalizadas"

        db.session.commit()
        return redirect(url_for("pane_detail", id=pane.id))

    # ======================
    # LISTAS
    # ======================

    steps = Step.query.filter_by(
        pane_id=pane.id
    ).order_by(Step.created_at.desc()).all()

    pendencias = Pendencia.query.filter_by(
        pane_id=pane.id
    ).order_by(Pendencia.created_at.desc()).all()

    # HTML SIMPLES FUNCIONAL
    html = f"""
    <h2>Pane #{pane.id} - ATA {pane.ata}</h2>
    <p>Status: {pane.status}</p>
    <p>Fotos: {total_fotos}/4</p>
    <hr>

    <h3>Etapas</h3>
    """

    for s in steps:
        html += f"""
        <div>
            <b>{s.description}</b><br>
            {hora_br(s.created_at)} - {s.created_by}
            <hr>
        </div>
        """

    html += f"""
    <form method="POST">
        <textarea name="step_desc" placeholder="Descrever etapa" required></textarea><br>
        <input name="responsavel_info" placeholder="Responsável" required><br>
        <input name="photo1" placeholder="Foto 1"><br>
        <input name="photo2" placeholder="Foto 2"><br>
        <input name="photo3" placeholder="Foto 3"><br>
        <button type="submit" name="action" value="add_step">Salvar Etapa</button>
    </form>
    <hr>

    <h3>Pendências</h3>
    """

    for p in pendencias:
        html += f"""
        <div>
            <b>{p.tipo_item}</b> - {p.descricao}<br>
            {hora_br(p.created_at)} - {p.created_by}
            <hr>
        </div>
        """

    html += """
    <form method="POST">
        <input name="descricao" placeholder="Descrição" required><br>
        <input name="responsavel" placeholder="Responsável" required><br>
        <input type="radio" name="tipo_item" value="Ferramenta" required> Ferramenta
        <input type="radio" name="tipo_item" value="Material" required> Material<br>
        <input type="radio" name="tipo_aquisicao" value="Transferência" required> Transferência
        <input type="radio" name="tipo_aquisicao" value="Compra" required> Compra<br>
        <button type="submit" name="action" value="add_pendencia">Salvar Pendência</button>
    </form>

    <form method="POST">
        <button type="submit" name="action" value="finalize">Finalizar Pane</button>
    </form>
    """

    return html

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
