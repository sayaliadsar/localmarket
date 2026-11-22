import os
import json
import uuid
import base64
import requests
import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "local-market-key")
DATABASE_URL = os.environ.get("DATABASE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

FALLBACK = "https://images.unsplash.com/photo-1542838132-92c53300491e?w=600"


def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode="require")


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users(
            id SERIAL PRIMARY KEY,
            name TEXT,
            email TEXT UNIQUE,
            password TEXT,
            phone TEXT,
            location TEXT,
            store_name TEXT,
            profile_pic TEXT,
            lat DOUBLE PRECISION,
            lng DOUBLE PRECISION,
            is_admin BOOLEAN DEFAULT FALSE,
            is_blocked BOOLEAN DEFAULT FALSE,
            is_pro BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS products(
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            title TEXT,
            category TEXT,
            price NUMERIC,
            mrp NUMERIC DEFAULT 0,
            description TEXT,
            image TEXT,
            store_name TEXT,
            owner_phone TEXT,
            details TEXT,
            rating NUMERIC DEFAULT 0,
            rating_count INTEGER DEFAULT 0,
            is_available BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS orders(
            id SERIAL PRIMARY KEY,
            buyer_id INTEGER,
            buyer_name TEXT,
            buyer_phone TEXT,
            product_id INTEGER,
            product_title TEXT,
            product_image TEXT,
            store_name TEXT,
            owner_phone TEXT,
            price NUMERIC,
            qty INTEGER DEFAULT 1,
            status TEXT DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT NOW()
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS reviews(
            id SERIAL PRIMARY KEY,
            product_id INTEGER,
            user_id INTEGER,
            user_name TEXT,
            rating INTEGER,
            comment TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS wishlist(
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            product_id INTEGER,
            UNIQUE(user_id, product_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS subscriptions(
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            store_name TEXT,
            plan TEXT,
            price NUMERIC DEFAULT 0,
            days INTEGER DEFAULT 30,
            status TEXT DEFAULT 'Active',
            created_at TIMESTAMP DEFAULT NOW()
        )
        """
    )
    cur.execute("SELECT id FROM users WHERE email='admin@localmarket.com'")
    if not cur.fetchone():
        admin_pw_hash = generate_password_hash("admin123")
        cur.execute(
            """
            INSERT INTO users (name, email, password, phone, location, store_name, is_admin)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            """,
            ("Admin", "admin@localmarket.com", admin_pw_hash, "9876543210", "Sangola", "Local Market Admin"),
        )
    conn.commit()
    cur.close()
    conn.close()


def save_photo(f):
    if not f or f.filename == "":
        return None
    try:
        ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else "jpg"
        fname = f"{uuid.uuid4()}.{ext}"
        data = f.read()
        if SUPABASE_URL and SUPABASE_KEY:
            url = f"{SUPABASE_URL}/storage/v1/object/product-images/{fname}"
            headers = {
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": f.content_type or "image/jpeg",
            }
            resp = requests.put(url, data=data, headers=headers, timeout=20)
            if resp.status_code in [200, 201]:
                return f"{SUPABASE_URL}/storage/v1/object/public/product-images/{fname}"
        return f"data:{f.content_type or 'image/jpeg'};base64,{base64.b64encode(data).decode()}"
    except Exception as e:
        print("Photo upload error:", e)
        return None


@app.route("/")
def home():
    search = request.args.get("search", "").strip()
    cat = request.args.get("cat", "All")
    sort = request.args.get("sort", "new")

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    q = """
        SELECT p.*, u.lat AS shop_lat, u.lng AS shop_lng
        FROM products p
        LEFT JOIN users u ON p.user_id = u.id
        WHERE p.is_available = TRUE
    """
    pms = []
    if cat != "All":
        q += " AND p.category = %s"
        pms.append(cat)
    if search:
        q += " AND (p.title ILIKE %s OR p.store_name ILIKE %s)"
        pms.extend([f"%{search}%", f"%{search}%"])

    if sort == "low":
        q += " ORDER BY p.price ASC"
    elif sort == "high":
        q += " ORDER BY p.price DESC"
    elif sort == "rating":
        q += " ORDER BY p.rating DESC"
    else:
        q += " ORDER BY p.id DESC"

    cur.execute(q, pms)
    products = cur.fetchall()

    try:
        cur.execute(
            "SELECT store_name, lat, lng, profile_pic, location FROM users WHERE lat IS NOT NULL AND lng IS NOT NULL"
        )
        shops = cur.fetchall()
    except Exception:
        shops = []

    wish = []
    if "user" in session:
        cur.execute("SELECT product_id FROM wishlist WHERE user_id = %s", (session["user"]["id"],))
        wish = [r["product_id"] for r in cur.fetchall()]

    cur.execute("SELECT * FROM products WHERE mrp > price ORDER BY id DESC LIMIT 4")
    offers = cur.fetchall()

    cur.close()
    conn.close()

    for x in products:
        if not x.get("details"):
            x["details"] = "{}"
        mrp_val = float(x.get("mrp") or 0)
        price_val = float(x.get("price") or 0)
        x["off"] = round((1 - price_val / mrp_val) * 100) if mrp_val > price_val and mrp_val > 0 else 0

    return render_template(
        "index.html",
        products=products,
        shops=shops,
        offer_products=offers,
        wish_ids=wish,
        user=session.get("user"),
        search=search,
        cat=cat,
        sort=sort,
        msg=request.args.get("msg", ""),
    )


@app.route("/register", methods=["POST"])
def register():
    conn = get_db()
    cur = conn.cursor()
    try:
        pw_hash = generate_password_hash(request.form.get("password") or "")
        cur.execute(
            "INSERT INTO users (name, email, password, phone, location, store_name) VALUES (%s, %s, %s, %s, %s, %s)",
            (
                request.form.get("name"),
                request.form.get("email"),
                pw_hash,
                request.form.get("phone"),
                request.form.get("location"),
                request.form.get("store_name"),
            ),
        )
        conn.commit()
        return redirect("/?msg=Account created successfully. Please login.")
    except Exception:
        conn.rollback()
        return redirect("/?msg=This email is already registered.")
    finally:
        cur.close()
        conn.close()


@app.route("/login", methods=["POST"])
def login():
    email = request.form.get("email")
    password = request.form.get("password") or ""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM users WHERE email = %s", (email,))
    u = cur.fetchone()
    cur.close()
    conn.close()

    if not u:
        return redirect("/?msg=Invalid email or password.")

    stored_pw = u.get("password") or ""
    is_valid = check_password_hash(stored_pw, password) or stored_pw == password
    if not is_valid:
        return redirect("/?msg=Invalid email or password.")
    if u["is_blocked"]:
        return redirect("/?msg=Your account is blocked.")

    u_safe = dict(u)
    u_safe.pop("password", None)
    session["user"] = u_safe
    return redirect("/?msg=Welcome, " + u["name"])


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/add", methods=["POST"])
def add_product():
    if "user" not in session:
        return redirect("/")

    img = save_photo(request.files.get("product_pic")) or FALLBACK
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT store_name, phone, location FROM users WHERE id = %s", (session["user"]["id"],))
    u = cur.fetchone() or {}

    detail_keys = [
        "size", "color", "fabric", "weight", "packet",
        "flavour", "material", "brand", "expiry", "veg_nonveg", "quantity",
    ]
    det = {k: request.form.get(k) for k in detail_keys if request.form.get(k)}
    mrp = request.form.get("mrp") or request.form.get("price")

    cur2 = conn.cursor()
    cur2.execute(
        """
        INSERT INTO products (user_id, title, category, price, mrp, description, image, store_name, owner_phone, details)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            session["user"]["id"],
            request.form.get("title"),
            request.form.get("category"),
            request.form.get("price"),
            mrp,
            request.form.get("description"),
            img,
            u.get("store_name") or session["user"]["name"],
            u.get("phone"),
            json.dumps(det, ensure_ascii=False),
        ),
    )
    conn.commit()
    cur.close()
    cur2.close()
    conn.close()
    return redirect("/?msg=Product added successfully.")


@app.route("/toggle-available/<int:pid>")
def toggle_available(pid):
    if "user" not in session:
        return redirect("/profile")
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE products SET is_available = NOT is_available WHERE id = %s AND user_id = %s",
        (pid, session["user"]["id"]),
    )
    conn.commit()
    cur.close()
    conn.close()
    return redirect("/profile")


@app.route("/delete/<int:pid>")
def delete_product(pid):
    if "user" not in session:
        return redirect("/")
    conn = get_db()
    cur = conn.cursor()
    if session["user"].get("is_admin"):
        cur.execute("DELETE FROM products WHERE id = %s", (pid,))
    else:
        cur.execute("DELETE FROM products WHERE id = %s AND user_id = %s", (pid, session["user"]["id"]))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(request.referrer or "/")
@app.route("/profile")
def profile():
    if "user" not in session:
        return redirect("/")
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        uid = session["user"]["id"]

        cur.execute("SELECT * FROM users WHERE id = %s", (uid,))
        u = cur.fetchone()
        cur.execute("SELECT * FROM products WHERE user_id = %s ORDER BY id DESC", (uid,))
        my = cur.fetchall()
        cur.execute("SELECT * FROM orders WHERE buyer_id = %s ORDER BY id DESC", (uid,))
        myo = cur.fetchall()
        cur.execute("SELECT o.* FROM orders o JOIN products p ON o.product_id = p.id WHERE p.user_id = %s ORDER BY o.id DESC", (uid,))
        shopo = cur.fetchall()
        cur.execute("SELECT * FROM subscriptions WHERE user_id = %s ORDER BY id DESC LIMIT 1", (uid,))
        sub = cur.fetchone()

        cur.close()
        conn.close()
        if u:
            u_safe = dict(u)
            u_safe.pop("password", None)
            session["user"] = u_safe

        return render_template(
            "profile.html",
            user=session.get("user"),
            products=my,
            my_orders=myo,
            shop_orders=shopo,
            my_sub=sub,
        )
    except Exception as e:
        return f"Profile Error: {e} <br><a href='/'>Go Home</a>"


@app.route("/profile/edit", methods=["POST"])
def edit_profile():
    if "user" not in session:
        return redirect("/")
    pic = save_photo(request.files.get("profile_pic"))
    conn = get_db()
    cur = conn.cursor()
    lat = request.form.get("lat") or None
    lng = request.form.get("lng") or None

    if pic:
        cur.execute(
            """
            UPDATE users
            SET name = %s, store_name = %s, phone = %s, location = %s, profile_pic = %s, lat = %s, lng = %s
            WHERE id = %s
            """,
            (
                request.form.get("name"),
                request.form.get("store_name"),
                request.form.get("phone"),
                request.form.get("location"),
                pic,
                lat,
                lng,
                session["user"]["id"],
            ),
        )
    else:
        cur.execute(
            """
            UPDATE users
            SET name = %s, store_name = %s, phone = %s, location = %s, lat = %s, lng = %s
            WHERE id = %s
            """,
            (
                request.form.get("name"),
                request.form.get("store_name"),
                request.form.get("phone"),
                request.form.get("location"),
                lat,
                lng,
                session["user"]["id"],
            ),
        )
    conn.commit()
    cur.close()
    conn.close()
    return redirect("/profile?msg=Profile updated successfully.")


@app.route("/profile/change-password", methods=["POST"])
def change_password():
    if "user" not in session:
        return redirect("/")
    old_pw = request.form.get("old_password") or ""
    new_pw = request.form.get("new_password") or ""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT password FROM users WHERE id = %s", (session["user"]["id"],))
    row = cur.fetchone()
    stored_pw = (row[0] if row else "") or ""

    if not row or not (check_password_hash(stored_pw, old_pw) or stored_pw == old_pw):
        cur.close()
        conn.close()
        return redirect("/profile?msg=Old password is incorrect.")

    cur.execute(
        "UPDATE users SET password = %s WHERE id = %s",
        (generate_password_hash(new_pw), session["user"]["id"]),
    )
    conn.commit()
    cur.close()
    conn.close()
    return redirect("/profile?msg=Password changed successfully.")


@app.route("/wishlist/<int:pid>")
def toggle_wishlist(pid):
    if "user" not in session:
        return redirect("/?msg=Please login first.")
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM wishlist WHERE user_id = %s AND product_id = %s",
        (session["user"]["id"], pid),
    )
    if cur.fetchone():
        cur.execute(
            "DELETE FROM wishlist WHERE user_id = %s AND product_id = %s",
            (session["user"]["id"], pid),
        )
    else:
        cur.execute(
            "INSERT INTO wishlist (user_id, product_id) VALUES (%s, %s)",
            (session["user"]["id"], pid),
        )
    conn.commit()
    cur.close()
    conn.close()
    return redirect(request.referrer or "/")


@app.route("/order/<int:pid>", methods=["POST"])
def create_order(pid):
    if "user" not in session:
        return redirect("/?msg=Please login first.")
    qty = int(request.form.get("qty", 1))
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM products WHERE id = %s", (pid,))
    p = cur.fetchone()
    if not p:
        cur.close()
        conn.close()
        return redirect("/")

    cur2 = conn.cursor()
    cur2.execute(
        """
        INSERT INTO orders (buyer_id, buyer_name, buyer_phone, product_id, product_title, product_image, store_name, owner_phone, price, qty)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            session["user"]["id"],
            session["user"]["name"],
            session["user"].get("phone", ""),
            pid,
            p["title"],
            p["image"],
            p["store_name"],
            p["owner_phone"],
            p["price"],
            qty,
        ),
    )
    conn.commit()
    cur.close()
    cur2.close()
    conn.close()
    return redirect("/?msg=Order placed successfully.")


@app.route("/order/status/<int:oid>/<status>")
def order_status(oid, status):
    if "user" not in session:
        return redirect("/")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE orders SET status = %s WHERE id = %s", (status, oid))
    conn.commit()
    cur.close()
    conn.close()
    return redirect("/profile?msg=Order status updated.")


@app.route("/review/<int:pid>", methods=["POST"])
def add_review(pid):
    if "user" not in session:
        return redirect("/?msg=Please login first.")
    rating = int(request.form.get("rating", 5))
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "INSERT INTO reviews (product_id, user_id, user_name, rating, comment) VALUES (%s, %s, %s, %s, %s)",
        (pid, session["user"]["id"], session["user"]["name"], rating, request.form.get("comment", "")),
    )
    cur.execute("SELECT AVG(rating) AS avg, COUNT(*) AS cnt FROM reviews WHERE product_id = %s", (pid,))
    r = cur.fetchone()

    cur2 = conn.cursor()
    cur2.execute(
        "UPDATE products SET rating = %s, rating_count = %s WHERE id = %s",
        (float(r["avg"] or 0), r["cnt"], pid),
    )
    conn.commit()
    cur.close()
    cur2.close()
    conn.close()
    return redirect("/?msg=Thank you for your review.")


@app.route("/subscribe/<plan>")
def subscribe_request(plan):
    if "user" not in session:
        return redirect("/?msg=Please login first.")
    price = 199 if plan == "Pro" else 499 if plan == "Premium" else 0
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO subscriptions (user_id, store_name, plan, price, days, status) VALUES (%s, %s, %s, %s, 30, 'Pending')",
        (session["user"]["id"], session["user"].get("store_name", ""), plan, price),
    )
    conn.commit()
    cur.close()
    conn.close()
    return redirect("/profile?msg=Subscription request sent. Admin will confirm.")
@app.route("/admin")
def admin():
    if "user" not in session or not session["user"].get("is_admin"):
        return redirect("/")

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT * FROM users ORDER BY id DESC")
    users = cur.fetchall()
    cur.execute("SELECT * FROM products ORDER BY id DESC")
    products = cur.fetchall()
    cur.execute("SELECT * FROM orders ORDER BY id DESC")
    orders = cur.fetchall()
    cur.execute("SELECT * FROM subscriptions ORDER BY id DESC")
    subs = cur.fetchall()
    cur.execute("SELECT r.*, p.title AS product_title FROM reviews r LEFT JOIN products p ON r.product_id = p.id ORDER BY r.id DESC")
    reviews = cur.fetchall()

    ot = sum(float(o["price"] or 0) * int(o["qty"] or 1) for o in orders)
    comm = round(ot * 0.05, 2)
    pend = len([o for o in orders if o["status"] == "Pending"])
    deli = len([o for o in orders if o["status"] == "Delivered"])

    cur.execute("SELECT store_name, COUNT(*) AS cnt, SUM(price * qty) AS total FROM orders GROUP BY store_name ORDER BY total DESC LIMIT 5")
    tops = cur.fetchall()
    cur.execute("SELECT TO_CHAR(created_at, 'DD Mon') AS day, COUNT(*) AS cnt, SUM(price * qty) AS total FROM orders GROUP BY day ORDER BY MIN(created_at) DESC LIMIT 7")
    daily = cur.fetchall()

    sub_inc = sum(float(s["price"] or 0) for s in subs if s["status"] == "Active")
    pro = len([s for s in subs if s["status"] == "Active"])
    ts = sum(float(p["price"] or 0) for p in products)

    cur.close()
    conn.close()

    return render_template(
        "admin.html",
        users=users,
        products=products,
        orders=orders,
        subs=subs,
        reviews=reviews,
        total_sell=ts,
        order_total=ot,
        commission=comm,
        pending=pend,
        delivered=deli,
        top_sellers=tops,
        daily=daily,
        sub_income=sub_inc,
        pro_users=pro,
        user=session.get("user"),
    )


@app.route("/admin/subscription/add", methods=["POST"])
def add_subscription():
    if "user" not in session or not session["user"].get("is_admin"):
        return redirect("/")
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO subscriptions (user_id, store_name, plan, price, days, status) VALUES (%s, %s, %s, %s, %s, 'Active')",
        (
            request.form.get("user_id"),
            request.form.get("store_name"),
            request.form.get("plan"),
            request.form.get("price"),
            request.form.get("days"),
        ),
    )
    cur.execute("UPDATE users SET is_pro = TRUE WHERE id = %s", (request.form.get("user_id"),))
    conn.commit()
    cur.close()
    conn.close()
    return redirect("/admin?msg=Subscription added.")


@app.route("/admin/subscription/approve/<int:sid>")
def approve_sub(sid):
    if "user" not in session or not session["user"].get("is_admin"):
        return redirect("/")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM subscriptions WHERE id = %s", (sid,))
    row = cur.fetchone()
    cur.execute("UPDATE subscriptions SET status = 'Active' WHERE id = %s", (sid,))
    if row:
        cur.execute("UPDATE users SET is_pro = TRUE WHERE id = %s", (row[0],))
    conn.commit()
    cur.close()
    conn.close()
    return redirect("/admin?msg=Subscription approved.")


@app.route("/admin/subscription/cancel/<int:sid>")
def cancel_sub(sid):
    if "user" not in session or not session["user"].get("is_admin"):
        return redirect("/")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE subscriptions SET status = 'Cancelled' WHERE id = %s", (sid,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect("/admin?msg=Subscription cancelled.")


@app.route("/admin/order/status/<int:oid>/<status>")
def admin_order_status(oid, status):
    if "user" not in session or not session["user"].get("is_admin"):
        return redirect("/")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE orders SET status = %s WHERE id = %s", (status, oid))
    conn.commit()
    cur.close()
    conn.close()
    return redirect("/admin")


@app.route("/admin/block/<int:uid>")
def block_user(uid):
    if "user" not in session or not session["user"].get("is_admin"):
        return redirect("/")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_blocked = TRUE WHERE id = %s", (uid,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect("/admin")


@app.route("/admin/unblock/<int:uid>")
def unblock_user(uid):
    if "user" not in session or not session["user"].get("is_admin"):
        return redirect("/")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_blocked = FALSE WHERE id = %s", (uid,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect("/admin")


@app.route("/admin/toggle-pro/<int:uid>")
def toggle_pro(uid):
    if "user" not in session or not session["user"].get("is_admin"):
        return redirect("/")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_pro = NOT is_pro WHERE id = %s", (uid,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect("/admin")


@app.route("/admin/delete-product/<int:pid>")
def admin_delete_product(pid):
    if "user" not in session or not session["user"].get("is_admin"):
        return redirect("/")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM products WHERE id = %s", (pid,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect("/admin")


@app.route("/admin/delete-user/<int:uid>")
def admin_delete_user(uid):
    if "user" not in session or not session["user"].get("is_admin"):
        return redirect("/")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM products WHERE user_id = %s", (uid,))
    cur.execute("DELETE FROM users WHERE id = %s", (uid,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect("/admin")


@app.route("/admin/delete-review/<int:rid>")
def admin_delete_review(rid):
    if "user" not in session or not session["user"].get("is_admin"):
        return redirect("/")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM reviews WHERE id = %s", (rid,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect("/admin")


if __name__ == "__main__":
    if DATABASE_URL:
        init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
