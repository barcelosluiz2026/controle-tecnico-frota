import os
from flask import Flask, request, redirect, url_for, session, render_template_string
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Banco de dados
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ======================
# MODELO DE USUÁRIO
# ======================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(50), nullable=False)

# ======================
# DECORATOR DE LOGIN
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
# ROTAS
# ======================

@app.route("/")
@login_required()
def home():
    return f"""
    <h1>Controle Técnico de Frota ✈️</h1>
    <p>Usuário: {session['username']}</p>
    <p>Perfil: {session['role']}</p>
    <a href='/logout'>Sair</a>
    """

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
    <h2>Login</h2>
    <form method="POST">
        Usuário: <input name="username"><br>
        Senha: <input type="password" name="password"><br><br>
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
