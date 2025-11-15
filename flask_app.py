from flask import Flask, redirect, render_template, request, url_for
from mysql.connector import pooling
from dotenv import load_dotenv
import os
import git
import hmac
import hashlib

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_DATABASE")
}
W_SECRET = os.getenv("W_SECRET")

app = Flask(__name__)
app.config["DEBUG"] = True

pool = pooling.MySQLConnectionPool(pool_name="pool", pool_size=5, **DB_CONFIG)

def get_conn():
    return pool.get_connection()

def is_valid_signature(x_hub_signature, data, private_key):
    hash_algorithm, github_signature = x_hub_signature.split('=', 1)
    algorithm = hashlib.__dict__.get(hash_algorithm)
    encoded_key = bytes(private_key, 'latin-1')
    mac = hmac.new(encoded_key, msg=data, digestmod=algorithm)
    return hmac.compare_digest(mac.hexdigest(), github_signature)

@app.post('/update_server')
def webhook():
    x_hub_signature = request.headers.get('X-Hub-Signature')
    if is_valid_signature(x_hub_signature, request.data, W_SECRET):
        repo = git.Repo('./mysite')
        origin = repo.remotes.origin
        origin.pull()
        return 'Updated PythonAnywhere successfully', 200
    return 'Unathorized', 401

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        conn = get_conn()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT id, content, due FROM todos ORDER BY due")
            todos = cur.fetchall()
        finally:
            try:
                cur.close()
            except:
                pass
            conn.close()

        return render_template("main_page.html", todos=todos)

    # POST
    content = request.form["contents"]
    due = request.form["due_at"]
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO todos (content, due) VALUES (%s, %s)", (content, due, ))
        conn.commit()
    finally:
        try:
            cur.close()
        except:
            pass
        conn.close()

    return redirect(url_for("index"))

@app.post("/complete")
def complete():

    # POST
    todo_id = request.form.get("id")
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM todos WHERE id=%s", (todo_id,))
        conn.commit()
    finally:
        try:
            cur.close()
        except:
            pass
        conn.close()

    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run()
