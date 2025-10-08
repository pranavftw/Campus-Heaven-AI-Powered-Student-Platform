from flask import Flask, render_template, request, redirect, url_for, session, flash,jsonify
import sqlite3, os
from datetime import datetime
import numpy as np
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with a secure secret key

# File paths for databases and review storage
USER_DB = 'users.db'
LISTINGS_DB = r'C:\Users\Admin\Desktop\chb\listings.db'
REVIEWS_DIR = r'C:\Users\Admin\Desktop\chb'
CHATLOG_DIR = r"C:\Users\Admin\Desktop\chb"
os.makedirs(CHATLOG_DIR, exist_ok=True)
# ---------------------------
# Database connection functions
# ---------------------------
def get_user_db_connection():
    conn = sqlite3.connect(USER_DB)
    conn.row_factory = sqlite3.Row
    return conn

def get_listings_db_connection():
    conn = sqlite3.connect(LISTINGS_DB)
    conn.row_factory = sqlite3.Row
    return conn

# ---------------------------
# Database initialization functions
# ---------------------------
def init_user_db():
    conn = get_user_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def init_listings_db():
    conn = get_listings_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            name TEXT NOT NULL,
            address TEXT,
            facilities TEXT,
            cuisine TEXT,
            price REAL NOT NULL,
            image TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_user_db()
init_listings_db()

# ---------------------------
# Routes
# ---------------------------

# Home page: shows login and register buttons if not logged in, otherwise shows username and logout option.
@app.route('/')
def home():
    return render_template('home.html')

# Registration route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        if not username or not password:
            flash("Please fill out all fields", "danger")
            return redirect(url_for('register'))
        conn = get_user_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
            flash("Registration successful, please login", "success")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Username already exists", "danger")
            return redirect(url_for('register'))
        finally:
            conn.close()
    return render_template('register.html')

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        conn = get_user_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password)).fetchone()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash("Logged in successfully", "success")
            return redirect(url_for('index'))
        else:
            flash("Invalid credentials", "danger")
            return redirect(url_for('login'))
    return render_template('login.html')

# Logout route
@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out", "success")
    return redirect(url_for('home'))

# Index page: shows all listings by category from the external listings.db
@app.route('/index')
def index():
    if 'user_id' not in session:
        flash("Please login first", "warning")
        return redirect(url_for('login'))
    # Define the categories to display
    categories = ["Accommodations", "Gyms", "Libraries", "Meal Services"]
    listings_by_category = {}
    conn = get_listings_db_connection()
    for cat in categories:
        listings = conn.execute("SELECT * FROM listings WHERE category = ?", (cat,)).fetchall()
        listings_by_category[cat] = listings
    conn.close()
    return render_template('index.html', listings_by_category=listings_by_category)

# Route to handle review submission for a listing
@app.route('/review/<int:listing_id>', methods=['POST'])
def review(listing_id):
    if 'user_id' not in session:
        flash("Please login to submit a review", "warning")
        return redirect(url_for('login'))
    review_text = request.form.get('review', '').strip()
    rating = request.form.get('rating')
    # Get the listing name
    conn = get_listings_db_connection()
    listing = conn.execute("SELECT name FROM listings WHERE id = ?", (listing_id,)).fetchone()
    conn.close()
    listing_name = listing['name'] if listing else "Unknown"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Save review in a single file in the specified format:
    # Listing Name | Review Text | X Stars | Timestamp
    review_line = f"{listing_name} | {review_text} | {rating} Stars | {now}\n{'-'*60}\n"
    review_filename = os.path.join(REVIEWS_DIR, "reviews.txt")
    with open(review_filename, 'a', encoding='utf-8') as f:
        f.write(review_line)
    flash("Review submitted", "success")
    return redirect(url_for('index'))

# Chatbot setup
# ---------------------------
intent_dict = {
    "homesickness": ["I miss my home", "I feel lonely", "I want to go home", "I miss my family"],
    "language_barrier": ["I don't understand the language", "I have difficulty speaking", "I struggle with communication"],
    "financial_issues": ["I can't afford my expenses", "I need money", "I have financial problems"],
    "academic_pressure": ["Too much homework", "I can't focus on studies", "I have exam stress"],
    "social_integration": ["I have no friends", "I feel isolated", "I find it hard to make friends"],
    "accommodation_problems": ["My dorm is noisy", "I need a better place to stay", "Housing is expensive"],
    "health_concerns": ["I feel sick", "I have a fever", "I need to see a doctor"],
    "transportation_challenges": ["Buses are always late", "I can't find transportation", "transport is bad"]
}

