import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import base64

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "local-market-key-2026")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", "sqlite:///localmarket.db")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

if app.config['SQLALCHEMY_DATABASE_URI'].startswith("postgres://"):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace("postgres://", "postgresql://", 1)

db = SQLAlchemy(app)

# ---------- MODELS ----------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(300), nullable=False)
    phone = db.Column(db.String(20))
    role = db.Column(db.String(20), default='customer')
    village = db.Column(db.String(100))
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)
    profile_pic = db.Column(db.Text)
    is_blocked = db.Column(db.Boolean, default=False)
    is_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    shop = db.relationship('Shop', backref='owner', uselist=False, cascade="all, delete-orphan")

class Village(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    taluka = db.Column(db.String(100), default='Malshiras')
    district = db.Column(db.String(100), default='Solapur')
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    icon = db.Column(db.String(50), default='🛒')

class Shop(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True)
    shop_name = db.Column(db.String(150), nullable=False)
    village = db.Column(db.String(100))
    address = db.Column(db.Text)
    phone = db.Column(db.String(20))
    timings = db.Column(db.String(100), default='9 AM - 9 PM')
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)
    shop_pic = db.Column(db.Text)
    is_verified = db.Column(db.Boolean, default=False)
    views = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shop.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100))
    price = db.Column(db.Float, nullable=False)
    mrp = db.Column(db.Float, default=0)
    description = db.Column(db.Text)
    image = db.Column(db.Text)
    stock_qty = db.Column(db.Integer, default=10)
    is_available = db.Column(db.Boolean, default=True)
    views = db.Column(db.Integer, default=0)
    rating = db.Column(db.Float, default=0)
    rating_count = db.Column(db.Integer, default=0)
    last_stock_check = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    shop = db.relationship('Shop', backref='products')
    images = db.relationship('ProductImage', backref='product', cascade="all, delete-orphan")
    inventory = db.relationship('Inventory', backref='product', uselist=False, cascade="all, delete-orphan")

class ProductImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    image_url = db.Column(db.Text)

