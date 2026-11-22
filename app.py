import os, uuid, requests
from flask import Flask, render_template, request, redirect, session, url_for
from werkzeug.utils import secure_filename
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "localmarket-mohane-123")
DATABASE_URL = os.environ.get("DATABASE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, sslmode='require')

def upload_to_supabase(file):
    if not file or file.filename == '':
        return None
    try:
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'jpg'
        fname = f"{uuid.uuid4()}.{ext}"
        data = file.read()
        if not SUPABASE_URL or not SUPABASE_KEY:
            print("SUPABASE ENV NAHI")
            return None
        url = f"{SUPABASE_URL}/storage/v1/object/photos/{fname}"
        headers = {"Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": file.mimetype or "image/jpeg", "x-upsert": "true"}
        r = requests.post(url, headers=headers, data=data, timeout=30)
        if r.status_code in [200, 201]:
            return f"{SUPABASE_URL}/storage/v1/object/public/photos/{fname}"
        print("UPLOAD FAIL", r.text)
        return None
    except Exception as e:
        print("UPLOAD ERROR", e)
        return None

def init_db():
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY, name TEXT, email TEXT UNIQUE, password TEXT,
            phone TEXT, store_name TEXT, role TEXT DEFAULT 'Customer',
            bio TEXT, location TEXT DEFAULT 'Mohane, Maharashtra',
            opening TEXT DEFAULT '9 AM - 9 PM', profile_pic TEXT,
            lat DOUBLE PRECISION DEFAULT 19.2144, lng DOUBLE PRECISION DEFAULT 73.0978,
            is_admin BOOLEAN DEFAULT FALSE, is_blocked BOOLEAN DEFAULT FALSE
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY, user_id INTEGER, title TEXT, category TEXT,
            price INTEGER, description TEXT, image TEXT,
            store_name TEXT, owner_phone TEXT, owner_loc TEXT, rating FLOAT DEFAULT 4.5
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS feedbacks (
            id SERIAL PRIMARY KEY, store_id INTEGER, product_id INTEGER,
            customer_name TEXT, rating INTEGER, comment TEXT
        )""")
        cur.execute("ALTER TABLE feedbacks ADD COLUMN IF NOT EXISTS product_id INTEGER")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION DEFAULT 19.2144")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS lng DOUBLE PRECISION DEFAULT 73.0978")
        # Admin banav
        cur.execute("SELECT * FROM users WHERE email='admin@localmarket.com'")
        if not cur.fetchone():
            cur.execute("INSERT INTO users (name,email,password,role,is_admin,store_name) VALUES (%s,%s,%s,%s,%s,%s)",
                ('Admin','admin@localmarket.com','admin123','Store',True,'LocalMarket Admin'))
        conn.commit(); cur.close(); conn.close()
        print("DB OK")
    except Exception as e:
        print("DB INIT FAIL", e)

init_db()

@app.route('/')
def home():
    q = request.args.get('q',''); cat = request.args.get('cat','All'); msg = request.args.get('msg','')
    conn = get_db(); cur = conn.cursor()
    query = "SELECT p.*, u.location as owner_loc, u.phone as owner_phone FROM products p LEFT JOIN users u ON p.user_id=u.id WHERE 1=1"
    params = []
    if q:
        query += " AND (p.title ILIKE %s OR p.store_name ILIKE %s)"
        params += [f"%{q}%", f"%{q}%"]
    if cat and cat != 'All':
        query += " AND p.category=%s"; params.append(cat)
    query += " ORDER BY p.id DESC"
    cur.execute(query, tuple(params)); products = cur.fetchall()
    cur.execute("SELECT * FROM feedbacks ORDER BY id DESC"); feedbacks = cur.fetchall()
    cur.execute("SELECT * FROM users WHERE is_blocked=FALSE ORDER BY id DESC LIMIT 10"); shops = cur.fetchall()
    cur.close(); conn.close()
    return render_template('index.html', products=products, feedbacks=feedbacks, shops=shops, user=session.get('user'), q=q, cat=cat, msg=msg)

@app.route('/register', methods=['POST'])
def register():
    try:
        pic_url = upload_to_supabase(request.files.get('profile_pic'))
        lat = request.form.get('lat') or 19.2144
        lng = request.form.get('lng') or 73.0978
        conn = get_db(); cur = conn.cursor()
        cur.execute("INSERT INTO users (name,store_name,phone,email,password,role,bio,location,profile_pic,lat,lng) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (request.form.get('name'), request.form.get('store_name'), request.form.get('phone'),
             request.form.get('email'), request.form.get('password'), request.form.get('role'),
             request.form.get('bio'), request.form.get('location') or 'Mohane, Maharashtra',
             pic_url, float(lat), float(lng)))
        uid = cur.fetchone()['id']
        conn.commit(); cur.close(); conn.close()
        session['user'] = {'id': uid, 'name': request.form.get('name'), 'email': request.form.get('email'), 'profile_pic': pic_url, 'is_admin': False}
        return redirect(f'/profile/{uid}?msg=Register Zala!')
    except Exception as e:
        print("REGISTER FAIL", e)
        return redirect('/?msg=Email aadhi vaprla aahe!')

@app.route('/login', methods=['POST'])
def login():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email=%s AND password=%s", (request.form.get('email'), request.form.get('password')))
    u = cur.fetchone(); cur.close(); conn.close()
    if u:
        if u['is_blocked']:
            return redirect('/?msg=Tumhala Block kelay!')
        session['user'] = {'id': u['id'], 'name': u['name'], 'email': u['email'], 'profile_pic': u['profile_pic'], 'is_admin': u['is_admin']}
        return redirect('/')
    return redirect('/?msg=Email / Password chukicha!')

@app.route('/logout')
def logout():
    session.clear(); return redirect('/')

@app.route('/profile/<int:uid>')
def profile(uid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id=%s", (uid,)); owner = cur.fetchone()
    if not owner:
        cur.close(); conn.close(); return redirect('/')
    cur.execute("SELECT * FROM products WHERE user_id=%s ORDER BY id DESC", (uid,)); products = cur.fetchall()
    cur.execute("SELECT * FROM feedbacks WHERE store_id=%s ORDER BY id DESC", (uid,)); feedbacks = cur.fetchall()
    # Avg rating
    avg = 4.5
    if feedbacks:
        avg = round(sum([f['rating'] or 5 for f in feedbacks])/len(feedbacks), 1)
    cur.close(); conn.close()
    return render_template('profile.html', owner=owner, products=products, feedbacks=feedbacks, avg=avg, user=session.get('user'))

@app.route('/update_profile', methods=['POST'])
def update_profile():
    if 'user' not in session: return redirect('/')
    uid = session['user']['id']
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT profile_pic FROM users WHERE id=%s", (uid,)); old = cur.fetchone()
        old_pic = old['profile_pic'] if old else None
        new_pic = upload_to_supabase(request.files.get('profile_pic'))
        final_pic = new_pic if new_pic else old_pic
        lat = request.form.get('lat') or 19.2144
        lng = request.form.get('lng') or 73.0978
        cur.execute("UPDATE users SET name=%s, store_name=%s, phone=%s, bio=%s, location=%s, opening=%s, profile_pic=%s, lat=%s, lng=%s WHERE id=%s",
            (request.form.get('name'), request.form.get('store_name'), request.form.get('phone'),
             request.form.get('bio'), request.form.get('location'), request.form.get('opening'),
             final_pic, float(lat), float(lng), uid))
        conn.commit(); cur.close(); conn.close()
        session['user']['profile_pic'] = final_pic
        session['user']['name'] = request.form.get('name')
        return redirect(f'/profile/{uid}?msg=Profile Save Zala!')
    except Exception as e:
        print("UPDATE FAIL", e); return redirect(f'/profile/{uid}')

@app.route('/add', methods=['POST'])
def add_product():
    if 'user' not in session: return redirect('/')
    img = upload_to_supabase(request.files.get('product_pic'))
    if not img:
        img = 'https://images.unsplash.com/photo-1542838132-92c53300491e?w=600'
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT store_name, phone, location FROM users WHERE id=%s", (session['user']['id'],)); u = cur.fetchone()
    cur.execute("INSERT INTO products (user_id,title,category,price,description,image,store_name,owner_phone,owner_loc) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (session['user']['id'], request.form.get('title'), request.form.get('category'), request.form.get('price'),
         request.form.get('description'), img, u['store_name'] or session['user']['name'], u['phone'], u['location']))
    conn.commit(); cur.close(); conn.close()
    return redirect('/?msg=Product Add Zala!')

@app.route('/feedback/<int:product_id>', methods=['POST'])
def add_feedback(product_id):
    if 'user' not in session: return redirect('/')
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT user_id FROM products WHERE id=%s", (product_id,)); prod = cur.fetchone()
        if prod:
            cur.execute("INSERT INTO feedbacks (store_id, product_id, customer_name, rating, comment) VALUES (%s,%s,%s,%s,%s)",
                (prod['user_id'], product_id, session['user']['name'], request.form.get('rating', 5), request.form.get('comment','')))
            conn.commit()
        cur.close(); conn.close()
    except Exception as e: print("FEEDBACK FAIL", e)
    return redirect('/')

@app.route('/delete/<int:pid>')
def delete_product(pid):
    if 'user' not in session: return redirect('/')
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM products WHERE id=%s", (pid,)); conn.commit(); cur.close(); conn.close()
    return redirect('/')

@app.route('/admin')
def admin():
    if 'user' not in session or not session['user'].get('is_admin'): return redirect('/')
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM users ORDER BY id DESC"); users = cur.fetchall()
    cur.execute("SELECT * FROM products ORDER BY id DESC"); products = cur.fetchall()
    total = sum([p['price'] or 0 for p in products])
    cur.close(); conn.close()
    return render_template('admin.html', users=users, products=products, total_sell=total, user=session.get('user'))

@app.route('/admin/block/<int:uid>')
def block_user(uid):
    if 'user' not in session or not session['user'].get('is_admin'): return redirect('/')
    conn = get_db(); cur = conn.cursor(); cur.execute("UPDATE users SET is_blocked=TRUE WHERE id=%s", (uid,)); conn.commit(); cur.close(); conn.close(); return redirect('/admin')

@app.route('/admin/unblock/<int:uid>')
def unblock_user(uid):
    if 'user' not in session or not session['user'].get('is_admin'): return redirect('/')
    conn = get_db(); cur = conn.cursor(); cur.execute("UPDATE users SET is_blocked=FALSE WHERE id=%s", (uid,)); conn.commit(); cur.close(); conn.close(); return redirect('/admin')

@app.route('/admin/delete_user/<int:uid>')
def delete_user(uid):
    if 'user' not in session or not session['user'].get('is_admin'): return redirect('/')
    conn = get_db(); cur = conn.cursor(); cur.execute("DELETE FROM products WHERE user_id=%s", (uid,)); cur.execute("DELETE FROM users WHERE id=%s", (uid,)); conn.commit(); cur.close(); conn.close(); return redirect('/admin')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
