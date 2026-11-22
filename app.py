import os
import json
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# Environment Variables
app.secret_key = os.environ.get("SECRET_KEY", "sangola_malshiras_akluj_natepute_secret_2026")
DATABASE_URL = os.environ.get("DATABASE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

FALLBACK_IMAGE = "https://images.unsplash.com/photo-1607082348824-0a96f2a4b9da?auto=format&fit=crop&w=600&q=80"

# चारही शहरांचे डिफॉल्ट कोऑर्डिनेट्स
CITY_COORDS = {
    "Sangola": (17.4368, 75.1886),
    "Malshiras": (17.8569, 74.9125),
    "Akluj": (17.8924, 75.0258),
    "Natepute": (17.8828, 74.7495)
}


def get_db():
    """PostgreSQL (Supabase) डेटाबेस कनेक्शन."""
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_db():
    """डेटाबेस टेबल्स, सुरक्षित मायग्रेशन आणि डिफॉल्ट ॲडमिन सेटअप."""
    if not DATABASE_URL:
        print("WARNING: DATABASE_URL missing!")
        return

    conn = get_db()
    cur = conn.cursor()
    try:
        # १. Users (Stores) टेबल
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(120) NOT NULL,
                email VARCHAR(150) UNIQUE NOT NULL,
                password TEXT NOT NULL,
                phone VARCHAR(20) NOT NULL,
                city VARCHAR(80) DEFAULT 'Sangola',
                location VARCHAR(150) NOT NULL,
                store_name VARCHAR(150) NOT NULL,
                store_bio TEXT DEFAULT '',
                shop_timing VARCHAR(100) DEFAULT 'Sakali 9 te Ratri 9',
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                is_admin BOOLEAN DEFAULT FALSE,
                is_blocked BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # २. Products टेबल
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                title VARCHAR(200) NOT NULL,
                category VARCHAR(80) NOT NULL,
                price NUMERIC(10, 2) NOT NULL,
                description TEXT,
                image TEXT,
                store_name VARCHAR(150),
                owner_phone VARCHAR(20),
                owner_city VARCHAR(80) DEFAULT 'Sangola',
                owner_loc VARCHAR(150),
                details TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # सुरक्षित मायग्रेशन (जुने टेबल्स असल्यास नवीन कॉलम जोडणे)
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS city VARCHAR(80) DEFAULT 'Sangola';")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS store_bio TEXT DEFAULT '';")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS shop_timing VARCHAR(100) DEFAULT 'Sakali 9 te Ratri 9';")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION;")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION;")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_blocked BOOLEAN DEFAULT FALSE;")
        cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS owner_city VARCHAR(80) DEFAULT 'Sangola';")
        cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS owner_loc VARCHAR(150);")
        cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS details TEXT DEFAULT '{}';")

        # ३. डिफॉल्ट ॲडमिन युजर
        admin_email = "admin@localmarket.com"
        admin_pass = os.environ.get("ADMIN_PASSWORD", "SangolaAdmin@2026")
        cur.execute("SELECT id FROM users WHERE email = %s;", (admin_email,))
        if not cur.fetchone():
            hashed_pw = generate_password_hash(admin_pass)
            cur.execute("""
                INSERT INTO users (name, email, password, phone, city, location, store_name, latitude, longitude, is_admin, is_blocked)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, FALSE);
            """, ("Platform Admin", admin_email, hashed_pw, "9999999999", "Sangola", "Main Market", "Local Market HQ", 17.4368, 75.1886))

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"DB Init Error: {e}")
    finally:
        cur.close()
        conn.close()


