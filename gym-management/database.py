import sqlite3
import os
from datetime import datetime, timedelta
from config import DATABASE_PATH

DATABASE_URL = os.environ.get('DATABASE_URL')
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg2
    from psycopg2.extras import RealDictCursor

def _convert_placeholders(query):
    return query.replace('?', '%s') if USE_POSTGRES else query

class PostgresCursor:
    def __init__(self, cursor):
        self.cursor = cursor
        self.lastrowid = None
        self.rowcount = -1

    def execute(self, query, params=None):
        self.cursor.execute(_convert_placeholders(query), params or ())
        self.rowcount = self.cursor.rowcount
        return self

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

class PostgresConnection:
    def __init__(self, conn):
        self.conn = conn

    def cursor(self):
        return PostgresCursor(self.conn.cursor(cursor_factory=RealDictCursor))

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

def init_database():
    """데이터베이스 초기화 및 테이블 생성"""
    conn = get_db_connection()
    cursor = conn.cursor()
    id_column = 'SERIAL PRIMARY KEY' if USE_POSTGRES else 'INTEGER PRIMARY KEY AUTOINCREMENT'
    
    # 회원 테이블
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS members (
            id {id_column},
            name TEXT NOT NULL,
            phone TEXT,
            parent_phone TEXT,
            birth_date TEXT,
            gender TEXT,
            branch TEXT DEFAULT '태평동',
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
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS attendance (
            id {id_column},
            member_id INTEGER NOT NULL,
            attendance_date TEXT NOT NULL,
            check_in_time TEXT,
            check_out_time TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (member_id) REFERENCES members (id) ON DELETE CASCADE
        )
    ''')
    
    # 스케줄 테이블
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS schedule (
            id {id_column},
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
    
    # 운동 프로그램 테이블
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS workout_programs (
            id {id_column},
            name TEXT NOT NULL,
            description TEXT,
            min_attendance INTEGER DEFAULT 0,
            max_attendance INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 관비 납부 테이블
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS fee_payment (
            id {id_column},
            member_id INTEGER NOT NULL,
            payment_year INTEGER NOT NULL,
            payment_month INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            payment_date TEXT,
            status TEXT DEFAULT 'unpaid',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (member_id) REFERENCES members(id)
        )
    ''')
    
    if USE_POSTGRES:
        cursor.execute('''
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'members'
        ''')
        member_columns = [row['column_name'] for row in cursor.fetchall()]
    else:
        cursor.execute("PRAGMA table_info(members)")
        member_columns = [row[1] for row in cursor.fetchall()]

    if 'parent_phone' not in member_columns:
        cursor.execute('ALTER TABLE members ADD COLUMN parent_phone TEXT')
    if 'branch' not in member_columns:
        cursor.execute("ALTER TABLE members ADD COLUMN branch TEXT DEFAULT '태평동'")
    if 'suspension_start_date' not in member_columns:
        cursor.execute('ALTER TABLE members ADD COLUMN suspension_start_date TEXT')
    if 'suspension_end_date' not in member_columns:
        cursor.execute('ALTER TABLE members ADD COLUMN suspension_end_date TEXT')
    if 'monthly_fee' not in member_columns:
        cursor.execute('ALTER TABLE members ADD COLUMN monthly_fee INTEGER DEFAULT 0')

    # 운동 프로그램 초기 데이터 추가 (테이블이 비어있을 때만)
    try:
        if USE_POSTGRES:
            cursor.execute('''
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'workout_programs'
                )
            ''')
            table_exists = cursor.fetchone()[0]
        else:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='workout_programs'")
            table_exists = cursor.fetchone() is not None
        
        if table_exists:
            cursor.execute('SELECT COUNT(*) as count FROM workout_programs')
            program_count = cursor.fetchone()['count']
            if program_count == 0:
                cursor.execute('''
                    INSERT INTO workout_programs (name, description, min_attendance, max_attendance) VALUES
                    ('Basic Fitness', 'Basic physical fitness training program.', 0, 4),
                    ('Basic Skills', 'Basic kickboxing skills training program.', 5, 9),
                    ('Sparring Training', 'Sparring training for skill improvement.', 10, 19),
                    ('Advanced Skills', 'Advanced techniques and strategy training.', 20, NULL)
                ''')
    except Exception as e:
        print(f"Warning: Failed to add initial workout programs: {e}")

    conn.commit()
    conn.close()

