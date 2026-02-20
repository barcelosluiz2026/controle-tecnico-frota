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
    model = db.Column(db.String(100), nullable=False)
    prefix = db.Column(db.String(10), unique=True, nullable=False)
    photo_url = db.Column(db.String(500))
    
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

    aircraft_list = Aircraft.query.order_by(Aircraft.prefix.asc()).all()

    grouped = defaultdict(list)
    for a in aircraft_list:
        grouped[a.model].append(a)

    html = f"""
    <h1>Controle Técnico de Frota 🚁</h1>
    <p>Usuário: {session['username']} | Perfil: {session['role']}</p>
    <a href='/add_aircraft'>Cadastrar Helicóptero</a> |
    <a href='/logout'>Sair</a>
    <hr>
    """

    for model, aircrafts in grouped.items():
        html += f"<h2>{model}</h2>"
        html += "<div style='display:grid; grid-template-columns: repeat(7, 1fr); gap:15px;'>"

        for a in aircrafts:
            html += f"""
            <div style='border:1px solid #ccc; padding:10px; text-align:center;'>
                <img src='{a.photo_url}' width='100'><br>
                <strong>{a.prefix}</strong><br>
                
            """

            if session["role"] == "Admin":
                html += f"<a href='/delete_aircraft/{a.id}'>Excluir</a>"

            html += "</div>"

        html += "</div><br>"

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

@app.route("/delete_aircraft/<int:id>")
@login_required("Admin")
def delete_aircraft(id):
    aircraft = Aircraft.query.get_or_404(id)
    db.session.delete(aircraft)
    db.session.commit()
    return redirect(url_for("home"))

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
                height: 100vh;
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



