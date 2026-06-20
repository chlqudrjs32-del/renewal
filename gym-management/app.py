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
    add_schedule, update_schedule, delete_schedule, get_database_status
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
        'expiring_soon': get_overdue_members_count(branch=branch_filter)  # 5일 기준 자동 집계
    }
    
    # 미출석 명단 내역 데이터 확보 완료!
    absent_members = get_absent_members(3, branch_filter)
    
    return render_template('index.html',
                           stats=stats,
                           absent_members=absent_members,
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
        
        add_member(name, phone, birth_date, gender, membership_type, memo, status, membership_start_date, parent_phone, branch)
        return redirect(url_for('members', branch=branch))
    
    return render_template('add_member.html', branches=BRANCHES)

@app.route('/members/<int:member_id>')
def member_detail(member_id):
    member = get_member_by_id(member_id)
    if not member:
        return redirect(url_for('members'))
        
    attendance_records = get_attendance_records(member_id)
    today_date = datetime.now().strftime('%Y-%m-%d')
    return render_template('member_detail.html', 
                           member=member, 
                           attendance_records=attendance_records,
                           today_date=today_date)

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
        
        update_member(member_id, name, phone, birth_date, gender, membership_type, membership_start_date, memo, status, parent_phone, branch)
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

