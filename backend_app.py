
import os
import re
from functools import wraps

from flask import (
    Flask, render_template, request,
    redirect, url_for, flash, session, jsonify
)
from supabase import create_client

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "local-market-development-key"
)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=os.environ.get("RENDER") == "true",
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 7,
    MAX_CONTENT_LENGTH=5 * 1024 * 1024
)


# ---------------- SUPABASE CONNECTION ----------------

def get_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL or SUPABASE_KEY is missing."
        )

    return create_client(url, key)
# Create a Supabase client using the logged-in user's access token.
def get_user_supabase():
    access_token = session.get("access_token")

    if not access_token:
        return None

    user_supabase = get_supabase()
    user_supabase.postgrest.auth(access_token)

    return user_supabase



# ---------------- COMMON FUNCTIONS ----------------

# Trim whitespace from form fields to avoid accidental empty-space values.
def clean(value):
    return (value or "").strip()


def valid_email(email):
    return bool(
        re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email or "")
    )


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please login first.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


# Protect routes so only the required account role can open them.
def role_required(required_role):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if session.get("role") != required_role:
                flash("You are not allowed to access this page.", "danger")
                return redirect(url_for("home"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


# ---------------- HOME ----------------

@app.route("/")
def home():
    return render_template("index.html")


# ---------------- REGISTER ----------------

@app.route("/register", methods=["GET", "POST"])
# Registration handler: processes Customer, Seller or Farmer signup form.
def register():

    if request.method == "GET":
        return render_template("register.html")

    role = clean(request.form.get("accountType")).lower()

    password = request.form.get("password", "")
    confirm_password = request.form.get("confirmPassword", "")

    # CUSTOMER, SELLER आणि FARMER या तीन account roles परवानगी आहेत.
    if role not in ["customer", "seller", "farmer"]:
        flash("Select Customer, Seller or Farmer account.", "danger")
        return redirect(url_for("register"))

    if len(password) < 8:
        flash("Password must be at least 8 characters.", "danger")
        return redirect(url_for("register"))

    if password != confirm_password:
        flash("Passwords do not match.", "danger")
        return redirect(url_for("register"))

    # CUSTOMER DETAILS
    if role == "customer":

        full_name = clean(request.form.get("full_name"))
        mobile = clean(request.form.get("mobile"))
        email = clean(request.form.get("email")).lower()

        state = clean(request.form.get("customer_state"))
        district = clean(request.form.get("customer_district"))
        taluka = clean(request.form.get("customer_taluka"))
        village = clean(request.form.get("customer_village"))
        address = clean(request.form.get("customer_address"))

        if not all([
            full_name, mobile, email,
            state, district, taluka, village
        ]):
            flash("Please fill all required customer details.", "danger")
            return redirect(url_for("register"))

        metadata = {
            "role": "customer",
            "full_name": full_name,
            "mobile": mobile,
            "state": state,
            "district": district,
            "taluka": taluka,
            "village": village,
            "address": address
        }

    # SELLER DETAILS\n    elif role == "seller":\n
        full_name = clean(request.form.get("owner_name"))
        mobile = clean(request.form.get("seller_mobile"))
        email = clean(request.form.get("seller_email")).lower()

        shop_name = clean(request.form.get("shop_name"))
        shop_category = clean(request.form.get("shop_category"))
        shop_description = clean(request.form.get("shop_description"))

        state = clean(request.form.get("seller_state"))
        district = clean(request.form.get("seller_district"))
        taluka = clean(request.form.get("seller_taluka"))
        village = clean(request.form.get("seller_village"))
        address = clean(request.form.get("seller_address"))

        opening_time = clean(request.form.get("opening_time"))
        closing_time = clean(request.form.get("closing_time"))

        if not all([
            full_name, mobile, email, shop_name,
            shop_category, state, district, taluka, village
        ]):
            flash("Please fill all required seller details.", "danger")
            return redirect(url_for("register"))

        metadata = {
            "role": "seller",
            "full_name": full_name,
            "mobile": mobile,
            "state": state,
            "district": district,
            "taluka": taluka,
            "village": village,
            "address": address,
            "shop_name": shop_name,
            "shop_category": shop_category,
            "shop_description": shop_description,
            "opening_time": opening_time,
            "closing_time": closing_time
        }



    # FARMER DETAILS
    else:
        full_name = clean(request.form.get("farmer_name"))
        mobile = clean(request.form.get("farmer_mobile"))
        email = clean(request.form.get("farmer_email")).lower()

        state = clean(request.form.get("farmer_state"))
        district = clean(request.form.get("farmer_district"))
        taluka = clean(request.form.get("farmer_taluka"))
        village = clean(request.form.get("farmer_village"))
        address = clean(request.form.get("farmer_address"))

        if not all([full_name, mobile, email, state, district, taluka, village]):
            flash("Please fill all required farmer details.", "danger")
            return redirect(url_for("register"))

        # Farmer profile metadata: handle_new_user() must allow the farmer role.
        metadata = {
            "role": "farmer",
            "full_name": full_name,
            "mobile": mobile,
            "state": state,
            "district": district,
            "taluka": taluka,
            "village": village,
            "address": address
        }

    if not valid_email(email):
        flash("Enter a valid email address.", "danger")
        return redirect(url_for("register"))

    try:
        supabase = get_supabase()

        result = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": metadata
            }
        })

        if result.user:
            flash(
                "Registration successful! Please verify your email.",
                "success"
            )
            return redirect(url_for("login"))

        flash("Registration failed. Please try again.", "danger")

    except Exception as error:
        message = str(error)

        if "already registered" in message.lower():
            message = "This email is already registered."

        flash(message, "danger")

    return redirect(url_for("register"))


