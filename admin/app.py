from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3, os

app = Flask(__name__)
app.secret_key = 'admin_secret'

STUDENT_DB = r'C:\Users\Admin\Desktop\chs\users.db'
BUSINESS_DB = r'C:\Users\Admin\Desktop\chb\users.db'
LISTINGS_DB = r'C:\Users\Admin\Desktop\chb\listings.db'
REVIEWS_PATH = r'C:\Users\Admin\Desktop\chb\reviews.txt'
CHATLOG_DIR = r'C:\Users\Admin\Desktop\chb'

def connect_db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == 'admin' and request.form['password'] == 'admin123':
            session['admin'] = True
            return redirect(url_for('dashboard'))
        flash("Invalid credentials.")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if not session.get('admin'): return redirect(url_for('login'))

    student_users = connect_db(STUDENT_DB).execute("SELECT * FROM users").fetchall()
    business_users = connect_db(BUSINESS_DB).execute("SELECT * FROM users").fetchall()
    listings = connect_db(LISTINGS_DB).execute("SELECT * FROM listings").fetchall()

    return render_template('dashboard.html', 
        student_users=student_users,
        business_users=business_users,
        listings=listings
    )

@app.route('/reviews')
def reviews():
    if not session.get('admin'): return redirect(url_for('login'))
    if os.path.exists(REVIEWS_PATH):
        with open(REVIEWS_PATH, 'r', encoding='utf-8') as f:
            data = f.read()
    else:
        data = "No reviews found."
    return render_template('reviews.html', content=data)

@app.route('/chatlogs')
def chatlogs():
    if not session.get('admin'): return redirect(url_for('login'))
    logs = []
    for fname in os.listdir(CHATLOG_DIR):
        if fname.endswith(".txt") and fname != "reviews.txt":
            with open(os.path.join(CHATLOG_DIR, fname), 'r', encoding='utf-8') as f:
                logs.append((fname, f.read()))
    return render_template('chatlogs.html', logs=logs)


# Delete a student user
@app.route('/delete_student/<int:user_id>', methods=['POST'])
def delete_student(user_id):
    if not session.get('admin'):
        return redirect(url_for('login'))
    conn = connect_db(STUDENT_DB)
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    flash("Student user deleted.")
    return redirect(url_for('dashboard'))

# Delete a business user
@app.route('/delete_business/<int:user_id>', methods=['POST'])
def delete_business(user_id):
    if not session.get('admin'):
        return redirect(url_for('login'))
    conn = connect_db(BUSINESS_DB)
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    flash("Business user deleted.")
    return redirect(url_for('dashboard'))

# Delete a review line by line
@app.route('/delete_review', methods=['POST'])
def delete_review():
    if not session.get('admin'):
        return redirect(url_for('login'))

    line_no = int(request.form.get('line_number', -1))
    if os.path.exists(REVIEWS_PATH):
        with open(REVIEWS_PATH, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        if 0 <= line_no < len(lines):
            del lines[line_no]
            with open(REVIEWS_PATH, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            flash("Review deleted.")
    return redirect(url_for('reviews'))

@app.route('/delete_listing/<int:listing_id>', methods=['POST'])
def delete_listing(listing_id):
    if not session.get('admin'):
        return redirect(url_for('login'))
    conn = connect_db(LISTINGS_DB)
    conn.execute("DELETE FROM listings WHERE id = ?", (listing_id,))
    conn.commit()
    conn.close()
    flash("Listing deleted.")
    return redirect(url_for('dashboard'))



if __name__ == '__main__':
    app.run(debug=True)
