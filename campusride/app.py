from flask import Flask, request, redirect, url_for, session, render_template_string, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import psycopg2
import psycopg2.extras
import html

app = Flask(__name__)
app.secret_key = "campusride-local-secret"

# pgAdmin connection values
DB_NAME = "CampusRide"
DB_USER = "postgres"
DB_PASSWORD = "yumami123"
DB_HOST = "localhost"
DB_PORT = "5432"

# Demo login passwords for the already inserted project users.
# They are written to the database as password_hash values, not as plain text.
ADMIN_BOOTSTRAP_PASSWORDS = {
    "miray35": "MirayRide2026!",
    "badenur48": "BadenurRide2026!",
    "iclal26": "IclalRide2026!",
}

SEED_USER_PASSWORD = "CampusRide2026!"
MIN_PASSWORD_LENGTH = 8


def get_connection():
    return psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
    )


def query_all(sql, params=()):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()
        return rows
    finally:
        conn.close()


def query_one(sql, params=()):
    rows = query_all(sql, params)
    return rows[0] if rows else None


def execute(sql, params=()):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        affected = cur.rowcount
        conn.commit()
        cur.close()
        return affected
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def esc(v):
    return "" if v is None else html.escape(str(v))


def init_database():
    conn = get_connection()
    try:
        cur = conn.cursor()

        # Authentication support for the web app.
        # The project schema stays the same; we only add a hashed password field to User.
        cur.execute('ALTER TABLE "User" ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);')

        # Assign strong demo passwords to existing admin users.
        for username, plain_password in ADMIN_BOOTSTRAP_PASSWORDS.items():
            cur.execute(
                'UPDATE "User" SET password_hash=%s WHERE user_name=%s;',
                (generate_password_hash(plain_password), username),
            )

        # Existing non-admin demo users also need a valid hashed password.
        cur.execute(
            'UPDATE "User" SET password_hash=%s WHERE (password_hash IS NULL OR password_hash = %s) AND user_name NOT IN (%s, %s, %s);',
            (generate_password_hash(SEED_USER_PASSWORD), "", "miray35", "badenur48", "iclal26"),
        )

        cur.execute("ALTER TABLE post ADD COLUMN IF NOT EXISTS destination VARCHAR(100);")
        cur.execute("UPDATE post SET destination = 'Destination not specified' WHERE destination IS NULL;")

        cur.execute("ALTER TABLE offer ADD COLUMN IF NOT EXISTS cost NUMERIC(10,2);")
        cur.execute("ALTER TABLE offer ADD COLUMN IF NOT EXISTS plate_number VARCHAR(20);")

        # Backfill old offer rows if this app is used on a database created before Offer.cost and Offer.plate_number.
        cur.execute("""
            UPDATE offer o
            SET cost = r.cost
            FROM ride r
            WHERE r.offer_ID = o.offer_ID
              AND o.cost IS NULL;
        """)
        cur.execute("""
            UPDATE offer o
            SET plate_number = r.plate_number
            FROM ride r
            WHERE r.offer_ID = o.offer_ID
              AND o.plate_number IS NULL;
        """)
        cur.execute("""
            UPDATE offer o
            SET plate_number = (
                SELECT c.plate_number
                FROM car c
                WHERE c.driver_ID = o.driver_ID
                ORDER BY c.plate_number
                LIMIT 1
            )
            WHERE o.plate_number IS NULL;
        """)
        cur.execute("UPDATE offer SET cost = 1000.00 WHERE cost IS NULL;")

        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_offer_post_driver ON offer(post_ID, driver_ID);")
        cur.execute(
            "SELECT setval(pg_get_serial_sequence('\"User\"', 'user_id'), "
            "COALESCE((SELECT MAX(user_ID) FROM \"User\"), 1));"
        )

        conn.commit()
        cur.close()
    finally:
        conn.close()


def current_user():
    if "user_id" not in session:
        return None
    return query_one(
        'SELECT user_ID AS user_id, email, user_name, phone_number, name, surname, gender FROM "User" WHERE user_ID=%s;',
        (session["user_id"],),
    )


def has_role(user_id, role):
    table = role.lower()
    if table not in ["admin", "passenger", "driver"]:
        return False
    return query_one(f"SELECT 1 FROM {table} WHERE user_ID=%s;", (user_id,)) is not None


def roles_of(user_id):
    roles = []
    if has_role(user_id, "admin"):
        roles.append("Admin")
    if has_role(user_id, "passenger"):
        roles.append("Passenger")
    if has_role(user_id, "driver"):
        roles.append("Driver")
    return roles


def permissions_of(user_id):
    rows = query_all("SELECT permission FROM adminpermission WHERE user_ID=%s ORDER BY permission;", (user_id,))
    return [r["permission"] for r in rows]


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please sign in first.")
            return redirect(url_for("signin"))
        return fn(*args, **kwargs)
    return wrapper


