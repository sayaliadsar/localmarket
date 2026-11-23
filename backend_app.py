
import os
import re

from flask import (
    Flask, render_template, request,
    redirect, url_for, flash
)
from supabase import create_client


app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=5 * 1024 * 1024
)


def get_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        raise RuntimeError("Supabase configuration is missing.")

    return create_client(url, key)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "GET":
        return render_template("register.html")

    role = request.form.get("accountType", "").strip().lower()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirmPassword", "")

    if role not in ("customer", "seller"):
        flash("Please select a valid account type.", "danger")
        return redirect(url_for("register"))

    if len(password) < 8:
        flash("Password must contain at least 8 characters.", "danger")
        return redirect(url_for("register"))

    if password != confirm_password:
        flash("Passwords do not match.", "danger")
        return redirect(url_for("register"))

    metadata = {"role": role}

    if role == "customer":

        full_name = request.form.get("full_name", "").strip()
        mobile = request.form.get("mobile", "").strip()
        email = request.form.get("email", "").strip().lower()

        state = request.form.get("customer_state", "").strip()
        district = request.form.get("customer_district", "").strip()
        taluka = request.form.get("customer_taluka", "").strip()
        village = request.form.get("customer_village", "").strip()
        address = request.form.get("customer_address", "").strip()

        if not all([full_name, mobile, email, state,
                    district, taluka, village, address]):
            flash("Please complete all required fields.", "danger")
            return redirect(url_for("register"))

        if not re.fullmatch(r"[0-9]{10}", mobile):
            flash("Enter a valid 10-digit mobile number.", "danger")
            return redirect(url_for("register"))

        metadata.update({
            "full_name": full_name,
            "mobile": mobile,
            "state": state,
            "district": district,
            "taluka": taluka,
            "village": village,
            "address": address
        })

    else:

        full_name = request.form.get("owner_name", "").strip()
        mobile = request.form.get("seller_mobile", "").strip()
        email = request.form.get("seller_email", "").strip().lower()

        shop_name = request.form.get("shop_name", "").strip()
        shop_category = request.form.get("shop_category", "").strip()

        state = request.form.get("seller_state", "").strip()
        district = request.form.get("seller_district", "").strip()
        taluka = request.form.get("seller_taluka", "").strip()
        village = request.form.get("seller_village", "").strip()
        address = request.form.get("seller_address", "").strip()

        description = request.form.get("shop_description", "").strip()
        opening_time = request.form.get("opening_time", "").strip()
        closing_time = request.form.get("closing_time", "").strip()

        if not all([full_name, mobile, email, shop_name,
                    shop_category, state, district,
                    taluka, village, address]):
            flash("Please complete all required shop details.", "danger")
            return redirect(url_for("register"))

        if not re.fullmatch(r"[0-9]{10}", mobile):
            flash("Enter a valid 10-digit mobile number.", "danger")
            return redirect(url_for("register"))

        metadata.update({
            "full_name": full_name,
            "mobile": mobile,
            "shop_name": shop_name,
            "shop_category": shop_category,
            "shop_description": description,
            "state": state,
            "district": district,
            "taluka": taluka,
            "village": village,
            "address": address,
            "opening_time": opening_time,
            "closing_time": closing_time
        })

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
                "Registration successful! Please check your email "
                "and verify your account before login.",
                "success"
            )
            return redirect(url_for("login"))

        flash("Registration could not be completed. Please try again.", "danger")

    except Exception:
        app.logger.exception("Registration failed")
        flash(
            "Registration failed. Please check your details "
            "or try again later.",
            "danger"
        )

    return redirect(url_for("register"))


@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/forgot-password")
def forgot_password():
    return render_template("forgot_password.html")


@app.route("/customer")
def customer():
    return render_template("customer.html")


@app.route("/seller")
def seller():
    return render_template("seller.html")


@app.route("/logout")
def logout():
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)
