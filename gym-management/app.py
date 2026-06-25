from flask import Flask, render_template, request, redirect, url_for, jsonify
from datetime import datetime, timedelta
import calendar
from database import (
    init_database, update_expired_members, get_member_count, get_today_attendance_count,
    get_overdue_members_count, get_absent_members_count, get_absent_members,
    get_expiring_members, get_member_by_id, get_all_members, get_members_by_status,
    add_member, update_member, delete_member, get_attendance_records,
    get_member_attendance_by_month, get_all_attendance_by_month, get_day_attendance_members,
    get_attendance_map_for_range, toggle_attendance, clear_today_attendance, toggle_attendance_by_date,
    get_all_schedules, get_schedules_by_month, get_schedules_by_date, get_schedule_by_id,
    add_schedule, update_schedule, delete_schedule, get_database_status, get_expired_members, get_expired_members_count,
    get_all_workout_programs, get_workout_program_by_id, get_workout_program_by_attendance,
    add_workout_program, update_workout_program, delete_workout_program,
    get_fee_payments_by_month, get_fee_payment_by_member_month, create_fee_payment, mark_fee_as_paid, mark_fee_as_unpaid, extend_member_expiry, get_db_connection
)
from config import Config

def split_phone(phone):
    """010-XXXX-XXXX 형식에서 중간·끝 4자리 분리"""
    if not phone:
        return '', ''
    digits = ''.join(c for c in str(phone) if c.isdigit())
    if len(digits) >= 11 and digits.startswith('010'):
        return digits[3:7], digits[7:11]
    if len(digits) == 8:
        return digits[:4], digits[4:]
    if '-' in str(phone):
        parts = str(phone).split('-')
        if len(parts) >= 3:
            return parts[1][-4:], parts[2][:4]
    return '', ''

def combine_phone_parts(middle, last):
    """중간·끝 4자리를 010-XXXX-XXXX 형식으로 조합"""
    middle = (middle or '').strip()
    last = (last or '').strip()
    if not middle and not last:
        return None
    if len(middle) == 4 and len(last) == 4 and middle.isdigit() and last.isdigit():
        return f'010-{middle}-{last}'
    return None

def get_phone_from_form(form, prefix, required=False):
    phone = combine_phone_parts(form.get(f'{prefix}_middle'), form.get(f'{prefix}_last'))
    if phone:
        return phone
    legacy = (form.get(prefix) or '').strip()
    if legacy:
        return legacy
    return None if not required else ''

app = Flask(__name__)
app.config.from_object(Config)

BRANCHES = ['태평동', '복수동']

# 초기화
init_database()

@app.route('/health/db')
def database_health():
    try:
        status = get_database_status()
        return jsonify({'success': True, **status})
    except Exception as error:
        return jsonify({'success': False, 'error': str(error)}), 500

def get_calendar_data(year, month, exclude_weekend=False):
    """달력 데이터를 생성하되, exclude_weekend가 True이면 주말 열을 제외"""
    first_day_of_week = calendar.monthrange(year, month)[0]
    days_in_month = calendar.monthrange(year, month)[1]
    
    calendar_weeks = []
    current_week = [None] * first_day_of_week
    
    for day in range(1, days_in_month + 1):
        current_week.append(day)
        if len(current_week) == 7:
            if exclude_weekend:
                # 0:월, 1:화, 2:수, 3:목, 4:금, 5:토, 6:일 구조에서 주말(인덱스 5, 6) 제거
                calendar_weeks.append(current_week[0:5])
            else:
                calendar_weeks.append(current_week)
            current_week = []
    
    if current_week:
        current_week += [None] * (7 - len(current_week))
        if exclude_weekend:
            calendar_weeks.append(current_week[0:5])
        else:
            calendar_weeks.append(current_week)
    
    return calendar_weeks

@app.route('/')
def index():
    branch = request.args.get('branch', 'all')
    branch_filter = branch if branch in BRANCHES else None
    update_expired_members()
    stats = {
        'total_members': get_member_count(branch_filter),
        'today_attendance': get_today_attendance_count(branch_filter),
        'absent_3days': get_absent_members_count(3, branch_filter),
        'absent_5days': get_absent_members_count(5, branch_filter),
        'absent_7days': get_absent_members_count(7, branch_filter),
        'expiring_soon': get_overdue_members_count(branch=branch_filter),  # 5일 기준 자동 집계
        'expired_members': get_expired_members_count(branch_filter)  # 만료된 관원 수
    }
    
    # 미출석 명단 내역 데이터 확보 완료!
    absent_members = get_absent_members(3, branch_filter)
    
    # 만료된 관원 목록
    expired_members_list = get_expired_members(branch_filter)
    
    # 오늘 예정된 스케줄
    today_date = datetime.now().strftime('%Y-%m-%d')
    today_schedules = get_schedules_by_date(today_date)
    
    return render_template('index.html',
                           stats=stats,
                           absent_members=absent_members,
                           expired_members=expired_members_list,
                           today_schedules=today_schedules,
                           current_branch=branch_filter or 'all',
                           branches=BRANCHES)