def role_required(role):
    def dec(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            u = current_user()
            if not u:
                flash("Please sign in first.")
                return redirect(url_for("signin"))
            if not has_role(u["user_id"], role):
                flash("You do not have permission for this page.")
                return redirect(url_for("home"))
            return fn(*args, **kwargs)
        return wrapper
    return dec


def next_code(table, column, prefix, width=3):
    start_index = len(prefix) + 1
    row = query_one(
        f"""
        SELECT COALESCE(MAX(CAST(SUBSTRING({column} FROM {start_index}) AS INTEGER)), 0) + 1 AS n
        FROM {table}
        WHERE {column} LIKE %s;
        """,
        (prefix + "%",),
    )
    return f"{prefix}{int(row['n']):0{width}d}"


def count_table(table):
    try:
        if table == "User":
            return query_one('SELECT COUNT(*) AS c FROM "User";')["c"]
        return query_one(f"SELECT COUNT(*) AS c FROM {table};")["c"]
    except Exception:
        return "N/A"


def db_stats():
    data = [
        ("Users", "User"), ("Passengers", "passenger"), ("Drivers", "driver"),
        ("Posts", "post"), ("Offers", "offer"), ("Rides", "ride"), ("Reports", "report"),
    ]
    out = '<div class="metrics">'
    for label, table in data:
        out += f'<div class="metric"><span>{esc(label)}</span><b>{esc(count_table(table))}</b></div>'
    return out + '</div>'


def table_html(title, rows):
    out = f"<h2>{esc(title)}</h2>"
    if not rows:
        return out + '<p class="muted">No records found.</p>'
    cols = list(rows[0].keys())
    out += '<div class="tablebox"><table><tr>'
    for c in cols:
        out += f"<th>{esc(c.replace('_', ' ').title())}</th>"
    out += "</tr>"
    for r in rows:
        out += "<tr>" + "".join(f"<td>{esc(r[c])}</td>" for c in cols) + "</tr>"
    return out + "</table></div>"


def layout(title, content):
    u = current_user()
    nav = ""
    user_box = ""
    if u:
        roles = roles_of(u["user_id"])
        role_badges = "".join(f'<span class="pill">{esc(x)}</span>' for x in roles)
        user_box = f'<div class="userbox"><div class="avatar">{esc(u["name"][:1])}</div><div><b>{esc(u["name"])} {esc(u["surname"])}</b><small>{role_badges}</small></div></div>'
        nav += '<a href="/">Home</a><a href="/profile">Profile</a><a href="/rides">Rides</a><a href="/report">Report</a>'
        if "Passenger" in roles:
            nav += '<a href="/post/new">Create Post</a><a href="/offers/received">Received Offers</a>'
        if "Driver" in roles:
            nav += '<a href="/offers/mine">My Offers</a><a href="/car/new">Add Car</a>'
        if "Admin" in roles:
            nav += '<a href="/admin">Admin Panel</a>'
        nav += '<a class="danger" href="/logout">Logout</a>'
    else:
        nav += '<a href="/signin">Sign In</a><a class="primary" href="/signup">Sign Up</a>'

    template = """
<!doctype html>
<html>
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }}</title>
<style>
:root{--navy:#101828;--navy2:#1d2939;--blue:#2f6fed;--green:#16a34a;--red:#dc2626;--orange:#f59e0b;--bg:#eef3fb;--border:#e5e7eb;--muted:#667085}
*{box-sizing:border-box}body{margin:0;font-family:Inter,"Segoe UI",Arial,sans-serif;color:#101828;background:radial-gradient(circle at 5% 0%,rgba(47,111,237,.16),transparent 28%),linear-gradient(135deg,#f8fbff,var(--bg));min-height:100vh}.top{background:rgba(16,24,40,.97);color:white;padding:20px 38px;display:flex;justify-content:space-between;align-items:center;gap:20px;box-shadow:0 14px 30px rgba(16,24,40,.18);position:sticky;top:0;z-index:4}.brand{display:flex;align-items:center;gap:12px}.logo{width:43px;height:43px;border-radius:15px;background:linear-gradient(135deg,#2f6fed,#66d9a8);display:grid;place-items:center;font-weight:900}.brand h1{margin:0;font-size:25px}.brand p{margin:2px 0 0;color:#cbd5e1;font-size:13px}.userbox{display:flex;align-items:center;gap:10px;background:rgba(255,255,255,.09);padding:8px 10px;border-radius:18px}.avatar{width:38px;height:38px;border-radius:13px;background:#dbeafe;color:#1d4ed8;display:grid;place-items:center;font-weight:900}.userbox small{display:block}.nav{max-width:1220px;margin:18px auto 0;padding:0 24px;display:flex;gap:10px;flex-wrap:wrap}.nav a,.btn,button{border:0;border-radius:12px;padding:10px 14px;font-weight:800;text-decoration:none;color:white;background:var(--navy2);cursor:pointer;display:inline-block;transition:.16s;font-size:14px}.nav a:hover,.btn:hover,button:hover{transform:translateY(-1px);box-shadow:0 8px 18px rgba(16,24,40,.15)}.primary,.btn.primary{background:var(--blue)!important}.green{background:var(--green)!important}.danger{background:var(--red)!important}.orange{background:var(--orange)!important}.mutebtn{background:#64748b!important}.wrap{max-width:1220px;margin:24px auto 46px;padding:0 24px}.panel{background:rgba(255,255,255,.94);border:1px solid rgba(255,255,255,.9);border-radius:28px;padding:28px;box-shadow:0 18px 46px rgba(16,24,40,.10);backdrop-filter:blur(12px)}.hero{display:grid;grid-template-columns:1.25fr .75fr;gap:18px}.hero-main{background:linear-gradient(135deg,#101828,#23365f);color:white;border-radius:28px;padding:40px;min-height:295px;display:flex;flex-direction:column;justify-content:center;position:relative;overflow:hidden}.hero-main:after{content:"";position:absolute;width:260px;height:260px;border-radius:999px;background:rgba(47,111,237,.28);right:-80px;top:-80px}.hero-main h2{font-size:44px;line-height:1.04;letter-spacing:-1.5px;margin:0 0 14px;position:relative;z-index:1}.hero-main p{font-size:17px;color:#dbeafe;line-height:1.6;position:relative;z-index:1}.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px;position:relative;z-index:1}.card,.post,.side,.metric{background:white;border:1px solid var(--border);border-radius:22px;padding:20px;box-shadow:0 10px 24px rgba(16,24,40,.06)}.featureicon{width:46px;height:46px;border-radius:14px;background:#eef2ff;color:#1d4ed8;display:grid;place-items:center;font-size:22px;font-weight:900;margin-bottom:10px}.authgrid{display:grid;grid-template-columns:1fr 1fr;gap:18px;align-items:stretch}.authside{background:linear-gradient(135deg,#101828,#23365f);color:white;border-radius:24px;padding:28px;display:flex;flex-direction:column;justify-content:center}.authside p{color:#dbeafe}.helper{margin-top:8px;color:var(--muted);font-size:14px}.softbox{background:#f8fafc;border:1px dashed #cbd5e1;border-radius:18px;padding:16px}.carhead{display:flex;align-items:center;gap:10px;margin-top:20px} .carhead .icon{width:42px;height:42px;border-radius:14px;background:#eef2ff;display:grid;place-items:center;color:#1d4ed8;font-size:22px}.muted{color:var(--muted)}.notice{background:#ecfdf5;border:1px solid #bbf7d0;color:#166534;padding:12px 14px;border-radius:14px;font-weight:700;margin-bottom:16px}.db{background:#f8fafc;border:1px solid #e5e7eb;color:#475467;border-radius:16px;padding:12px 14px;font-weight:700;margin-bottom:16px;font-size:14px}.cards,.posts{display:grid;grid-template-columns:repeat(auto-fit,minmax(265px,1fr));gap:16px;margin-top:16px}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;margin:16px 0 22px}.metric span{color:var(--muted);display:block;font-weight:700}.metric b{font-size:28px;margin-top:5px;display:block}.pill{display:inline-block;padding:5px 9px;border-radius:999px;background:#dbeafe;color:#1e40af;font-size:12px;font-weight:900;margin:2px 4px 2px 0}.ok{background:#dcfce7;color:#166534}.warn{background:#ffedd5;color:#9a3412}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 16px}form{max-width:850px}label{display:block;margin:12px 0 6px;font-weight:900}input,select{width:100%;padding:12px 13px;border-radius:14px;border:1px solid #cbd5e1;font-size:15px;background:white}input:focus,select:focus{outline:3px solid rgba(47,111,237,.18);border-color:var(--blue)}.tablebox{overflow-x:auto;margin-top:15px}table{width:100%;border-collapse:collapse;border-radius:16px;overflow:hidden;background:white}th{background:var(--navy);color:white;text-align:left;padding:12px;white-space:nowrap}td{border-bottom:1px solid var(--border);padding:12px;vertical-align:top}tr:hover td{background:#f8fafc}.hidden{display:none}.post h3{margin:0 0 6px;font-size:22px}.posttop{display:flex;justify-content:space-between;gap:12px}.inline{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}@media(max-width:900px){.authgrid{grid-template-columns:1fr}}@media(max-width:800px){.top{padding:18px 22px;align-items:flex-start;flex-direction:column}.hero{grid-template-columns:1fr}.hero-main{padding:28px;min-height:auto}.hero-main h2{font-size:34px}.grid{grid-template-columns:1fr}.panel{padding:20px}}
</style>
<script>
function toggleCar(){
  const r=document.getElementById('role');
  const c=document.getElementById('carbox');
  const note=document.getElementById('role-note');
  if(!r||!c)return;
  const on=r.value==='driver'||r.value==='both';
  c.classList.toggle('hidden',!on);
  c.querySelectorAll('input').forEach(i=>i.required=on);
  if(note){
    if(r.value==='driver') note.textContent='Driver account selected. Car information is required.';
    else if(r.value==='both') note.textContent='Passenger + Driver selected. Car information is required.';
    else if(r.value==='passenger') note.textContent='Passenger account selected. Car information is not required.';
    else note.textContent='Choose an account type to continue.';
  }
}
window.addEventListener('DOMContentLoaded',toggleCar);
</script>
</head><body>
<header class="top"><div class="brand"><div class="logo" aria-label="CampusRide logo"><svg width="26" height="26" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M14 36L20 22C21.3 19 24.2 17 27.5 17H40.5C43.8 17 46.7 19 48 22L54 36" stroke="white" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M12 35H52C55.3 35 58 37.7 58 41V43C58 46.3 55.3 49 52 49H12C8.7 49 6 46.3 6 43V41C6 37.7 8.7 35 12 35Z" fill="white" fill-opacity="0.18" stroke="white" stroke-width="4"/><circle cx="18" cy="46" r="5" fill="white"/><circle cx="46" cy="46" r="5" fill="white"/><path d="M22 35L25 25H43L46 35" stroke="white" stroke-width="4" stroke-linejoin="round"/></svg></div><div><h1>CampusRide</h1><p>Smart campus ride-sharing platform</p></div></div>{{ user_box|safe }}</header>
<nav class="nav">{{ nav|safe }}</nav>
<main class="wrap"><section class="panel">{% for m in get_flashed_messages() %}<div class="notice">{{ m }}</div>{% endfor %}{{ content|safe }}</section></main>
</body></html>
"""
    return render_template_string(template, title=title, nav=nav, user_box=user_box, content=content)


@app.route("/")
def home():
    if "user_id" not in session:
        content = """
        <div class="hero">
            <div class="hero-main">
                <h2>Professional ride management for campus life.</h2>
                <p>CampusRide is a modern university ride-sharing platform where passengers create ride requests, drivers send offers, and accepted offers become tracked rides.</p>
                <div class="actions">
                    <a class="btn primary" href="/signup">Create Account</a>
                    <a class="btn mutebtn" href="/signin">Sign In</a>
                </div>
            </div>
            <div class="side">
                <h3>Platform Highlights</h3>
                <div class="featureicon">🚗</div>
                <p class="muted">Role-based access, driver car registration, offer management, ride ratings, and reporting.</p>
                <p><span class="pill">User</span><span class="pill">Passenger</span><span class="pill">Driver</span><span class="pill">Admin</span></p>
            </div>
        </div>
        <div class="cards">
            <div class="card"><div class="featureicon">📝</div><h3>Create Ride Requests</h3><p class="muted">Passengers can share ride requests with pickup location, destination, passenger count, and date-time information.</p></div>
            <div class="card"><div class="featureicon">🤝</div><h3>Send Offers</h3><p class="muted">Drivers can send offers only when they have a suitable registered car in the system.</p></div>
            <div class="card"><div class="featureicon">📊</div><h3>Clear Workflow</h3><p class="muted">Important actions show clean success messages, while the admin panel keeps records easy to review.</p></div>
        </div>
        """
        return layout("Welcome", content)

    u = current_user()
    roles = roles_of(u["user_id"])
    posts = query_all(
        """
        SELECT p.post_ID AS post_id, p.location, p.destination, p.date_time, p.passenger_number,
               p.passenger_ID AS passenger_id, u.name || ' ' || u.surname AS passenger_name,
               COUNT(o.offer_ID) AS offer_count,
               EXISTS (SELECT 1 FROM ride r JOIN offer ox ON r.offer_ID=ox.offer_ID WHERE ox.post_ID=p.post_ID) AS has_ride,
               EXISTS (SELECT 1 FROM offer myo WHERE myo.post_ID=p.post_ID AND myo.driver_ID=%s) AS already_offered
        FROM post p JOIN "User" u ON p.passenger_ID=u.user_ID LEFT JOIN offer o ON p.post_ID=o.post_ID
        GROUP BY p.post_ID, p.location, p.destination, p.date_time, p.passenger_number, p.passenger_ID, u.name, u.surname
        ORDER BY p.date_time DESC;
        """,
        (u["user_id"],),
    )
    content = ''
    content += f'<div class="hero"><div class="hero-main"><h2>Welcome, {esc(u["name"])}.</h2><p>Manage campus ride requests, offers, rides, ratings, and reports from one official platform.</p><div class="actions">'
    if "Passenger" in roles:
        content += '<a class="btn green" href="/post/new">Create Ride Post</a><a class="btn mutebtn" href="/offers/received">View Received Offers</a>'
    if "Driver" in roles:
        content += '<a class="btn primary" href="/offers/mine">View My Offers</a>'
    content += '</div></div><div class="side"><h3>Platform Overview</h3><div class="featureicon">📌</div><p class="muted">Live platform counts and a quick summary of users, posts, offers, rides, and reports.</p></div></div>'
    content += db_stats() + '<h2>Ride Request Feed</h2>'
    if not posts:
        content += '<p class="muted">No ride request posts are available.</p>'
        return layout("Home", content)
    content += '<div class="posts">'
    for p in posts:
        status = '<span class="pill ok">Open</span>' if not p["has_ride"] else '<span class="pill warn">Matched</span>'
        action = ""
        if "Driver" in roles:
            if p["passenger_id"] == u["user_id"]:
                action = '<span class="muted">This is your own passenger post.</span>'
            elif p["has_ride"]:
                action = '<span class="muted">This post already generated a ride.</span>'
            elif p["already_offered"]:
                action = '<span class="muted">You already sent an offer.</span>'
            else:
                action = f'<a class="btn primary" href="/offer/new/{esc(p["post_id"])}">Make Offer</a>'
        elif "Passenger" in roles and p["passenger_id"] == u["user_id"]:
            action = '<a class="btn mutebtn" href="/offers/received">Review Offers</a>'
            if not p["has_ride"]:
                action += f' <a class="btn danger" href="/post/delete/{esc(p["post_id"])}">Delete Post</a>'
        content += f'<article class="post"><div class="posttop"><div><h3>{esc(p["location"])} → {esc(p["destination"])}</h3><p class="muted">Posted by {esc(p["passenger_name"])}</p></div>{status}</div><p><b>Pickup Location:</b> {esc(p["location"])}</p><p><b>Destination:</b> {esc(p["destination"])}</p><p><b>Date & Time:</b> {esc(p["date_time"])}</p><p><b>Passenger Count:</b> {esc(p["passenger_number"])}</p><p><b>Offer Count:</b> {esc(p["offer_count"])}</p><div class="inline">{action}</div></article>'
    return layout("Home", content + '</div>')


@app.route("/signin", methods=["GET", "POST"])
def signin():
    if request.method == "POST":
        ident = request.form.get("username_or_email", "").strip()
        password = request.form.get("password", "")
        user = query_one('SELECT user_ID AS user_id, password_hash FROM "User" WHERE user_name=%s OR email=%s;', (ident, ident))
        if user and user["password_hash"] and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["user_id"]
            flash("Signed in successfully.")
            return redirect(url_for("home"))
        flash("Invalid sign-in information.")
    content = """
    <div class="authgrid">
        <div class="authside">
            <div class="featureicon">🚗</div>
            <h2>Sign in to CampusRide.</h2>
            <p>Access ride requests, offers, ride history, and your profile from one secure campus platform.</p>
            <div class="actions"><span class="pill">Ride posts</span><span class="pill">Driver offers</span><span class="pill">Profile</span></div>
        </div>
        <div class="card">
            <h2>Welcome back</h2>
            <form method="POST">
                <label>Email or Username</label>
                <input name="username_or_email" placeholder="Enter your email or username" required>
                <label>Password</label>
                <input type="password" name="password" placeholder="Enter your password" autocomplete="current-password" required>
                <button class="primary">Sign In</button>
            </form>
            <p class="helper">New to CampusRide? <a href="/signup">Create an account</a>.</p>
        </div>
    </div>
    """
    return layout("Sign In", content)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        role = request.form.get("role", "")
        password = request.form.get("password", "")

        if len(password) < MIN_PASSWORD_LENGTH:
            flash("Password must be at least 8 characters long.")
            return redirect(url_for("signup"))

        plate = request.form.get("plate_number", "").strip()
        brand = request.form.get("brand", "").strip()
        model = request.form.get("model", "").strip()
        seats = request.form.get("seat_number", "").strip()

        if role in ["driver", "both"] and (not plate or not brand or not model or not seats):
            flash("Driver registration requires complete car information.")
            return redirect(url_for("signup"))

        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                'INSERT INTO "User" (email,user_name,phone_number,name,surname,gender,password_hash) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING user_ID;',
                (
                    request.form["email"].strip(),
                    request.form["user_name"].strip(),
                    request.form["phone_number"].strip(),
                    request.form["name"].strip(),
                    request.form["surname"].strip(),
                    request.form["gender"],
                    generate_password_hash(password),
                ),
            )
            new_id = cur.fetchone()[0]
            created_parts = ["account"]

            if role in ["passenger", "both"]:
                cur.execute("INSERT INTO passenger(user_ID) VALUES(%s);", (new_id,))
                created_parts.append("passenger profile")

            if role in ["driver", "both"]:
                cur.execute("INSERT INTO driver(user_ID, rate) VALUES(%s,0.00);", (new_id,))
                cur.execute(
                    "INSERT INTO car(plate_number,brand,model,seat_number,driver_ID) VALUES(%s,%s,%s,%s,%s);",
                    (plate, brand, model, int(seats), new_id),
                )
                created_parts.extend(["driver profile", "car record"])

            conn.commit()
            cur.close()
            flash("Account created successfully with " + ", ".join(created_parts) + ".")
            return redirect(url_for("signin"))

        except Exception as err:
            conn.rollback()
            flash(f"Registration failed. No changes were saved. Details: {err}")

        finally:
            conn.close()

    content = """
    <div class="authgrid">
        <div class="authside">
            <div class="featureicon">🚗</div>
            <h2>Create your CampusRide account.</h2>
            <p>Choose your role, enter your profile information, and start using the platform with the correct passenger or driver access.</p>
            <div class="actions">
                <span class="pill">Passenger posts</span>
                <span class="pill">Driver offers</span>
                <span class="pill">Ride tracking</span>
            </div>
        </div>

        <div class="card">
            <h2>Sign up</h2>
            <p id="role-note" class="helper">Choose an account type to continue.</p>

            <form method="POST">
                <div class="grid">
                    <div>
                        <label>Email</label>
                        <input type="email" name="email" placeholder="e000000@metu.edu.tr" required>
                    </div>

                    <div>
                        <label>Username</label>
                        <input name="user_name" placeholder="Create a username" required>
                    </div>

                    <div>
                        <label>Phone Number</label>
                        <input name="phone_number" placeholder="05xxxxxxxxx" required>
                    </div>

                    <div>
                        <label>Gender</label>
                        <select name="gender" required>
                            <option value="">Choose</option>
                            <option>Female</option>
                            <option>Male</option>
                        </select>
                    </div>

                    <div>
                        <label>Name</label>
                        <input name="name" placeholder="First name" required>
                    </div>

                    <div>
                        <label>Surname</label>
                        <input name="surname" placeholder="Last name" required>
                    </div>

                    <div>
                        <label>Password</label>
                        <input type="password" name="password" placeholder="At least 8 characters" minlength="8" required>
                        <p class="helper">Password must be at least 8 characters long.</p>
                    </div>

                    <div>
                        <label>Account Type</label>
                        <select id="role" name="role" onchange="toggleCar()" required>
                            <option value="">Choose user type</option>
                            <option value="passenger">Passenger</option>
                            <option value="driver">Driver</option>
                            <option value="both">Passenger and Driver</option>
                        </select>
                    </div>
                </div>

                <div id="carbox" class="hidden">
                    <div class="carhead">
                        <div class="icon">🚘</div>
                        <div>
                            <h3 style="margin:0">Car Information</h3>
                            <p class="helper" style="margin:2px 0 0">Required only for driver accounts.</p>
                        </div>
                    </div>

                    <div class="grid">
                        <div>
                            <label>Plate Number</label>
                            <input name="plate_number" placeholder="35 ABC 123">
                        </div>

                        <div>
                            <label>Brand</label>
                            <input name="brand" placeholder="Toyota">
                        </div>

                        <div>
                            <label>Model</label>
                            <input name="model" placeholder="Corolla">
                        </div>

                        <div>
                            <label>Seat Number</label>
                            <input type="number" min="1" name="seat_number" placeholder="4">
                        </div>
                    </div>
                </div>

                <button class="primary">Create Account</button>
            </form>
        </div>
    </div>
    """
    return layout("Sign Up", content)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("signin"))