# ---------------- LOGIN ----------------



@app.route("/login", methods=["GET", "POST"])
# Login handler: fetch profile role and redirect to the correct dashboard.
def login():

    if request.method == "GET":
        return render_template("login.html")

    email = clean(request.form.get("email")).lower()
    password = request.form.get("password", "")

    if not valid_email(email) or not password:
        flash("Enter valid email and password.", "danger")
        return redirect(url_for("login"))

    try:
        supabase = get_supabase()

        result = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })

        if not result.user or not result.session:
            flash("Login failed. Please try again.", "danger")
            return redirect(url_for("login"))

        # Save Supabase access token
        access_token = result.session.access_token
        supabase.postgrest.auth(access_token)

        profile_result = (
            supabase.table("profiles")
            .select("id, role, full_name, is_active")
            .eq("id", str(result.user.id))
            .maybe_single()
            .execute()
        )

        profile = profile_result.data

        if not profile:
            flash("Profile not found. Please contact support.", "danger")
            return redirect(url_for("login"))

        if profile.get("is_active") is False:
            flash("Your account is inactive.", "danger")
            return redirect(url_for("login"))

        role = profile.get("role")

        if role not in ["customer", "seller", "farmer", "admin"]:
            flash("Invalid account role.", "danger")
            return redirect(url_for("login"))

        session.clear()
        session.permanent = True

        session["user_id"] = str(result.user.id)
        session["role"] = role
        session["full_name"] = profile.get("full_name") or ""
        session["email"] = result.user.email or ""
        session["access_token"] = access_token

        if role == "customer":
            return redirect(url_for("customer"))

        elif role == "seller":
            return redirect(url_for("seller"))

        elif role == "farmer":
            return redirect(url_for("farmer_dashboard"))

        else:
            return redirect(url_for("admin_dashboard"))

    except Exception as error:

        app.logger.exception("Login error")

        message = str(error)

        if "email not confirmed" in message.lower():
            message = "Please verify your email before login."

        elif "invalid login credentials" in message.lower():
            message = "Incorrect email or password."

        flash(message, "danger")
        return redirect(url_for("login"))






# ---------------- FORGOT PASSWORD ----------------

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():

    if request.method == "GET":
        return render_template("forgot_password.html")

    email = clean(request.form.get("email")).lower()

    if not valid_email(email):
        flash("Enter a valid email address.", "danger")
        return redirect(url_for("forgot_password"))

    try:
        supabase = get_supabase()

        supabase.auth.reset_password_for_email(
            email,
            options={
                "redirect_to": url_for("login", _external=True)
            }
        )

    except Exception:
        pass

    flash(
        "If this email is registered, a reset link will be sent.",
        "success"
    )
    return redirect(url_for("login"))


# ---------------- CUSTOMER API ----------------

