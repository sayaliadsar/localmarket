
from flask import Flask, render_template
import os

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "local-market-dev-key")

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login")
def login():
    return render_template("login.html")

@app.route("/register")
def register():
    return render_template("register.html")

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
    return "Logout route ready"

if __name__ == "__main__":
    app.run(debug=True)