@app.route("/profile")
@login_required
def profile():
    u = current_user()
    roles = roles_of(u["user_id"])
    role_pills = "".join(f'<span class="pill">{esc(r)}</span>' for r in roles)
    perms = "".join(f'<span class="pill">{esc(p)}</span>' for p in permissions_of(u["user_id"])) or '<span class="muted">No admin permissions assigned.</span>'
    content = f'<h2>Profile</h2><div class="cards"><div class="card"><h3>Account Information</h3><p><b>User ID:</b> {esc(u["user_id"])}</p><p><b>Name:</b> {esc(u["name"])} {esc(u["surname"])}</p><p><b>Username:</b> {esc(u["user_name"])}</p><p><b>Email:</b> {esc(u["email"])}</p><p><b>Phone:</b> {esc(u["phone_number"])}</p><p><b>Gender:</b> {esc(u["gender"])}</p><a class="btn primary" href="/profile/edit">Edit Profile</a></div><div class="card"><h3>Roles</h3><p>{role_pills}</p><h3>Admin Permissions</h3><p>{perms}</p></div></div>'
    if "Driver" in roles:
        cars = query_all("SELECT plate_number, brand, model, seat_number FROM car WHERE driver_ID=%s ORDER BY plate_number;", (u["user_id"],))
        content += table_html("Registered Cars", cars)
    return layout("Profile", content)


