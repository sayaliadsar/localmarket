import os, json, uuid, base64
import psycopg2, psycopg2.extras
from flask import Flask, render_template, request, redirect, session, jsonify

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
        price NUMERIC, mrp NUMERIC DEFAULT 0, description TEXT, image TEXT, store_name TEXT,
        owner_phone TEXT, owner_loc TEXT, details TEXT, custom_name TEXT,
        rating NUMERIC DEFAULT 0, rating_count INTEGER DEFAULT 0,
        is_available BOOLEAN DEFAULT TRUE, created_at TIMESTAMP DEFAULT NOW())""")
    cur.execute("""CREATE TABLE IF NOT EXISTS orders(
        id SERIAL PRIMARY KEY, buyer_id INTEGER, buyer_name TEXT, buyer_phone TEXT,
        product_id INTEGER, product_title TEXT, product_image TEXT, store_name TEXT,
        owner_phone TEXT, price NUMERIC, qty INTEGER DEFAULT 1, status TEXT DEFAULT 'Pending',
        created_at TIMESTAMP DEFAULT NOW())""")
    cur.execute("""CREATE TABLE IF NOT EXISTS reviews(
        id SERIAL PRIMARY KEY, product_id INTEGER, user_id INTEGER, user_name TEXT,
        rating INTEGER, comment TEXT, created_at TIMESTAMP DEFAULT NOW())""")
    cur.execute("""CREATE TABLE IF NOT EXISTS wishlist(
        id SERIAL PRIMARY KEY, user_id INTEGER, product_id INTEGER, UNIQUE(user_id, product_id))""")
    # Safe migrations
    for col in ["profile_pic TEXT","lat DOUBLE PRECISION","lng DOUBLE PRECISION"]:
        cur.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col}")
    for col in ["details TEXT","custom_name TEXT","store_name TEXT","owner_phone TEXT","owner_loc TEXT","mrp NUMERIC DEFAULT 0","rating NUMERIC DEFAULT 0","rating_count INTEGER DEFAULT 0","is_available BOOLEAN DEFAULT TRUE"]:
        cur.execute(f"ALTER TABLE products ADD COLUMN IF NOT EXISTS {col}")
    cur.execute("SELECT id FROM users WHERE email='admin@localmarket.com'")
    if not cur.fetchone():
        cur.execute("INSERT INTO users (name,email,password,phone,location,store_name,is_admin) VALUES (%s,%s,%s,%s,%s,%s,TRUE)",
                    ('Admin','admin@localmarket.com','admin123','9876543210','Sangola','Local Market Admin'))
    conn.commit(); cur.close(); conn.close()

def save_photo(file):
    if not file or file.filename == '': return None
    try:
        import requests
        ext = file.filename.rsplit('.',1)[-1].lower()
        fname = f"{uuid.uuid4()}.{ext}"
        data = file.read()
        if SUPABASE_URL and SUPABASE_KEY:
            url = f"{SUPABASE_URL}/storage/v1/object/product-images/{fname}"
            headers = {"Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": file.content_type or "image/jpeg"}
            r = requests.put(url, data=data, headers=headers, timeout=20)
            if r.status_code in [200,201]:
                return f"{SUPABASE_URL}/storage/v1/object/public/product-images/{fname}"
        b64 = base64.b64encode(data).decode('utf-8')
        return f"data:{file.content_type or 'image/jpeg'};base64,{b64}"
    except Exception as e:
        print("Photo Error:", e); return None

FALLBACK_IMG = "https://images.unsplash.com/photo-1542838132-92c53300491e?w=600"

@app.route('/')
def home():
    init_db()
    search = request.args.get('search','').strip()
    cat = request.args.get('cat','All')
    sort = request.args.get('sort','new')
    conn = get_db(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    q = "SELECT p.*, u.lat as shop_lat, u.lng as shop_lng, u.profile_pic as shop_pic FROM products p LEFT JOIN users u ON p.user_id=u.id WHERE p.is_available=TRUE"; params=[]
    if cat != 'All':
        q += " AND p.category=%s"; params.append(cat)
    if search:
        q += " AND (p.title ILIKE %s OR p.store_name ILIKE %s OR p.custom_name ILIKE %s)"; params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    if sort=='low': q += " ORDER BY p.price ASC"
    elif sort=='high': q += " ORDER BY p.price DESC"
    elif sort=='rating': q += " ORDER BY p.rating DESC"
    else: q += " ORDER BY p.id DESC"
    cur.execute(q, params); products = cur.fetchall()
    cur.execute("SELECT store_name, lat, lng, profile_pic, location FROM users WHERE lat IS NOT NULL AND lng IS NOT NULL")
    shops = cur.fetchall()
    # Wishlist ids
    wish_ids = []
    if 'user' in session:
        cur.execute("SELECT product_id FROM wishlist WHERE user_id=%s", (session['user']['id'],))
        wish_ids = [r['product_id'] for r in cur.fetchall()]
    # Top rated + Offers
    cur.execute("SELECT * FROM products WHERE rating >= 4 ORDER BY rating DESC LIMIT 4"); top_products = cur.fetchall()
    cur.execute("SELECT * FROM products WHERE mrp > price ORDER BY id DESC LIMIT 4"); offer_products = cur.fetchall()
    cur.close(); conn.close()
    for p in products:
        if not p.get('details'): p['details']='{}'
        if p.get('mrp') and float(p['mrp'] or 0) > float(p['price'] or 0):
            p['off'] = round((1 - float(p['price'])/float(p['mrp']))*100)
        else: p['off'] = 0
    return render_template('index.html', products=products, shops=shops, top_products=top_products, offer_products=offer_products, wish_ids=wish_ids, user=session.get('user'), search=search, cat=cat, sort=sort, msg=request.args.get('msg',''))

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
    details={k: request.form.get(k) for k in ['size','color','fabric','weight','packet','flavour','material','brand','expiry','veg_nonveg','quantity'] if request.form.get(k)}
    details_json=json.dumps(details, ensure_ascii=False)
    mrp = request.form.get('mrp') or request.form.get('price')
    cur2=conn.cursor()
    cur2.execute("INSERT INTO products (user_id,title,category,price,mrp,description,image,store_name,owner_phone,owner_loc,details,custom_name) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (session['user']['id'], request.form.get('title'), request.form.get('category'), request.form.get('price'), mrp,
         request.form.get('description'), img, u['store_name'] or session['user']['name'], u['phone'], u['location'], details_json, request.form.get('custom_name')))
    conn.commit(); cur.close(); cur2.close(); conn.close()
    return redirect('/?msg=Product Add Zala!')

@app.route('/toggle-available/<int:pid>')
def toggle_available(pid):
    if 'user' not in session: return redirect('/profile')
    conn=get_db(); cur=conn.cursor()
    cur.execute("UPDATE products SET is_available = NOT is_available WHERE id=%s AND user_id=%s", (pid, session['user']['id']))
    conn.commit(); cur.close(); conn.close(); return redirect('/profile')

@app.route('/profile')
def profile():
    if 'user' not in session: return redirect('/')
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM users WHERE id=%s", (session['user']['id'],))
    u=cur.fetchone()
    cur.execute("SELECT * FROM products WHERE user_id=%s ORDER BY id DESC", (session['user']['id'],))
    my_products=cur.fetchall()
    cur.execute("SELECT * FROM orders WHERE buyer_id=%s ORDER BY id DESC", (session['user']['id'],))
    my_orders=cur.fetchall()
    cur.execute("SELECT o.* FROM orders o JOIN products p ON o.product_id=p.id WHERE p.user_id=%s ORDER BY o.id DESC", (session['user']['id'],))
    shop_orders=cur.fetchall()
    cur.execute("SELECT product_id FROM wishlist WHERE user_id=%s", (session['user']['id'],))
    wish_ids=[r['product_id'] for r in cur.fetchall()]
    cur.close(); conn.close()
    if u: session['user']=dict(u)
    return render_template('profile.html', user=session.get('user'), products=my_products, my_orders=my_orders, shop_orders=shop_orders, wish_ids=wish_ids)

@app.route('/profile/edit', methods=['POST'])
def edit_profile():
    if 'user' not in session: return redirect('/')
    pic = save_photo(request.files.get('profile_pic'))
    conn=get_db(); cur=conn.cursor()
    lat = request.form.get('lat') or None; lng = request.form.get('lng') or None
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

@app.route('/wishlist/<int:pid>')
def toggle_wishlist(pid):
    if 'user' not in session: return redirect('/?msg=Adhi Login Kara')
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT id FROM wishlist WHERE user_id=%s AND product_id=%s", (session['user']['id'], pid))
    if cur.fetchone():
        cur.execute("DELETE FROM wishlist WHERE user_id=%s AND product_id=%s", (session['user']['id'], pid))
        msg="Wishlist madhun kadhla"
    else:
        cur.execute("INSERT INTO wishlist (user_id, product_id) VALUES (%s,%s)", (session['user']['id'], pid))
        msg="Wishlist madhe Save Zala ❤️"
    conn.commit(); cur.close(); conn.close()
    return redirect(request.referrer or '/?msg='+msg)

@app.route('/order/<int:pid>', methods=['POST'])
def create_order(pid):
    if 'user' not in session: return redirect('/?msg=Adhi Login Kara')
    qty = int(request.form.get('qty',1))
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM products WHERE id=%s", (pid,))
    p=cur.fetchone()
    if not p: return redirect('/')
    cur2=conn.cursor()
    cur2.execute("INSERT INTO orders (buyer_id,buyer_name,buyer_phone,product_id,product_title,product_image,store_name,owner_phone,price,qty) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (session['user']['id'], session['user']['name'], session['user'].get('phone',''), pid, p['title'], p['image'], p['store_name'], p['owner_phone'], p['price'], qty))
    conn.commit(); cur.close(); cur2.close(); conn.close()
    wa = f"https://wa.me/91{p['owner_phone']}?text=" + f"Namaste! Mala {p['title']} x {qty} pahije. Order ID: Local Market. Maza nav: {session['user']['name']}"
    return redirect(f"/?msg=Order Zali! Seller la WhatsApp kela aahe")

@app.route('/order/status/<int:oid>/<status>')
def order_status(oid, status):
    if 'user' not in session: return redirect('/')
    conn=get_db(); cur=conn.cursor()
    # Seller kiwa Admin ch badalvu shakto
    cur.execute("UPDATE orders SET status=%s WHERE id=%s", (status, oid))
    conn.commit(); cur.close(); conn.close()
    return redirect('/profile?msg=Order Status Badalla: '+status)

@app.route('/review/<int:pid>', methods=['POST'])
def add_review(pid):
    if 'user' not in session: return redirect('/?msg=Adhi Login Kara')
    rating = int(request.form.get('rating',5)); comment = request.form.get('comment','')
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("INSERT INTO reviews (product_id,user_id,user_name,rating,comment) VALUES (%s,%s,%s,%s,%s)",
        (pid, session['user']['id'], session['user']['name'], rating, comment))
    cur.execute("SELECT AVG(rating) as avg, COUNT(*) as cnt FROM reviews WHERE product_id=%s", (pid,))
    r = cur.fetchone()
    cur2=conn.cursor()
    cur2.execute("UPDATE products SET rating=%s, rating_count=%s WHERE id=%s", (float(r['avg'] or 0), r['cnt'], pid))
    conn.commit(); cur.close(); cur2.close(); conn.close()
    return redirect('/?msg=Review Dilya baddal Dhanyavad ⭐')

@app.route('/delete/<int:pid>')
def delete_product(pid):
    if 'user' not in session: return redirect('/')
    conn=get_db(); cur=conn.cursor()
    if session['user'].get('is_admin'):
        cur.execute("DELETE FROM products WHERE id=%s", (pid,))
    else:
        cur.execute("DELETE FROM products WHERE id=%s AND user_id=%s", (pid, session['user']['id']))
    conn.commit(); cur.close(); conn.close()
    return redirect(request.referrer or '/')

@app.route('/admin')
def admin():
    if 'user' not in session or not session['user'].get('is_admin'): return redirect('/')
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM users ORDER BY id DESC"); users=cur.fetchall()
    cur.execute("SELECT * FROM products ORDER BY id DESC"); products=cur.fetchall()
    cur.execute("SELECT * FROM orders ORDER BY id DESC"); orders=cur.fetchall()
    total=sum([float(p['price'] or 0) for p in products])
    order_total=sum([float(o['price'] or 0)*int(o['qty'] or 1) for o in orders])
    cur.close(); conn.close()
    return render_template('admin.html', users=users, products=products, orders=orders, total_sell=total, order_total=order_total, user=session.get('user'))

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