@app.route('/members')
def members():
    status = request.args.get('status', 'active')
    search_query = request.args.get('search', '').strip() or None
    branch = request.args.get('branch', 'all')
    branch_filter = branch if branch in BRANCHES else None
    
    if status in ['active', 'suspended', 'inactive']:
        all_members = get_members_by_status(status, search_query, branch_filter)
    else:
        all_members = get_all_members(search_query, branch_filter)
    
    today_date = datetime.now().strftime('%Y-%m-%d')
    return render_template('members.html', 
                           members=all_members,
                           member_count=len(all_members),
                           today_date=today_date,
                           current_status=status,
                           search_query=search_query or '',
                           current_branch=branch_filter or 'all',
                           branches=BRANCHES)

@app.route('/members/add', methods=['GET', 'POST'])
def add_member_page():
    if request.method == 'POST':
        name = request.form.get('name')
        phone = get_phone_from_form(request.form, 'phone', required=True)
        parent_phone = get_phone_from_form(request.form, 'parent_phone')
        birth_date = request.form.get('birth_date')
        gender = request.form.get('gender')
        branch = request.form.get('branch') if request.form.get('branch') in BRANCHES else '태평동'
        membership_type = int(request.form.get('membership_type', 1))
        membership_start_date = request.form.get('membership_start_date')
        memo = request.form.get('memo')
        status = request.form.get('status', 'active')
        monthly_fee = int(request.form.get('monthly_fee', 0)) if request.form.get('monthly_fee') else 0
        registration_source = request.form.get('registration_source')
        exercise_purpose = request.form.get('exercise_purpose')
        
        # 기타 직접 입력 처리
        if registration_source == '기타':
            registration_source = request.form.get('registration_source_other')
        if exercise_purpose == '기타':
            exercise_purpose = request.form.get('exercise_purpose_other')
        
        add_member(name, phone, birth_date, gender, membership_type, memo, status, membership_start_date, parent_phone, branch, monthly_fee, registration_source, exercise_purpose)
        return redirect(url_for('members', branch=branch))
    
    return render_template('add_member.html', branches=BRANCHES)

@app.route('/members/<int:member_id>')
def member_detail(member_id):
    member = get_member_by_id(member_id)
    if not member:
        return redirect(url_for('members'))
        
    attendance_records = get_attendance_records(member_id)
    today_date = datetime.now().strftime('%Y-%m-%d')
    
    # 출석 횟수에 맞는 운동 프로그램 조회
    attendance_count = member['total_attendance'] if member['total_attendance'] else 0
    workout_program = get_workout_program_by_attendance(attendance_count)
    
    return render_template('member_detail.html', 
                           member=member, 
                           attendance_records=attendance_records,
                           today_date=today_date,
                           workout_program=workout_program,
                           attendance_count=attendance_count)