@app.route("/profile/edit", methods=["GET", "POST"])
@login_required
def edit_profile():
    u = current_user()

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        user_name = request.form.get("user_name", "").strip()
        phone_number = request.form.get("phone_number", "").strip()
        name = request.form.get("name", "").strip()
        surname = request.form.get("surname", "").strip()
        gender = request.form.get("gender", "").strip()
        new_password = request.form.get("new_password", "")

        if not email or not user_name or not phone_number or not name or not surname or not gender:
            flash("All profile fields except password are required.")
            return redirect(url_for("edit_profile"))

        try:
            if new_password:
                if len(new_password) < MIN_PASSWORD_LENGTH:
                    flash("New password must be at least 8 characters long.")
                    return redirect(url_for("edit_profile"))

                execute(
                    'UPDATE "User" SET email=%s, user_name=%s, phone_number=%s, name=%s, surname=%s, gender=%s, password_hash=%s WHERE user_ID=%s;',
                    (email, user_name, phone_number, name, surname, gender, generate_password_hash(new_password), u["user_id"]),
                )
            else:
                execute(
                    'UPDATE "User" SET email=%s, user_name=%s, phone_number=%s, name=%s, surname=%s, gender=%s WHERE user_ID=%s;',
                    (email, user_name, phone_number, name, surname, gender, u["user_id"]),
                )

            flash("Profile updated successfully.")
            return redirect(url_for("profile"))

        except Exception as err:
            flash(f"Profile could not be updated. No changes were saved. Details: {err}")

    content = f"""
    <h2>Edit Profile</h2>
    <p class="muted">Update your personal account information. Password is optional; leave it empty if you do not want to change it.</p>
    <form method="POST">
        <div class="grid">
            <div>
                <label>Email</label>
                <input type="email" name="email" value="{esc(u["email"])}" required>
            </div>
            <div>
                <label>Username</label>
                <input name="user_name" value="{esc(u["user_name"])}" required>
            </div>
            <div>
                <label>Phone Number</label>
                <input name="phone_number" value="{esc(u["phone_number"])}" required>
            </div>
            <div>
                <label>Gender</label>
                <select name="gender" required>
                    <option {"selected" if u["gender"] == "Female" else ""}>Female</option>
                    <option {"selected" if u["gender"] == "Male" else ""}>Male</option>
                </select>
            </div>
            <div>
                <label>Name</label>
                <input name="name" value="{esc(u["name"])}" required>
            </div>
            <div>
                <label>Surname</label>
                <input name="surname" value="{esc(u["surname"])}" required>
            </div>
            <div>
                <label>New Password</label>
                <input type="password" name="new_password" placeholder="Leave empty to keep current password" minlength="8">
                <p class="helper">Password must be at least 8 characters if changed.</p>
            </div>
        </div>
        <button class="primary">Save Changes</button>
        <a class="btn mutebtn" href="/profile">Cancel</a>
    </form>
    """
    return layout("Edit Profile", content)


@app.route("/post/new", methods=["GET", "POST"])
@login_required
@role_required("passenger")
def create_post():
    u = current_user()
    if request.method == "POST":
        pid = next_code("post", "post_ID", "P", 3)
        try:
            execute(
                "INSERT INTO post(post_ID,passenger_number,location,destination,date_time,passenger_ID) VALUES(%s,%s,%s,%s,%s,%s);",
                (
                    pid,
                    int(request.form["passenger_number"]),
                    request.form["location"].strip(),
                    request.form["destination"].strip(),
                    request.form["date_time"],
                    u["user_id"],
                ),
            )
            flash(f"Ride post shared successfully. Post ID: {pid}.")
            return redirect(url_for("home"))
        except Exception as err:
            flash(f"Post could not be created. No changes were saved. Details: {err}")
    content = """
    <h2>Create Ride Request</h2>
    <p class="muted">Share your ride request by entering where you want to be picked up, where you want to go, the preferred time, and the number of passengers.</p>
    <form method="POST">
        <label>Pickup Location</label>
        <input name="location" placeholder="Example: METU NCC Library" required>

        <label>Destination</label>
        <input name="destination" placeholder="Example: Nicosia City Center" required>

        <label>Date and Time</label>
        <input type="datetime-local" name="date_time" required>

        <label>Passenger Count</label>
        <input type="number" name="passenger_number" min="1" required>

        <button class="green">Share Post</button>
    </form>
    """
    return layout("Create Post", content)


@app.route("/post/delete/<post_id>")
@login_required
@role_required("passenger")
def delete_post(post_id):
    u = current_user()

    post = query_one(
        "SELECT post_ID AS post_id, passenger_ID AS passenger_id FROM post WHERE post_ID=%s;",
        (post_id,),
    )

    if not post or post["passenger_id"] != u["user_id"]:
        flash("You can delete only your own posts.")
        return redirect(url_for("home"))

    has_ride = query_one(
        "SELECT 1 FROM ride r JOIN offer o ON r.offer_ID=o.offer_ID WHERE o.post_ID=%s;",
        (post_id,),
    )

    if has_ride:
        flash("This post already generated a ride and cannot be deleted.")
        return redirect(url_for("home"))

    try:
        n = execute("DELETE FROM post WHERE post_ID=%s AND passenger_ID=%s;", (post_id, u["user_id"]))
        flash(f"Post deleted successfully. Affected rows: {n} row(s).")
    except Exception as err:
        flash(f"Post could not be deleted. No changes were saved. Details: {err}")

    return redirect(url_for("home"))