# Customer-only API helper: ensures the session belongs to a Customer.
def customer_api_client():
    if not session.get("user_id"):
        return None

    if session.get("role") != "customer":
        return None

    return get_user_supabase()


# 1. CUSTOMER CATEGORIES
@app.route("/api/customer/categories")
def customer_categories_api():

    supabase = customer_api_client()

    if not supabase:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        result = (
            supabase.table("categories")
            .select("id, name, description, image_url")
            .eq("is_active", True)
            .order("name")
            .execute()
        )

        return jsonify({"success": True, "categories": result.data})

    except Exception as error:
        app.logger.exception("Categories API failed")
        return jsonify({"error": "Unable to load categories"}), 500


# 2. CUSTOMER PRODUCTS
@app.route("/api/customer/products")
def customer_products_api():

    supabase = customer_api_client()

    if not supabase:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        search = clean(request.args.get("search"))

        query = (
            supabase.table("products")
            .select(
                "id, store_id, category_id, name, description, "
                "price, stock_quantity, unit, image_url, "
                "is_available, stores!products_store_id_fkey("
                "id, store_name, village, address, latitude, "
                "longitude, mobile)"
            )
            .eq("is_active", True)
            .eq("is_available", True)
            .gt("stock_quantity", 0)
        )

        if search:
            query = query.ilike("name", f"%{search}%")

        result = query.order("name").limit(100).execute()

        return jsonify({"success": True, "products": result.data})

    except Exception as error:
        app.logger.exception("Products API failed")
        return jsonify({"error": "Unable to load products"}), 500


# 3. CUSTOMER SHOPS
@app.route("/api/customer/shops")
def customer_shops_api():

    supabase = customer_api_client()

    if not supabase:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        result = (
            supabase.table("stores")
            .select(
                "id, store_name, description, mobile, address, "
                "village, latitude, longitude, logo_url, "
                "opening_time, closing_time, delivery_available"
            )
            .eq("status", "approved")
            .eq("is_active", True)
            .order("store_name")
            .limit(100)
            .execute()
        )

        return jsonify({"success": True, "shops": result.data})

    except Exception as error:
        app.logger.exception("Shops API failed")
        return jsonify({"error": "Unable to load shops"}), 500

# ---------------- CUSTOMER DASHBOARD ----------------


@app.route("/customer")
@role_required("customer")
# Customer dashboard: loads profile and active categories.
def customer():
    try:
        access_token = session.get("access_token")

        if not access_token:
            session.clear()
            flash("Please login again.", "warning")
            return redirect(url_for("login"))

        supabase = get_supabase()
        supabase.postgrest.auth(access_token)

        profile_result = (
            supabase.table("profiles")
            .select("*")
            .eq("id", session["user_id"])
            .maybe_single()
            .execute()
        )

        categories_result = (
            supabase.table("categories")
            .select("id, name, description, image_url")
            .eq("is_active", True)
            .order("name")
            .execute()
        )

        profile = profile_result.data or {}
        categories = categories_result.data or []

        return render_template(
            "customer.html",
            profile=profile,
            categories=categories,
            user_email=session.get("email", "")
        )

    except Exception:
        app.logger.exception("Customer dashboard error")
        flash("Unable to load customer dashboard.", "danger")
        return redirect(url_for("login"))


# ---------------- SELLER DASHBOARD ----------------

@app.route("/seller")
@role_required("seller")
# Seller dashboard route (seller template integration can be expanded separately).
def seller():
    return render_template("seller.html")




# ---------------- FARMER DASHBOARD & PRODUCT MANAGEMENT ----------------

@app.route("/farmer")
@role_required("farmer")
def farmer_dashboard():
    # Farmer Dashboard: logged-in farmer sees only their own posts.
    supabase = get_user_supabase()
    if not supabase:
        return redirect(url_for("login"))

    try:
        result = (
            supabase.table("farmer_products")
            .select("*")
            .eq("farmer_id", session["user_id"])
            .order("created_at", desc=True)
            .execute()
        )
        products = result.data or []
        return render_template(
            "farmer.html",
            products=products,
            name=session.get("full_name", "शेतकरी")
        )
    except Exception:
        app.logger.exception("Farmer dashboard load failed")
        flash("शेतमाल माहिती लोड करता आली नाही.", "danger")
        return render_template(
            "farmer.html",
            products=[],
            name=session.get("full_name", "शेतकरी")
        )


