import os
from flask import Flask, flash, redirect, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash
from cs50 import SQL
from flask_session import Session
import requests
from functools import wraps

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Create tables if they don't exist
def create_tables():
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            hash TEXT NOT NULL,
            cash NUMERIC DEFAULT 10000.00
        );
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            shares INTEGER NOT NULL,
            price NUMERIC NOT NULL,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)

# Call create_tables function when starting your app
create_tables()

@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Define login_required before using it in routes
def login_required(f):
    """Decorate routes to require login."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function

@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    rows = db.execute("""
        SELECT symbol, SUM(shares) AS total_shares
        FROM transactions WHERE user_id = :user_id GROUP BY symbol
    """, user_id=session["user_id"])
    portfolio = []
    total_value = 0

    for row in rows:
        symbol = row["symbol"]
        shares = row["total_shares"]
        price = lookup(symbol)["price"]
        total_value += shares * price
        portfolio.append({"symbol": symbol, "shares": shares, "price": price, "total": shares * price})

    cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])[0]["cash"]

    return render_template("index.html", portfolio=portfolio, cash=cash, total_value=total_value)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    if request.method == "POST":
        if not request.form.get("username"):
            flash("Must provide username", "danger")
            return render_template("login.html")

        if not request.form.get("password"):
            flash("Must provide password", "danger")
            return render_template("login.html")

        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            flash("Invalid username and/or password", "danger")
            return render_template("login.html")

        session["user_id"] = rows[0]["id"]
        return redirect("/")

    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out"""
    session.clear()
    return redirect("/")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Check for empty fields
        if not username or not password or not confirmation:
            flash("All fields must be filled out", "danger")
            return render_template("register.html"), 400

        # Check for password mismatch
        if password != confirmation:
            flash("Passwords don't match", "danger")
            return render_template("register.html"), 400

        # Check if username already exists
        if db.execute("SELECT * FROM users WHERE username = :username", username=username):
            flash("Username already exists", "danger")
            return render_template("register.html"), 400

        hash = generate_password_hash(password)
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
                    username=username, hash=hash)

        flash("Registration successful!", "success")
        return redirect("/login")

    else:
        return render_template("register.html")

@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Look up stock quote"""
    if request.method == "POST":
        symbol = request.form.get("symbol")

        if not symbol:
            flash("Must provide a stock symbol", "danger")
            return render_template("quote.html"), 400

        stock = lookup(symbol)
        if not stock:
            flash("Invalid stock symbol", "danger")
            return render_template("quote.html"), 400

        return render_template("quoted.html", stock=stock)

    else:
        return render_template("quote.html")

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        if not symbol:
            flash("Must provide symbol", "danger")
            return render_template("buy.html"), 400

        if not shares or not shares.isdigit() or int(shares) <= 0:
            flash("Invalid number of shares", "danger")
            return render_template("buy.html"), 400

        shares = int(shares)
        stock = lookup(symbol)
        if stock is None:
            flash("Invalid stock symbol", "danger")
            return render_template("buy.html"), 400

        price = stock["price"]
        total_price = shares * price

        user_cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])[0]["cash"]
        if user_cash < total_price:
            flash("Not enough cash", "danger")
            return render_template("buy.html"), 400

        db.execute("UPDATE users SET cash = cash - :total_price WHERE id = :user_id",
                    total_price=total_price, user_id=session["user_id"])

        db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES (:user_id, :symbol, :shares, :price)",
                    user_id=session["user_id"], symbol=symbol, shares=shares, price=price)

        flash(f"Bought {shares} shares of {symbol} for {total_price:.2f}", "success")
        return redirect("/")

    else:
        return render_template("buy.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        if not symbol:
            flash("Must provide symbol", "danger")
            return render_template("sell.html"), 400

        if not shares or not shares.isdigit() or int(shares) <= 0:
            flash("Invalid number of shares", "danger")
            return render_template("sell.html"), 400

        shares = int(shares)
        rows = db.execute("""
            SELECT SUM(shares) AS total_shares FROM transactions WHERE user_id = :user_id AND symbol = :symbol GROUP BY symbol
        """, user_id=session["user_id"], symbol=symbol)

        if not rows or rows[0]["total_shares"] < shares:
            flash("Not enough shares", "danger")
            return render_template("sell.html"), 400

        stock = lookup(symbol)
        if stock is None:
            flash("Invalid stock symbol", "danger")
            return render_template("sell.html"), 400

        price = stock["price"]
        total_price = shares * price

        db.execute("UPDATE users SET cash = cash + :total_price WHERE id = :user_id", total_price=total_price, user_id=session["user_id"])
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES (:user_id, :symbol, :shares, :price)",
                    user_id=session["user_id"], symbol=symbol, shares=-shares, price=price)

        flash(f"Sold {shares} shares of {symbol} for {total_price:.2f}", "success")
        return redirect("/")

    else:
        return render_template("sell.html")

def lookup(symbol):
    """Look up a stock quote."""
    try:
        # Using Yahoo Finance API for stock data (replace with your API key for a different service)
        response = requests.get(f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}")
        data = response.json()

        if "quoteResponse" in data and "result" in data["quoteResponse"]:
            result = data["quoteResponse"]["result"][0]
            return {
                "name": result["longName"],
                "symbol": result["symbol"],
                "price": result["regularMarketPrice"]
            }
        else:
            return None
    except Exception:
        return None

if __name__ == "__main__":
    app.run(debug=True)