@app.route('/members/<int:member_id>/edit', methods=['GET', 'POST'])
def edit_member(member_id):
    member = get_member_by_id(member_id)
    if not member:
        return redirect(url_for('members'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        phone = get_phone_from_form(request.form, 'phone', required=True)
        parent_phone = get_phone_from_form(request.form, 'parent_phone')
        birth_date = request.form.get('birth_date')
        gender = request.form.get('gender')
        branch = request.form.get('branch') if request.form.get('branch') in BRANCHES else (member['branch'] or '태평동')
        memo = request.form.get('memo')
        status = request.form.get('status') or member['status']
        
        membership_type_raw = request.form.get('membership_type')
        if membership_type_raw is not None and membership_type_raw.strip() != '':
            membership_type = int(membership_type_raw)
        else:
            membership_type = int(member['membership_type'])
            
        membership_start_date = request.form.get('membership_start_date')
        if not membership_start_date or membership_start_date.strip() == '':
            membership_start_date = member['membership_start_date']
            if not membership_start_date:
                membership_start_date = datetime.now().strftime('%Y-%m-%d')
        
        # 일시정지 기간 처리
        suspension_start_date = request.form.get('suspension_start_date') or None
        suspension_end_date = request.form.get('suspension_end_date') or None
        
        # status가 'suspended'가 아니면 일시정지 날짜 초기화
        if status != 'suspended':
            suspension_start_date = None
            suspension_end_date = None
        
        monthly_fee = int(request.form.get('monthly_fee', 0)) if request.form.get('monthly_fee') else 0
        registration_source = request.form.get('registration_source')
        exercise_purpose = request.form.get('exercise_purpose')
        
        # 기타 직접 입력 처리
        if registration_source == '기타':
            registration_source = request.form.get('registration_source_other')
        if exercise_purpose == '기타':
            exercise_purpose = request.form.get('exercise_purpose_other')
        
        update_member(member_id, name, phone, birth_date, gender, membership_type, membership_start_date, memo, status, parent_phone, branch, suspension_start_date, suspension_end_date, monthly_fee, registration_source, exercise_purpose)
        return redirect(url_for('member_detail', member_id=member_id))
    
    phone_middle, phone_last = split_phone(member['phone'])
    parent_middle, parent_last = split_phone(member['parent_phone'])
    return render_template('edit_member.html', member=member,
                           phone_middle=phone_middle, phone_last=phone_last,
                           parent_middle=parent_middle, parent_last=parent_last)

@app.route('/members/<int:member_id>/delete', methods=['POST'])
def delete_member_page(member_id):
    delete_member(member_id)
    return redirect(url_for('members'))

@app.route('/attendance')
def attendance():
    """출석 타임라인 테이블 뷰 (주말 토, 일 완벽 제거)"""
    branch = request.args.get('branch', 'all')
    branch_filter = branch if branch in BRANCHES else None
    today = datetime.now().date()
    weekday_names = ['월', '화', '수', '목', '금', '토', '일']

    year, month = today.year, today.month
    first_day = datetime(year, month, 1).date()
    last_day = datetime(year + 1, 1, 1).date() - timedelta(days=1) if month == 12 else datetime(year, month + 1, 1).date() - timedelta(days=1)
    
    day_labels = []
    current_day = first_day
    while current_day <= last_day:
        if current_day.weekday() in (5, 6):
            current_day += timedelta(days=1)
            continue
            
        day_labels.append({
            'date': current_day.strftime('%Y-%m-%d'),
            'label': current_day.strftime('%m/%d'),
            'weekday': weekday_names[current_day.weekday()],
            'is_today': current_day == today
        })
        current_day += timedelta(days=1)

    if day_labels:
        start_date = day_labels[0]['date']
        end_date = day_labels[-1]['date']
    else:
        start_date = first_day.strftime('%Y-%m-%d')
        end_date = last_day.strftime('%Y-%m-%d')
        
    members_list = get_members_by_status('active', branch=branch_filter)
    attendance_map = get_attendance_map_for_range(start_date, end_date)

    absent_flags = {}
    for member in members_list:
        last_attendance = member['last_attendance']
        if last_attendance:
            last_date = datetime.strptime(last_attendance, '%Y-%m-%d').date()
            days_since = (today - last_date).days
        else:
            days_since = 999
        absent_flags[member['id']] = days_since

    return render_template('attendance.html',
                           members=members_list,
                           member_count=len(members_list),
                           day_labels=day_labels,
                           attendance_map=attendance_map,
                           absent_flags=absent_flags,
                           today_date=today.strftime('%Y-%m-%d'),
                           current_branch=branch_filter or 'all',
                           branches=BRANCHES)

@app.route('/attendance/today')
def today_attendance():
    today = datetime.now().strftime('%Y-%m-%d')
    return render_template('today_attendance.html', members=get_day_attendance_members(today), today_date=today)

@app.route('/attendance/add/<int:member_id>', methods=['POST'])
def add_attendance_api(member_id):
    member = get_member_by_id(member_id)
    if member:
        result = toggle_attendance(member_id)
        return jsonify({'success': True, 'status': result['status'], 'message': f'{member["name"]} - {result["message"]}'})
    return jsonify({'success': False, 'message': '회원을 찾을 수 없습니다.'}), 404

@app.route('/attendance/clear', methods=['POST'])
def clear_attendance():
    deleted_count = clear_today_attendance()
    return jsonify({'success': True, 'message': f'오늘의 출석 기록 {deleted_count}명이 일괄 초기화되었습니다.'})

@app.route('/attendance/toggle/<int:member_id>/<date_str>', methods=['POST'])
def toggle_attendance_by_date_api(member_id, date_str):
    member = get_member_by_id(member_id)
    if member:
        result = toggle_attendance_by_date(member_id, date_str)
        return jsonify({'success': True, 'status': result['status'], 'message': f'{member["name"]} ({date_str}) - {result["message"]}'})
    return jsonify({'success': False, 'message': '회원을 찾을 수 없습니다.'}), 404

@app.route('/attendance/calendar')
def attendance_calendar():
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    
    attendance_by_date = get_all_attendance_by_month(year, month)
    attendance_dict = {}
    for record in attendance_by_date:
        date = record['attendance_date']
        attendance_dict[date] = record['count']
    
    return render_template('attendance_calendar.html', 
                           year=year, month=month,
                           calendar_weeks=get_calendar_data(year, month, exclude_weekend=True),
                           attendance_dict=attendance_dict)

@app.route('/attendance/calendar/<int:member_id>')
def member_attendance_calendar(member_id):
    member = get_member_by_id(member_id)
    if not member:
        return redirect(url_for('members'))
    
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    attendance_set = set(get_member_attendance_by_month(member_id, year, month))
    
    return render_template('member_attendance_calendar.html',
                           member=member, year=year, month=month,
                           calendar_weeks=get_calendar_data(year, month, exclude_weekend=True),
                           attendance_set=attendance_set)

@app.route('/reports')
def reports():
    active_tab = request.args.get('tab', 'expiring')
    if active_tab not in {'expiring', 'absent3', 'absent5', 'absent7'}:
        active_tab = 'expiring'
    
    return render_template('reports.html',
                           absent_3days=get_absent_members(3),
                           absent_5days=get_absent_members(5),
                           absent_7days=get_absent_members(7),
                           expiring=get_expiring_members(),
                           active_tab=active_tab)

# ============= 스케줄 관리 =============

@app.route('/schedule')
def schedule():
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    
    schedules = get_schedules_by_month(year, month)
    schedule_dict = {}
    for s in schedules:
        date = s['schedule_date']
        if date not in schedule_dict:
            schedule_dict[date] = []
        schedule_dict[date].append(s)
    
    return render_template('schedule.html',
                           year=year, month=month,
                           calendar_weeks=get_calendar_data(year, month),
                           schedule_dict=schedule_dict,
                           schedules=schedules)

@app.route('/schedule/add', methods=['GET', 'POST'])
def add_schedule_page():
    if request.method == 'POST':
        add_schedule(
            request.form.get('title'),
            request.form.get('description'),
            request.form.get('schedule_date'),
            request.form.get('start_time'),
            request.form.get('end_time'),
            request.form.get('category', 'general')
        )
        return redirect(url_for('schedule'))
    return render_template('add_schedule.html')

@app.route('/schedule/<int:schedule_id>/edit', methods=['GET', 'POST'])
def edit_schedule_page(schedule_id):
    schedule_item = get_schedule_by_id(schedule_id)
    if not schedule_item:
        return redirect(url_for('schedule'))
    
    if request.method == 'POST':
        update_schedule(
            schedule_id,
            request.form.get('title'),
            request.form.get('description'),
            request.form.get('schedule_date'),
            request.form.get('start_time'),
            request.form.get('end_time'),
            request.form.get('category', 'general')
        )
        return redirect(url_for('schedule'))
    return render_template('edit_schedule.html', schedule=schedule_item)

@app.route('/schedule/<int:schedule_id>/delete', methods=['POST'])
def delete_schedule_page(schedule_id):
    delete_schedule(schedule_id)
    return redirect(url_for('schedule'))

# ============= 운동 프로그램 관리 =============

@app.route('/workout_programs')
def workout_programs():
    programs = get_all_workout_programs()
    return render_template('workout_programs.html', programs=programs)

@app.route('/workout_programs/add', methods=['GET', 'POST'])
def add_workout_program_page():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        min_attendance = int(request.form.get('min_attendance', 0))
        max_attendance = request.form.get('max_attendance')
        max_attendance = int(max_attendance) if max_attendance else None
        
        add_workout_program(name, description, min_attendance, max_attendance)
        return redirect(url_for('workout_programs'))
    
    return render_template('add_workout_program.html')

@app.route('/workout_programs/<int:program_id>/edit', methods=['GET', 'POST'])
def edit_workout_program_page(program_id):
    program = get_workout_program_by_id(program_id)
    if not program:
        return redirect(url_for('workout_programs'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        min_attendance = int(request.form.get('min_attendance', 0))
        max_attendance = request.form.get('max_attendance')
        max_attendance = int(max_attendance) if max_attendance else None
        
        update_workout_program(program_id, name, description, min_attendance, max_attendance)
        return redirect(url_for('workout_programs'))
    
    return render_template('edit_workout_program.html', program=program)

@app.route('/workout_programs/<int:program_id>/delete', methods=['POST'])
def delete_workout_program_page(program_id):
    delete_workout_program(program_id)
    return redirect(url_for('workout_programs'))

# ============= 관비 납부 관리 =============

@app.route('/fee_management')
def fee_management():
    year = int(request.args.get('year', datetime.now().year))
    month = int(request.args.get('month', datetime.now().month))
    branch = request.args.get('branch', 'all')
    status = request.args.get('status', 'all')
    
    branch_filter = branch if branch in BRANCHES else None
    status_filter = status if status in ['paid', 'unpaid'] else None
    
    members = get_fee_payments_by_month(year, month, status_filter, branch_filter)
    
    # 통계 계산
    total_count = len(members)
    paid_count = len([m for m in members if m['payment_status'] == 'paid'])
    unpaid_count = len([m for m in members if m['payment_status'] != 'paid'])
    
    return render_template('fee_management.html',
                           members=members,
                           current_year=year,
                           current_month=month,
                           current_branch=branch,
                           current_status=status,
                           branches=BRANCHES,
                           total_count=total_count,
                           paid_count=paid_count,
                           unpaid_count=unpaid_count)

@app.route('/fee_management/generate')
def generate_fee_payments():
    year = int(request.args.get('year', datetime.now().year))
    month = int(request.args.get('month', datetime.now().month))
    
    # 모든 활성 회원에 대해 납부 대상 생성
    active_members = get_members_by_status('active', None, None)
    for member in active_members:
        amount = member.get('monthly_fee', 0) or 0
        if amount > 0:
            create_fee_payment(member['id'], year, month, amount)
    
    return redirect(url_for('fee_management', year=year, month=month))

@app.route('/fee_management/<int:member_id>/paid', methods=['POST'])
def mark_fee_paid(member_id):
    year = int(request.form.get('year', datetime.now().year))
    month = int(request.form.get('month', datetime.now().month))
    extend_months = int(request.form.get('extend_months', 3))
    payment_amount = int(request.form.get('payment_amount', 0)) if request.form.get('payment_amount') else 0
    
    # 납부 레코드 확인 및 생성
    payment = get_fee_payment_by_member_month(member_id, year, month)
    if not payment:
        member = get_member_by_id(member_id)
        amount = payment_amount if payment_amount > 0 else (member.get('monthly_fee', 0) or 0)
        payment_id = create_fee_payment(member_id, year, month, amount)
    else:
        payment_id = payment['id']
    
    # 결제 금액 업데이트 (입력된 금액이 있으면 해당 금액으로)
    if payment_id:
        if payment_amount > 0:
            mark_fee_as_paid(payment_id, amount=payment_amount)
        else:
            mark_fee_as_paid(payment_id)
        
        # 회원의 monthly_fee 업데이트 (입력된 금액이 있으면 해당 금액으로)
        if payment_amount > 0:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('UPDATE members SET monthly_fee = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', 
                         (payment_amount, member_id))
            conn.commit()
            conn.close()
        
        # 회원권 만료일 연장 (결제 날짜 기준)
        payment_date = datetime.now().strftime('%Y-%m-%d')
        extend_member_expiry(member_id, extend_months, payment_date)
    
    branch = request.form.get('branch', 'all')
    status = request.form.get('status', 'all')
    return redirect(url_for('fee_management', year=year, month=month, branch=branch, status=status))

@app.route('/fee_management/<int:member_id>/unpaid', methods=['POST'])
def mark_fee_unpaid(member_id):
    year = int(request.form.get('year', datetime.now().year))
    month = int(request.form.get('month', datetime.now().month))
    
    # 납부 레코드 확인
    payment = get_fee_payment_by_member_month(member_id, year, month)
    if payment:
        mark_fee_as_unpaid(payment['id'])
    
    branch = request.form.get('branch', 'all')
    status = request.form.get('status', 'all')
    return redirect(url_for('fee_management', year=year, month=month, branch=branch, status=status))

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 1926))
    debug = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'
    app.run(debug=debug, host='0.0.0.0', port=port)