responses = {
    "homesickness": "Homesickness is common. Try joining student groups or video calling your family!",
    "language_barrier": "Learning a new language takes time. Join language exchange programs or practice with friends.",
    "financial_issues": "Consider part-time jobs or checking if your school offers financial aid. <br><a href='https://www.india.gov.in/spotlight/pradhan-mantri-vidya-lakshmi-karyakram-towards-bright-future' target='_blank'><button style='background:green; color:white;'>Apply for Aid</button></a>",
    "academic_pressure": "Break study into chunks and don’t hesitate to seek help from professors. <br><a href='https://www.khanacademy.org/' target='_blank'><button style='background:blue; color:white;'>Khan Academy</button></a>",
    "social_integration": "Join clubs, social events, or online groups to meet people. <br><a href='https://www.reddit.com/r/nashik/' target='_blank'><button style='background:red; color:white;'>Join Reddit Nashik</button></a>",
    "accommodation_problems": "Contact student housing for better accommodation help.",
    "health_concerns": "If unwell, consider booking an appointment. <br><a href='https://calendly.com/blinklinkin01/doctor-appointment?hide_gdpr_banner=1' target='_blank'><button style='background:#0069ff; color:white;'>Book Doctor</button></a>",
    "transportation_challenges": "Plan routes early and check for student transport <br><a href='https://citilinc.nmc.gov.in/#/' target='_blank'><button style='background:#0069ff; color:white;'>Check City Bus timings</button></a>",
    "unknown": "I'm not sure about that. Can you rephrase?"
}

# Vectorizer
all_intents = sum(intent_dict.values(), [])
vectorizer = CountVectorizer().fit(all_intents)
intent_vectors = vectorizer.transform(all_intents)

def classify_intent(user_input):
    user_vec = vectorizer.transform([user_input])
    similarities = cosine_similarity(user_vec, intent_vectors).flatten()
    if len(similarities) == 0 or max(similarities) < 0.3:
        return "unknown"
    best_match_idx = np.argmax(similarities)
    matched_phrase = all_intents[best_match_idx]
    for intent, phrases in intent_dict.items():
        if matched_phrase in phrases:
            return intent
    return "unknown"


# ---------------------------
# Routes for chatbot
# ---------------------------
@app.route('/chatbot')
def chatbot():
    if 'user_id' not in session:
        flash("Please login to use the chatbot", "warning")
        return redirect(url_for('login'))

    # Fetch all accommodation names from your listings.db
    conn = get_listings_db_connection()
    rows = conn.execute("SELECT name FROM listings").fetchall()
    conn.close()
    accommodations = [r['name'] for r in rows]

    return render_template('chatbot.html', accommodations=accommodations)


@app.route('/chatbot_api', methods=['POST'])
def chatbot_api():
    # Safely parse JSON body (defaults to {} if parsing fails)
    data = request.get_json(silent=True) or {}

    # Pull out fields, defaulting to empty strings
    msg = (data.get("message") or "").strip()
    accommodation = (data.get("accommodation") or "").strip()

    # If we haven’t captured the accommodation name yet, prompt again
    if not accommodation:
        return jsonify({
            "response": "Thanks! Which accommodation are you from?",
            "ask_accommodation": True
        })

    # If user sent an empty message
    if not msg:
        return jsonify({
            "response": "Please say something so I can help!",
            "ask_accommodation": False
        })

    # Classify intent and pick a response
    intent = classify_intent(msg)
    reply = responses.get(intent, responses["unknown"])

    # … after you classify intent …
    today = datetime.now().strftime("%Y-%m-%d")
    log_entry = f"{accommodation}| {today} | {intent}\n"   # <-- here
    fname = f"{accommodation.replace(' ', '_')}.txt"
    with open(os.path.join(CHATLOG_DIR, fname), "a", encoding="utf-8") as logf:
        logf.write(log_entry)

    return jsonify({
        "response": reply,
        "ask_accommodation": False
    })





if __name__ == '__main__':
    app.run(debug=True)
