import sqlite3
import datetime
import time
import threading
from flask import Flask, request, jsonify, g

# --- Veritabanı Ayarları ---
DATABASE = 'reminders.db'

def get_db():
    """Veritabanı bağlantısını açar veya mevcut olanı kullanır."""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row  # Satırları dict gibi erişilebilir yapar
    return db

def init_db():
    """Veritabanı şemasını (tabloyu) oluşturur."""
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
            -- Olası durumlar: pending (beklemede), triggered (tetiklendi), completed (tamamlandı)
        );
        """)
        db.commit()
        print("Veritabanı başarıyla başlatıldı.")

# --- Flask Uygulaması ve API Uç Noktaları ---

app = Flask(__name__)

@app.teardown_appcontext
def close_connection(exception):
    """Her istek sonunda veritabanı bağlantısını kapatır."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# --- YENİ EKLENEN ÖZELLİKLER (Buraya taşındı) ---

@app.route('/health', methods=['GET'])
def health_check():
    """
    Sistemin çalışıp çalışmadığını kontrol etmek için basit bir endpoint.
    Ödev gereği yeni özellik olarak eklendi.
    """
    return jsonify({
        "status": "active",
        "message": "Sistem sorunsuz çalışıyor.",
        "time": datetime.datetime.now().isoformat()
    }), 200

@app.route('/')
def home():
    """Ana sayfa mesajı."""
    return "Merhaba! Hatırlatıcı Uygulaması Çalışıyor. /health adresinden durumu kontrol edebilirsiniz."

# --- Mevcut API Endpointleri ---

@app.route('/reminders', methods=['POST'])
def create_reminder():
    """Yeni bir hatırlatıcı oluşturur."""
    data = request.get_json()
    
    if not data or not data.get('title') or not data.get('trigger_time'):
        return jsonify({"hata": "Eksik bilgi: 'title' ve 'trigger_time' zorunludur."}), 400

    title = data.get('title')
    trigger_time_str = data.get('trigger_time')
    sound = data.get('sound', 'default') # Opsiyonel ses tonu
    status = 'pending' # Yeni hatırlatıcı her zaman beklemede başlar

    # Zaman formatı doğrulaması
    try:
        datetime.datetime.fromisoformat(trigger_time_str)
    except ValueError:
        return jsonify({"hata": "Geçersiz 'trigger_time' formatı. ISO formatı kullanın (YYYY-MM-DDTHH:MM:SS)."}), 400

    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO reminders (title, trigger_time, sound, status) VALUES (?, ?, ?, ?)",
        (title, trigger_time_str, sound, status)
    )
    db.commit()
    
    reminder_id = cursor.lastrowid
    print(f"[API] Yeni hatırlatıcı kaydedildi (ID: {reminder_id}): {title}")
    
    return jsonify({"mesaj": "Hatırlatıcı başarıyla kaydedildi.", "id": reminder_id}), 201


@app.route('/reminders/triggered', methods=['GET'])
def get_triggered_reminders():
    """Durumu 'triggered' (tetiklenmiş) olan tüm hatırlatıcıları getirir."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM reminders WHERE status = 'triggered'")
    reminders = [dict(row) for row in cursor.fetchall()]
    return jsonify(reminders), 200

@app.route('/reminders/<int:reminder_id>/complete', methods=['PUT'])
def complete_reminder(reminder_id):
    """Hatırlatıcının durumunu 'completed' (tamamlandı) olarak günceller."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
    reminder = cursor.fetchone()

    if reminder is None:
        return jsonify({"hata": "Hatırlatıcı bulunamadı."}), 404

    cursor.execute("UPDATE reminders SET status = 'completed' WHERE id = ?", (reminder_id,))
    db.commit()
    
    print(f"[API] Hatırlatıcı tamamlandı (ID: {reminder_id})")
    return jsonify({"mesaj": "Hatırlatıcı 'tamamlandı' olarak işaretlendi."}), 200

@app.route('/reminders', methods=['GET'])
def get_all_reminders():
    """Tüm hatırlatıcıları listeler (test için)."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM reminders")
    reminders = [dict(row) for row in cursor.fetchall()]
    return jsonify(reminders), 200


# --- Zamanlayıcı (Scheduler) Mantığı ---
def reminder_scheduler():
    """
    Veritabanını periyodik olarak kontrol eder, zamanı gelen 'pending'
    hatırlatıcıları 'triggered' durumuna geçirir.
    """
    print("[Zamanlayıcı] Hatırlatıcı kontrol servisi başlatıldı...")
    while True:
        try:
            # Ayrı bir thread olduğu için kendi veritabanı bağlantısını yönetmeli
            with sqlite3.connect(DATABASE) as db:
                db.row_factory = sqlite3.Row
                cursor = db.cursor()
                
                now_iso = datetime.datetime.now().isoformat()
                
                # Zamanı gelmiş ve hala 'pending' olanları bul
                cursor.execute(
                    "SELECT * FROM reminders WHERE status = 'pending' AND trigger_time <= ?", 
                    (now_iso,)
                )
                
                reminders_to_trigger = cursor.fetchall()
                
                for reminder in reminders_to_trigger:
                    print("\n" + "="*40)
                    print(f"!!! ALARM TETİKLENDİ (ID: {reminder['id']}) !!!")
                    print(f"    Başlık: {reminder['title']}")
                    print(f"    Zaman: {reminder['trigger_time']}")
                    print(f"    Ses: {reminder['sound']}")
                    print("="*40 + "\n")
                    
                    # Durumu 'triggered' olarak güncelle
                    cursor.execute("UPDATE reminders SET status = 'triggered' WHERE id = ?", (reminder['id'],))
                    db.commit()

        except Exception as e:
            print(f"[Zamanlayıcı] Hata: {e}")
            
        # Kontrol sıklığı (demo için 10 saniye)
        time.sleep(10)


# --- Ana Çalıştırma Bloğu ---
if __name__ == '__main__':
    # Flask'ı çalıştırmadan önce veritabanını başlat
    init_db()
    
    # Zamanlayıcıyı ayrı bir 'daemon' thread olarak başlat
    scheduler_thread = threading.Thread(target=reminder_scheduler, daemon=True)
    scheduler_thread.start()
    
    # Flask sunucusunu başlat
    print("[Flask] API sunucusu http://127.0.0.1:5000 adresinde başlatılıyor...")
    
    # app.run() EN SONDA OLMALIDIR. Bu komut çalıştığında kod burada döngüye girer.
    app.run(
        debug=True,
        host="0.0.0.0",
        port=5000,
        use_reloader=False
    )