def upload_to_supabase(file_obj):
    """Supabase Storage 'product-images' बकेटमध्ये फोटो अपलोड करणे."""
    if not file_obj or file_obj.filename == "" or not SUPABASE_URL or not SUPABASE_KEY:
        return FALLBACK_IMAGE

    try:
        ext = file_obj.filename.rsplit(".", 1)[-1].lower() if "." in file_obj.filename else "jpg"
        if ext not in ["jpg", "jpeg", "png", "webp"]:
            ext = "jpg"

        filename = f"{uuid.uuid4().hex}.{ext}"
        upload_url = f"{SUPABASE_URL}/storage/v1/object/product-images/{filename}"

        headers = {
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "apikey": SUPABASE_KEY,
            "Content-Type": file_obj.content_type or "image/jpeg",
            "x-upsert": "true"
        }

        response = requests.put(upload_url, data=file_obj.read(), headers=headers, timeout=15)
        if response.status_code in (200, 201):
            return f"{SUPABASE_URL}/storage/v1/object/public/product-images/{filename}"
        return FALLBACK_IMAGE
    except Exception as e:
        print(f"Upload Error: {e}")
        return FALLBACK_IMAGE


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id") or not session.get("is_admin"):
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated_function


with app.app_context():
    init_db()


# ==================== PAGE ROUTES ====================

@app.route("/")
def index():
    """मुख्य होम पेज (Products + Interactive Store Map)."""
    user = None
    if session.get("user_id"):
        user = {
            "id": session.get("user_id"),
            "name": session.get("name"),
            "email": session.get("email"),
            "store_name": session.get("store_name"),
            "city": session.get("city", "Sangola"),
            "location": session.get("location"),
            "phone": session.get("phone"),
            "is_admin": session.get("is_admin", False)
        }
    return render_template("index.html", user=user)


@app.route("/store/<int:store_id>")
def store_profile(store_id):
    """प्रत्येक दुकानाचे स्वतंत्र Store Profile Page."""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, name, store_name, phone, city, location, store_bio, shop_timing, latitude, longitude, is_blocked
            FROM users
            WHERE id = %s AND is_admin = FALSE;
        """, (store_id,))
        store = cur.fetchone()

        if not store or store["is_blocked"]:
            return redirect(url_for("index"))

        cur.execute("""
            SELECT * FROM products
            WHERE user_id = %s
            ORDER BY created_at DESC;
        """, (store_id,))
        rows = cur.fetchall()

        products = []
        for r in rows:
            item = dict(r)
            item["price"] = float(item["price"])
            try:
                item["details"] = json.loads(item["details"]) if item["details"] else {}
            except Exception:
                item["details"] = {}
            products.append(item)

        return render_template("store.html", store=store, products=products)
    finally:
        cur.close()
        conn.close()


# ==================== API ROUTES ====================

@app.route("/api/stores", methods=["GET"])
def get_stores():
    """मॅपवर दाखवण्यासाठी सर्व सक्रिय दुकानांची यादी आणि लोकेशन."""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT u.id, u.store_name, u.name, u.phone, u.city, u.location, u.shop_timing, u.latitude, u.longitude,
                   COUNT(p.id) AS product_count
            FROM users u
            LEFT JOIN products p ON u.id = p.user_id
            WHERE u.is_admin = FALSE AND u.is_blocked = FALSE
            GROUP BY u.id
            ORDER BY product_count DESC;
        """)
        stores = [dict(row) for row in cur.fetchall()]
        return jsonify({"success": True, "stores": stores})
    finally:
        cur.close()
        conn.close()


