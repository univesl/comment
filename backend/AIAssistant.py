import pymysql
import pymysql.cursors
import os
import argparse
import json
import csv
import sys
from datetime import datetime, timedelta
from tabulate import tabulate

MYSQL_HOST = os.environ.get('MYSQL_HOST', '10.132.24.115')
MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', 'root')
MYSQL_DB = os.environ.get('MYSQL_DB', 'ai_assistant')
MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3308))

def adjust_time(dt_obj):
    if isinstance(dt_obj, datetime):
        return dt_obj + timedelta(hours=8)
    return dt_obj

_db_config = {}

def get_connection():
    host = _db_config.get('host', MYSQL_HOST)
    port = _db_config.get('port', MYSQL_PORT)
    user = _db_config.get('user', MYSQL_USER)
    password = _db_config.get('password', MYSQL_PASSWORD)
    db = _db_config.get('db', MYSQL_DB)
    return pymysql.connect(
        host=host,
        user=user,
        password=password,
        database=db,
        port=port,
        cursorclass=pymysql.cursors.DictCursor
    )

def run_query(sql, params=None):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params or ())
            rows = cursor.fetchall()
            return rows
    finally:
        conn.close()

def list_students():
    rows = run_query("""
        SELECT s.student_id, s.name, s.class_name, s.created_at,
               COUNT(DISTINCT ss.id) as session_count,
               COUNT(m.id) as message_count
        FROM students s
        LEFT JOIN sessions ss ON s.student_id = ss.student_id AND ss.is_deleted = 0
        LEFT JOIN messages m ON ss.id = m.session_id
        GROUP BY s.student_id, s.name, s.class_name, s.created_at
        ORDER BY session_count DESC
    """)
    for r in rows:
        r['created_at'] = str(adjust_time(r['created_at']))
    return rows

def list_sessions(student_id=None, include_deleted=False):
    if student_id:
        sql = """
            SELECT s.id, s.name, s.student_id, s.created_at, s.is_deleted,
                   st.name as student_name, st.class_name,
                   COUNT(m.id) as message_count
            FROM sessions s
            LEFT JOIN students st ON s.student_id = st.student_id
            LEFT JOIN messages m ON s.id = m.session_id
            WHERE s.student_id = %s
        """
        params = [student_id]
    else:
        sql = """
            SELECT s.id, s.name, s.student_id, s.created_at, s.is_deleted,
                   st.name as student_name, st.class_name,
                   COUNT(m.id) as message_count
            FROM sessions s
            LEFT JOIN students st ON s.student_id = st.student_id
            LEFT JOIN messages m ON s.id = m.session_id
            WHERE 1=1
        """
        params = []
    if not include_deleted:
        sql += " AND s.is_deleted = 0"
    sql += " GROUP BY s.id ORDER BY s.created_at DESC"
    rows = run_query(sql, params)
    for r in rows:
        r['created_at'] = str(adjust_time(r['created_at']))
    return rows

def get_messages(session_id):
    rows = run_query("""
        SELECT m.id, m.session_id, m.role, m.content, m.created_at
        FROM messages m
        WHERE m.session_id = %s
        ORDER BY m.created_at ASC
    """, (session_id,))
    for r in rows:
        r['created_at'] = str(adjust_time(r['created_at']))
    return rows

def get_knowledge_progress(student_id=None):
    if student_id:
        sql = """
            SELECT skp.*, s.name as student_name, kp.name as knowledge_name
            FROM student_knowledge_progress skp
            LEFT JOIN students s ON skp.student_id = s.student_id
            LEFT JOIN knowledge_points kp ON skp.knowledge_point_id = kp.id
            WHERE skp.student_id = %s
            ORDER BY skp.updated_at DESC
        """
        rows = run_query(sql, (student_id,))
    else:
        sql = """
            SELECT skp.*, s.name as student_name, kp.name as knowledge_name
            FROM student_knowledge_progress skp
            LEFT JOIN students s ON skp.student_id = s.student_id
            LEFT JOIN knowledge_points kp ON skp.knowledge_point_id = kp.id
            ORDER BY skp.updated_at DESC
        """
        rows = run_query(sql)
    for r in rows:
        for dt_key in ('created_at', 'updated_at'):
            if r.get(dt_key):
                r[dt_key] = str(adjust_time(r[dt_key]))
    return rows

