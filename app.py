import os, json, uuid, base64
import psycopg2, psycopg2.extras
from flask import Flask, render_template, request, redirect, session

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "local-market-secret-key")
DATABASE_URL = os.environ.get("DATABASE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users(
        id SERIAL PRIMARY KEY, name TEXT, email TEXT UNIQUE, password TEXT,
        phone TEXT, location TEXT, store_name TEXT, profile_pic TEXT,
        lat DOUBLE PRECISION, lng DOUBLE PRECISION,
        is_admin BOOLEAN DEFAULT FALSE, is_blocked BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT NOW())""")
    cur.execute("""CREATE TABLE IF NOT EXISTS products(
        id SERIAL PRIMARY KEY, user_id INTEGER, title TEXT, category TEXT,
        price NUMERIC, description TEXT, image TEXT, store_name TEXT,
        owner_phone TEXT, owner_loc TEXT, details TEXT, custom_name TEXT,
        created_at TIMESTAMP DEFAULT NOW())""")
    # Junya table la navin columns add kara
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_pic TEXT")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS lng DOUBLE PRECISION")
    cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS details TEXT")
    cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS custom_name TEXT")
    cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS store_name TEXT")
    cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS owner_phone TEXT")
    cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS owner_loc TEXT")
    cur.execute("SELECT id FROM users WHERE email='admin@localmarket.com'")
    if not cur.fetchone():
        cur.execute("INSERT INTO users (name,email,password,phone,location,store_name,is_admin) VALUES (%s,%s,%s,%s,%s,%s,TRUE)",
                    ('Admin','admin@localmarket.com','admin123','9876543210','Sangola','Local Market Admin'))
    conn.commit(); cur.close(); conn.close()

# PHOTO - Supabase la try kar, nahi zala tar Base64 madhe save kar (100% chalen)
def save_photo(file):
    if not file or file.filename == '':
        return None
    try:
        import requests
        ext = file.filename.rsplit('.',1)[-1].lower()
        fname = f"{uuid.uuid4()}.{ext}"
        data = file.read()
        # 1. Supabase try
        if SUPABASE_URL and SUPABASE_KEY:
            url = f"{SUPABASE_URL}/storage/v1/object/product-images/{fname}"
            headers = {"Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": file.content_type or "image/jpeg"}
            r = requests.put(url, data=data, headers=headers, timeout=20)
            if r.status_code in [200,201]:
                return f"{SUPABASE_URL}/storage/v1/object/public/product-images/{fname}"
        # 2. Supabase fail zala tar Base64 - photo kadhich gayab honar nahi
        b64 = base64.b64encode(data).decode('utf-8')
        mime = file.content_type or "image/jpeg"
        return f"data:{mime};base64,{b64}"
    except Exception as e:
        print("Photo Error:", e)
        return None

FALLBACK_IMG = "https://images.unsplash.com/photo-1542838132-92c53300491e?w=600"

@app.route('/')
def home():
    init_db()
    search = request.args.get('search','').strip()
    cat = request.args.get('cat','All')
    conn = get_db(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    q = "SELECT p.*, u.lat as shop_lat, u.lng as shop_lng, u.profile_pic as shop_pic FROM products p LEFT JOIN users u ON p.user_id=u.id WHERE 1=1"; params=[]
    if cat != 'All':
        q += " AND p.category=%s"; params.append(cat)
    if search:
        q += " AND (p.title ILIKE %s OR p.store_name ILIKE %s)"; params.extend([f"%{search}%", f"%{search}%"])
    q += " ORDER BY p.id DESC"
    cur.execute(q, params); products = cur.fetchall()
    # Map sathi sagli dukana
    cur.execute("SELECT store_name, lat, lng, profile_pic, location FROM users WHERE lat IS NOT NULL AND lng IS NOT NULL")
    shops = cur.fetchall()
    cur.close(); conn.close()
    for p in products:
        if not p.get('details'): p['details']='{}'
    return render_template('index.html', products=products, shops=shops, user=session.get('user'), search=search, cat=cat, msg=request.args.get('msg',''))

@app.route('/register', methods=['POST'])
def register():
    conn=get_db(); cur=conn.cursor()
    try:
        cur.execute("INSERT INTO users (name,email,password,phone,location,store_name) VALUES (%s,%s,%s,%s,%s,%s)",
            (request.form.get('name'), request.form.get('email'), request.form.get('password'),
             request.form.get('phone'), request.form.get('location'), request.form.get('store_name')))
        conn.commit(); return redirect('/?msg=Register Zala! Aata Login Kara')
    except: return redirect('/?msg=Ha Email aadhi aahe')
    finally: cur.close(); conn.close()

@app.route('/login', methods=['POST'])
def login():
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM users WHERE email=%s AND password=%s", (request.form.get('email'), request.form.get('password')))
    u=cur.fetchone(); cur.close(); conn.close()
    if not u: return redirect('/?msg=Chukicha Email / Password')
    if u['is_blocked']: return redirect('/?msg=Tumhi Block Aahat')
    session['user']=dict(u); return redirect('/?msg=Welcome '+u['name'])

@app.route('/logout')
def logout():
    session.clear(); return redirect('/')

@app.route('/add', methods=['POST'])
def add_product():
    if 'user' not in session: return redirect('/')
    img = save_photo(request.files.get('product_pic')) or FALLBACK_IMG
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT store_name, phone, location FROM users WHERE id=%s", (session['user']['id'],))
    u=cur.fetchone()
    # Sagla custom - pratyek field text
    details={k: request.form.get(k) for k in ['size','color','fabric','weight','packet','flavour','material','brand','expiry','veg_nonveg','quantity'] if request.form.get(k)}
    details_json=json.dumps(details, ensure_ascii=False)
    cur2=conn.cursor()
    cur2.execute("INSERT INTO products (user_id,title,category,price,description,image,store_name,owner_phone,owner_loc,details,custom_name) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (session['user']['id'], request.form.get('title'), request.form.get('category'), request.form.get('price'),
         request.form.get('description'), img, u['store_name'] or session['user']['name'], u['phone'], u['location'], details_json, request.form.get('custom_name')))
    conn.commit(); cur.close(); cur2.close(); conn.close()
    return redirect('/?msg=Product Add Zala!')

@app.route('/profile')
def profile():
    if 'user' not in session: return redirect('/')
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM users WHERE id=%s", (session['user']['id'],))
    u=cur.fetchone()
    cur.execute("SELECT * FROM products WHERE user_id=%s ORDER BY id DESC", (session['user']['id'],))
    my_products=cur.fetchall()
    cur.close(); conn.close()
    if u: session['user']=dict(u)
    return render_template('profile.html', user=session.get('user'), products=my_products)

@app.route('/profile/edit', methods=['POST'])
def edit_profile():
    if 'user' not in session: return redirect('/')
    pic = save_photo(request.files.get('profile_pic'))
    conn=get_db(); cur=conn.cursor()
    # Map che lat/lng save kara - ekda save zala ki fix rahil
    lat = request.form.get('lat') or None
    lng = request.form.get('lng') or None
    if pic:
        cur.execute("UPDATE users SET name=%s, store_name=%s, phone=%s, location=%s, profile_pic=%s, lat=%s, lng=%s WHERE id=%s",
            (request.form.get('name'), request.form.get('store_name'), request.form.get('phone'), request.form.get('location'), pic, lat, lng, session['user']['id']))
    else:
        cur.execute("UPDATE users SET name=%s, store_name=%s, phone=%s, location=%s, lat=%s, lng=%s WHERE id=%s",
            (request.form.get('name'), request.form.get('store_name'), request.form.get('phone'), request.form.get('location'), lat, lng, session['user']['id']))
    conn.commit(); cur.close(); conn.close()
    return redirect('/profile?msg=Profile + Location Save Zala!')

@app.route('/profile/change-password', methods=['POST'])
def change_password():
    if 'user' not in session: return redirect('/')
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT password FROM users WHERE id=%s", (session['user']['id'],))
    row=cur.fetchone()
    if not row or row[0]!=request.form.get('old_password'):
        cur.close(); conn.close(); return redirect('/profile?msg=Juna Password Chukicha Aahe')
    cur.execute("UPDATE users SET password=%s WHERE id=%s", (request.form.get('new_password'), session['user']['id']))
    conn.commit(); cur.close(); conn.close()
    return redirect('/profile?msg=Password Badalla!')

@app.route('/delete/<int:pid>')
def delete_product(pid):
    if 'user' not in session: return redirect('/')
    conn=get_db(); cur=conn.cursor()
    if session['user'].get('is_admin'):
        cur.execute("DELETE FROM products WHERE id=%s", (pid,))
    else:
        cur.execute("DELETE FROM products WHERE id=%s AND user_id=%s", (pid, session['user']['id']))
    conn.commit(); cur.close(); conn.close()
    return redirect('/')

@app.route('/admin')
def admin():
    if 'user' not in session or not session['user'].get('is_admin'): return redirect('/')
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM users ORDER BY id DESC"); users=cur.fetchall()
    cur.execute("SELECT * FROM products ORDER BY id DESC"); products=cur.fetchall()
    total=sum([float(p['price'] or 0) for p in products])
    cur.close(); conn.close()
    return render_template('admin.html', users=users, products=products, total_sell=total, user=session.get('user'))

@app.route('/admin/block/<int:uid>')
def block_user(uid):
    if 'user' not in session or not session['user'].get('is_admin'): return redirect('/')
    conn=get_db(); cur=conn.cursor(); cur.execute("UPDATE users SET is_blocked=TRUE WHERE id=%s",(uid,)); conn.commit(); cur.close(); conn.close(); return redirect('/admin')

@app.route('/admin/unblock/<int:uid>')
def unblock_user(uid):
    if 'user' not in session or not session['user'].get('is_admin'): return redirect('/')
    conn=get_db(); cur=conn.cursor(); cur.execute("UPDATE users SET is_blocked=FALSE WHERE id=%s",(uid,)); conn.commit(); cur.close(); conn.close(); return redirect('/admin')

@app.route('/admin/delete_user/<int:uid>')
def delete_user(uid):
    if 'user' not in session or not session['user'].get('is_admin'): return redirect('/')
    conn=get_db(); cur=conn.cursor(); cur.execute("DELETE FROM products WHERE user_id=%s",(uid,)); cur.execute("DELETE FROM users WHERE id=%s",(uid,)); conn.commit(); cur.close(); conn.close(); return redirect('/admin')

if __name__=='__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT",5000)))