@app.route("/api/register", methods=["POST"])
def register():
    """नवीन दुकान रजिस्टर करणे (शहर आणि मॅप लोकेशनसह)."""
    data = request.json or {}
    name = data.get("name", "").strip()
    store_name = data.get("store_name", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    phone = data.get("phone", "").strip()
    city = data.get("city", "Sangola").strip()
    location = data.get("location", "").strip()
    shop_timing = data.get("shop_timing", "Sakali 9 te Ratri 9").strip()
    store_bio = data.get("store_bio", "").strip()

    if not all([name, store_name, email, password, phone, city, location]):
        return jsonify({"success": False, "message": "Sarva mahiti bharne aavashyak aahe!"}), 400

    clean_phone = "".join(filter(str.isdigit, phone))[-10:]
    if len(clean_phone) != 10:
        return jsonify({"success": False, "message": "Yogya 10 anki mobile number taka!"}), 400

    # कोऑर्डिनेट्स मिळवणे (जर युजरने पिन केले नसतील तर शहराचे डिफॉल्ट कोऑर्डिनेट्स घेणे)
    default_lat, default_lng = CITY_COORDS.get(city, (17.4368, 75.1886))
    try:
        lat = float(data.get("latitude")) if data.get("latitude") else default_lat
        lng = float(data.get("longitude")) if data.get("longitude") else default_lng
    except ValueError:
        lat, lng = default_lat, default_lng

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE email = %s;", (email,))
        if cur.fetchone():
            return jsonify({"success": False, "message": "Ha email adhich register aahe!"}), 400

        hashed_pw = generate_password_hash(password)
        cur.execute("""
            INSERT INTO users (name, email, password, phone, city, location, store_name, store_bio, shop_timing, latitude, longitude)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, name, email, store_name, city, location, phone, is_admin;
        """, (name, email, hashed_pw, clean_phone, city, location, store_name, store_bio, shop_timing, lat, lng))
        new_user = cur.fetchone()
        conn.commit()

        session["user_id"] = new_user["id"]
        session["name"] = new_user["name"]
        session["email"] = new_user["email"]
        session["store_name"] = new_user["store_name"]
        session["city"] = new_user["city"]
        session["location"] = new_user["location"]
        session["phone"] = new_user["phone"]
        session["is_admin"] = new_user["is_admin"]

        return jsonify({"success": True, "message": "Dukan Register Zala!", "user": new_user})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": "Server error!"}), 500
    finally:
        cur.close()
        conn.close()


@app.route("/api/login", methods=["POST"])
def login():
    """दुकानदार लॉगिन."""
    data = request.json or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM users WHERE email = %s;", (email,))
        user = cur.fetchone()

        if not user or not check_password_hash(user["password"], password):
            return jsonify({"success": False, "message": "Email kinva Password chukicha aahe!"}), 401

        if user["is_blocked"]:
            return jsonify({"success": False, "message": "Tumche khate Block kele aahe!"}), 403

        session["user_id"] = user["id"]
        session["name"] = user["name"]
        session["email"] = user["email"]
        session["store_name"] = user["store_name"]
        session["city"] = user.get("city", "Sangola")
        session["location"] = user["location"]
        session["phone"] = user["phone"]
        session["is_admin"] = user["is_admin"]

        return jsonify({
            "success": True,
            "message": "Login Zala!",
            "user": {
                "id": user["id"],
                "name": user["name"],
                "email": user["email"],
                "store_name": user["store_name"],
                "city": user.get("city", "Sangola"),
                "location": user["location"],
                "phone": user["phone"],
                "is_admin": user["is_admin"]
            }
        })
    finally:
        cur.close()
        conn.close()


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True, "message": "Logout Zala!"})


@app.route("/api/products", methods=["GET"])
def get_products():
    """सर्व प्रॉडक्ट्स किंवा 'My Products' मिळवणे."""
    mine_only = request.args.get("mine") == "true"
    conn = get_db()
    cur = conn.cursor()
    try:
        if mine_only:
            if not session.get("user_id"):
                return jsonify({"success": False, "message": "Aadhi login kara!"}), 401
            cur.execute("SELECT * FROM products WHERE user_id = %s ORDER BY created_at DESC;", (session["user_id"],))
        else:
            cur.execute("""
                SELECT p.* FROM products p
                JOIN users u ON p.user_id = u.id
                WHERE u.is_blocked = FALSE
                ORDER BY p.created_at DESC;
            """)
        rows = cur.fetchall()
        products = []
        for r in rows:
            item = dict(r)
            item["price"] = float(item["price"])
            try:
                item["details"] = json.loads(item["details"]) if item["details"] else {}
            except Exception:
                item["details"] = {}
            products.append(item)

        return jsonify({"success": True, "products": products})
    finally:
        cur.close()
        conn.close()