@app.route("/offer/new/<post_id>", methods=["GET", "POST"])
@login_required
@role_required("driver")
def make_offer(post_id):
    u = current_user()

    post = query_one(
        '''
        SELECT p.post_ID AS post_id,
               p.location,
               p.destination,
               p.date_time,
               p.passenger_number,
               p.passenger_ID AS passenger_id,
               u.name || ' ' || u.surname AS passenger_name
        FROM post p
        JOIN "User" u ON p.passenger_ID = u.user_ID
        WHERE p.post_ID = %s;
        ''',
        (post_id,),
    )

    if not post:
        flash("Post not found.")
        return redirect(url_for("home"))

    if post["passenger_id"] == u["user_id"]:
        flash("Drivers cannot send an offer to their own passenger post.")
        return redirect(url_for("home"))

    matched = query_one(
        "SELECT 1 FROM ride r JOIN offer o ON r.offer_ID=o.offer_ID WHERE o.post_ID=%s;",
        (post_id,),
    )

    already = query_one(
        "SELECT 1 FROM offer WHERE post_ID=%s AND driver_ID=%s;",
        (post_id, u["user_id"]),
    )

    cars = query_all(
        '''
        SELECT plate_number, brand, model, seat_number
        FROM car
        WHERE driver_ID=%s AND seat_number >= %s
        ORDER BY seat_number DESC, plate_number;
        ''',
        (u["user_id"], post["passenger_number"]),
    )

    if request.method == "POST":
        if matched:
            flash("Offer cannot be sent because this post already generated a ride.")
            return redirect(url_for("home"))

        if already:
            flash("You already sent an offer for this post.")
            return redirect(url_for("home"))

        if not cars:
            flash("Offer cannot be sent because you do not have a suitable car for this passenger count.")
            return redirect(url_for("new_car"))

        selected_plate = request.form.get("plate_number", "").strip()
        selected_car = next((c for c in cars if c["plate_number"] == selected_plate), None)

        if not selected_car:
            flash("Please select one of your registered suitable cars.")
            return redirect(url_for("make_offer", post_id=post_id))

        try:
            cost = float(request.form.get("cost", ""))
        except ValueError:
            flash("Please enter a valid offer price.")
            return redirect(url_for("make_offer", post_id=post_id))

        if cost < 0:
            flash("Offer price cannot be negative.")
            return redirect(url_for("make_offer", post_id=post_id))

        oid = next_code("offer", "offer_ID", "O", 3)

        try:
            execute(
                "INSERT INTO offer(offer_ID, post_ID, driver_ID, cost, plate_number) VALUES(%s,%s,%s,%s,%s);",
                (oid, post_id, u["user_id"], cost, selected_plate),
            )
            flash(f"Offer sent successfully. Offer ID: {oid}.")
            return redirect(url_for("my_offers"))

        except Exception as err:
            flash(f"Offer failed. No changes were saved. Details: {err}")

    content = f'''
    <h2>Make Offer</h2>
    <p class="muted">Choose the car you will use for this ride and enter your proposed price.</p>

    <div class="card">
        <h3>{esc(post["location"])} → {esc(post["destination"])}</h3>
        <p><b>Passenger:</b> {esc(post["passenger_name"])}</p>
        <p><b>Pickup Location:</b> {esc(post["location"])}</p>
        <p><b>Destination:</b> {esc(post["destination"])}</p>
        <p><b>Date:</b> {esc(post["date_time"])}</p>
        <p><b>Passenger Count:</b> {esc(post["passenger_number"])}</p>
    </div>
    '''

    if matched:
        content += '<p class="muted">This post already generated a ride.</p>'
    elif already:
        content += '<p class="muted">You already sent an offer for this post.</p>'
    elif not cars:
        content += '<p class="muted">You need a suitable registered car before sending an offer.</p><a class="btn primary" href="/car/new">Add Car</a>'
    else:
        car_options = "".join(
            f'<option value="{esc(c["plate_number"])}">{esc(c["plate_number"])} - {esc(c["brand"])} {esc(c["model"])} ({esc(c["seat_number"])} seats)</option>'
            for c in cars
        )
        content += f'''
        <form method="POST">
            <label>Offer Price</label>
            <input type="number" step="0.01" min="0" name="cost" placeholder="Example: 850" required>

            <label>Car Used for This Offer</label>
            <select name="plate_number" required>
                {car_options}
            </select>

            <button class="primary">Send Offer</button>
        </form>
        '''

    return layout("Make Offer", content)


@app.route("/offers/mine")
@login_required
@role_required("driver")
def my_offers():
    u = current_user()
    rows = query_all(
        """
        SELECT o.offer_ID AS offer_id,
               o.post_ID AS post_id,
               p.location AS pickup,
               p.destination,
               p.date_time,
               pu.name || ' ' || pu.surname AS passenger,
               o.cost AS offer_price,
               o.plate_number AS selected_car,
               CASE
                   WHEN own_ride.ride_ID IS NOT NULL THEN 'Accepted'
                   WHEN accepted_ride.ride_ID IS NOT NULL THEN 'Rejected'
                   ELSE 'Waiting'
               END AS status,
               own_ride.ride_ID AS ride_id
        FROM offer o
        JOIN post p ON o.post_ID = p.post_ID
        JOIN "User" pu ON p.passenger_ID = pu.user_ID
        LEFT JOIN ride own_ride ON o.offer_ID = own_ride.offer_ID
        LEFT JOIN offer accepted_offer ON accepted_offer.post_ID = o.post_ID
        LEFT JOIN ride accepted_ride ON accepted_ride.offer_ID = accepted_offer.offer_ID
        WHERE o.driver_ID = %s
        ORDER BY o.offer_ID DESC;
        """,
        (u["user_id"],),
    )
    return layout("My Offers", table_html("My Offers", rows))


@app.route("/offers/received")
@login_required
@role_required("passenger")
def received_offers():
    u = current_user()
    rows = query_all(
        '''
        SELECT p.post_ID AS post_id,
               p.location AS pickup,
               p.destination,
               p.date_time,
               o.offer_ID AS offer_id,
               du.name || ' ' || du.surname AS driver_name,
               d.rate AS driver_rate,
               o.cost AS offer_price,
               o.plate_number AS selected_car,
               c.brand,
               c.model,
               r.ride_ID AS ride_id,
               EXISTS (
                   SELECT 1
                   FROM ride rx
                   JOIN offer ox ON rx.offer_ID = ox.offer_ID
                   WHERE ox.post_ID = p.post_ID
               ) AS post_has_ride
        FROM post p
        JOIN offer o ON p.post_ID = o.post_ID
        JOIN driver d ON o.driver_ID = d.user_ID
        JOIN "User" du ON o.driver_ID = du.user_ID
        LEFT JOIN car c ON o.plate_number = c.plate_number
        LEFT JOIN ride r ON o.offer_ID = r.offer_ID
        WHERE p.passenger_ID = %s
        ORDER BY p.post_ID DESC, o.cost ASC, o.offer_ID DESC;
        ''',
        (u["user_id"],),
    )

    content = '<h2>Received Offers</h2>'
    if not rows:
        return layout("Received Offers", content + '<p class="muted">No offers received yet.</p>')

    content += '''
    <div class="tablebox">
    <table>
        <tr>
            <th>Post</th>
            <th>Route</th>
            <th>Date</th>
            <th>Offer</th>
            <th>Driver</th>
            <th>Rate</th>
            <th>Price</th>
            <th>Car</th>
            <th>Status</th>
            <th>Action</th>
        </tr>
    '''

    for r in rows:
        car_text = f'{esc(r["selected_car"])} - {esc(r["brand"])} {esc(r["model"])}'
        if r["ride_id"]:
            status, action = "Accepted", "-"
        elif r["post_has_ride"]:
            status, action = "Another offer accepted", "-"
        else:
            status = "Waiting"
            action = f'<a class="btn green" href="/offer/accept/{esc(r["offer_id"])}">Accept Offer</a>'

        content += f'''
        <tr>
            <td>{esc(r["post_id"])}</td>
            <td>{esc(r["pickup"])} → {esc(r["destination"])}</td>
            <td>{esc(r["date_time"])}</td>
            <td>{esc(r["offer_id"])}</td>
            <td>{esc(r["driver_name"])}</td>
            <td>{esc(r["driver_rate"])}</td>
            <td>{esc(r["offer_price"])}</td>
            <td>{car_text}</td>
            <td>{esc(status)}</td>
            <td>{action}</td>
        </tr>
        '''

    return layout("Received Offers", content + '</table></div>')


