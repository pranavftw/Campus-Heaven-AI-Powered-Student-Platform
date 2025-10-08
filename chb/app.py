import os
import re
import sqlite3
from collections import defaultdict, Counter
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, send_file
)
from werkzeug.security import generate_password_hash, check_password_hash
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
from fpdf import FPDF
import numpy as np

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # ← Change this!

USERS_DB = 'users.db'
LISTINGS_DB = 'listings.db'

# ——— Database Setup ———

def get_user_db_connection():
    conn = sqlite3.connect(USERS_DB)
    conn.row_factory = sqlite3.Row
    return conn

def get_listings_db_connection():
    conn = sqlite3.connect(LISTINGS_DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_user_db():
    with get_user_db_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL
            )
        ''')

def init_listings_db():
    with get_listings_db_connection() as conn:
        conn.execute('''
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

init_user_db()
init_listings_db()

# ——— Authentication & Listing Routes ———

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip()
        password = request.form['password']
        if not username or not email or not password:
            flash('Please fill out all fields.')
            return redirect(url_for('register'))
        conn = get_user_db_connection()
        try:
            conn.execute(
                "INSERT INTO users(username,email,password) VALUES(?,?,?)",
                (username, email, generate_password_hash(password))
            )
            conn.commit()
            flash('Registration successful. Please log in.')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username or email already exists.')
            return redirect(url_for('register'))
        finally:
            conn.close()
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        conn = get_user_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE username=?", (username,)
        ).fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('Logged in successfully.')
            return redirect(url_for('dashboard'))
        flash('Invalid username or password.')
        return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.')
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Please log in first.')
        return redirect(url_for('login'))
    conn = get_listings_db_connection()
    listings = conn.execute(
        "SELECT * FROM listings WHERE user_id=?", (session['user_id'],)
    ).fetchall()
    conn.close()
    return render_template('dashboard.html', listings=listings)

