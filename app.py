from flask import Flask, render_template, request, redirect, session, url_for, g, flash
import sqlite3
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = "replace-with-a-strong-random-secret"
app.permanent_session_lifetime = timedelta(days=30)
from datetime import datetime

@app.context_processor
def inject_datetime():
    return {'datetime': datetime}


DATABASE = "medicines.db"


# ---------- DB helper ----------
def get_db():
    if hasattr(g, '_db'):
        return g._db
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    g._db = conn
    return conn


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_db', None)
    if db is not None:
        db.close()


def init_db():
    conn = get_db()
    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS medicine (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        expiry_date TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """)
    conn.commit()


@app.before_request
def startup():
    if not hasattr(g, 'db_initialized'):
        init_db()
        g.db_initialized = True


# ---------- Authentication ----------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please login to access that page.", "warning")
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated_function


def get_current_user():
    if 'user_id' in session:
        conn = get_db()
        user = conn.execute("SELECT id, username FROM users WHERE id = ?", (session['user_id'],)).fetchone()
        return user
    return None


# ---------- Auth routes ----------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == "POST":
        username = request.form['username'].strip()
        password = request.form['password']
        confirm = request.form['confirm_password']

        if not username or not password:
            flash("Please provide both username and password.", "danger")
            return render_template("signup.html")

        if password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("signup.html")

        password_hash = generate_password_hash(password)
        conn = get_db()
        try:
            conn.execute("INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                         (username, password_hash, datetime.utcnow().isoformat()))
            conn.commit()
            flash("Account created! Please login.", "success")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Username already taken. Try another.", "danger")
            return render_template("signup.html")
    return render_template("signup.html")


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == "POST":
        username = request.form['username'].strip()
        password = request.form['password']
        remember = request.form.get('remember') == "on"

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session.permanent = remember
            flash(f"Welcome back, {user['username']}!", "success")
            next_page = request.args.get('next') or url_for('dashboard')
            return redirect(next_page)
        else:
            flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for('login'))


# ---------- Medicine Routes ----------
@app.route('/')
def root():
    return redirect('/dashboard')


@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db()
    c = conn.cursor()
    uid = session['user_id']

    c.execute("SELECT COUNT(*) FROM medicine WHERE user_id = ?", (uid,))
    total = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM medicine WHERE expiry_date <= DATE('now') AND user_id = ?", (uid,))
    expired = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM medicine WHERE expiry_date <= DATE('now','+30 day') AND expiry_date > DATE('now') AND user_id = ?", (uid,))
    near = c.fetchone()[0]

    return render_template("index.html", total_count=total, expired_count=expired, near_expiry=near, user=get_current_user())


@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_medicine():
    if request.method == 'POST':
        name = request.form['name']
        expiry_date = request.form['expiry_date']
        quantity = request.form['quantity']

        conn = get_db()
        conn.execute("INSERT INTO medicine (name, expiry_date, quantity, user_id) VALUES (?, ?, ?, ?)",
                    (name, expiry_date, quantity, session['user_id']))
        conn.commit()
        flash("Medicine added.", "success")
        return redirect('/view')

    return render_template("add_medicine.html", user=get_current_user())


@app.route('/view')
@login_required
def view_medicines():
    user = get_current_user()  # get logged-in user details
    query = request.args.get('q', '').strip().lower()
    conn = get_db()

    # 🔒 Only fetch medicines belonging to the logged-in user
    medicines = conn.execute(
        "SELECT * FROM medicine WHERE user_id = ? ORDER BY expiry_date ASC",
        (user['id'],)
    ).fetchall()

    updated_list = []
    today = datetime.today().date()
    near_limit = today + timedelta(days=30)

    for med in medicines:
        expiry = datetime.strptime(med['expiry_date'], "%Y-%m-%d").date()
        if expiry < today:
            status = "expired"
        elif today <= expiry <= near_limit:
            status = "near"
        else:
            status = "safe"

        med_dict = {
            "id": med["id"],
            "name": med["name"],
            "expiry_date": med["expiry_date"],
            "quantity": med["quantity"],
            "status": status
        }

        # 🔍 Apply search filtering
        if not query or query in med["name"].lower():
            updated_list.append(med_dict)

    return render_template("view_medicines.html", medicines=updated_list, query=query)


@app.route('/near-expiry')
@login_required
def near_expiry():
    conn = get_db()
    threshold = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
    now = datetime.now().strftime('%Y-%m-%d')
    rows = conn.execute(
        "SELECT id, name, expiry_date, quantity FROM medicine WHERE expiry_date <= ? AND expiry_date >= ? AND user_id = ?",
        (threshold, now, session['user_id'])
    ).fetchall()
    return render_template("view_medicines.html", medicines=[dict(r) for r in rows], user=get_current_user())


@app.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_medicine(id):
    conn = get_db()

    if request.method == "POST":
        name = request.form["name"]
        expiry_date = request.form["expiry_date"]
        quantity = request.form["quantity"]

        conn.execute("UPDATE medicine SET name=?, expiry_date=?, quantity=? WHERE id=? AND user_id=?",
                     (name, expiry_date, quantity, id, session['user_id']))
        conn.commit()
        flash("Medicine updated successfully.", "success")
        return redirect("/view")

    med = conn.execute("SELECT * FROM medicine WHERE id=? AND user_id=?", (id, session['user_id'])).fetchone()
    return render_template("edit_medicine.html", med=med, user=get_current_user())


@app.route("/delete/<int:id>")
@login_required
def delete_medicine(id):
    conn = get_db()
    conn.execute("DELETE FROM medicine WHERE id=? AND user_id=?", (id, session['user_id']))
    conn.commit()
    flash("Medicine deleted.", "info")
    return redirect("/view")


# ---------- Run ----------
if __name__ == "__main__":
    app.run(debug=True)