@app.route("/offer/accept/<offer_id>", methods=["GET", "POST"])
@login_required
@role_required("passenger")
def accept_offer(offer_id):
    u = current_user()

    offer = query_one(
        '''
        SELECT o.offer_ID AS offer_id,
               o.post_ID AS post_id,
               o.driver_ID AS driver_id,
               o.cost,
               o.plate_number,
               p.passenger_ID AS passenger_id,
               p.location,
               p.destination,
               p.passenger_number,
               du.name || ' ' || du.surname AS driver_name
        FROM offer o
        JOIN post p ON o.post_ID = p.post_ID
        JOIN "User" du ON o.driver_ID = du.user_ID
        WHERE o.offer_ID = %s;
        ''',
        (offer_id,),
    )

    if not offer or offer["passenger_id"] != u["user_id"]:
        flash("You can accept only offers for your own posts.")
        return redirect(url_for("home"))

    existing = query_one(
        '''
        SELECT r.ride_ID
        FROM ride r
        JOIN offer o ON r.offer_ID = o.offer_ID
        WHERE o.post_ID = %s;
        ''',
        (offer["post_id"],),
    )

    if existing:
        flash("This post already has an accepted offer. No changes were saved.")
        return redirect(url_for("received_offers"))

    if offer["cost"] is None or not offer["plate_number"]:
        flash("This offer is incomplete and cannot be accepted.")
        return redirect(url_for("received_offers"))

    rid = next_code("ride", "ride_ID", "R", 3)

    try:
        execute(
            '''
            INSERT INTO ride(ride_ID, start_destination, end_destination, cost, rating, offer_ID, plate_number)
            VALUES(%s,%s,%s,%s,NULL,%s,%s);
            ''',
            (
                rid,
                offer["location"],
                offer["destination"],
                offer["cost"],
                offer_id,
                offer["plate_number"],
            ),
        )
        flash(f"Offer accepted successfully. Ride ID: {rid}.")
        return redirect(url_for("rides"))

    except Exception as err:
        flash(f"Ride could not be created. No changes were saved. Details: {err}")
        return redirect(url_for("received_offers"))


@app.route("/car/new", methods=["GET", "POST"])
@login_required
@role_required("driver")
def new_car():
    u = current_user()
    if request.method == "POST":
        try:
            execute("INSERT INTO car(plate_number,brand,model,seat_number,driver_ID) VALUES(%s,%s,%s,%s,%s);", (request.form["plate_number"].strip(), request.form["brand"].strip(), request.form["model"].strip(), int(request.form["seat_number"]), u["user_id"]))
            flash("Car added successfully.")
            return redirect(url_for("profile"))
        except Exception as err:
            flash(f"Car could not be added. No changes were saved. Details: {err}")
    content = '<h2>Add Car</h2><p class="muted">Drivers need registered cars before making offers.</p><form method="POST"><label>Plate Number</label><input name="plate_number" required><label>Brand</label><input name="brand" required><label>Model</label><input name="model" required><label>Seat Number</label><input type="number" name="seat_number" min="1" required><button class="primary">Add Car</button></form>'
    return layout("Add Car", content)


@app.route("/rides")
@login_required
def rides():
    u = current_user()
    roles = roles_of(u["user_id"])
    content = '<h2>Rides</h2>'

    # Important: A user can be Admin + Passenger at the same time.
    # Therefore, the admin section must NOT return early; otherwise the passenger
    # rating buttons disappear for admin-passenger users such as Miray.
    if "Admin" in roles:
        rows = query_all("""
            SELECT r.ride_ID AS ride_id,
                   pu.name || ' ' || pu.surname AS passenger,
                   du.name || ' ' || du.surname AS driver,
                   r.start_destination,
                   r.end_destination,
                   p.date_time AS ride_time,
                   r.cost,
                   r.rating,
                   r.plate_number
            FROM ride r
            JOIN offer o ON r.offer_ID = o.offer_ID
            JOIN post p ON o.post_ID = p.post_ID
            JOIN "User" pu ON p.passenger_ID = pu.user_ID
            JOIN "User" du ON o.driver_ID = du.user_ID
            ORDER BY r.ride_ID;
        """)
        content += table_html("All Rides", rows)

    if "Passenger" in roles:
        rows = query_all("""
            SELECT r.ride_ID AS ride_id,
                   du.name || ' ' || du.surname AS driver,
                   r.start_destination,
                   r.end_destination,
                   p.date_time AS ride_time,
                   r.cost,
                   r.rating,
                   r.plate_number,
                   (p.date_time <= CURRENT_TIMESTAMP) AS can_rate
            FROM ride r
            JOIN offer o ON r.offer_ID = o.offer_ID
            JOIN post p ON o.post_ID = p.post_ID
            JOIN "User" du ON o.driver_ID = du.user_ID
            WHERE p.passenger_ID = %s
            ORDER BY r.ride_ID;
        """, (u["user_id"],))

        content += '<h3>My Passenger Rides</h3>'
        if rows:
            content += '<div class="tablebox"><table><tr><th>Ride</th><th>Driver</th><th>Start</th><th>End</th><th>Ride Time</th><th>Cost</th><th>Rating</th><th>Car</th><th>Actions</th></tr>'
            for r in rows:
                rate_label = "Rate" if r["rating"] is None else "Update Rating"
                rate_action = f'<a class="btn primary" href="/ride/rate/{esc(r["ride_id"])}">{rate_label}</a>'
                if not r["can_rate"]:
                    rate_action += ' <span class="muted">available after ride time</span>'

                report_action = f'<a class="btn danger" href="/ride/report/{esc(r["ride_id"])}">Report This Ride</a>'
                actions = rate_action + " " + report_action

                content += f'<tr><td>{esc(r["ride_id"])}</td><td>{esc(r["driver"])}</td><td>{esc(r["start_destination"])}</td><td>{esc(r["end_destination"])}</td><td>{esc(r["ride_time"])}</td><td>{esc(r["cost"])}</td><td>{esc(r["rating"])}</td><td>{esc(r["plate_number"])}</td><td>{actions}</td></tr>'
            content += '</table></div>'
        else:
            content += '<p class="muted">No passenger rides found.</p>'

    if "Driver" in roles:
        rows = query_all("""
            SELECT r.ride_ID AS ride_id,
                   pu.name || ' ' || pu.surname AS passenger,
                   r.start_destination,
                   r.end_destination,
                   p.date_time AS ride_time,
                   r.cost,
                   r.rating,
                   r.plate_number
            FROM ride r
            JOIN offer o ON r.offer_ID = o.offer_ID
            JOIN post p ON o.post_ID = p.post_ID
            JOIN "User" pu ON p.passenger_ID = pu.user_ID
            WHERE o.driver_ID = %s
            ORDER BY r.ride_ID;
        """, (u["user_id"],))

        content += '<h3>My Driven Rides</h3>'
        if rows:
            content += '<div class="tablebox"><table><tr><th>Ride</th><th>Passenger</th><th>Start</th><th>End</th><th>Ride Time</th><th>Cost</th><th>Rating</th><th>Car</th><th>Actions</th></tr>'
            for r in rows:
                report_action = f'<a class="btn danger" href="/ride/report/{esc(r["ride_id"])}">Report This Ride</a>'
                content += f'<tr><td>{esc(r["ride_id"])}</td><td>{esc(r["passenger"])}</td><td>{esc(r["start_destination"])}</td><td>{esc(r["end_destination"])}</td><td>{esc(r["ride_time"])}</td><td>{esc(r["cost"])}</td><td>{esc(r["rating"])}</td><td>{esc(r["plate_number"])}</td><td>{report_action}</td></tr>'
            content += '</table></div>'
        else:
            content += '<p class="muted">No driven rides found.</p>'

    return layout("Rides", content)