# Add a new business listing
@app.route('/add_listing', methods=['GET', 'POST'])
def add_listing():
    if 'user_id' not in session:
        flash('Please log in first.')
        return redirect(url_for('login'))
    if request.method == 'POST':
        category = request.form['category']
        name = request.form['name'].strip()
        address = request.form.get('address', '').strip()
        facilities = request.form.get('facilities', '').strip()
        cuisine = request.form.get('cuisine', '').strip()
        price = request.form['price']
        image = request.form.get('image', '').strip()  # URL or filename

        conn = get_listings_db_connection()
        conn.execute('''
            INSERT INTO listings (user_id, category, name, address, facilities, cuisine, price, image)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (session['user_id'], category, name, address, facilities, cuisine, price, image))
        conn.commit()
        conn.close()
        flash('Listing added successfully.')
        return redirect(url_for('dashboard'))
    return render_template('add_listing.html')

# Edit an existing listing (route remains for direct POST)
@app.route('/edit_listing/<int:listing_id>', methods=['POST'])
def edit_listing(listing_id):
    if 'user_id' not in session:
        flash('Please log in first.')
        return redirect(url_for('login'))
    conn = get_listings_db_connection()
    conn.execute('''
        UPDATE listings
        SET category = ?, name = ?, address = ?, facilities = ?, cuisine = ?, price = ?, image = ?
        WHERE id = ? AND user_id = ?
    ''', (request.form['category'], request.form['name'].strip(), 
          request.form.get('address', '').strip(), request.form.get('facilities', '').strip(), 
          request.form.get('cuisine', '').strip(), request.form['price'], 
          request.form.get('image', '').strip(), listing_id, session['user_id']))
    conn.commit()
    conn.close()
    flash('Listing updated successfully.')
    return redirect(url_for('dashboard'))

# Delete a listing
@app.route('/delete_listing/<int:listing_id>', methods=['POST'])
def delete_listing(listing_id):
    if 'user_id' not in session:
        flash('Please log in first.')
        return redirect(url_for('login'))
    conn = get_listings_db_connection()
    conn.execute("DELETE FROM listings WHERE id = ? AND user_id = ?", (listing_id, session['user_id']))
    conn.commit()
    conn.close()
    flash('Listing deleted successfully.')
    return redirect(url_for('dashboard'))

# ——— Analytics Helpers ———

def detect_sarcasm(review):
    """
    Detects sarcasm using:
    - overlap of strongly positive and negative words (contradiction)
    - presence of sarcastic phrases
    - known sarcastic expressions
    """
    sarcasm_indicators = {
        "great", "amazing", "awesome", "loved", "best", "fantastic", "incredible", 
        "brilliant", "spectacular", "marvelous", "phenomenal", "stunning", "mind-blowing", 
        "impressive", "wonderful", "terrific", "fabulous", "superb"
    }

    negative_words = {
        "worst", "bad", "terrible", "awful", "hate", "poor", "horrible", "sucks", 
        "dreadful", "abysmal", "lousy", "disappointing", "pathetic", "subpar"
    }

    sarcastic_phrases = [
        "oh great", "just perfect", "yeah right", "exactly what i wanted", 
        "fantastic... not", "well isn't that nice", "what a joy", "wonderful experience... not",
        "i just love waiting", "oh, joy", "perfect timing", "exactly what i expected", 
        "not impressed", "no kidding", "obviously", "clearly", "incredible, really", "amazing, isn't it", 
        "so hilarious", "how convenient", "excellent, as always"
    ]

    additional_sarcasm = {
        "oh, absolutely!", "how thoughtful!", "well, isn't that special!", "wow, groundbreaking!",
        "oh, you don't say!", "bravo, well done!", "how original!", "a true masterpiece!",
        "clearly the best!", "oh, just perfect!", "what a surprise!", "outstanding effort!",
        "really impressive!", "oh, that's rich!", "truly state-of-the-art!", "wonderful choice!",
        "oh, this is fine!", "remarkably consistent!", "simply flawless!", "my favorite part!"
    }

    review_lower = review.lower()
    words = set(review_lower.split())

    indicator_negative_overlap = bool(words & sarcasm_indicators and words & negative_words)
    phrase_detected = any(phrase in review_lower for phrase in sarcastic_phrases)
    additional_detected = any(phrase in review_lower for phrase in additional_sarcasm)

    return indicator_negative_overlap or phrase_detected or additional_detected



def get_user_pg_names(user_id):
    conn = get_listings_db_connection()
    rows = conn.execute(
        "SELECT name FROM listings WHERE user_id=?", (user_id,)
    ).fetchall()
    conn.close()
    return set(r["name"] for r in rows)

def analyze_reviews(user_pgs):
    reviews = defaultdict(list)
    if not os.path.exists("reviews.txt"):
        return reviews
    with open("reviews.txt","r",encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("|")
            if len(parts) >= 3:
                pg = parts[0].strip()
                if pg not in user_pgs:
                    continue
                txt = parts[1].strip()
                rating = parts[2].strip()
                reviews[pg].append((txt, rating))
    return reviews

def analyze_chat_logs(user_pgs):
    counts = Counter()
    by_date = {}
    by_type_date = defaultdict(lambda: defaultdict(int))
    pg_issues = defaultdict(Counter)

    for fn in os.listdir():
        if fn.endswith(".txt") and fn != "reviews.txt":
            with open(fn,"r",encoding="utf-8") as f:
                for line in f:
                    parts = [p.strip() for p in line.strip().split("|")]
                    if len(parts) == 3:
                        pg, date_str, category = parts
                        if pg not in user_pgs:
                            continue
                        counts[category] += 1
                        by_date[date_str] = by_date.get(date_str, 0) + 1
                        by_type_date[category][date_str] += 1
                        pg_issues[pg][category] += 1
    return counts, by_date, by_type_date, pg_issues


positive_words = {
    "good", "great", "excellent", "amazing", "awesome", "wonderful",
    "clean", "friendly", "comfortable", "delicious", "perfect", "happy",
    "helpful", "spacious", "affordable", "recommend", "fast", "satisfied",
    "peaceful", "nice", "quiet"
}

negative_words = {
    "bad", "worst", "dirty", "rude", "late", "expensive", "poor",
    "horrible", "noisy", "uncomfortable", "slow", "broken", "crowded",
    "terrible", "disappointed", "not good", "problem", "issue", "hate"
}


def generate_insights(user_pgs):
    revs = analyze_reviews(user_pgs)
    issues, timeline, type_tl, pg_iss = analyze_chat_logs(user_pgs)
    insights = {}
    avg_ratings = {}
    log_data = []

    for pg, lst in revs.items():
        total = pos = neg = neu = 0
        for txt, r in lst:
            m = re.search(r"(\d)/5", r)
            val = int(m.group(1)) if m else 0
            total += val

            txt_lower = txt.lower()
            pos_count = sum(1 for word in positive_words if word in txt_lower)
            neg_count = sum(1 for word in negative_words if word in txt_lower)

            if pos_count > neg_count:
                sentiment = "Positive"; pos += 1
            elif neg_count > pos_count:
                sentiment = "Negative"; neg += 1
            else:
                sentiment = "Neutral"; neu += 1

            if detect_sarcasm(txt) and val <= 2:
                sentiment = "Sarcastically Negative"

            log_data.append({
                "pg": pg,
                "review": txt,
                "rating": r,
                "type": sentiment
            })

        avg = round(total / len(lst), 2) if lst else 0
        insights[pg] = {
            "avg": avg,
            "total": len(lst),
            "pos": pos,
            "neg": neg,
            "neu": neu
        }
        avg_ratings[pg] = avg

    return insights, avg_ratings, issues, timeline, type_tl, pg_iss, log_data


def generate_graphs(avg_ratings, chat_issues, issue_timeline, timeline_by_type, pg_issues):
    # Ensure static folder exists
    os.makedirs("static", exist_ok=True)

    # 1) PG Ratings Bar Chart
    fig, ax = plt.subplots(figsize=(8, 4))
    names = list(avg_ratings.keys())
    ratings = list(avg_ratings.values())
    sns.barplot(x=ratings, y=names, hue=names, ax=ax, palette="viridis", dodge=False)
    if ax.get_legend():
        ax.get_legend().remove()
    ax.set_xlabel("Average Rating")
    ax.set_title("Key Insights for Your Business Performance")
    ratings_graph = "ratings_graph.png"
    fig.tight_layout()
    fig.savefig(f"static/{ratings_graph}")
    plt.close(fig)

    # 2) Chat Issues Breakdown Pie Chart
    fig, ax = plt.subplots(figsize=(6, 6))
    labels = list(chat_issues.keys())
    sizes = list(chat_issues.values())
    ax.pie(sizes, labels=labels, autopct='%1.1f%%', colors=sns.color_palette("pastel"))
    ax.set_title("Chat Issues Breakdown")
    chat_graph = "chat_graph.png"
    fig.tight_layout()
    fig.savefig(f"static/{chat_graph}")
    plt.close(fig)

    # 3) Issues Over Time
    fig, ax = plt.subplots(figsize=(8, 4))
    dates = sorted(issue_timeline.keys())
    counts = [issue_timeline[d] for d in dates]
    ax.plot(dates, counts, marker='o', color='#00bfff')
    ax.set_xlabel("Date")
    ax.set_ylabel("Number of Issues")
    ax.set_title("Issues Over Time")
    plt.xticks(rotation=45)
    time_graph = "time_graph.png"
    fig.tight_layout()
    fig.savefig(f"static/{time_graph}")
    plt.close(fig)

    # 4) Type of Issue Over Time
    fig, ax = plt.subplots(figsize=(8, 4))
    for issue_type, tl in timeline_by_type.items():
        ds = sorted(tl.keys())
        cs = [tl[d] for d in ds]
        ax.plot(ds, cs, marker='o', label=issue_type)
    ax.set_xlabel("Date")
    ax.set_ylabel("Count")
    ax.set_title("Type of Issue Over Time")
    plt.xticks(rotation=45)
    if timeline_by_type:
        ax.legend()
    type_graph = "type_issue_time_graph.png"
    fig.tight_layout()
    fig.savefig(f"static/{type_graph}")
    plt.close(fig)

    # 5) PG Issues Breakdown
    num = len(pg_issues)
    pg_graph = "pg_issues_graph.png"
    if num == 0:
        fig, ax = plt.subplots(figsize=(5, 5))
        ax.text(0.5, 0.5, "No PG issues found", ha="center", va="center")
        ax.axis("off")
        fig.tight_layout()
        fig.savefig(f"static/{pg_graph}")
        plt.close(fig)
    else:
        cols = 2
        rows = (num + 1) // 2
        fig, axes = plt.subplots(rows, cols, figsize=(cols * 5, rows * 5))

        # Flatten safely
        if isinstance(axes, np.ndarray):
            axes = axes.flatten()
        else:
            axes = [axes]

        for i, (pg, ctr) in enumerate(pg_issues.items()):
            axes[i].pie(list(ctr.values()), labels=list(ctr.keys()),
                        autopct='%1.1f%%', colors=sns.color_palette("pastel"))
            axes[i].set_title(f"{pg} Issues Breakdown")

        # Hide unused subplots
        for j in range(i + 1, len(axes)):
            axes[j].axis("off")

        fig.tight_layout()
        fig.savefig(f"static/{pg_graph}")
        plt.close(fig)

    return ratings_graph, chat_graph, time_graph, type_graph, pg_graph

def safe_text(text):
    return str(text).encode("latin-1", "replace").decode("latin-1")

def generate_pdf_report(log_data):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Analytics Report", 0, 1, "C")

    pdf.set_font("Arial", "B", 12)
    pdf.cell(30, 10, "PG", 1)
    pdf.cell(100, 10, "Review", 1)
    pdf.cell(30, 10, "Rating", 1)
    pdf.cell(30, 10, "Type", 1)
    pdf.ln()

    pdf.set_font("Arial", "", 10)
    for entry in log_data:
        pg = safe_text(entry["pg"])[:28]
        review = safe_text(entry["review"])[:70]
        rating = safe_text(entry["rating"])
        sentiment = safe_text(entry["type"])
        pdf.cell(30, 10, pg, 1)
        pdf.cell(100, 10, review, 1)
        pdf.cell(30, 10, rating, 1)
        pdf.cell(30, 10, sentiment, 1)
        pdf.ln()

    report_path = "static/report.pdf"
    pdf.output(report_path)
    return report_path


# ——— Analytics Routes ———

@app.route('/analytics')
def analytics():
    if 'user_id' not in session:
        flash('Please log in first.')
        return redirect(url_for('login'))

    user_pgs = get_user_pg_names(session['user_id'])
    insights, avgs, issues, timeline, type_tl, pg_iss, logd = generate_insights(user_pgs)
    r_g, c_g, t_g, ty_g, p_g = generate_graphs(avgs, issues, timeline, type_tl, pg_iss)

    return render_template('businessdb.html',
        insights=insights,
        ratings_graph=r_g,
        chat_graph=c_g,
        time_graph=t_g,
        type_graph=ty_g,
        pg_graph=p_g,
        log_data=logd
    )

@app.route('/download_report')
def download_report():
    if 'user_id' not in session:
        flash('Please log in first.')
        return redirect(url_for('login'))

    user_pgs = get_user_pg_names(session['user_id'])
    _, _, _, _, _, _, log_data = generate_insights(user_pgs)
    report_path = generate_pdf_report(log_data)
    return send_file(report_path, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
