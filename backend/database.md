# 数据库项目文档

## 项目概述

这是一个教育数据查询工具集，包含两个独立的数据库系统和相应的查询工具：

1. **hangfudao**（航服道）：编程题目练习系统，记录学生答题情况和知识点掌握程度
2. **ai_assistant**（AI助手）：智能问答系统，记录学生与AI的对话会话和学习进度

---

## 一、数据库结构

### 数据库 1：`hangfudao`（编程练习系统，端口 3307）

**连接信息**：
- 主机：10.132.24.115
- 端口：3307
- 用户：root
- 密码：hangfudao123

| 表名 | 行数 | 说明 |
|------|------|------|
| `students` | 695 | 学生信息表 |
| `answer_records` | 1365 | 学生答题记录 |
| `knowledge_mastery` | 228 | 知识点掌握情况 |

#### students（学生信息表）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | int PK AUTO_INCREMENT | 内部自增主键 |
| student_id | varchar(50) UNIQUE | 学号（如 `25371432`、`anonymous`） |
| name | varchar(100) | 学生姓名 |
| class_name | varchar(100) | 班级名称 |
| created_at | datetime | 注册时间 |

#### answer_records（答题记录表）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | int PK AUTO_INCREMENT | 记录ID |
| student_db_id | int FK→students.id | 关联学生（注意：关联的是students.id而非student_id） |
| session_id | varchar(64) | 会话ID |
| topic | varchar(50) | 知识点/作业主题 |
| difficulty | varchar(10) | 难度（简单/中等/困难） |
| problem_text | text | 题目内容 |
| submitted_code | text | 学生提交的代码 |
| diagnosis_result | text | 诊断结果 |
| is_correct | tinyint(1) | 是否正确（1=正确，0=错误） |
| language | varchar(20) | 编程语言 |
| created_at | datetime | 提交时间 |

#### knowledge_mastery（知识点掌握表）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | int PK AUTO_INCREMENT | 主键 |
| student_db_id | int FK→students.id | 关联学生 |
| topic | varchar(50) | 知识点名称 |
| correct_count | int | 答对次数 |
| total_count | int | 总答题次数 |
| mastery_level | varchar(10) | 掌握等级 |
| updated_at | datetime | 更新时间 |

---

### 数据库 2：`ai_assistant`（AI问答助手系统，端口 3308）

**连接信息**：
- 主机：10.132.24.115
- 端口：3308
- 用户：root
- 密码：root

| 表名 | 行数 | 说明 |
|------|------|------|
| `students` | 347 | 学生信息表 |
| `sessions` | 565 | 对话会话表 |
| `messages` | 3794 | 对话消息表 |
| `knowledge_points` | 14 | 知识点列表 |
| `student_knowledge_progress` | 275 | 知识点学习进度 |

#### students（学生信息表）
| 字段 | 类型 | 说明 |
|------|------|------|
| student_id | varchar(50) PK | 学号（主键直接是学号） |
| name | varchar(100) | 学生姓名 |
| class_name | varchar(100) | 班级名称 |
| created_at | timestamp | 注册时间 |

#### sessions（对话会话表）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | varchar(255) PK | 会话ID（UUID格式） |
| student_id | varchar(50) FK | 关联学生学号 |
| name | varchar(255) | 会话名称 |
| created_at | timestamp | 创建时间 |
| is_deleted | tinyint(1) | 是否已删除（1=已删除，0=正常） |

#### messages（对话消息表）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | int PK AUTO_INCREMENT | 消息ID |
| session_id | varchar(255) FK | 关联会话ID |
| role | varchar(20) | 角色（user/assistant） |
| content | text | 消息内容 |
| created_at | timestamp | 发送时间 |

#### knowledge_points（知识点表）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | varchar(50) PK | 知识点ID（如 `array`、`tree`） |
| name | varchar(100) | 知识点名称 |
| description | text | 知识点描述 |
| is_custom | tinyint(1) | 是否自定义知识点 |
| created_by | varchar(50) FK | 创建者学号 |

#### student_knowledge_progress（知识点学习进度表）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | int PK AUTO_INCREMENT | 主键 |
| student_id | varchar(50) FK | 学生学号 |
| knowledge_point_id | varchar(50) FK | 知识点ID |
| mastery | int | 掌握程度（0-100分） |
| stage | varchar(50) | 当前学习阶段 |
| history | json | 对话历史记录 |
| created_at | timestamp | 创建时间 |
| updated_at | timestamp | 更新时间 |

---

## 二、重要说明

### 1. 学生表的主键差异

两个数据库的学生表设计有所不同：

**hangfudao.students**：
- 使用自增 `id` 作为主键
- `student_id` 是 UNIQUE 字段，存储学号
- 联表查询时使用：`LEFT JOIN students st ON ar.student_db_id = st.id`

**ai_assistant.students**：
- 直接使用 `student_id`（学号）作为主键
- 联表查询时使用：`LEFT JOIN students st ON s.student_id = st.student_id`

### 2. 学生信息补充（stus1.xlsx）

项目包含一个 `stus1.xlsx` 文件，包含约1200条完整的学生信息：
- 学号 → 姓名/班级/专业/院系的映射关系
- 用于补充和验证数据库中的学生信息
- 当数据库中姓名或班级为空时，可从此文件获取

### 3. 时区处理

数据库中的时间字段为 UTC 时间，需要 +8 小时转换为北京时间：
- Python 代码中使用 `adjust_time()` 函数处理
- SQL 查询中使用 `DATE_ADD(field, INTERVAL 8 HOUR)`

---

## 三、命令行工具使用

### 1. Hangfudao 数据库查询工具

```bash
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
```

### 2. AIAssistant 数据库查询工具

```bash
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
```

### 3. 智能查询 Agent

```bash
# 启动交互式查询Agent（支持自然语言提问）
python agent.py
```

Agent 功能：
- 支持自然语言提问（中文）
- 自动判断使用哪个数据库
- 使用大模型生成 SQL 查询
- 自动总结查询结果
- 集成 stus1.xlsx 学生信息

---

## 四、技术依赖

- **pymysql**：MySQL 数据库连接
- **openpyxl**：Excel 文件读取
- **openai**：LLM API 客户端（调用 Qwen 模型）
- **tabulate**：表格格式化输出
- **argparse**：命令行参数解析

---

## 五、安全说明

1. 所有 SQL 查询工具仅允许 SELECT 操作，禁止修改数据
2. LLM 生成的 SQL 会进行安全验证
3. 敏感信息（数据库密码）应通过环境变量配置