@app.route("/farmer/add", methods=["POST"])
@role_required("farmer")
def farmer_add_product():
    # Insert a farmer product using the logged-in user's access token.
    supabase = get_user_supabase()
    if not supabase:
        return redirect(url_for("login"))

    try:
        data = {
            "farmer_id": session["user_id"],
            "product_name": clean(request.form.get("product_name")),
            "category": clean(request.form.get("category")),
            "description": clean(request.form.get("description")),
            "price": request.form.get("price"),
            "quantity": request.form.get("quantity"),
            "unit": clean(request.form.get("unit")),
            "image_url": clean(request.form.get("image_url")),
            "mobile": clean(request.form.get("mobile")),
            "village": clean(request.form.get("village")),
            "taluka": clean(request.form.get("taluka")),
            "district": clean(request.form.get("district")),
            "state": clean(request.form.get("state")) or "Maharashtra",
            "latitude": request.form.get("latitude") or None,
            "longitude": request.form.get("longitude") or None,
            "is_available": True
        }

        # Basic validation before sending data to Supabase.
        if not all([data["product_name"], data["category"], data["price"], data["quantity"], data["mobile"], data["village"]]):
            flash("कृपया आवश्यक माहिती भरा.", "danger")
            return redirect(url_for("farmer_dashboard"))

        supabase.table("farmer_products").insert(data).execute()
        flash("माल पोस्ट केला!", "success")
    except Exception:
        app.logger.exception("Farmer product insert failed")
        flash("माल पोस्ट करता आला नाही. Database तपासा.", "danger")

    return redirect(url_for("farmer_dashboard"))


@app.route("/farmer/delete/<int:product_id>", methods=["POST"])
@role_required("farmer")
def farmer_delete_product(product_id):
    # RLS and owner filter restrict deletion to the owner's post.
    supabase = get_user_supabase()
    if not supabase:
        return redirect(url_for("login"))

    try:
        supabase.table("farmer_products") \
            .delete() \
            .eq("id", product_id) \
            .eq("farmer_id", session["user_id"]) \
            .execute()
        flash("पोस्ट हटवली.", "success")
    except Exception:
        app.logger.exception("Farmer product delete failed")
        flash("पोस्ट हटवता आली नाही.", "danger")

    return redirect(url_for("farmer_dashboard"))


# ---------------- PUBLIC FARMER PRODUCTS API ----------------

@app.route("/api/farmer-products")
def public_farmer_products_api():
    # This endpoint returns only currently available posts for the customer marketplace.
    try:
        supabase = get_supabase()
        category = clean(request.args.get("category"))

        query = (
            supabase.table("farmer_products")
            .select("*")
            .eq("is_available", True)
        )

        if category:
            query = query.eq("category", category)

        result = query.order("created_at", desc=True).limit(100).execute()
        return jsonify(result.data or [])
    except Exception:
        app.logger.exception("Public farmer products API failed")
        return jsonify({"error": "Unable to load farmer products"}), 500



# ---------------- ADMIN DASHBOARD ----------------

@app.route("/admin")
@role_required("admin")
# Admin dashboard: loads data for the existing admin template.
def admin_dashboard():
    supabase = get_user_supabase()

    if not supabase:
        return redirect(url_for("login"))

    try:
        profiles = supabase.table("profiles").select("*").execute().data or []
        stores = supabase.table("stores").select("*").execute().data or []
        products = supabase.table("products").select("*").execute().data or []
        categories = supabase.table("categories").select("*").execute().data or []
        requests_data = supabase.table("product_requests").select("*").execute().data or []
        villages = supabase.table("villages").select("*").execute().data or []

        return render_template(
            "admin.html",
            users=profiles,
            shops=stores,
            products=products,
            cats=categories,
            requests=requests_data,
            villages=villages
        )

    except Exception as e:
        return render_template(
            "admin.html",
            users=[],
            shops=[],
            products=[],
            cats=[],
            requests=[],
            villages=[],
            error=str(e)
        )


# ---------------- LOGOUT ----------------

@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# ---------------- ERROR HANDLER ----------------

@app.errorhandler(413)
def file_too_large(error):
    flash("File is too large. Maximum size is 5 MB.", "danger")
    return redirect(request.referrer or url_for("home"))


# ---------------- RUN APPLICATION ----------------

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
