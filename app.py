import os
import re
from flask import Flask, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from collections import defaultdict

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
    status = db.Column(db.String(50), default="Aberta")
    aircraft = db.relationship("Aircraft", backref="panes")
    
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
    aircrafts = Aircraft.query.order_by(Aircraft.model, Aircraft.prefix).all()

    grouped = {}
    for ac in aircrafts:
        grouped.setdefault(ac.model, []).append(ac)

    html = """
    <html>
    <head>
        <title>Controle Técnico</title>
        <style>
            body {
                font-family: Arial;
                background-color: #0f172a;
                color: white;
                padding: 20px;
            }

            .model-title {
                margin-top: 40px;
                font-size: 24px;
                border-bottom: 2px solid #1e293b;
                padding-bottom: 10px;
            }

            .grid {
                display: grid;
                grid-template-columns: repeat(7, 1fr);
                gap: 15px;
                margin-top: 20px;
            }

            .card {
                background: #1e293b;
                padding: 10px;
                border-radius: 8px;
                text-align: center;
            }

            .card img {
                width: 100%;
                height: 100px;
                object-fit: cover;
                border-radius: 6px;
            }

            .prefix {
                font-weight: bold;
                margin-top: 5px;
            }

            .top-bar {
                display:flex;
                justify-content: space-between;
            }

            a {
                color: #38bdf8;
                text-decoration: none;
            }

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
    """

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
            status="Pane Lançada"
        )

        db.session.add(new_pane)
        db.session.commit()

        return redirect(url_for("aircraft_page", id=aircraft.id))

    panes = Pane.query.filter_by(aircraft_id=aircraft.id).all()

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
                font-family: Arial, sans-serif;
                background-color: #0f172a;
                color: white;
                margin: 0;
                padding: 40px;
            }}

            .container {{
                max-width: 1200px;
                margin: 0 auto;
            }}

            .top {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 30px;
            }}

            .btn {{
                padding: 10px 20px;
                background: #2563eb;
                color: white;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                font-size: 14px;
            }}

            .btn:hover {{
                background: #1d4ed8;
            }}

            .form-box {{
                background: #1e293b;
                padding: 25px;
                border-radius: 10px;
                margin-bottom: 40px;
            }}

            form {{
                display: flex;
                flex-direction: column;
                gap: 15px;
            }}

            textarea, input {{
                width: 100%;
                padding: 10px;
                border-radius: 5px;
                border: none;
                box-sizing: border-box;
            }}

            .row-flex {{
                display: flex;
                gap: 15px;
                align-items: center;
            }}

            .radio-group {{
                display: flex;
                gap: 20px;
                align-items: center;
            }}

            .radio-group label {{
                display: flex;
                align-items: center;
                gap: 6px;
            }}

            .kanban {{
                display: grid;
                grid-template-columns: repeat(7, 1fr);
                gap: 15px;
                overflow-x: auto;
            }}

            .column {{
                background: #1e293b;
                border-radius: 8px;
                padding: 10px;
                min-width: 200px;
            }}

            .column h4 {{
                text-align: center;
                background: #334155;
                padding: 8px;
                border-radius: 5px;
                margin-bottom: 10px;
            }}

            .card {{
                background: #334155;
                padding: 10px;
                border-radius: 6px;
                margin-bottom: 10px;
            }}

            .card img {{
                margin-top: 8px;
                border-radius: 5px;
                max-width: 100%;
            }}

            a {{
                color: #38bdf8;
                text-decoration: none;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="top">
                <a href="/">← Voltar</a>
                <h2>🚁 {aircraft.prefix} - {aircraft.model}</h2>
            </div>

            <div class="form-box">
                <h3>Registrar Nova Pane</h3>
                <form method="POST">
                    <textarea name="description" placeholder="Descrição da Pane" required></textarea>
                    <div class="row-flex">
                        <input name="ata" placeholder="ATA (2 dígitos)" type="number" min="0" max="99" required>
                        <div class="radio-group">
                            <label><input type="radio" name="tipo" value="Mecânico" required> Mecânico</label>
                            <label><input type="radio" name="tipo" value="Aviônico" required> Aviônico</label>
                        </div>
                    </div>
                    <input name="responsavel" placeholder="Responsável pela informação" required>
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
            <div class='card'>
                <strong>ATA {pane.ata} - {pane.tipo}</strong><br>
                <small>Responsável: {pane.responsavel}</small>
                <p>{pane.description}</p>
                {"<img src='"+pane.photo_url+"' alt='foto da pane'>" if pane.photo_url else ""}
            </div>
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