@app.route("/ride/rate/<ride_id>", methods=["GET", "POST"])
@login_required
@role_required("passenger")
def rate_ride(ride_id):
    u = current_user()

    ride = query_one(
        """
        SELECT p.passenger_ID AS passenger_id,
               p.date_time,
               (p.date_time <= CURRENT_TIMESTAMP) AS can_rate
        FROM ride r
        JOIN offer o ON r.offer_ID = o.offer_ID
        JOIN post p ON o.post_ID = p.post_ID
        WHERE r.ride_ID = %s;
        """,
        (ride_id,),
    )

    if not ride or ride["passenger_id"] != u["user_id"]:
        flash("You can rate only your own rides.")
        return redirect(url_for("rides"))

    if not ride["can_rate"]:
        flash("Rating is available only after the ride time has started.")
        return redirect(url_for("rides"))

    if request.method == "POST":
        try:
            rating = int(request.form["rating"])
            if rating < 1 or rating > 5:
                flash("Rating must be between 1 and 5.")
                return redirect(url_for("rate_ride", ride_id=ride_id))

            execute("UPDATE ride SET rating=%s WHERE ride_ID=%s;", (rating, ride_id))
            execute("""
                UPDATE driver d
                SET rate = sub.avg_rating
                FROM (
                    SELECT o.driver_ID, ROUND(AVG(r.rating)::NUMERIC, 2) AS avg_rating
                    FROM offer o
                    JOIN ride r ON r.offer_ID = o.offer_ID
                    WHERE r.rating IS NOT NULL
                    GROUP BY o.driver_ID
                ) sub
                WHERE d.user_ID = sub.driver_ID
                  AND d.rate IS DISTINCT FROM sub.avg_rating;
            """)
            flash("Rating saved successfully. Driver rate was recalculated.")
            return redirect(url_for("rides"))
        except Exception as err:
            flash(f"Rating failed. No changes were saved. Details: {err}")

    content = """
    <h2>Rate Ride</h2>
    <p class="muted">Rate the driver after the ride time has started. Your rating updates the ride and refreshes the driver's average rate.</p>
    <form method="POST">
        <label>Rating</label>
        <select name="rating" required>
            <option value="5">5 - Excellent</option>
            <option value="4">4 - Good</option>
            <option value="3">3 - Average</option>
            <option value="2">2 - Poor</option>
            <option value="1">1 - Very Poor</option>
        </select>
        <button class="primary">Save Rating</button>
    </form>
    """
    return layout("Rate Ride", content)



@app.route("/report")
@login_required
def report_center():
    u = current_user()

    related_rides = query_all(
        """
        SELECT DISTINCT
               r.ride_ID AS ride_id,
               r.start_destination,
               r.end_destination,
               p.date_time AS ride_time,
               pu.name || ' ' || pu.surname AS passenger,
               du.name || ' ' || du.surname AS driver,
               r.cost,
               r.rating
        FROM ride r
        JOIN offer o ON r.offer_ID = o.offer_ID
        JOIN post p ON o.post_ID = p.post_ID
        JOIN "User" pu ON p.passenger_ID = pu.user_ID
        JOIN "User" du ON o.driver_ID = du.user_ID
        WHERE p.passenger_ID = %s OR o.driver_ID = %s
        ORDER BY p.date_time DESC, r.ride_ID DESC;
        """,
        (u["user_id"], u["user_id"]),
    )

    content = """
    <h2>Report Center</h2>
    <p class="muted">Choose whether your report is about a specific ride or a general application issue.</p>

    <div class="cards">
        <div class="card">
            <div class="featureicon">🚘</div>
            <h3>Report a Ride</h3>
            <p class="muted">Use this option if the problem is related to a specific ride. Select the correct ride below and submit your explanation.</p>
        </div>

        <div class="card">
            <div class="featureicon">⚠️</div>
            <h3>Report App Issue</h3>
            <p class="muted">Use this option if the problem is about the application, interface, login, data display, or another general platform issue.</p>
            <a class="btn danger" href="/issue/new">Report App Issue</a>
        </div>
    </div>
    """

    content += "<h3>My Related Rides</h3>"

    if not related_rides:
        content += '<p class="muted">No related ride records were found for ride-specific reporting.</p>'
        return layout("Report Center", content)

    content += """
    <div class="tablebox">
    <table>
        <tr>
            <th>Ride</th>
            <th>Route</th>
            <th>Ride Time</th>
            <th>Passenger</th>
            <th>Driver</th>
            <th>Cost</th>
            <th>Rating</th>
            <th>Action</th>
        </tr>
    """

    for r in related_rides:
        content += f"""
        <tr>
            <td>{esc(r["ride_id"])}</td>
            <td>{esc(r["start_destination"])} → {esc(r["end_destination"])}</td>
            <td>{esc(r["ride_time"])}</td>
            <td>{esc(r["passenger"])}</td>
            <td>{esc(r["driver"])}</td>
            <td>{esc(r["cost"])}</td>
            <td>{esc(r["rating"])}</td>
            <td><a class="btn danger" href="/ride/report/{esc(r["ride_id"])}">Report This Ride</a></td>
        </tr>
        """

    return layout("Report Center", content + "</table></div>")


@app.route("/ride/report/<ride_id>", methods=["GET", "POST"])
@login_required
def report_ride(ride_id):
    u = current_user()

    ride = query_one(
        """
        SELECT r.ride_ID AS ride_id,
               p.passenger_ID AS passenger_id,
               o.driver_ID AS driver_id,
               r.start_destination,
               r.end_destination
        FROM ride r
        JOIN offer o ON r.offer_ID = o.offer_ID
        JOIN post p ON o.post_ID = p.post_ID
        WHERE r.ride_ID = %s;
        """,
        (ride_id,),
    )

    if not ride:
        flash("Ride not found.")
        return redirect(url_for("rides"))

    if u["user_id"] not in [ride["passenger_id"], ride["driver_id"]]:
        flash("You can report only rides related to your account.")
        return redirect(url_for("rides"))

    if request.method == "POST":
        report_text = request.form.get("report_text", "").strip()

        if len(report_text) < 5:
            flash("Please describe the ride issue with at least 5 characters.")
            return redirect(url_for("report_ride", ride_id=ride_id))

        try:
            execute(
                "INSERT INTO report(ride_ID, user_ID, report_text, report_type) VALUES(%s,%s,%s,'Ride');",
                (ride_id, u["user_id"], report_text),
            )
            flash("Ride report submitted successfully.")
            return redirect(url_for("rides"))

        except Exception as err:
            flash(f"Ride report failed. No changes were saved. Details: {err}")

    content = f"""
    <h2>Report Ride</h2>
    <p class="muted">Use this form only for a problem related to the selected ride. The ride ID and route are shown below so the report is connected to the correct ride.</p>
    <div class="card">
        <h3>Ride {esc(ride_id)}</h3>
        <p><b>Route:</b> {esc(ride["start_destination"])} → {esc(ride["end_destination"])}</p>
    </div>
    <form method="POST">
        <label>Report Description</label>
        <input name="report_text" placeholder="Describe the ride-related issue" required>
        <button class="danger">Submit Ride Report</button>
    </form>
    """
    return layout("Report Ride", content)


@app.route("/issue/new", methods=["GET", "POST"])
@login_required
def new_issue_report():
    u = current_user()

    if request.method == "POST":
        report_text = request.form.get("report_text", "").strip()

        if len(report_text) < 5:
            flash("Please describe the issue with at least 5 characters.")
            return redirect(url_for("new_issue_report"))

        try:
            execute(
                "INSERT INTO report(ride_ID, user_ID, report_text, report_type) VALUES(NULL,%s,%s,'General');",
                (u["user_id"], report_text),
            )
            flash("Report submitted successfully.")
            return redirect(url_for("home"))

        except Exception as err:
            flash(f"Report could not be submitted. No changes were saved. Details: {err}")

    content = """
    <h2>Report App Issue</h2>
    <p class="muted">Use this page only for general platform problems such as interface issues, login problems, wrong data display, or other application-related concerns. This report is not tied to a specific ride.</p>
    <form method="POST">
        <label>Report Description</label>
        <input name="report_text" placeholder="Describe the application issue briefly" required>
        <button class="danger">Submit Report</button>
    </form>
    """
    return layout("Report Issue", content)


@app.route("/admin")
@login_required
@role_required("admin")
def admin_panel():
    u = current_user()
    perms = "".join(f'<span class="pill">{esc(p)}</span>' for p in permissions_of(u["user_id"]))
    content = f'<h2>Admin Panel</h2><div class="card"><h3>Admin Permissions</h3><p>{perms}</p></div>{db_stats()}<div class="cards"><div class="card"><h3>Users</h3><p class="muted">Read and delete user records.</p><a class="btn primary" href="/admin/users">Open</a></div><div class="card"><h3>Admins & Permissions</h3><p class="muted">Read Admin and AdminPermission records.</p><a class="btn primary" href="/admin/admins">Open</a></div><div class="card"><h3>Drivers</h3><p class="muted">Read Driver rates and car counts.</p><a class="btn primary" href="/admin/drivers">Open</a></div><div class="card"><h3>Reports</h3><p class="muted">Review ride-related and general user reports.</p><a class="btn danger" href="/admin/reports">Open</a></div><div class="card"><h3>Refresh Driver Rates</h3><p class="muted">UPDATE Driver.rate using average Ride.rating.</p><a class="btn green" href="/admin/refresh-rates">Run</a></div><div class="card"><h3>Apply Discount</h3><p class="muted">UPDATE Ride.cost for expensive low-rated rides.</p><a class="btn orange" href="/admin/apply-discount">Run</a></div></div>'
    return layout("Admin Panel", content)


