import os
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# ==========================================
# CONFIGURAÇÃO APP
# ==========================================

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey")

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

# ==========================================
# MODELOS
# ==========================================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default="User")  # Admin ou User


class Aircraft(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    model = db.Column(db.String(100), nullable=False)
    prefix = db.Column(db.String(50), nullable=False)
    photo_url = db.Column(db.String(300))
    status = db.Column(db.String(50))


# ==========================================
# LOGIN MANAGER
# ==========================================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ==========================================
# ROTAS
# ==========================================

@app.route("/")
@login_required
def dashboard():
    aircrafts = Aircraft.query.order_by(Aircraft.prefix.asc()).all()
    return render_template("dashboard.html", aircrafts=aircrafts)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for("dashboard"))
        else:
            flash("Usuário ou senha incorretos")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/add_aircraft", methods=["GET", "POST"])
@login_required
def add_aircraft():
    if request.method == "POST":
        try:
            model = request.form.get("model")
            prefix = request.form.get("prefix")
            photo_url = request.form.get("photo_url")
            status = request.form.get("status")

            new_aircraft = Aircraft(
                model=model,
                prefix=prefix,
                photo_url=photo_url,
                status=status
            )

            db.session.add(new_aircraft)
            db.session.commit()

            return redirect(url_for("dashboard"))

        except Exception as e:
            db.session.rollback()
            return f"Erro interno: {e}"

    return render_template("add_aircraft.html")


@app.route("/delete_aircraft/<int:id>")
@login_required
def delete_aircraft(id):
    if current_user.role != "Admin":
        return "Acesso negado"

    aircraft = Aircraft.query.get_or_404(id)
    db.session.delete(aircraft)
    db.session.commit()

    return redirect(url_for("dashboard"))


# ==========================================
# CRIAR ADMIN AUTOMATICAMENTE (PRIMEIRA EXECUÇÃO)
# ==========================================

@app.before_first_request
def create_tables():
    db.create_all()

    if not User.query.filter_by(username="admin").first():
        admin = User(
            username="admin",
            password=generate_password_hash("admin123"),
            role="Admin"
        )
        db.session.add(admin)
        db.session.commit()
        print("Admin criado: admin / admin123")


# ==========================================
# EXECUÇÃO LOCAL
# ==========================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))



