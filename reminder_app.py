import sqlite3
import datetime
import time
import threading
import jwt  # PyJWT kütüphanesi
from flask import Flask, request, jsonify, g
from flask_cors import CORS # Frontend iletişimi için gerekli
from functools import wraps

# --- Yapılandırma ---
DATABASE = 'reminders.db'
SECRET_KEY = 'cok_gizli_anahtar_buraya' # JWT imzalamak için gerekli gizli anahtar

# --- Veritabanı Yardımcıları ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            trigger_time TEXT NOT NULL,
            sound TEXT,
            status TEXT NOT NULL DEFAULT 'pending'
        );
        """)
        db.commit()
        print("Veritabanı başarıyla başlatıldı.")

app = Flask(__name__)
# CORS'u aktif et (Tüm domainlerden gelen isteklere izin ver)
CORS(app) 
app.config['SECRET_KEY'] = SECRET_KEY

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# --- GÜVENLİK (AUTH) DECORATOR ---
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        # Header'da 'Authorization: Bearer <token>' formatı aranır
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(" ")[1]
        
        if not token:
            return jsonify({'message': 'Token eksik! Lütfen giriş yapın.'}), 401

        try:
            # Token'ı çözümle
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            # İsteğe bağlı: data['user'] ile kullanıcı kontrolü yapılabilir
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token süresi dolmuş.'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Geçersiz Token.'}), 401

        return f(*args, **kwargs)
    return decorated

# --- AUTH ENDPOINT ---
@app.route('/login', methods=['POST'])
def login():
    """Kullanıcı adı ve şifre ile Token alma noktası."""
    auth = request.get_json()

    # Basitlik için hardcoded kullanıcı: admin / password: 1234
    if not auth or not auth.get('username') or not auth.get('password'):
        return jsonify({'message': 'Kullanıcı adı ve şifre gerekli'}), 401

    if auth['username'] == 'admin' and auth['password'] == '1234':
        # Token oluştur (30 dakika geçerli)
        token = jwt.encode({
            'user': auth['username'],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=30)
        }, app.config['SECRET_KEY'], algorithm="HS256")

        return jsonify({'token': token})

    return jsonify({'message': 'Giriş başarısız! (Kullanıcı: admin, Şifre: 1234 deneyin)'}), 401

# --- API ENDPOINTLERİ ---

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "active", "message": "Backend çalışıyor."}), 200

# [GÜVENLİ] Sadece token sahipleri hatırlatıcı ekleyebilir
@app.route('/reminders', methods=['POST'])
@token_required 
def create_reminder():
    data = request.get_json()
    title = data.get('title')
    trigger_time_str = data.get('trigger_time')
    sound = data.get('sound', 'default')
    status = 'pending'

    if not title or not trigger_time_str:
        return jsonify({"hata": "Eksik bilgi."}), 400

    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO reminders (title, trigger_time, sound, status) VALUES (?, ?, ?, ?)",
        (title, trigger_time_str, sound, status)
    )
    db.commit()
    return jsonify({"mesaj": "Hatırlatıcı kaydedildi.", "id": cursor.lastrowid}), 201

# [HERKESE AÇIK] Herkes listeyi görebilir (Okuma izni)
@app.route('/reminders', methods=['GET'])
def get_all_reminders():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM reminders ORDER BY id DESC")
    reminders = [dict(row) for row in cursor.fetchall()]
    return jsonify(reminders), 200

@app.route('/reminders/<int:reminder_id>/complete', methods=['PUT'])
def complete_reminder(reminder_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE reminders SET status = 'completed' WHERE id = ?", (reminder_id,))
    db.commit()
    return jsonify({"mesaj": "Tamamlandı."}), 200

# --- ZAMANLAYICI ---
def reminder_scheduler():
    print("[Zamanlayıcı] Başlatıldı...")
    while True:
        try:
            with sqlite3.connect(DATABASE) as db:
                db.row_factory = sqlite3.Row
                cursor = db.cursor()
                now_iso = datetime.datetime.now().isoformat()
                cursor.execute("SELECT * FROM reminders WHERE status = 'pending' AND trigger_time <= ?", (now_iso,))
                for reminder in cursor.fetchall():
                    print(f"\n!!! ALARM: {reminder['title']} !!!\n")
                    cursor.execute("UPDATE reminders SET status = 'triggered' WHERE id = ?", (reminder['id'],))
                    db.commit()
        except Exception as e:
            print(f"Hata: {e}")
        time.sleep(10)

if __name__ == '__main__':
    init_db()
    threading.Thread(target=reminder_scheduler, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, use_reloader=False)  
