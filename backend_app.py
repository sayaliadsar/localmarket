
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
def get_user_supabase():
    access_token = session.get("access_token")

    if not access_token:
        return None

    user_supabase = get_supabase()
    user_supabase.postgrest.auth(access_token)

    return user_supabase



# ---------------- COMMON FUNCTIONS ----------------

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
def register():

    if request.method == "GET":
        return render_template("register.html")

    role = clean(request.form.get("accountType")).lower()

    password = request.form.get("password", "")
    confirm_password = request.form.get("confirmPassword", "")

    if role not in ["customer", "seller"]:
        flash("Select Customer or Seller account.", "danger")
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

    # SELLER DETAILS
    else:

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

        if role not in ["customer", "seller", "admin"]:
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


@app.route("/logout", methods=["GET", "POST"])
def logout():

    session.clear()

    flash("You have been logged out.", "success")

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
def seller():
    return render_template("seller.html")


# ---------------- ADMIN DASHBOARD ----------------

@app.route("/admin")
@role_required("admin")
def admin_dashboard():
    return render_template("admin.html")


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
