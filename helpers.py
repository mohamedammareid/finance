import os
import requests
import urllib.parse
from functools import wraps
from flask import render_template, redirect, session, flash

def apology(message, code=400):
    """Render message as an apology to user."""
    def escape(s):
        """Escape special characters."""
        for old, new in [("-", "--"), (" ", "-"), ("_", "__"), ("?", "~q"),
                         ("%", "~p"), ("#", "~h"), ("/", "~s"), ("\"", "''")]:
            s = s.replace(old, new)
        return s
    return render_template("apology.html", top=code, bottom=escape(message)), code


def login_required(f):
    """Decorate routes to require login."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            flash("You must be logged in to access this page.", "warning")
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function


def lookup(symbol):
    """Look up quote for symbol."""
    # Get API Key from environment variable
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise RuntimeError("API_KEY not set in environment variables")

    # Contact API
    try:
        url = f"https://cloud.iexapis.com/stable/stock/{urllib.parse.quote_plus(symbol)}/quote?token={api_key}"
        response = requests.get(url)
        response.raise_for_status()  # Raises an exception for a 4xx or 5xx response
    except requests.RequestException as e:
        print(f"Error contacting the API: {e}")
        return {"error": "Unable to fetch stock data."}

    # Parse the response
    try:
        quote = response.json()
        if "error" in quote:  # Check for error in the response
            return {"error": quote["error"]}
        return {
            "name": quote["companyName"],
            "price": float(quote["latestPrice"]),
            "symbol": quote["symbol"]
        }
    except (KeyError, TypeError, ValueError) as e:
        print(f"Error parsing the response: {e}")
        return {"error": "Invalid data received from the API."}


def usd(value: float) -> str:
    """Format value as USD."""
    return f"${value:,.2f}"
