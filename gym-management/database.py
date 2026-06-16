import sqlite3
from datetime import datetime, timedelta
from config import DATABASE_PATH

def init_database():
    """SQLite 데이터베이스 초기화 및 테이블 생성"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # 회원 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            parent_phone TEXT,
            birth_date TEXT,
            gender TEXT,
            registration_date TEXT NOT NULL,
            membership_type INTEGER NOT NULL,
            membership_start_date TEXT,
            expiry_date TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            memo TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 출석 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            attendance_date TEXT NOT NULL,
            check_in_time TEXT,
            check_out_time TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (member_id) REFERENCES members (id) ON DELETE CASCADE
        )
    ''')
    
    # 스케줄 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            schedule_date TEXT NOT NULL,
            start_time TEXT,
            end_time TEXT,
            category TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute("PRAGMA table_info(members)")
    member_columns = [row[1] for row in cursor.fetchall()]
    if 'parent_phone' not in member_columns:
        cursor.execute('ALTER TABLE members ADD COLUMN parent_phone TEXT')
    if 'suspension_start_date' not in member_columns:
        cursor.execute('ALTER TABLE members ADD COLUMN suspension_start_date TEXT')
    if 'suspension_end_date' not in member_columns:
        cursor.execute('ALTER TABLE members ADD COLUMN suspension_end_date TEXT')

    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def update_expired_members():
    """만료일이 지난 회원을 자동으로 'inactive' 상태 전환"""
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE members 
        SET status = 'inactive' 
        WHERE expiry_date < ? AND status = 'active'
    ''', (today,))
    conn.commit()
    conn.close()

def get_member_count():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM members WHERE status = 'active'")
    result = cursor.fetchone()
    conn.close()
    return result['count'] if result else 0

def get_today_attendance_count():
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM attendance WHERE attendance_date = ?', (today,))
    result = cursor.fetchone()
    conn.close()
    return result['count'] if result else 0

# ★ 수정: 외부에서 일수 조절이 가능하게 확장하고 기본값을 5일로 변경 (TypeError 완벽 방지)
def get_overdue_members_count(days=5):
    today = datetime.now()
    future_date = (today + timedelta(days=days)).strftime('%Y-%m-%d')
    today_str = today.strftime('%Y-%m-%d')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COUNT(*) as count FROM members 
        WHERE expiry_date BETWEEN ? AND ? AND status = 'active'
    ''', (today_str, future_date))
    result = cursor.fetchone()
    conn.close()
    return result['count'] if result else 0

def get_absent_members_count(days):
    target_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COUNT(*) as count FROM members m
        WHERE m.status = 'active' AND m.id NOT IN (
            SELECT DISTINCT member_id FROM attendance 
            WHERE attendance_date > ?
        )
    ''', (target_date,))
    result = cursor.fetchone()
    conn.close()
    return result['count'] if result else 0

def get_absent_members(days):
    target_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT m.*, 
               (SELECT MAX(attendance_date) FROM attendance WHERE member_id = m.id) as last_attendance
        FROM members m
        WHERE m.status = 'active' AND m.id NOT IN (
            SELECT DISTINCT member_id FROM attendance 
            WHERE attendance_date > ?
        )
        ORDER BY last_attendance ASC
    ''', (target_date,))
    result = cursor.fetchall()
    conn.close()
    return result

# ★ 수정: 외부에서 일수 조절이 가능하게 확장하고 기본값을 5일로 변경 (보고서 연동 최적화)
def get_expiring_members(days=5):
    today = datetime.now()
    future_date = (today + timedelta(days=days)).strftime('%Y-%m-%d')
    today_str = today.strftime('%Y-%m-%d')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM members 
        WHERE expiry_date BETWEEN ? AND ? AND status = 'active'
        ORDER BY expiry_date ASC
    ''', (today_str, future_date))
    result = cursor.fetchall()
    conn.close()
    return result

def get_member_by_id(member_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT m.*,
               (SELECT COUNT(*) FROM attendance WHERE member_id = m.id) as total_attendance,
               (SELECT MAX(attendance_date) FROM attendance WHERE member_id = m.id) as last_attendance
        FROM members m WHERE m.id = ?
    ''', (member_id,))
    result = cursor.fetchone()
    conn.close()
    return result

def get_all_members(search_query=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if search_query:
        cursor.execute('''
            SELECT m.*,
                   (SELECT COUNT(*) FROM attendance WHERE member_id = m.id) as total_attendance,
                   (SELECT MAX(attendance_date) FROM attendance WHERE member_id = m.id) as last_attendance
            FROM members m
            WHERE m.name LIKE ? OR m.phone LIKE ? OR m.parent_phone LIKE ?
            ORDER BY m.registration_date DESC
        ''', (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'))
    else:
        cursor.execute('''
            SELECT m.*,
                   (SELECT COUNT(*) FROM attendance WHERE member_id = m.id) as total_attendance,
                   (SELECT MAX(attendance_date) FROM attendance WHERE member_id = m.id) as last_attendance
            FROM members m ORDER BY m.registration_date DESC
        ''')
    result = cursor.fetchall()
    conn.close()
    return result

def get_members_by_status(status, search_query=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if search_query:
        cursor.execute('''
            SELECT m.*,
                   (SELECT COUNT(*) FROM attendance WHERE member_id = m.id) as total_attendance,
                   (SELECT MAX(attendance_date) FROM attendance WHERE member_id = m.id) as last_attendance
            FROM members m
            WHERE m.status = ? AND (m.name LIKE ? OR m.phone LIKE ? OR m.parent_phone LIKE ?)
            ORDER BY m.registration_date DESC
        ''', (status, f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'))
    else:
        cursor.execute('''
            SELECT m.*,
                   (SELECT COUNT(*) FROM attendance WHERE member_id = m.id) as total_attendance,
                   (SELECT MAX(attendance_date) FROM attendance WHERE member_id = m.id) as last_attendance
            FROM members m WHERE m.status = ? ORDER BY m.registration_date DESC
        ''', (status,))
    result = cursor.fetchall()
    conn.close()
    return result

def calculate_expiry_date(start_date_str, membership_type):
    start_datetime = datetime.strptime(start_date_str, '%Y-%m-%d')
    if membership_type == 1:
        return (start_datetime + timedelta(days=30)).strftime('%Y-%m-%d')
    elif membership_type == 3:
        return (start_datetime + timedelta(days=90)).strftime('%Y-%m-%d')
    elif membership_type == 6:
        return (start_datetime + timedelta(days=180)).strftime('%Y-%m-%d')
    else:
        return (start_datetime + timedelta(days=365)).strftime('%Y-%m-%d')

def add_member(name, phone, birth_date, gender, membership_type, memo, status='active', membership_start_date=None, parent_phone=None):
    today = datetime.now().strftime('%Y-%m-%d')
    if not membership_start_date:
        membership_start_date = today
        
    expiry_date = calculate_expiry_date(membership_start_date, int(membership_type))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO members (name, phone, parent_phone, birth_date, gender, registration_date, 
                               membership_type, membership_start_date, expiry_date, memo, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, phone, parent_phone, birth_date, gender, today, membership_type, membership_start_date, expiry_date, memo, status))
        conn.commit()
        member_id = cursor.lastrowid
        return member_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def update_member(member_id, name, phone, birth_date, gender, membership_type, membership_start_date, memo, status, parent_phone=None, suspension_start_date=None, suspension_end_date=None):
    expiry_date = calculate_expiry_date(membership_start_date, int(membership_type))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE members 
            SET name = ?, phone = ?, parent_phone = ?, birth_date = ?, gender = ?, membership_type = ?, 
                membership_start_date = ?, expiry_date = ?, memo = ?, status = ?, updated_at = CURRENT_TIMESTAMP,
                suspension_start_date = ?, suspension_end_date = ?
            WHERE id = ?
        ''', (name, phone, parent_phone, birth_date, gender, membership_type, membership_start_date, expiry_date, memo, status, suspension_start_date, suspension_end_date, member_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def delete_member(member_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM members WHERE id = ?', (member_id,))
    conn.commit()
    conn.close()

def get_attendance_map_for_range(start_date, end_date):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT member_id, attendance_date FROM attendance
        WHERE attendance_date BETWEEN ? AND ?
    ''', (start_date, end_date))
    attendance_map = {}
    for row in cursor.fetchall():
        member_id = row['member_id']
        if member_id not in attendance_map:
            attendance_map[member_id] = set()
        attendance_map[member_id].add(row['attendance_date'])
    conn.close()
    return attendance_map

def toggle_attendance(member_id):
    today = datetime.now().strftime('%Y-%m-%d')
    return toggle_attendance_by_date(member_id, today)

def toggle_attendance_by_date(member_id, attendance_date):
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    if attendance_date == today_str:
        check_in_time = datetime.now().strftime('%H:%M:%S')
    else:
        check_in_time = "06:00:00"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM attendance WHERE member_id = ? AND attendance_date = ?', (member_id, attendance_date))
    existing = cursor.fetchone()
    
    if existing:
        cursor.execute('DELETE FROM attendance WHERE member_id = ? AND attendance_date = ?', (member_id, attendance_date))
        conn.commit()
        conn.close()
        return {'success': True, 'status': 'deleted', 'message': '출석이 취소되었습니다.'}
    else:
        cursor.execute('''
            INSERT INTO attendance (member_id, attendance_date, check_in_time)
            VALUES (?, ?, ?)
        ''', (member_id, attendance_date, check_in_time))
        conn.commit()
        conn.close()
        return {'success': True, 'status': 'added', 'message': '출석이 기록되었습니다.'}

def clear_today_attendance():
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM attendance WHERE attendance_date = ?', (today,))
    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted_count

def get_attendance_records(member_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM attendance WHERE member_id = ? ORDER BY attendance_date DESC LIMIT 50', (member_id,))
    result = cursor.fetchall()
    conn.close()
    return result

def get_member_attendance_by_month(member_id, year, month):
    start_date = f'{year}-{month:02d}-01'
    end_date = f'{year+1}-01-01' if month == 12 else f'{year}-{month+1:02d}-01'
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DISTINCT attendance_date FROM attendance 
        WHERE member_id = ? AND attendance_date >= ? AND attendance_date < ?
        ORDER BY attendance_date
    ''', (member_id, start_date, end_date))
    result = cursor.fetchall()
    conn.close()
    return [row['attendance_date'] for row in result]

def get_all_attendance_by_month(year, month):
    start_date = f'{year}-{month:02d}-01'
    end_date = f'{year+1}-01-01' if month == 12 else f'{year}-{month+1:02d}-01'
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT attendance_date, COUNT(DISTINCT member_id) as count
        FROM attendance 
        WHERE attendance_date >= ? AND attendance_date < ?
        GROUP BY attendance_date
    ''', (start_date, end_date))
    result = cursor.fetchall()
    conn.close()
    return result

def get_day_attendance_members(date):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DISTINCT m.*, a.check_in_time, a.check_out_time
        FROM members m
        JOIN attendance a ON m.id = a.member_id
        WHERE a.attendance_date = ?
        ORDER BY m.name
    ''', (date,))
    result = cursor.fetchall()
    conn.close()
    return result

# ============= 스케줄 데이터 핸들러 =============

def get_all_schedules():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM schedule ORDER BY schedule_date DESC, start_time')
    result = cursor.fetchall()
    conn.close()
    return result

def get_schedules_by_month(year, month):
    month_str = f'{year}-{month:02d}'
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM schedule
        WHERE schedule_date LIKE ?
        ORDER BY schedule_date ASC, start_time
    ''', (f'{month_str}%',))
    result = cursor.fetchall()
    conn.close()
    return result

def get_schedules_by_date(date):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM schedule WHERE schedule_date = ? ORDER BY start_time', (date,))
    result = cursor.fetchall()
    conn.close()
    return result

def get_schedule_by_id(schedule_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM schedule WHERE id = ?', (schedule_id,))
    result = cursor.fetchone()
    conn.close()
    return result

def add_schedule(title, description, schedule_date, start_time, end_time, category):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO schedule (title, description, schedule_date, start_time, end_time, category)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (title, description, schedule_date, start_time, end_time, category))
    conn.commit()
    schedule_id = cursor.lastrowid
    conn.close()
    return schedule_id

def update_schedule(schedule_id, title, description, schedule_date, start_time, end_time, category):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE schedule 
        SET title = ?, description = ?, schedule_date = ?, start_time = ?, end_time = ?, category = ?
        WHERE id = ?
    ''', (title, description, schedule_date, start_time, end_time, category, schedule_id))
    conn.commit()
    conn.close()

def delete_schedule(schedule_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM schedule WHERE id = ?', (schedule_id,))
    conn.commit()
    conn.close()