@app.route("/admin/users")
@login_required
@role_required("admin")
def admin_users():
    u = current_user()
    rows = query_all(
        'SELECT user_ID AS user_id,user_name,name,surname,email,phone_number,gender FROM "User" ORDER BY user_ID;'
    )

    content = '<h2>All Users</h2>'
    if not rows:
        return layout("Users", content + '<p class="muted">No users found.</p>')

    content += """
    <div class="tablebox">
    <table>
        <tr>
            <th>User Id</th>
            <th>Username</th>
            <th>Name</th>
            <th>Email</th>
            <th>Phone</th>
            <th>Gender</th>
            <th>Action</th>
        </tr>
    """

    for r in rows:
        if r["user_id"] == u["user_id"]:
            action = '<span class="muted">Current admin</span>'
        else:
            action = f'<a class="btn danger" href="/admin/user/delete/{esc(r["user_id"])}">Delete User</a>'

        content += f"""
        <tr>
            <td>{esc(r["user_id"])}</td>
            <td>{esc(r["user_name"])}</td>
            <td>{esc(r["name"])} {esc(r["surname"])}</td>
            <td>{esc(r["email"])}</td>
            <td>{esc(r["phone_number"])}</td>
            <td>{esc(r["gender"])}</td>
            <td>{action}</td>
        </tr>
        """

    return layout("Users", content + '</table></div>')


@app.route("/admin/user/delete/<int:user_id>")
@login_required
@role_required("admin")
def admin_delete_user(user_id):
    u = current_user()

    if user_id == u["user_id"]:
        flash("You cannot delete your own admin account while you are signed in.")
        return redirect(url_for("admin_users"))

    target = query_one('SELECT user_ID AS user_id, user_name FROM "User" WHERE user_ID=%s;', (user_id,))
    if not target:
        flash("User not found.")
        return redirect(url_for("admin_users"))

    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute(
            """
            DELETE FROM report
            WHERE ride_ID IN (
                SELECT r.ride_ID
                FROM ride r
                JOIN offer o ON r.offer_ID = o.offer_ID
                WHERE o.driver_ID = %s
                   OR o.post_ID IN (SELECT post_ID FROM post WHERE passenger_ID = %s)
            );
            """,
            (user_id, user_id),
        )

        cur.execute(
            """
            DELETE FROM ride
            WHERE offer_ID IN (
                SELECT offer_ID
                FROM offer
                WHERE driver_ID = %s
                   OR post_ID IN (SELECT post_ID FROM post WHERE passenger_ID = %s)
            );
            """,
            (user_id, user_id),
        )

        cur.execute(
            """
            DELETE FROM offer
            WHERE driver_ID = %s
               OR post_ID IN (SELECT post_ID FROM post WHERE passenger_ID = %s);
            """,
            (user_id, user_id),
        )

        cur.execute("DELETE FROM post WHERE passenger_ID=%s;", (user_id,))
        cur.execute("DELETE FROM report WHERE user_ID=%s;", (user_id,))
        cur.execute("DELETE FROM car WHERE driver_ID=%s;", (user_id,))
        cur.execute("DELETE FROM adminpermission WHERE user_ID=%s;", (user_id,))
        cur.execute("DELETE FROM admin WHERE user_ID=%s;", (user_id,))
        cur.execute("DELETE FROM passenger WHERE user_ID=%s;", (user_id,))
        cur.execute("DELETE FROM driver WHERE user_ID=%s;", (user_id,))
        cur.execute('DELETE FROM "User" WHERE user_ID=%s;', (user_id,))
        affected = cur.rowcount

        conn.commit()
        cur.close()

        flash(f"User deleted successfully. Affected User rows: {affected}.")

    except Exception as err:
        conn.rollback()
        flash(f"User could not be deleted. No changes were saved. Details: {err}")

    finally:
        conn.close()

    return redirect(url_for("admin_users"))


@app.route("/admin/admins")
@login_required
@role_required("admin")
def admin_admins():
    rows = query_all("""SELECT a.user_ID AS user_id,u.name||' '||u.surname AS admin_name,STRING_AGG(ap.permission, ', ' ORDER BY ap.permission) AS permissions FROM admin a JOIN "User" u ON a.user_ID=u.user_ID LEFT JOIN adminpermission ap ON a.user_ID=ap.user_ID GROUP BY a.user_ID,u.name,u.surname ORDER BY a.user_ID;""")
    return layout("Admins", table_html("Admins and Permissions", rows))


@app.route("/admin/drivers")
@login_required
@role_required("admin")
def admin_drivers():
    rows = query_all("""SELECT d.user_ID AS driver_id,u.name||' '||u.surname AS driver_name,u.email,d.rate,COUNT(c.plate_number) AS car_count FROM driver d JOIN "User" u ON d.user_ID=u.user_ID LEFT JOIN car c ON d.user_ID=c.driver_ID GROUP BY d.user_ID,u.name,u.surname,u.email,d.rate ORDER BY d.rate DESC;""")
    return layout("Drivers", table_html("Drivers", rows))


@app.route("/admin/reports")
@login_required
@role_required("admin")
def admin_reports():
    rows = query_all(
        """
        SELECT rp.report_ID AS report_id,
               rp.report_type,
               rp.ride_ID AS ride_id,
               u.name || ' ' || u.surname AS reporter,
               u.user_name,
               rp.report_text,
               rp.status,
               rp.created_at
        FROM report rp
        JOIN "User" u ON rp.user_ID = u.user_ID
        ORDER BY rp.created_at DESC, rp.report_ID DESC;
        """
    )

    content = '<h2>Reports</h2>'
    if not rows:
        return layout("Reports", content + '<p class="muted">No reports found.</p>')

    content += """
    <div class="tablebox">
    <table>
        <tr>
            <th>Report</th>
            <th>Type</th>
            <th>Ride</th>
            <th>Reporter</th>
            <th>Description</th>
            <th>Status</th>
            <th>Created At</th>
            <th>Action</th>
        </tr>
    """

    for r in rows:
        content += f"""
        <tr>
            <td>{esc(r["report_id"])}</td>
            <td>{esc(r["report_type"])}</td>
            <td>{esc(r["ride_id"])}</td>
            <td>{esc(r["reporter"])} ({esc(r["user_name"])})</td>
            <td>{esc(r["report_text"])}</td>
            <td>{esc(r["status"])}</td>
            <td>{esc(r["created_at"])}</td>
            <td><a class="btn danger" href="/admin/report/delete/{esc(r["report_id"])}">Delete</a></td>
        </tr>
        """

    return layout("Reports", content + '</table></div>')


@app.route("/admin/report/delete/<int:report_id>")
@login_required
@role_required("admin")
def delete_report(report_id):
    try:
        n = execute("DELETE FROM report WHERE report_ID=%s;", (report_id,))
        flash(f"Report deleted successfully. Affected rows: {n} row(s).")
    except Exception as err:
        flash(f"Delete failed. No changes were saved. Details: {err}")
    return redirect(url_for("admin_reports"))


@app.route("/admin/refresh-rates")
@login_required
@role_required("admin")
def refresh_rates():
    try:
        n = execute("""UPDATE driver d SET rate=sub.avg_rating FROM (SELECT o.driver_ID, ROUND(AVG(r.rating)::NUMERIC,2) AS avg_rating FROM offer o JOIN ride r ON r.offer_ID=o.offer_ID WHERE r.rating IS NOT NULL GROUP BY o.driver_ID) sub WHERE d.user_ID=sub.driver_ID AND d.rate IS DISTINCT FROM sub.avg_rating;""")
        flash(f"Driver rates refreshed successfully. Affected rows: {n} row(s).")
    except Exception as err:
        flash(f"Rate refresh failed. No changes were saved. Details: {err}")
    return redirect(url_for("admin_panel"))


@app.route("/admin/apply-discount")
@login_required
@role_required("admin")
def apply_discount():
    try:
        n = execute("UPDATE ride SET cost=ROUND((cost*0.90)::NUMERIC,2) WHERE cost > 1000 AND rating < 4;")
        flash(f"Discount operation completed. Affected rides: {n} row(s).")
    except Exception as err:
        flash(f"Discount failed. No changes were saved. Details: {err}")
    return redirect(url_for("rides"))


if __name__ == "__main__":
    init_database()
    app.run(debug=True)
