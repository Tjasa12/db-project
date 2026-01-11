import hashlib
import hmac
import logging
import os

import git
from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from auth import authenticate, login_manager, register_user
from db import db_read, db_write

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Logger für dieses Modul
logger = logging.getLogger(__name__)

# Load .env variables
load_dotenv()
W_SECRET = os.getenv("W_SECRET")

# Init flask app
app = Flask(__name__)
app.config["DEBUG"] = True
app.secret_key = "supersecret"

# Init auth
login_manager.init_app(app)
login_manager.login_view = "login"

# DON'T CHANGE
def is_valid_signature(x_hub_signature, data, private_key):
    hash_algorithm, github_signature = x_hub_signature.split('=', 1)
    algorithm = hashlib.__dict__.get(hash_algorithm)
    encoded_key = bytes(private_key, 'latin-1')
    mac = hmac.new(encoded_key, msg=data, digestmod=algorithm)
    return hmac.compare_digest(mac.hexdigest(), github_signature)

# DON'T CHANGE
@app.post('/update_server')
def webhook():
    x_hub_signature = request.headers.get('X-Hub-Signature')
    if is_valid_signature(x_hub_signature, request.data, W_SECRET):
        repo = git.Repo('./mysite')
        origin = repo.remotes.origin
        origin.pull()
        return 'Updated PythonAnywhere successfully', 200
    return 'Unathorized', 401

# Auth routes
@app.route("/login", methods=["GET", "POST"])
def login():

    error = None

    if request.method == "POST":
        user = authenticate(
            request.form["username"],
            request.form["password"]
        )

        if user:
            login_user(user)
            return redirect(url_for("index"))

        error = "Benutzername oder Passwort ist falsch."

    return render_template(
        "auth.html",
        title="In dein Konto einloggen",
        action=url_for("login"),
        button_label="Einloggen",
        error=error,
        footer_text="Noch kein Konto?",
        footer_link_url=url_for("register"),
        footer_link_label="Registrieren"
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    error = None

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        ok = register_user(username, password)
        if ok:
            return redirect(url_for("login"))

        error = "Benutzername existiert bereits."

    return render_template(
        "auth.html",
        title="Neues Konto erstellen",
        action=url_for("register"),
        button_label="Registrieren",
        error=error,
        footer_text="Du hast bereits ein Konto?",
        footer_link_url=url_for("login"),
        footer_link_label="Einloggen"
    )

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))



# App routes
# @app.route("/", methods=["GET", "POST"])
# @login_required
# def index():
#     # GET
#     if request.method == "GET":
#         todos = db_read("SELECT id, content, due FROM todos WHERE user_id=%s ORDER BY due", (current_user.id,))
#         return render_template("main_page.html", todos=todos)

#     # POST
#     content = request.form["contents"]
#     due = request.form["due_at"]
#     db_write("INSERT INTO todos (user_id, content, due) VALUES (%s, %s, %s)", (current_user.id, content, due, ))
#     return redirect(url_for("index"))


# App routes
@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    # GET
    Test = "Hallo"
    if request.method == "GET":
        return render_template("willkommen.html",Template_test=Test)

# App routes
@app.route("/zutaten", methods=["GET", "POST"])
@login_required
def zutaten():
    # GET
    if request.method == "GET":
        try:
            row = db_read(
                "SELECT * FROM Zutaten;")
            logger.debug("Zutaten DB-Ergebnis: %r", row)
        except Exception:
            logger.exception("Fehler bei Zutaten abfrage")
            return None

        return render_template("zutaten.html", zutaten=row)

@app.route("/backstube", methods=["GET"])
@login_required
def backstube():
    rezepte = db_read("""
        SELECT r.id, r.titel, r.link, r.website_name
        FROM Backstube b
        JOIN Rezepte r ON r.id = b.rezept_id
        WHERE b.user_id = %s
        ORDER BY b.created_at DESC
    """, (current_user.id,))

    return render_template("backstube.html", rezepte=rezepte)




@app.post("/complete")
@login_required
def complete():
    todo_id = request.form.get("id")
    db_write("DELETE FROM todos WHERE user_id=%s AND id=%s", (current_user.id, todo_id,))
    return redirect(url_for("index"))


@app.route("/rezepte", methods=["POST"])
@login_required
def rezepte():
    selected_ids = request.form.getlist("zutat_ids")

    if not selected_ids:
        return render_template(
            "rezepte.html",
            exact=[],
            almost=[],
            message="Bitte wähle mindestens eine Zutat aus."
        )

    selected_ids = [int(x) for x in selected_ids]
    placeholders = ",".join(["%s"] * len(selected_ids))

    # 1) Exakt passende Rezepte (missing = 0)
    sql_exact = f"""
        SELECT
            r.id, r.titel, r.link, r.website_name,
            (COUNT(*) - SUM(rz.zutat_id IN ({placeholders}))) AS missing
        FROM Rezepte r
        JOIN Rezept_Zutaten rz ON rz.rezept_id = r.id
        GROUP BY r.id, r.titel, r.link, r.website_name
        HAVING missing = 0
        ORDER BY r.titel;
    """
    exact = db_read(sql_exact, tuple(selected_ids))

    # 2) Fast passende Rezepte (missing > 0)
    sql_almost = f"""
        SELECT
            r.id, r.titel, r.link, r.website_name,
            (COUNT(*) - SUM(rz.zutat_id IN ({placeholders}))) AS missing
        FROM Rezepte r
        JOIN Rezept_Zutaten rz ON rz.rezept_id = r.id
        GROUP BY r.id, r.titel, r.link, r.website_name
        HAVING missing > 0
        ORDER BY missing ASC, r.titel
        LIMIT 10;
    """
    almost = db_read(sql_almost, tuple(selected_ids))

    return render_template(
        "rezepte.html",
        exact=exact,
        almost=almost,
        message="Hier sind deine Ergebnisse:"
    )

@app.post("/backstube/toggle")
@login_required
def backstube_toggle():
    rezept_id = int(request.form["rezept_id"])

    # Prüfen ob schon drin
    existing = db_read(
        "SELECT 1 FROM Backstube WHERE user_id=%s AND rezept_id=%s",
        (current_user.id, rezept_id)
    )

    if existing:
        db_write(
            "DELETE FROM Backstube WHERE user_id=%s AND rezept_id=%s",
            (current_user.id, rezept_id)
        )
        return {"saved": False}

    db_write(
        "INSERT INTO Backstube (user_id, rezept_id) VALUES (%s, %s)",
        (current_user.id, rezept_id)
    )
    return {"saved": True}


if __name__ == "__main__":
    app.run()