def get_db_connection():
    if USE_POSTGRES:
        return PostgresConnection(psycopg2.connect(DATABASE_URL, sslmode='require'))
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_database_status():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM members')
    result = cursor.fetchone()
    conn.close()
    return {
        'database': 'postgres' if USE_POSTGRES else 'sqlite',
        'database_url_configured': USE_POSTGRES,
        'members_count': result['count'] if result else 0
    }

def update_expired_members():
    """만료일이 지난 회원을 자동으로 'inactive' 상태 전환하고, 일시정지 기간이 끝난 회원을 'active'로 복구"""
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. 만료일이 지난 회원을 'inactive'로 전환
    cursor.execute('''
        UPDATE members 
        SET status = 'inactive' 
        WHERE expiry_date < ? AND status = 'active'
    ''', (today,))
    
    # 2. 일시정지 기간이 끝난 회원을 'active'로 복구
    cursor.execute('''
        UPDATE members 
        SET status = 'active' 
        WHERE status = 'suspended' AND suspension_end_date IS NOT NULL AND suspension_end_date < ?
    ''', (today,))
    
    conn.commit()
    conn.close()

def get_member_count(branch=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if branch in ['태평동', '복수동']:
        cursor.execute("SELECT COUNT(*) as count FROM members WHERE (status = 'active' OR status = 'suspended') AND branch = ?", (branch,))
    else:
        cursor.execute("SELECT COUNT(*) as count FROM members WHERE status = 'active' OR status = 'suspended'")
    result = cursor.fetchone()
    conn.close()
    return result['count'] if result else 0

def get_today_attendance_count(branch=None):
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_db_connection()
    cursor = conn.cursor()
    if branch in ['태평동', '복수동']:
        cursor.execute('''
            SELECT COUNT(*) as count
            FROM attendance a
            JOIN members m ON m.id = a.member_id
            WHERE a.attendance_date = ? AND m.branch = ?
        ''', (today, branch))
    else:
        cursor.execute('SELECT COUNT(*) as count FROM attendance WHERE attendance_date = ?', (today,))
    result = cursor.fetchone()
    conn.close()
    return result['count'] if result else 0

# ★ 수정: 외부에서 일수 조절이 가능하게 확장하고 기본값을 5일로 변경 (TypeError 완벽 방지)
def get_overdue_members_count(days=5, branch=None):
    today = datetime.now()
    future_date = (today + timedelta(days=days)).strftime('%Y-%m-%d')
    today_str = today.strftime('%Y-%m-%d')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    query = '''
        SELECT COUNT(*) as count FROM members 
        WHERE expiry_date BETWEEN ? AND ? AND status = 'active'
    '''
    params = [today_str, future_date]
    if branch in ['태평동', '복수동']:
        query += ' AND branch = ?'
        params.append(branch)
    cursor.execute(query, params)
    result = cursor.fetchone()
    conn.close()
    return result['count'] if result else 0

def get_absent_members_count(days, branch=None):
    target_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    conn = get_db_connection()
    cursor = conn.cursor()
    query = '''
        SELECT COUNT(*) as count FROM members m
        WHERE (m.status = 'active' OR m.status = 'suspended') AND m.id NOT IN (
            SELECT DISTINCT member_id FROM attendance 
            WHERE attendance_date > ?
        )
    '''
    params = [target_date]
    if branch in ['태평동', '복수동']:
        query += ' AND m.branch = ?'
        params.append(branch)
    cursor.execute(query, params)
    result = cursor.fetchone()
    conn.close()
    return result['count'] if result else 0

def get_absent_members(days, branch=None):
    target_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    conn = get_db_connection()
    cursor = conn.cursor()
    query = '''
        SELECT m.*, 
               (SELECT MAX(attendance_date) FROM attendance WHERE member_id = m.id) as last_attendance
        FROM members m
        WHERE (m.status = 'active' OR m.status = 'suspended') AND m.id NOT IN (
            SELECT DISTINCT member_id FROM attendance 
            WHERE attendance_date > ?
        )
    '''
    params = [target_date]
    if branch in ['태평동', '복수동']:
        query += ' AND m.branch = ?'
        params.append(branch)
    query += '''
        ORDER BY last_attendance ASC
    '''
    cursor.execute(query, params)
    result = cursor.fetchall()
    conn.close()
    return result

# ★ 수정: 외부에서 일수 조절이 가능하게 확장하고 기본값을 5일로 변경 (보고서 연동 최적화)
def get_expiring_members(days=5, branch=None):
    today = datetime.now()
    future_date = (today + timedelta(days=days)).strftime('%Y-%m-%d')
    today_str = today.strftime('%Y-%m-%d')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    query = '''
        SELECT * FROM members 
        WHERE expiry_date BETWEEN ? AND ? AND status = 'active'
    '''
    params = [today_str, future_date]
    if branch in ['태평동', '복수동']:
        query += ' AND branch = ?'
        params.append(branch)
    query += '''
        ORDER BY expiry_date ASC
    '''
    cursor.execute(query, params)
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

def get_all_members(search_query=None, branch=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    branch_filter = branch if branch in ['태평동', '복수동'] else None
    if search_query:
        query = '''
            SELECT m.*,
                   (SELECT COUNT(*) FROM attendance WHERE member_id = m.id) as total_attendance,
                   (SELECT MAX(attendance_date) FROM attendance WHERE member_id = m.id) as last_attendance
            FROM members m
            WHERE (m.name LIKE ? OR m.phone LIKE ? OR m.parent_phone LIKE ?)
        '''
        params = [f'%{search_query}%', f'%{search_query}%', f'%{search_query}%']
        if branch_filter:
            query += ' AND m.branch = ?'
            params.append(branch_filter)
        query += '''
            ORDER BY m.registration_date DESC
        '''
        cursor.execute(query, params)
    else:
        query = '''
            SELECT m.*,
                   (SELECT COUNT(*) FROM attendance WHERE member_id = m.id) as total_attendance,
                   (SELECT MAX(attendance_date) FROM attendance WHERE member_id = m.id) as last_attendance
            FROM members m
        '''
        params = []
        if branch_filter:
            query += ' WHERE m.branch = ?'
            params.append(branch_filter)
        query += ' ORDER BY m.registration_date DESC'
        cursor.execute(query, params)
    result = cursor.fetchall()
    conn.close()
    return result

def get_members_by_status(status, search_query=None, branch=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    branch_filter = branch if branch in ['태평동', '복수동'] else None
    
    # status='active'일 때 정지 관원도 함께 포함
    if status == 'active':
        status_filter = "(m.status = 'active' OR m.status = 'suspended')"
        use_param = False
    else:
        status_filter = "m.status = ?"
        use_param = True
    
    if search_query:
        query = f'''
            SELECT m.*,
                   (SELECT COUNT(*) FROM attendance WHERE member_id = m.id) as total_attendance,
                   (SELECT MAX(attendance_date) FROM attendance WHERE member_id = m.id) as last_attendance
            FROM members m
            WHERE {status_filter} AND (m.name LIKE ? OR m.phone LIKE ? OR m.parent_phone LIKE ?)
        '''
        params = []
        if use_param:
            params.append(status)
        params.extend([f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'])
        if branch_filter:
            query += ' AND m.branch = ?'
            params.append(branch_filter)
        query += ' ORDER BY m.registration_date DESC'
        cursor.execute(query, params)
    else:
        query = f'''
            SELECT m.*,
                   (SELECT COUNT(*) FROM attendance WHERE member_id = m.id) as total_attendance,
                   (SELECT MAX(attendance_date) FROM attendance WHERE member_id = m.id) as last_attendance
            FROM members m WHERE {status_filter}
        '''
        params = []
        if use_param:
            params.append(status)
        if branch_filter:
            query += ' AND m.branch = ?'
            params.append(branch_filter)
        query += ' ORDER BY m.registration_date DESC'
        cursor.execute(query, params)
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

def add_member(name, phone, birth_date, gender, membership_type, memo, status='active', membership_start_date=None, parent_phone=None, branch='태평동', monthly_fee=0):
    today = datetime.now().strftime('%Y-%m-%d')
    if not membership_start_date:
        membership_start_date = today
        
    expiry_date = calculate_expiry_date(membership_start_date, int(membership_type))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    query = '''
        INSERT INTO members (name, phone, parent_phone, birth_date, gender, registration_date, 
                           branch, membership_type, membership_start_date, expiry_date, memo, status, monthly_fee)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    '''
    if USE_POSTGRES:
        query += ' RETURNING id'
    cursor.execute(query, (name, phone, parent_phone, birth_date, gender, today, branch, membership_type, membership_start_date, expiry_date, memo, status, monthly_fee))
    member_id = cursor.fetchone()['id'] if USE_POSTGRES else cursor.lastrowid
    conn.commit()
    conn.close()
    return member_id

def update_member(member_id, name, phone, birth_date, gender, membership_type, membership_start_date, memo, status, parent_phone=None, branch='태평동', suspension_start_date=None, suspension_end_date=None, monthly_fee=0):
    expiry_date = calculate_expiry_date(membership_start_date, int(membership_type))
    
    # 수련정지 기간을 제외한 만료일 계산
    if status == 'suspended' and suspension_start_date and suspension_end_date:
        try:
            start = datetime.strptime(suspension_start_date, '%Y-%m-%d')
            end = datetime.strptime(suspension_end_date, '%Y-%m-%d')
            suspension_days = (end - start).days + 1  # +1: 마지막 날도 포함
            
            expiry_dt = datetime.strptime(expiry_date, '%Y-%m-%d')
            expiry_date = (expiry_dt + timedelta(days=suspension_days)).strftime('%Y-%m-%d')
        except:
            pass
    # 상태가 suspended가 아니면 정지 기간 정보 제거
    elif status != 'suspended':
        suspension_start_date = None
        suspension_end_date = None
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE members 
        SET name = ?, phone = ?, parent_phone = ?, birth_date = ?, gender = ?, branch = ?, membership_type = ?, 
            membership_start_date = ?, expiry_date = ?, memo = ?, status = ?, suspension_start_date = ?, 
            suspension_end_date = ?, monthly_fee = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (name, phone, parent_phone, birth_date, gender, branch, membership_type, membership_start_date, expiry_date, memo, status, suspension_start_date, suspension_end_date, monthly_fee, member_id))
    conn.commit()
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
    query = '''
        INSERT INTO schedule (title, description, schedule_date, start_time, end_time, category)
        VALUES (?, ?, ?, ?, ?, ?)
    '''
    if USE_POSTGRES:
        query += ' RETURNING id'
    cursor.execute(query, (title, description, schedule_date, start_time, end_time, category))
    schedule_id = cursor.fetchone()['id'] if USE_POSTGRES else cursor.lastrowid
    conn.commit()
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

def get_expired_members(branch=None):
    """만료된 관원(inactive status) 목록 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    query = '''
        SELECT m.*,
               (SELECT COUNT(*) FROM attendance WHERE member_id = m.id) as total_attendance,
               (SELECT MAX(attendance_date) FROM attendance WHERE member_id = m.id) as last_attendance
        FROM members m 
        WHERE m.status = 'inactive'
    '''
    params = []
    if branch in ['태평동', '복수동']:
        query += ' AND m.branch = ?'
        params.append(branch)
    query += '''
        ORDER BY m.expiry_date DESC
    '''
    cursor.execute(query, params)
    result = cursor.fetchall()
    conn.close()
    return result

def get_expired_members_count(branch=None):
    """만료된 관원(inactive status) 수 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "SELECT COUNT(*) as count FROM members WHERE status = 'inactive'"
    params = []
    if branch in ['태평동', '복수동']:
        query += ' AND branch = ?'
        params.append(branch)
    cursor.execute(query, params)
    result = cursor.fetchone()
    conn.close()
    return result['count'] if result else 0

# ============= 운동 프로그램 관리 =============

def get_all_workout_programs():
    """모든 운동 프로그램 조회"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM workout_programs ORDER BY min_attendance ASC')
        result = cursor.fetchall()
        conn.close()
        return result
    except Exception as e:
        print(f"Warning: Failed to get workout programs: {e}")
        return []

def get_workout_program_by_id(program_id):
    """ID로 운동 프로그램 조회"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM workout_programs WHERE id = ?', (program_id,))
        result = cursor.fetchone()
        conn.close()
        return result
    except Exception as e:
        print(f"Warning: Failed to get workout program by id: {e}")
        return None

def get_workout_program_by_attendance(attendance_count):
    """출석 횟수에 맞는 운동 프로그램 조회"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM workout_programs
            WHERE min_attendance <= ? AND (max_attendance IS NULL OR max_attendance >= ?)
            ORDER BY min_attendance DESC
            LIMIT 1
        ''', (attendance_count, attendance_count))
        result = cursor.fetchone()
        conn.close()
        return result
    except Exception as e:
        print(f"Warning: Failed to get workout program by attendance: {e}")
        return None

def add_workout_program(name, description, min_attendance, max_attendance=None):
    """운동 프로그램 추가"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # 테이블이 없으면 생성
        if USE_POSTGRES:
            cursor.execute('''
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'workout_programs'
                )
            ''')
            table_exists = cursor.fetchone()[0]
        else:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='workout_programs'")
            table_exists = cursor.fetchone() is not None
        
        if not table_exists:
            id_column = 'SERIAL PRIMARY KEY' if USE_POSTGRES else 'INTEGER PRIMARY KEY AUTOINCREMENT'
            cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS workout_programs (
                    id {id_column},
                    name TEXT NOT NULL,
                    description TEXT,
                    min_attendance INTEGER DEFAULT 0,
                    max_attendance INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
        
        query = '''
            INSERT INTO workout_programs (name, description, min_attendance, max_attendance)
            VALUES (?, ?, ?, ?)
        '''
        if USE_POSTGRES:
            query += ' RETURNING id'
        cursor.execute(query, (name, description, min_attendance, max_attendance))
        program_id = cursor.fetchone()['id'] if USE_POSTGRES else cursor.lastrowid
        conn.commit()
        conn.close()
        return program_id
    except Exception as e:
        print(f"Warning: Failed to add workout program: {e}")
        return None

def update_workout_program(program_id, name, description, min_attendance, max_attendance=None):
    """운동 프로그램 수정"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE workout_programs
            SET name = ?, description = ?, min_attendance = ?, max_attendance = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (name, description, min_attendance, max_attendance, program_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Warning: Failed to update workout program: {e}")

def delete_workout_program(program_id):
    """운동 프로그램 삭제"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM workout_programs WHERE id = ?', (program_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Warning: Failed to delete workout program: {e}")

# ============= 관비 납부 관리 =============

def get_fee_payments_by_month(year, month, status=None, branch=None):
    """특정 월의 관비 납부 현황 조회"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = '''
            SELECT m.*, fp.id as payment_id, fp.payment_date, fp.status as payment_status, fp.amount as payment_amount, m.expiry_date
            FROM members m
            LEFT JOIN fee_payment fp ON m.id = fp.member_id AND fp.payment_year = ? AND fp.payment_month = ?
            WHERE m.status = 'active'
        '''
        params = [year, month]
        
        if branch in ['태평동', '복수동']:
            query += ' AND m.branch = ?'
            params.append(branch)
        
        if status:
            query += ' AND fp.status = ?'
            params.append(status)
        
        query += ' ORDER BY m.name ASC'
        
        cursor.execute(query, params)
        result = cursor.fetchall()
        conn.close()
        return result
    except Exception as e:
        print(f"Warning: Failed to get fee payments: {e}")
        return []

def get_fee_payment_by_member_month(member_id, year, month):
    """특정 회원의 특정 월 납부 상태 조회"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM fee_payment
            WHERE member_id = ? AND payment_year = ? AND payment_month = ?
        ''', (member_id, year, month))
        result = cursor.fetchone()
        conn.close()
        return result
    except Exception as e:
        print(f"Warning: Failed to get fee payment by member month: {e}")
        return None

def create_fee_payment(member_id, year, month, amount):
    """관비 납부 레코드 생성"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 이미 존재하는지 확인
        existing = get_fee_payment_by_member_month(member_id, year, month)
        if existing:
            conn.close()
            return existing['id']
        
        query = '''
            INSERT INTO fee_payment (member_id, payment_year, payment_month, amount, status)
            VALUES (?, ?, ?, ?, 'unpaid')
        '''
        if USE_POSTGRES:
            query += ' RETURNING id'
        cursor.execute(query, (member_id, year, month, amount))
        payment_id = cursor.fetchone()['id'] if USE_POSTGRES else cursor.lastrowid
        conn.commit()
        conn.close()
        return payment_id
    except Exception as e:
        print(f"Warning: Failed to create fee payment: {e}")
        return None

def mark_fee_as_paid(payment_id, payment_date=None):
    """관비 납부 완료 처리"""
    try:
        if not payment_date:
            payment_date = datetime.now().strftime('%Y-%m-%d')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE fee_payment
            SET status = 'paid', payment_date = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (payment_date, payment_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Warning: Failed to mark fee as paid: {e}")

def mark_fee_as_unpaid(payment_id):
    """관비 납부 취소 처리"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE fee_payment
            SET status = 'unpaid', payment_date = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (payment_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Warning: Failed to mark fee as unpaid: {e}")

def extend_member_expiry(member_id, extend_months):
    """회원권 만료일 연장"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 현재 만료일 조회
        cursor.execute('SELECT expiry_date FROM members WHERE id = ?', (member_id,))
        result = cursor.fetchone()
        
        if result and result['expiry_date']:
            current_expiry = datetime.strptime(result['expiry_date'], '%Y-%m-%d')
            # 현재 만료일이 이미 지난 경우 오늘부터, 아니면 만료일부터 연장
            today = datetime.now()
            base_date = max(current_expiry, today)
            new_expiry = (base_date + timedelta(days=extend_months * 30)).strftime('%Y-%m-%d')
            
            cursor.execute('UPDATE members SET expiry_date = ?, membership_type = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', 
                         (new_expiry, extend_months, member_id))
            conn.commit()
        
        conn.close()
    except Exception as e:
        print(f"Warning: Failed to extend member expiry: {e}")
