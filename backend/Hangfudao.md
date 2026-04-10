# 总体统计
python Hangfudao.py stats

# 查看所有学生（含答题数、正确数）
python Hangfudao.py students

# 查看答题记录（默认最近50条）
python Hangfudao.py records

# 查看某学生的答题记录
python Hangfudao.py records --student 25371432

# 只看错误的记录
python Hangfudao.py records --wrong --limit 100

# 查看某条记录的完整详情（含题目、代码、诊断）
python Hangfudao.py detail 1234

# 查看知识点掌握情况
python Hangfudao.py mastery

# 查看某学生的掌握情况
python Hangfudao.py mastery --student 25371432

# 自定义 SQL
python Hangfudao.py sql "SELECT topic, COUNT(*) as cnt FROM answer_records GROUP BY topic"

# 导出 CSV / JSON
python Hangfudao.py records --csv records.csv
python Hangfudao.py records --json

# 指定远程连接
python Hangfudao.py --host 10.132.24.115 --port 3307 --user root --password hangfudao123 students