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
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', 'hangfudao123')
MYSQL_DB = os.environ.get('MYSQL_DB', 'hangfudao')
MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3307))

_db_config = {}

def adjust_time(dt_obj):
    if isinstance(dt_obj, datetime):
        return dt_obj + timedelta(hours=8)
    return dt_obj

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
        SELECT s.id, s.student_id, s.name, s.class_name, s.created_at,
               COUNT(DISTINCT ar.id) as answer_count,
               SUM(CASE WHEN ar.is_correct = 1 THEN 1 ELSE 0 END) as correct_count
        FROM students s
        LEFT JOIN answer_records ar ON s.id = ar.student_db_id
        GROUP BY s.id, s.student_id, s.name, s.class_name, s.created_at
        ORDER BY answer_count DESC
    """)
    for r in rows:
        r['created_at'] = str(adjust_time(r['created_at']))
    return rows

def list_records(student_id=None, correct_only=False, wrong_only=False, limit=50):
    sql = """
        SELECT 
            ar.id as record_id,
            ar.session_id,
            ar.topic,
            ar.difficulty,
            ar.is_correct,
            ar.language,
            ar.created_at,
            st.student_id,
            st.name as student_name,
            st.class_name
        FROM answer_records ar
        LEFT JOIN students st ON ar.student_db_id = st.id
        WHERE 1=1
    """
    params = []
    if student_id:
        sql += " AND st.student_id = %s"
        params.append(student_id)
    if correct_only:
        sql += " AND ar.is_correct = 1"
    if wrong_only:
        sql += " AND ar.is_correct = 0"
    sql += " ORDER BY ar.created_at DESC LIMIT %s"
    params.append(limit)
    rows = run_query(sql, params)
    for r in rows:
        r['created_at'] = str(adjust_time(r['created_at']))
    return rows

def get_record_detail(record_id):
    rows = run_query("""
        SELECT 
            ar.*,
            st.student_id,
            st.name as student_name,
            st.class_name
        FROM answer_records ar
        LEFT JOIN students st ON ar.student_db_id = st.id
        WHERE ar.id = %s
    """, (record_id,))
    for r in rows:
        for dt_key in ('created_at',):
            if r.get(dt_key):
                r[dt_key] = str(adjust_time(r[dt_key]))
    return rows

def get_mastery(student_id=None):
    if student_id:
        sql = """
            SELECT km.*, st.student_id, st.name as student_name, st.class_name
            FROM knowledge_mastery km
            LEFT JOIN students st ON km.student_db_id = st.id
            WHERE st.student_id = %s
            ORDER BY km.topic
        """
        rows = run_query(sql, (student_id,))
    else:
        sql = """
            SELECT km.*, st.student_id, st.name as student_name, st.class_name
            FROM knowledge_mastery km
            LEFT JOIN students st ON km.student_db_id = st.id
            ORDER BY km.topic
        """
        rows = run_query(sql)
    for r in rows:
        total = r.get('total_count') or 0
        correct = r.get('correct_count') or 0
        r['accuracy'] = round(correct / total * 100, 1) if total > 0 else 0
        for dt_key in ('created_at', 'updated_at'):
            if r.get(dt_key):
                r[dt_key] = str(adjust_time(r[dt_key]))
    return rows

def get_stats():
    rows = run_query("""
        SELECT 
            COUNT(DISTINCT st.student_id) as total_students,
            COUNT(ar.id) as total_records,
            SUM(CASE WHEN ar.is_correct = 1 THEN 1 ELSE 0 END) as correct_records,
            COUNT(DISTINCT ar.topic) as total_topics,
            COUNT(DISTINCT ar.session_id) as total_sessions
        FROM answer_records ar
        LEFT JOIN students st ON ar.student_db_id = st.id
    """)
    if rows:
        r = rows[0]
        r['accuracy'] = round(r['correct_records'] / r['total_records'] * 100, 1) if r['total_records'] > 0 else 0
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
    parser = argparse.ArgumentParser(description='Programate SQL Interface (hangfudao DB)')
    parser.add_argument('--host', default=MYSQL_HOST, help='MySQL host')
    parser.add_argument('--port', type=int, default=MYSQL_PORT, help='MySQL port')
    parser.add_argument('--user', default=MYSQL_USER, help='MySQL user')
    parser.add_argument('--password', default=MYSQL_PASSWORD, help='MySQL password')
    parser.add_argument('--db', default=MYSQL_DB, help='Database name')

    sub = parser.add_subparsers(dest='command')

    p_stats = sub.add_parser('stats', help='Overall statistics')

    p_students = sub.add_parser('students', help='List all students')
    p_students.add_argument('--csv', help='Export to CSV file')
    p_students.add_argument('--json', action='store_true', help='Output as JSON')

    p_records = sub.add_parser('records', help='List answer records')
    p_records.add_argument('--student', help='Filter by student_id')
    p_records.add_argument('--correct', action='store_true', help='Only correct answers')
    p_records.add_argument('--wrong', action='store_true', help='Only wrong answers')
    p_records.add_argument('--limit', type=int, default=50, help='Max records (default: 50)')
    p_records.add_argument('--csv', help='Export to CSV file')
    p_records.add_argument('--json', action='store_true', help='Output as JSON')

    p_detail = sub.add_parser('detail', help='Get full detail of a record')
    p_detail.add_argument('record_id', type=int, help='Record ID')
    p_detail.add_argument('--json', action='store_true', help='Output as JSON')

    p_mastery = sub.add_parser('mastery', help='Knowledge mastery')
    p_mastery.add_argument('--student', help='Filter by student_id')
    p_mastery.add_argument('--csv', help='Export to CSV file')
    p_mastery.add_argument('--json', action='store_true', help='Output as JSON')

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

    if args.command == 'stats':
        rows = get_stats()
        print_table(rows)

    elif args.command == 'students':
        rows = list_students()
        if getattr(args, 'json', False):
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        elif args.csv:
            export_csv(rows, args.csv)
        else:
            print_table(rows)

    elif args.command == 'records':
        rows = list_records(
            student_id=args.student,
            correct_only=args.correct,
            wrong_only=args.wrong,
            limit=args.limit
        )
        if getattr(args, 'json', False):
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        elif args.csv:
            export_csv(rows, args.csv)
        else:
            print_table(rows)

    elif args.command == 'detail':
        rows = get_record_detail(args.record_id)
        if getattr(args, 'json', False):
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        elif rows:
            for r in rows:
                for k, v in r.items():
                    print(f"{k}: {v}")
        else:
            print(f"Record {args.record_id} not found.")

    elif args.command == 'mastery':
        rows = get_mastery(student_id=args.student)
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
