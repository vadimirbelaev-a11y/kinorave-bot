import sqlite3
from datetime import datetime, timedelta

DB_NAME = 'bot_database.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            vip_status INTEGER DEFAULT 0,
            vip_expires_at TIMESTAMP,
            invited_by INTEGER,
            referral_count INTEGER DEFAULT 0,
            bonuses_claimed INTEGER DEFAULT 0,
            joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Таблица для защиты от накрутки рефералов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            referrer_id INTEGER,
            referred_id INTEGER PRIMARY KEY
        )
    ''')
    # Таблица настроек (тех. работы)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('maintenance', 'off')")
    conn.commit()
    conn.close()

def db_add_user(user_id, username, first_name, referrer_id=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('SELECT user_id, invited_by FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    
    if not row:
        actual_referrer = None
        if referrer_id and referrer_id != user_id:
            cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (referrer_id,))
            if cursor.fetchone():
                actual_referrer = referrer_id

        cursor.execute('''
            INSERT INTO users (user_id, username, first_name, invited_by, vip_status) 
            VALUES (?, ?, ?, ?, 0)
        ''', (user_id, username, first_name, actual_referrer))
        
        if actual_referrer:
            try:
                cursor.execute('INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)', (actual_referrer, user_id))
                cursor.execute('UPDATE users SET referral_count = referral_count + 1 WHERE user_id = ?', (actual_referrer,))
                
                cursor.execute('SELECT referral_count, bonuses_claimed FROM users WHERE user_id = ?', (actual_referrer,))
                ref_data = cursor.fetchone()
                if ref_data:
                    current_refs, claimed = ref_data[0], ref_data[1]
                    earned_bonuses = current_refs // 3
                    if earned_bonuses > claimed and claimed < 3:
                        cursor.execute('UPDATE users SET bonuses_claimed = bonuses_claimed + 1 WHERE user_id = ?', (actual_referrer,))
                        
                        cursor.execute('SELECT vip_expires_at, vip_status FROM users WHERE user_id = ?', (actual_referrer,))
                        v_row = cursor.fetchone()
                        now = datetime.now()
                        
                        if v_row[1] == 1 and v_row[0]:
                            try:
                                exp_time = datetime.fromisoformat(v_row[0])
                                if exp_time > now:
                                    new_exp = exp_time + timedelta(hours=24)
                                else:
                                    new_exp = now + timedelta(hours=24)
                            except:
                                new_exp = now + timedelta(hours=24)
                        else:
                            new_exp = now + timedelta(hours=24)
                            
                        cursor.execute('UPDATE users SET vip_status = 1, vip_expires_at = ? WHERE user_id = ?', (new_exp.isoformat(), actual_referrer))
            except sqlite3.IntegrityError:
                pass

        conn.commit()
    conn.close()

def check_vip_status_expiration(user_id, admin_id) -> int:
    if user_id == admin_id:
        return 1
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT vip_status, vip_expires_at FROM users WHERE user_id = ?', (user_id,))
    res = cursor.fetchone()
    conn.close()
    
    if not res:
        return 0
    
    vip_status, expires_at = res[0], res[1]
    if vip_status == 1 and expires_at:
        try:
            if datetime.now() > datetime.fromisoformat(expires_at):
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute('UPDATE users SET vip_status = 0, vip_expires_at = NULL WHERE user_id = ?', (user_id,))
                conn.commit()
                conn.close()
                return 0
        except:
            pass
    return vip_status

def db_get_user_info(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT referral_count, bonuses_claimed FROM users WHERE user_id = ?', (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res if res else (0, 0)

def db_set_user_vip_months(user_id, months=1):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    now = datetime.now()
    new_exp = now + timedelta(days=30 * months)
    cursor.execute('UPDATE users SET vip_status = 1, vip_expires_at = ? WHERE user_id = ?', (new_exp.isoformat(), user_id))
    conn.commit()
    conn.close()

def db_get_stats():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    total = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM users WHERE vip_status = 1')
    vip_total = cursor.fetchone()[0]
    conn.close()
    return total, vip_total

def db_get_all_users():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

def get_maintenance_mode():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key='maintenance'")
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else 'off'

def set_maintenance_mode(status: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE settings SET value = ? WHERE key='maintenance'", (status,))
    conn.commit()
    conn.close()