def export_csv(rows, output_file):
    if not rows:
        print("No data to export.")
        return
    fieldnames = list(rows[0].keys())
    with open(output_file, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Exported {len(rows)} rows to {output_file}")

def print_table(rows):
    if not rows:
        print("No results found.")
        return
    truncated = []
    for row in rows:
        t = {}
        for k, v in row.items():
            s = str(v) if v is not None else ''
            if len(s) > 80:
                s = s[:77] + '...'
            t[k] = s
        truncated.append(t)
    print(tabulate(truncated, headers="keys", tablefmt="grid"))

def main():
    parser = argparse.ArgumentParser(description='AI Assistant SQL Interface')
    parser.add_argument('--host', default=MYSQL_HOST, help='MySQL host')
    parser.add_argument('--port', type=int, default=MYSQL_PORT, help='MySQL port')
    parser.add_argument('--user', default=MYSQL_USER, help='MySQL user')
    parser.add_argument('--password', default=MYSQL_PASSWORD, help='MySQL password')
    parser.add_argument('--db', default=MYSQL_DB, help='Database name')

    sub = parser.add_subparsers(dest='command')

    p_students = sub.add_parser('students', help='List all students')
    p_students.add_argument('--csv', help='Export to CSV file')
    p_students.add_argument('--json', action='store_true', help='Output as JSON')

    p_sessions = sub.add_parser('sessions', help='List sessions')
    p_sessions.add_argument('--student', help='Filter by student_id')
    p_sessions.add_argument('--all', action='store_true', help='Include deleted sessions')
    p_sessions.add_argument('--csv', help='Export to CSV file')
    p_sessions.add_argument('--json', action='store_true', help='Output as JSON')

    p_messages = sub.add_parser('messages', help='Get messages of a session')
    p_messages.add_argument('session_id', help='Session ID')
    p_messages.add_argument('--csv', help='Export to CSV file')
    p_messages.add_argument('--json', action='store_true', help='Output as JSON')

    p_kp = sub.add_parser('progress', help='Knowledge progress')
    p_kp.add_argument('--student', help='Filter by student_id')
    p_kp.add_argument('--csv', help='Export to CSV file')
    p_kp.add_argument('--json', action='store_true', help='Output as JSON')

    p_sql = sub.add_parser('sql', help='Execute raw SQL (SELECT only)')
    p_sql.add_argument('query', help='SQL query')
    p_sql.add_argument('--csv', help='Export to CSV file')
    p_sql.add_argument('--json', action='store_true', help='Output as JSON')

    args = parser.parse_args()

    _db_config['host'] = args.host
    _db_config['port'] = args.port
    _db_config['user'] = args.user
    _db_config['password'] = args.password
    _db_config['db'] = args.db

    if args.command == 'students':
        rows = list_students()
        if getattr(args, 'json', False):
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        elif args.csv:
            export_csv(rows, args.csv)
        else:
            print_table(rows)

    elif args.command == 'sessions':
        rows = list_sessions(student_id=args.student, include_deleted=args.all)
        if getattr(args, 'json', False):
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        elif args.csv:
            export_csv(rows, args.csv)
        else:
            print_table(rows)

    elif args.command == 'messages':
        rows = get_messages(args.session_id)
        if getattr(args, 'json', False):
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        elif args.csv:
            export_csv(rows, args.csv)
        else:
            print_table(rows)

    elif args.command == 'progress':
        rows = get_knowledge_progress(student_id=args.student)
        if getattr(args, 'json', False):
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        elif args.csv:
            export_csv(rows, args.csv)
        else:
            print_table(rows)

    elif args.command == 'sql':
        stripped = args.query.strip().upper()
        if not stripped.startswith('SELECT') and not stripped.startswith('SHOW') and not stripped.startswith('DESCRIBE'):
            print("ERROR: Only SELECT/SHOW/DESCRIBE queries are allowed.")
            sys.exit(1)
        rows = run_query(args.query)
        if getattr(args, 'json', False):
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        elif args.csv:
            export_csv(rows, args.csv)
        else:
            print_table(rows)

    else:
        parser.print_help()

if __name__ == '__main__':
    main()