@app.route("/api/products", methods=["POST"])
def add_product():
    """नवीन प्रॉडक्ट ॲड करणे."""
    if not session.get("user_id"):
        return jsonify({"success": False, "message": "Aadhi login kara!"}), 401

    title = request.form.get("title", "").strip()
    category = request.form.get("category", "").strip()
    price = request.form.get("price", "").strip()
    description = request.form.get("description", "").strip()
    details_raw = request.form.get("details", "{}")

    if not title or not category or not price:
        return jsonify({"success": False, "message": "Title, Category ani Price aavashyak aahe!"}), 400

    try:
        price_val = float(price)
    except ValueError:
        return jsonify({"success": False, "message": "Yogya kimmat taka!"}), 400

    try:
        clean_details = json.dumps(json.loads(details_raw), ensure_ascii=False)
    except Exception:
        clean_details = "{}"

    image_url = upload_to_supabase(request.files.get("photo"))

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT is_blocked, store_name, phone, city, location FROM users WHERE id = %s;", (session["user_id"],))
        seller = cur.fetchone()
        if not seller or seller["is_blocked"]:
            session.clear()
            return jsonify({"success": False, "message": "Khate Block aahe!"}), 403

        cur.execute("""
            INSERT INTO products (
                user_id, title, category, price, description, image,
                store_name, owner_phone, owner_city, owner_loc, details
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """, (
            session["user_id"], title, category, price_val, description, image_url,
            seller["store_name"], seller["phone"], seller.get("city", "Sangola"), seller["location"], clean_details
        ))
        conn.commit()
        return jsonify({"success": True, "message": "Product Add Zala!"})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": "Product save kartana adchan aali!"}), 500
    finally:
        cur.close()
        conn.close()


@app.route("/api/products/<int:product_id>", methods=["DELETE"])
def delete_product(product_id):
    if not session.get("user_id"):
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    conn = get_db()
    cur = conn.cursor()
    try:
        if session.get("is_admin"):
            cur.execute("DELETE FROM products WHERE id = %s;", (product_id,))
        else:
            cur.execute("DELETE FROM products WHERE id = %s AND user_id = %s;", (product_id, session["user_id"]))
        conn.commit()
        return jsonify({"success": True, "message": "Product Delete Zala!"})
    finally:
        cur.close()
        conn.close()


# ==================== ADMIN ROUTES ====================

@app.route("/admin")
@admin_required
def admin_panel():
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COALESCE(SUM(price), 0) AS total_value FROM products;")
        total_value = float(cur.fetchone()["total_value"])

        cur.execute("""
            SELECT id, name, email, phone, city, location, store_name, is_blocked, created_at
            FROM users WHERE is_admin = FALSE ORDER BY created_at DESC;
        """)
        users = cur.fetchall()

        cur.execute("""
            SELECT id, title, category, price, store_name, owner_city, created_at
            FROM products ORDER BY created_at DESC;
        """)
        products = cur.fetchall()

        return render_template("admin.html", total_value=total_value, users=users, products=products)
    finally:
        cur.close()
        conn.close()


@app.route("/api/admin/users/<int:user_id>/toggle-block", methods=["POST"])
@admin_required
def toggle_block_user(user_id):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE users SET is_blocked = NOT is_blocked
            WHERE id = %s AND is_admin = FALSE RETURNING is_blocked;
        """, (user_id,))
        res = cur.fetchone()
        conn.commit()
        status = "Block Zala!" if res and res["is_blocked"] else "Unblock Zala!"
        return jsonify({"success": True, "message": f"User {status}"})
    finally:
        cur.close()
        conn.close()


@app.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
@admin_required
def delete_user(user_id):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM users WHERE id = %s AND is_admin = FALSE;", (user_id,))
        conn.commit()
        return jsonify({"success": True, "message": "User ani tyache products delete zale!"})
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
