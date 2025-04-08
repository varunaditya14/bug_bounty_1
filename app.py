from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "your_secret_key"

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"  # Redirects to login page if not authenticated

# Database connection
def create_connection():
    try:
        connection = mysql.connector.connect(
            host='localhost',
            user='root',
            password='',
            database='url_tester_db'
        )
        return connection
    except Error as e:
        print(f"Database connection error: {e}")
        return None

# Initialize Database
def init_db():
    connection = create_connection()
    if connection:
        cursor = connection.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS test_cases (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                test_case_name VARCHAR(255) NOT NULL,
                url TEXT NOT NULL,
                status_code VARCHAR(10) NOT NULL,
                error_message TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS errors (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                url TEXT NOT NULL,
                error_message TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        connection.commit()
        cursor.close()
        connection.close()

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    connection = create_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        cursor.close()
        connection.close()
        if user:
            return User(user["id"], user["username"])
    return None

# Signup Route
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password)

        connection = create_connection()
        if connection:
            cursor = connection.cursor()
            try:
                cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, hashed_password))
                connection.commit()
                flash("Signup successful! You can now log in.", "success")
                return redirect(url_for('login'))
            except Error:
                flash("Username already exists!", "danger")
            finally:
                cursor.close()
                connection.close()
    return render_template('signup.html')

# Login Route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        connection = create_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()
            cursor.close()
            connection.close()

            if user and check_password_hash(user["password"], password):
                user_obj = User(user["id"], user["username"])
                login_user(user_obj)
                return redirect(url_for('index'))
            else:
                flash("Invalid username or password", "danger")
    return render_template('login.html')

# Logout Route
@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash("Logged out successfully", "success")
    return redirect(url_for('login'))

# Main Page (Requires Login)
@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        base_url = request.form['url']
        urls = crawl_website(base_url)

        for index, url in enumerate(urls, start=1):
            test_case_name = f"Test Case {index}"
            status_code, error_message = test_url(url)
            log_test_case(current_user.id, test_case_name, url, status_code if status_code else "Error", error_message)
            if error_message:
                log_error(current_user.id, url, error_message)

    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute('SELECT test_case_name, url, status_code, error_message FROM test_cases WHERE user_id = %s ORDER BY timestamp DESC', (current_user.id,))
    test_cases = cursor.fetchall()
    cursor.execute('SELECT url, error_message FROM errors WHERE user_id = %s ORDER BY timestamp DESC', (current_user.id,))
    errors = cursor.fetchall()
    cursor.close()
    connection.close()

    return render_template('index.html', test_cases=test_cases, errors=errors)

# Crawling and Testing Functions
def crawl_website(base_url):
    urls = set()
    try:
        response = requests.get(base_url)
        soup = BeautifulSoup(response.text, 'html.parser')
        for link in soup.find_all('a', href=True):
            full_url = urljoin(base_url, link['href'])
            urls.add(full_url)
    except Exception as e:
        print(f"Error crawling {base_url}: {e}")
    return urls

def test_url(url):
    try:
        response = requests.get(url)
        return response.status_code, None
    except requests.exceptions.RequestException as e:
        return None, str(e)

# Logging Functions
def log_test_case(user_id, test_case_name, url, status_code, error_message):
    connection = create_connection()
    if connection:
        cursor = connection.cursor()
        cursor.execute('INSERT INTO test_cases (user_id, test_case_name, url, status_code, error_message) VALUES (%s, %s, %s, %s, %s)', (user_id, test_case_name, url, status_code, error_message))
        connection.commit()
        cursor.close()
        connection.close()

def log_error(user_id, url, error_message):
    connection = create_connection()
    if connection:
        cursor = connection.cursor()
        cursor.execute('INSERT INTO errors (user_id, url, error_message) VALUES (%s, %s, %s)', (user_id, url, error_message))
        connection.commit()
        cursor.close()
        connection.close()

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
