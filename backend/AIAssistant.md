# 查看所有学生（含会话数、消息数统计）
python AIAssistant.py students

# 查看所有会话
python AIAssistant.py sessions

# 查看某学生的会话
python AIAssistant.py sessions --student 25371041

# 查看某会话的消息
python AIAssistant.py messages <session_id>

# 查看知识点学习进度
python AIAssistant.py progress

# 自定义 SQL 查询（仅允许 SELECT）
python AIAssistant.py sql "SELECT COUNT(*) FROM sessions WHERE is_deleted=0"

# 导出为 CSV
python AIAssistant.py students --csv students.csv

# 导出为 JSON
python AIAssistant.py students --json

# 指定远程数据库连接
python AIAssistant.py --host 10.132.24.115 --port 3308 --user root --password root students