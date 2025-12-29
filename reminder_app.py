import os
import datetime
import time
import threading
import psycopg2
import jwt
from psycopg2.extras import RealDictCursor
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from functools import wraps

# --- Ayarlar ---
SECRET_KEY = "cok_gizli_anahtar"  # Token imzalamak için
DATABASE_URL = os.environ.get("DATABASE_URL", "dbname=reminders_db user=admin password=sifre123 host=db")

app = Flask(__name__)
CORS(app) # Tarayıcıdan gelen isteklere izin ver (Frontend için şart!)
app.config['SECRET_KEY'] = SECRET_KEY

# --- Veritabanı Fonksiyonları ---
def get_db_connection():
    return psycopg2.connect(
        host=os.environ.get('DB_HOST', 'db'),
        database=os.environ.get('DB_NAME', 'reminders_db'),
        user=os.environ.get('DB_USER', 'admin'),
        password=os.environ.get('DB_PASS', 'sifre123'),
        cursor_factory=RealDictCursor
    )

def wait_for_db():
    retries = 10
    while retries > 0:
        try:
            conn = get_db_connection()
            conn.close()
            print("[Sistem] Veritabanı bağlantısı başarılı!")
            return True
        except:
            print(f"[Sistem] Veritabanı bekleniyor... ({retries})")
            time.sleep(2)
            retries -= 1
    return False

def init_db():
    if not wait_for_db(): return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                trigger_time TEXT NOT NULL,
                sound TEXT,
                status TEXT DEFAULT 'pending'
            );
        """)
        conn.commit()
        conn.close()
    except Exception as e: print(f"DB Hatası: {e}")

# --- Token Kontrol Mekanizması (Decorator) ---
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        # Header'da 'Authorization: Bearer <token>' var mı?
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split(" ")[1]
        
        if not token:
            return jsonify({'message': 'Token eksik!'}), 401
        
        try:
            # Token geçerli mi?
            jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
        except:
            return jsonify({'message': 'Geçersiz Token!'}), 401
        
        return f(*args, **kwargs)
    return decorated

# --- Endpointler ---

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "active", "db": "Postgres"}), 200

# 1. LOGIN (Frontend buraya istek atacak)
@app.route('/login', methods=['POST'])
def login():
    auth = request.get_json()
    if not auth or not auth.get('username') or not auth.get('password'):
        return jsonify({'message': 'Eksik bilgi'}), 401

    # Basitlik için kullanıcı adı/şifre kodun içinde. Normalde DB'den bakılır.
    if auth['username'] == 'admin' and auth['password'] == '1234':
        token = jwt.encode({
            'user': auth['username'],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=30)
        }, app.config['SECRET_KEY'], algorithm="HS256")
        return jsonify({'token': token})

    return jsonify({'message': 'Hatalı şifre'}), 401

# 2. EKLEME (Token Zorunlu!)
@app.route('/reminders', methods=['POST'])
@token_required 
def create_reminder():
    data = request.get_json()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO reminders (title, trigger_time) VALUES (%s, %s) RETURNING id",
        (data['title'], data['trigger_time'])
    )
    conn.commit()
    conn.close()
    return jsonify({"mesaj": "Kaydedildi"}), 201

# 3. LİSTELEME (Herkes görebilir, token istemedim)
@app.route('/reminders', methods=['GET'])
def get_reminders():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reminders ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return jsonify(rows), 200

# --- Zamanlayıcı ---
def scheduler():
    wait_for_db()
    while True:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            now = datetime.datetime.now().isoformat()
            cursor.execute("SELECT * FROM reminders WHERE status='pending' AND trigger_time <= %s", (now,))
            for r in cursor.fetchall():
                print(f"!!! ALARM: {r['title']} !!!")
                cursor.execute("UPDATE reminders SET status='triggered' WHERE id=%s", (r['id'],))
                conn.commit()
            conn.close()
        except: pass
        time.sleep(5)

if __name__ == '__main__':
    init_db()
    threading.Thread(target=scheduler, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
