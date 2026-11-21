from flask import Flask, render_template, request, redirect, session, jsonify, url_for
import os
from werkzeug.utils import secure_filename
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.secret_key = "localmarket_secret_123"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED = {'png','jpg','jpeg','webp','avif'}

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    conn.autocommit = False
    return conn

def save_file(file):
    if not file or file.filename == '':
        return None
    ext = file.filename.rsplit('.',1)[-1].lower()
    if ext not in ALLOWED: return None
    name = secure_filename(file.filename)
    path = os.path.join(app.config['UPLOAD_FOLDER'], name)
    base, e = os.path.splitext(name)
    i=1
    while os.path.exists(path):
        path = os.path.join(app.config['UPLOAD_FOLDER'], f"{base}_{i}{e}"); i+=1
    file.save(path)
    return "/static/uploads/" + os.path.basename(path)

def init_db():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        name TEXT, store_name TEXT, phone TEXT,
        email TEXT UNIQUE, password TEXT, role TEXT DEFAULT 'Customer',
        profile_pic TEXT DEFAULT '', bio TEXT DEFAULT '',
        location TEXT DEFAULT '', opening TEXT DEFAULT '9 AM - 9 PM',
        rating REAL DEFAULT 4.5,
        is_blocked INTEGER DEFAULT 0, is_admin INTEGER DEFAULT 0
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS products (
        id SERIAL PRIMARY KEY,
        user_id INTEGER, store_name TEXT, title TEXT,
        category TEXT, price REAL, description TEXT,
        image TEXT, rating REAL DEFAULT 4.8, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS notifications (
        id SERIAL PRIMARY KEY,
        user_id INTEGER, message TEXT, is_read INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("SELECT * FROM users WHERE email='admin@localmarket.com'")
    admin = cur.fetchone()
    if not admin:
        cur.execute("INSERT INTO users (name,store_name,email,password,role,is_admin,rating) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            ('Admin','LocalMarket Admin','admin@localmarket.com','admin123','Store',1,5.0))
    cur.execute("SELECT COUNT(*) as c FROM products")
    if cur.fetchone()['c']==0:
        demo=[
            (1,'Sayali Fashion','Designer Kurti','Clothes',499,'Premium cotton kurti','https://images.unsplash.com/photo-1445205170230-053b83016050?w=600'),
            (1,'Shinde Kirana','Tandal 5kg','Kirana',320,'Best quality, 30 min delivery','https://images.unsplash.com/photo-1542838132-92c53300491e?w=600'),
        ]
        cur.executemany("INSERT INTO products (user_id,store_name,title,category,price,description,image) VALUES (%s,%s,%s,%s,%s,%s,%s)", demo)
    conn.commit(); cur.close(); conn.close()

init_db()

@app.route('/')
def home():
    conn=get_db(); cur=conn.cursor()
    cat=request.args.get('cat',''); q=request.args.get('q','')
    sql="SELECT p.*, u.profile_pic as owner_pic, u.phone as owner_phone, u.location as owner_loc, u.opening as owner_open, u.bio as owner_bio, u.is_blocked as owner_blocked FROM products p LEFT JOIN users u ON p.user_id=u.id WHERE 1=1"
    params=[]
    if cat and cat!='All': sql+=" AND p.category=%s"; params.append(cat)
    if q: sql+=" AND (p.title LIKE %s OR p.store_name LIKE %s)"; params+=[f"%{q}%",f"%{q}%"]
    cur.execute(sql+" ORDER BY p.id DESC", params)
    products=cur.fetchall()
    notifs=[]
    if 'user' in session:
        cur.execute("SELECT * FROM notifications WHERE user_id=%s ORDER BY id DESC LIMIT 5",(session['user']['id'],))
        notifs=cur.fetchall()
    cur.close(); conn.close()
    return render_template('index.html', products=products, user=session.get('user'), cat=cat, q=q, notifs=notifs)

@app.route('/register', methods=['POST'])
def register():
    d=request.form
    pic=save_file(request.files.get('profile_pic'))
    conn=get_db(); cur=conn.cursor()
    try:
        cur.execute("INSERT INTO users (name,store_name,phone,email,password,role,profile_pic,bio,location,opening) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (d['name'], d.get('store_name',''), d.get('phone',''), d['email'], d['password'], d['role'], pic or '', d.get('bio',''), d.get('location',''), d.get('opening','9 AM - 9 PM')))
        user=cur.fetchone()
        conn.commit()
        session['user']=dict(user)
    except Exception as e: print(e); conn.rollback()
    cur.close(); conn.close(); return redirect('/')

@app.route('/login', methods=['POST'])
def login():
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT * FROM users WHERE email=%s AND password=%s", (request.form['email'], request.form['password']))
    user=cur.fetchone()
    cur.close(); conn.close()
    if user:
        u=dict(user)
        if u['is_blocked']==1:
            session['blocked_msg']="Tumcha account Admin ne block kela aahe."
            return redirect('/')
        session['user']=u; session.pop('blocked_msg',None)
    else:
        session['blocked_msg']="Wrong Email / Password"
    return redirect('/')

@app.route('/logout')
def logout(): session.clear(); return redirect('/')

@app.route('/update_profile', methods=['POST'])
def update_profile():
    if 'user' not in session: return redirect('/')
    d=request.form; uid=session['user']['id']
    pic=save_file(request.files.get('profile_pic'))
    conn=get_db(); cur=conn.cursor()
    if pic:
        cur.execute("UPDATE users SET name=%s, store_name=%s, phone=%s, bio=%s, location=%s, opening=%s, profile_pic=%s WHERE id=%s",
            (d['name'], d.get('store_name',''), d.get('phone',''), d.get('bio',''), d.get('location',''), d.get('opening',''), pic, uid))
    else:
        cur.execute("UPDATE users SET name=%s, store_name=%s, phone=%s, bio=%s, location=%s, opening=%s WHERE id=%s",
            (d['name'], d.get('store_name',''), d.get('phone',''), d.get('bio',''), d.get('location',''), d.get('opening',''), uid))
    conn.commit()
    cur.execute("SELECT * FROM users WHERE id=%s",(uid,))
    user=cur.fetchone()
    cur.close(); conn.close(); session['user']=dict(user); return redirect('/')

@app.route('/add', methods=['POST'])
def add():
    if 'user' not in session: return redirect('/')
    if session['user'].get('is_blocked'): return redirect('/')
    u=session['user']
    img=save_file(request.files.get('product_pic'))
    if not img: img=request.form.get('image') or 'https://images.unsplash.com/photo-1542838132-92c53300491e?w=600'
    conn=get_db(); cur=conn.cursor()
    cur.execute("INSERT INTO products (user_id,store_name,title,category,price,description,image) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (u['id'], u.get('store_name') or u['name'], request.form['title'], request.form['category'], request.form['price'], request.form['description'], img))
    conn.commit(); cur.close(); conn.close(); return redirect('/')

@app.route('/delete/<int:pid>')
def delete(pid):
    if 'user' not in session: return redirect('/')
    conn=get_db(); cur=conn.cursor()
    if session['user'].get('is_admin'):
        cur.execute("DELETE FROM products WHERE id=%s", (pid,))
    else:
        cur.execute("DELETE FROM products WHERE id=%s AND user_id=%s", (pid, session['user']['id']))
    conn.commit(); cur.close(); conn.close(); return redirect('/')

@app.route('/admin')
def admin():
    if 'user' not in session or not session['user'].get('is_admin'): return redirect('/')
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT * FROM users ORDER BY id DESC"); users=cur.fetchall()
    cur.execute("SELECT p.*, u.email as owner_email, u.phone as owner_phone FROM products p LEFT JOIN users u ON p.user_id=u.id ORDER BY p.id DESC"); products=cur.fetchall()
    cur.execute("SELECT COALESCE(SUM(price),0) as s FROM products"); total_sell=cur.fetchone()['s']
    cur.close(); conn.close()
    return render_template('admin.html', users=users, products=products, user=session['user'], total_sell=total_sell)

@app.route('/admin/block/<int:uid>')
def admin_block(uid):
    if 'user' not in session or not session['user'].get('is_admin'): return redirect('/')
    conn=get_db(); cur=conn.cursor()
    cur.execute("UPDATE users SET is_blocked=1 WHERE id=%s", (uid,))
    cur.execute("INSERT INTO notifications (user_id,message) VALUES (%s,%s)", (uid, "Tumcha account Admin ne block kela aahe."))
    conn.commit(); cur.close(); conn.close(); return redirect('/admin')

@app.route('/admin/unblock/<int:uid>')
def admin_unblock(uid):
    if 'user' not in session or not session['user'].get('is_admin'): return redirect('/')
    conn=get_db(); cur=conn.cursor()
    cur.execute("UPDATE users SET is_blocked=0 WHERE id=%s", (uid,))
    cur.execute("INSERT INTO notifications (user_id,message) VALUES (%s,%s)", (uid, "Tumcha account parat unblock zala aahe."))
    conn.commit(); cur.close(); conn.close(); return redirect('/admin')

@app.route('/admin/delete_user/<int:uid>')
def admin_delete_user(uid):
    if 'user' not in session or not session['user'].get('is_admin'): return redirect('/')
    conn=get_db(); cur=conn.cursor()
    cur.execute("DELETE FROM products WHERE user_id=%s", (uid,))
    cur.execute("DELETE FROM notifications WHERE user_id=%s", (uid,))
    cur.execute("DELETE FROM users WHERE id=%s", (uid,))
    conn.commit(); cur.close(); conn.close(); return redirect('/admin')

if __name__=='__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