class Inventory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), unique=True)
    qty = db.Column(db.Integer, default=0)
    low_stock_at = db.Column(db.Integer, default=5)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    shop_id = db.Column(db.Integer, db.ForeignKey('shop.id'))
    customer_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    customer_name = db.Column(db.String(100))
    customer_phone = db.Column(db.String(20))
    qty = db.Column(db.Integer, default=1)
    status = db.Column(db.String(20), default='Pending')
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    product = db.relationship('Product', backref='reservations')

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    shop_id = db.Column(db.Integer, db.ForeignKey('shop.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user_name = db.Column(db.String(100))
    rating = db.Column(db.Integer, default=5)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shop.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    title = db.Column(db.String(200))
    message = db.Column(db.Text)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SubscriptionPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True)
    monthly_price = db.Column(db.Float, default=0)
    yearly_price = db.Column(db.Float, default=0)
    product_limit = db.Column(db.Integer, default=10)
    features = db.Column(db.Text, default='')
    is_active = db.Column(db.Boolean, default=True)

class SellerSubscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    shop_id = db.Column(db.Integer, db.ForeignKey('shop.id'), nullable=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('subscription_plan.id'))
    plan_name = db.Column(db.String(50))
    duration = db.Column(db.String(20), default='monthly')
    price = db.Column(db.Float, default=0)
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    expiry_date = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='Pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    plan = db.relationship('SubscriptionPlan')

class SubscriptionPayment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey('seller_subscription.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    amount = db.Column(db.Float, default=0)
    method = db.Column(db.String(50), default='UPI - At Shop / Manual')
    status = db.Column(db.String(20), default='Pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SubscriptionHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    action = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer)
    action = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
# ---------- HELPERS ----------

def current_user():
    if 'user_id' not in session:
        return None
    return User.query.get(session['user_id'])

def save_photo(f):
    if not f or f.filename == '':
        return None
    try:
        data = f.read()
        return f"data:{f.content_type or 'image/jpeg'};base64,{base64.b64encode(data).decode()}"
    except:
        return None

def log_audit(admin_id, action):
    try:
        db.session.add(AuditLog(admin_id=admin_id, action=action))
        db.session.commit()
    except:
        db.session.rollback()

def get_active_sub(user_id):
    sub = SellerSubscription.query.filter_by(user_id=user_id, status='Active').order_by(SellerSubscription.expiry_date.desc()).first()
    if sub and sub.expiry_date and sub.expiry_date < datetime.utcnow():
        sub.status = 'Expired'
        db.session.commit()
        return None
    return sub

def init_db():
    with app.app_context():
        db.create_all()

        if not Village.query.first():
            villages = ["Malshiras", "Akluj", "Velapur", "Natepute", "Piliv", "Sangola", "Pandharpur", "Mohol", "Mardi", "Borgaon", "Khandali", "Gondhave", "Jinti", "Tandulwadi", "Kurduwadi"]
            for v in villages:
                db.session.add(Village(name=v))

        if not Category.query.first():
            for c, i in [("Kirana", "🛒"), ("Kapad / Cloth", "👕"), ("Electronics", "📱"), ("Medical", "💊"), ("Hardware", "🔧"), ("Bakery", "🍞"), ("Sheti / Agro", "🌾"), ("Beauty", "💄"), ("Mobile Shop", "📞"), ("General", "🏪")]:
                db.session.add(Category(name=c, icon=i))

        if not SubscriptionPlan.query.first():
            db.session.add(SubscriptionPlan(name='Free', monthly_price=0, yearly_price=0, product_limit=10, features='Basic Shop Profile,10 Products,Basic Discovery'))
            db.session.add(SubscriptionPlan(name='Silver', monthly_price=199, yearly_price=1999, product_limit=50, features='50 Products,Insights,Enquiry Management,Extra Visibility'))
            db.session.add(SubscriptionPlan(name='Gold', monthly_price=499, yearly_price=4999, product_limit=-1, features='Unlimited Products,Advanced Analytics,Featured Shop,Promotions,Demand Insights'))

        if not User.query.filter_by(email='admin@localmarket.com').first():
            db.session.add(User(name='Admin', email='admin@localmarket.com', password=generate_password_hash('admin123'), phone='9876543210', role='admin', village='Malshiras'))

        db.session.commit()

# ---------- CUSTOMER - HOME ----------

@app.route('/')
def home():
    init_db()
    search = request.args.get('search', '').strip()
    cat = request.args.get('cat', 'All')
    village = request.args.get('village', 'All')
    sort = request.args.get('sort', 'new')

    q = Product.query.join(Shop, Product.shop_id == Shop.id).filter(Product.is_available == True)

    if cat != 'All':
        q = q.filter(Product.category == cat)

    if village != 'All':
        q = q.filter(Shop.village == village)

    if search:
        q = q.filter(Product.title.ilike(f"%{search}%"))

    if sort == 'low':
        q = q.order_by(Product.price.asc())
    elif sort == 'high':
        q = q.order_by(Product.price.desc())
    elif sort == 'rating':
        q = q.order_by(Product.rating.desc())
    else:
        q = q.order_by(Product.id.desc())

    products = q.all()
    shops = Shop.query.filter(Shop.lat.isnot(None)).all()

    map_shops = []
    for p in products:
        if p.shop and p.shop.lat:
            map_shops.append({
                'pid': p.id,
                'title': p.title,
                'price': p.price,
                'image': p.image,
                'shop': p.shop.shop_name,
                'village': p.shop.village,
                'lat': p.shop.lat,
                'lng': p.shop.lng,
                'stock': p.stock_qty,
                'phone': p.shop.phone
            })

    fav_ids = []
    u = current_user()
    if u:
        fav_ids = [f.product_id for f in Favorite.query.filter_by(user_id=u.id).all()]

    offers = Product.query.filter(Product.mrp > Product.price).order_by(Product.id.desc()).limit(4).all()
    villages = Village.query.all()
    cats = Category.query.all()

    return render_template('index.html', products=products, shops=shops, map_shops=map_shops, fav_ids=fav_ids, user=u, search=search, cat=cat, village=village, sort=sort, offers=offers, villages=villages, cats=cats, msg=request.args.get('msg', ''))
# ---------- AUTH ----------

@app.route('/register', methods=['POST'])
def register():
    role = request.form.get('role', 'customer')

    if User.query.filter_by(email=request.form.get('email')).first():
        return redirect('/?msg=Email already registered')

    u = User(
        name=request.form.get('name'),
        email=request.form.get('email'),
        password=generate_password_hash(request.form.get('password')),
        phone=request.form.get('phone'),
        village=request.form.get('village'),
        role=role
    )
    db.session.add(u)
    db.session.commit()

    if role == 'seller':
        shop = Shop(
            user_id=u.id,
            shop_name=request.form.get('shop_name') or f"{u.name} Store",
            village=u.village,
            phone=u.phone
        )
        db.session.add(shop)
        db.session.commit()

        free = SubscriptionPlan.query.filter_by(name='Free').first()
        if free:
            sub = SellerSubscription(
                user_id=u.id,
                shop_id=shop.id,
                plan_id=free.id,
                plan_name='Free',
                duration='monthly',
                price=0,
                start_date=datetime.utcnow(),
                expiry_date=datetime.utcnow() + timedelta(days=3650),
                status='Active'
            )
            db.session.add(sub)
            db.session.commit()

    return redirect('/?msg=Account created. Please login.')

@app.route('/login', methods=['POST'])
def login():
    u = User.query.filter_by(email=request.form.get('email')).first()

    if not u or not check_password_hash(u.password, request.form.get('password')):
        return redirect('/?msg=Invalid email or password')

    if u.is_blocked:
        return redirect('/?msg=Your account is blocked')

    session['user_id'] = u.id
    return redirect('/?msg=Welcome, ' + u.name)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ---------- SHOP & PRODUCT DETAIL ----------

@app.route('/shop/<int:shop_id>')
def shop_detail(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    shop.views += 1
    db.session.commit()

    prods = Product.query.filter_by(shop_id=shop_id, is_available=True).all()
    revs = Review.query.filter_by(shop_id=shop_id).order_by(Review.id.desc()).all()

    return render_template('shop.html', shop=shop, products=prods, reviews=revs, user=current_user())

@app.route('/product/<int:pid>')
def product_detail(pid):
    p = Product.query.get_or_404(pid)
    p.views += 1
    db.session.commit()

    revs = Review.query.filter_by(product_id=pid).order_by(Review.id.desc()).all()

    return render_template('product.html', p=p, reviews=revs, user=current_user())
# ---------- RESERVE - NO DELIVERY, FAKT RESERVE ----------

@app.route('/reserve/<int:pid>', methods=['POST'])
def reserve(pid):
    u = current_user()
    if not u:
        return redirect('/?msg=Please login to reserve')

    p = Product.query.get_or_404(pid)

    r = Reservation(
        product_id=pid,
        shop_id=p.shop_id,
        customer_id=u.id,
        customer_name=u.name,
        customer_phone=u.phone,
        qty=int(request.form.get('qty', 1)),
        note=request.form.get('note', '')
    )
    db.session.add(r)

    db.session.add(Notification(
        user_id=p.user_id,
        title='New Reservation',
        message=f"{u.name} ne {p.title} reserve kelay ({r.qty} qty)"
    ))

    db.session.commit()
    return redirect('/?msg=Reservation request sent! Seller will confirm. Visit shop to collect.')

# ---------- FAVORITE ----------

@app.route('/favorite/<int:pid>')
def toggle_fav(pid):
    u = current_user()
    if not u:
        return redirect('/?msg=Please login first')

    f = Favorite.query.filter_by(user_id=u.id, product_id=pid).first()

    if f:
        db.session.delete(f)
    else:
        db.session.add(Favorite(user_id=u.id, product_id=pid))

    db.session.commit()
    return redirect(request.referrer or '/')

@app.route('/favorite-shop/<int:sid>')
def toggle_fav_shop(sid):
    u = current_user()
    if not u:
        return redirect('/?msg=Please login first')

    f = Favorite.query.filter_by(user_id=u.id, shop_id=sid).first()

    if f:
        db.session.delete(f)
    else:
        db.session.add(Favorite(user_id=u.id, shop_id=sid))

    db.session.commit()
    return redirect(request.referrer or '/')

# ---------- REVIEW ----------

@app.route('/review/<int:pid>', methods=['POST'])
def add_review(pid):
    u = current_user()
    if not u:
        return redirect('/?msg=Please login first')

    p = Product.query.get_or_404(pid)

    db.session.add(Review(
        product_id=pid,
        shop_id=p.shop_id,
        user_id=u.id,
        user_name=u.name,
        rating=int(request.form.get('rating', 5)),
        comment=request.form.get('comment', '')
    ))

    all_r = Review.query.filter_by(product_id=pid).all()
    p.rating = round(sum([x.rating for x in all_r]) / len(all_r), 1)
    p.rating_count = len(all_r)

    db.session.commit()
    return redirect('/?msg=Thank you for review!')
# ---------- SELLER ----------
# ---------- SELLER ----------

@app.route('/seller')
def seller_dashboard():
    u = current_user()
    if not u or u.role not in ['seller', 'admin']:
        return redirect('/?msg=Login as Seller')
    shop = Shop.query.filter_by(user_id=u.id).first()
    if not shop:
        return redirect('/?msg=Shop not found')
    prods = Product.query.filter_by(shop_id=shop.id).order_by(Product.id.desc()).all()
    res = Reservation.query.filter_by(shop_id=shop.id).order_by(Reservation.id.desc()).all()
    revs = Review.query.filter_by(shop_id=shop.id).order_by(Review.id.desc()).all()
    followers = Favorite.query.filter_by(shop_id=shop.id).count()
    sub = get_active_sub(u.id)
    total_views = sum([p.views for p in prods]) + shop.views
    low_stock = [p for p in prods if p.stock_qty <= 5]
    pending_res = len([r for r in res if r.status == 'Pending'])
    village_demand = {}
    for r in res:
        cu = User.query.get(r.customer_id)
        if cu:
            village_demand[cu.village or 'Unknown'] = village_demand.get(cu.village or 'Unknown', 0) + 1
    notifs = Notification.query.filter_by(user_id=u.id).order_by(Notification.id.desc()).limit(10).all()
    plans = SubscriptionPlan.query.filter_by(is_active=True).all()
    cats = Category.query.all()
    return render_template('seller.html', user=u, shop=shop, products=prods, reservations=res, reviews=revs, followers=followers, sub=sub, total_views=total_views, low_stock=low_stock, pending_res=pending_res, village_demand=village_demand, notifs=notifs, plans=plans, cats=cats, msg=request.args.get('msg', ''))

@app.route('/seller/add-product', methods=['POST'])
def seller_add_product():
    u = current_user()
    if not u:
        return redirect('/')
    shop = Shop.query.filter_by(user_id=u.id).first()
    if not shop:
        return redirect('/seller?msg=Shop not found')
    sub = get_active_sub(u.id)
    limit = 10
    if sub and sub.plan:
        limit = sub.plan.product_limit
    count = Product.query.filter_by(shop_id=shop.id).count()
    if limit != -1 and count >= limit:
        return redirect('/seller?msg=Product limit reached! Upgrade to Silver/Gold plan.')
    img = save_photo(request.files.get('product_pic')) or "https://images.unsplash.com/photo-1542838132-92c53300491e?w=600"
    price = float(request.form.get('price', 0))
    mrp = float(request.form.get('mrp') or price)
    p = Product(shop_id=shop.id, user_id=u.id, title=request.form.get('title'), category=request.form.get('category'), price=price, mrp=mrp, description=request.form.get('description'), image=img, stock_qty=int(request.form.get('stock_qty') or 10), is_available=True)
    db.session.add(p)
    db.session.commit()
    db.session.add(Inventory(product_id=p.id, qty=p.stock_qty))
    db.session.commit()
    return redirect('/seller?msg=Product added successfully!')

@app.route('/seller/delete-product/<int:pid>')
def seller_delete_product(pid):
    u = current_user()
    if not u: return redirect('/')
    p = Product.query.get_or_404(pid)
    if p.user_id != u.id and u.role != 'admin':
        return redirect('/seller')
    db.session.delete(p)
    db.session.commit()
    return redirect('/seller?msg=Product deleted')

@app.route('/seller/toggle-stock/<int:pid>')
def seller_toggle_stock(pid):
    u = current_user()
    if not u: return redirect('/')
    p = Product.query.get_or_404(pid)
    p.is_available = not p.is_available
    db.session.commit()
    return redirect('/seller')

@app.route('/seller/update-stock/<int:pid>', methods=['POST'])
def update_stock(pid):
    u = current_user()
    if not u: return redirect('/')
    p = Product.query.get_or_404(pid)
    if p.user_id != u.id and u.role != 'admin':
        return redirect('/seller')
    qty = int(request.form.get('qty', 0))
    p.stock_qty = qty
    p.is_available = qty > 0
    p.last_stock_check = datetime.utcnow()
    inv = Inventory.query.filter_by(product_id=pid).first()
    if inv:
        inv.qty = qty
        inv.updated_at = datetime.utcnow()
    db.session.commit()
    return redirect('/seller?msg=Stock updated!')

@app.route('/seller/reservation/<int:rid>/<status>')
def update_reservation(rid, status):
    u = current_user()
    if not u: return redirect('/')
    r = Reservation.query.get_or_404(rid)
    if status in ['Pending','Confirmed','Ready','Completed','Cancelled']:
        r.status = status
        db.session.commit()
        db.session.add(Notification(user_id=r.customer_id, title=f'Reservation {status}', message=f'Tumchi reservation {status} zali aahe. Shop la visit kara.'))
        db.session.commit()
    return redirect('/seller?msg=Reservation ' + status)

@app.route('/seller/shop-update', methods=['POST'])
def shop_update():
    u = current_user()
    if not u:
        return redirect('/?msg=Please login')
    shop = Shop.query.filter_by(user_id=u.id).first()
    if not shop:
        return redirect('/seller?msg=Shop not found')
    shop.shop_name = request.form.get('shop_name') or shop.shop_name
    shop.village = request.form.get('village') or shop.village
    shop.address = request.form.get('address')
    shop.phone = request.form.get('phone')
    shop.timings = request.form.get('timings')
    try:
        if request.form.get('lat'):
            shop.lat = float(request.form.get('lat'))
        if request.form.get('lng'):
            shop.lng = float(request.form.get('lng'))
    except:
        pass
    pic = save_photo(request.files.get('shop_pic'))
    if pic:
        shop.shop_pic = pic
    db.session.commit()
    return redirect('/seller?msg=Shop updated!')

@app.route('/seller/add-category', methods=['POST'])
def seller_add_new_category():
    u = current_user()
    if not u: return redirect('/')
    name = request.form.get('name','').strip()
    if name and not Category.query.filter_by(name=name).first():
        db.session.add(Category(name=name, icon='🏪'))
        db.session.commit()
    return redirect('/seller?msg=Category added!')
# ---------- SELLER SUBSCRIBE ----------

@app.route('/seller/subscribe/<int:plan_id>/<duration>')
def seller_subscribe(plan_id, duration):
    u = current_user()
    if not u:
        return redirect('/')

    plan = SubscriptionPlan.query.get_or_404(plan_id)
    price = plan.monthly_price if duration == 'monthly' else plan.yearly_price
    days = 30 if duration == 'monthly' else 365

    shop = Shop.query.filter_by(user_id=u.id).first()

    sub = SellerSubscription(
        user_id=u.id,
        shop_id=shop.id if shop else None,
        plan_id=plan.id,
        plan_name=plan.name,
        duration=duration,
        price=price,
        start_date=datetime.utcnow(),
        expiry_date=datetime.utcnow() + timedelta(days=days),
        status='Pending' if price > 0 else 'Active'
    )
    db.session.add(sub)
    db.session.commit()

    db.session.add(SubscriptionPayment(
        subscription_id=sub.id,
        user_id=u.id,
        amount=price,
        status='Pending' if price > 0 else 'Verified'
    ))

    db.session.add(SubscriptionHistory(
        user_id=u.id,
        action=f"Subscribed to {plan.name} ({duration}) - Rs.{price}"
    ))

    db.session.commit()

    if price == 0:
        return redirect('/seller?msg=Free plan activated!')

    return redirect('/seller?msg=Subscription request sent! Admin will verify payment.')

# ---------- ADMIN DASHBOARD ----------

@app.route('/admin')
def admin_dashboard():
    u = current_user()
    if not u or u.role != 'admin':
        return redirect('/?msg=Admin only')

    users = User.query.order_by(User.id.desc()).all()
    shops = Shop.query.order_by(Shop.id.desc()).all()
    products = Product.query.order_by(Product.id.desc()).all()
    reservations = Reservation.query.order_by(Reservation.id.desc()).all()
    plans = SubscriptionPlan.query.all()
    subs = SellerSubscription.query.order_by(SellerSubscription.id.desc()).all()
    payments = SubscriptionPayment.query.order_by(SubscriptionPayment.id.desc()).all()
    reviews = Review.query.order_by(Review.id.desc()).all()
    villages = Village.query.all()
    cats = Category.query.all()
    logs = AuditLog.query.order_by(AuditLog.id.desc()).limit(20).all()

    revenue = sum([p.amount for p in payments if p.status == 'Verified'])
    active_subs = len([s for s in subs if s.status == 'Active'])

    return render_template('admin.html', user=u, users=users, shops=shops, products=products, reservations=reservations, plans=plans, subs=subs, payments=payments, reviews=reviews, villages=villages, cats=cats, logs=logs, revenue=revenue, active_subs=active_subs, msg=request.args.get('msg', ''))

# ---------- ADMIN - PLAN ----------

@app.route('/admin/plan', methods=['POST'])
def admin_plan_create():
    u = current_user()
    if not u or u.role != 'admin':
        return redirect('/')

    plan = SubscriptionPlan(
        name=request.form.get('name'),
        monthly_price=float(request.form.get('monthly_price', 0)),
        yearly_price=float(request.form.get('yearly_price', 0)),
        product_limit=int(request.form.get('product_limit', 10)),
        features=request.form.get('features', '')
    )
    db.session.add(plan)
    db.session.commit()
    log_audit(u.id, f"Created plan {plan.name}")

    return redirect('/admin?msg=Plan created!')

@app.route('/admin/plan/edit/<int:pid>', methods=['POST'])
def admin_plan_edit(pid):
    u = current_user()
    if not u or u.role != 'admin':
        return redirect('/')

    p = SubscriptionPlan.query.get_or_404(pid)
    p.name = request.form.get('name')
    p.monthly_price = float(request.form.get('monthly_price', 0))
    p.yearly_price = float(request.form.get('yearly_price', 0))
    p.product_limit = int(request.form.get('product_limit', 10))
    p.features = request.form.get('features', '')

    db.session.commit()
    log_audit(u.id, f"Edited plan {p.name}")

    return redirect('/admin?msg=Plan updated!')

@app.route('/admin/plan/toggle/<int:pid>')
def admin_plan_toggle(pid):
    u = current_user()
    if not u or u.role != 'admin':
        return redirect('/')

    p = SubscriptionPlan.query.get_or_404(pid)
    p.is_active = not p.is_active
    db.session.commit()

    return redirect('/admin')
# ---------- ADMIN - SUBSCRIPTION ACTIONS ----------

@app.route('/admin/sub/<int:sid>/<action>')
def admin_sub_action(sid, action):
    u = current_user()
    if not u or u.role != 'admin':
        return redirect('/')

    s = SellerSubscription.query.get_or_404(sid)

    if action == 'approve':
        s.status = 'Active'
        db.session.add(SubscriptionHistory(user_id=s.user_id, action=f"Subscription {s.plan_name} approved"))
    elif action == 'reject':
        s.status = 'Cancelled'
    elif action == 'suspend':
        s.status = 'Cancelled'
    elif action == 'extend':
        s.expiry_date = (s.expiry_date or datetime.utcnow()) + timedelta(days=30)
        s.status = 'Active'
    elif action == 'reactivate':
        s.status = 'Active'

    db.session.commit()
    log_audit(u.id, f"Sub {sid} -> {action}")

    return redirect('/admin?msg=Subscription ' + action)

@app.route('/admin/payment/<int:pid>/<status>')
def admin_payment(pid, status):
    u = current_user()
    if not u or u.role != 'admin':
        return redirect('/')

    pay = SubscriptionPayment.query.get_or_404(pid)
    pay.status = status

    if status == 'Verified':
        sub = SellerSubscription.query.get(pay.subscription_id)
        if sub:
            sub.status = 'Active'

    db.session.commit()
    return redirect('/admin?msg=Payment ' + status)

@app.route('/admin/shop-verify/<int:sid>')
def admin_shop_verify(sid):
    u = current_user()
    if not u or u.role != 'admin':
        return redirect('/')

    s = Shop.query.get_or_404(sid)
    s.is_verified = not s.is_verified
    db.session.commit()

    return redirect('/admin')

@app.route('/admin/user-block/<int:uid>')
def admin_user_block(uid):
    u = current_user()
    if not u or u.role != 'admin':
        return redirect('/')

    target = User.query.get_or_404(uid)
    target.is_blocked = not target.is_blocked
    db.session.commit()
    log_audit(u.id, f"Blocked/Unblocked user {uid}")

    return redirect('/admin')

@app.route('/admin/village', methods=['POST'])
def admin_village():
    u = current_user()
    if not u or u.role != 'admin':
        return redirect('/')

    db.session.add(Village(name=request.form.get('name')))
    db.session.commit()

    return redirect('/admin?msg=Village added!')

@app.route('/admin/category', methods=['POST'])
def admin_category():
    u = current_user()
    if not u or u.role != 'admin':
        return redirect('/')

    db.session.add(Category(name=request.form.get('name'), icon=request.form.get('icon', '🛒')))
    db.session.commit()

    return redirect('/admin?msg=Category added!')

@app.route('/admin/delete-product/<int:pid>')
def admin_delete_product(pid):
    u = current_user()
    if not u or u.role != 'admin':
        return redirect('/')

    db.session.delete(Product.query.get_or_404(pid))
    db.session.commit()

    return redirect('/admin')

# ---------- API - PRODUCT MAP SEARCH ----------

@app.route('/api/map-search')
def api_map_search():
    q = request.args.get('q', '')
    prods = Product.query.filter(Product.title.ilike(f"%{q}%"), Product.is_available == True).all()

    out = []
    for p in prods:
        if p.shop and p.shop.lat:
            out.append({
                'title': p.title,
                'price': p.price,
                'image': p.image,
                'shop': p.shop.shop_name,
                'village': p.shop.village,
                'lat': p.shop.lat,
                'lng': p.shop.lng,
                'stock': p.stock_qty,
                'phone': p.shop.phone,
                'pid': p.id
            })

    return jsonify(out)
@app.route('/seller/add-category', methods=['POST'])
def seller_add_category():
    u = current_user()
    if not u: return redirect('/')
    name = request.form.get('name','').strip()
    if name and not Category.query.filter_by(name=name).first():
        db.session.add(Category(name=name, icon='🏪'))
        db.session.commit()
    return redirect('/seller?msg=Category added!')

# ---------- RUN ----------

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))