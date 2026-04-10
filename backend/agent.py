import pymysql
import pymysql.cursors
import os
import json
import sys
import re
from functools import lru_cache
from datetime import datetime, timedelta

from pymysql.err import OperationalError
from openai import OpenAI

API_KEY = "sk-I8oiGaYzHqcIXhjKz7D0fQ"
API_BASE = os.environ.get("PAPER_WRITING_API_BASE", "http://10.70.247.113:4000/v1")
MODEL = "Qwen/Qwen3-235B-A22B-Instruct-2507-FP8"

MYSQL_CONNECT_TIMEOUT = 10
MYSQL_READ_TIMEOUT = 120
MYSQL_WRITE_TIMEOUT = 120
MYSQL_RETRY_ERROR_CODES = {2006, 2013}


class UserFacingError(Exception):
    pass


class ClarificationNeeded(UserFacingError):
    pass


class QueryGenerationError(UserFacingError):
    pass


class QueryExecutionError(UserFacingError):
    pass

XLSX_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stus1.xlsx")
RULES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules.md")

DATABASES = {
    "hangfudao": {
        "host": "10.132.24.115",
        "port": 3307,
        "user": "root",
        "password": "hangfudao123",
        "db": "hangfudao",
        "description": "编程题目练习系统，包含学生答题记录、知识点掌握情况",
    },
    "ai_assistant": {
        "host": "10.132.24.115",
        "port": 3308,
        "user": "root",
        "password": "root",
        "db": "ai_assistant",
        "description": "AI问答助手系统，包含对话会话、消息记录、知识点学习进度",
    },
}

DB_SCHEMAS = """
== 数据库1: hangfudao (端口3307) ==
说明: 编程题目练习系统

表 students (学生信息):
- id: int, PK, AUTO_INCREMENT, 内部主键
- student_id: varchar(50), UNIQUE, 学号(如25371432)
- name: varchar(100), 姓名
- class_name: varchar(100), 班级
- created_at: datetime, 注册时间

表 answer_records (答题记录):
- id: int, PK, AUTO_INCREMENT, 记录ID
- student_db_id: int, FK→students.id, 关联学生(注意: 关联的是students.id而非student_id)
- session_id: varchar(64), 会话ID
- topic: varchar(50), 知识点/作业主题
- difficulty: varchar(10), 难度(简单/中等/困难)
- problem_text: text, 题目内容
- submitted_code: text, 学生提交的代码
- diagnosis_result: text, 诊断结果
- is_correct: tinyint(1), 是否正确(1=正确, 0=错误)
- language: varchar(20), 编程语言
- created_at: datetime, 提交时间

表 knowledge_mastery (知识点掌握):
- id: int, PK, AUTO_INCREMENT
- student_db_id: int, FK→students.id
- topic: varchar(50), 知识点名称
- correct_count: int, 正确次数
- total_count: int, 总次数
- mastery_level: varchar(10), 掌握等级
- updated_at: datetime, 更新时间

== 数据库2: ai_assistant (端口3308) ==
说明: AI问答助手系统

表 students (学生信息):
- student_id: varchar(50), PK, 学号(主键直接是学号)
- name: varchar(100), 姓名
- class_name: varchar(100), 班级
- created_at: timestamp, 注册时间

表 sessions (对话会话):
- id: varchar(255), PK, 会话ID(UUID)
- student_id: varchar(50), FK→students.student_id
- name: varchar(255), 会话名称
- created_at: timestamp, 创建时间
- is_deleted: tinyint(1), 是否已删除(1=已删除)

表 messages (对话消息):
- id: int, PK, AUTO_INCREMENT
- session_id: varchar(255), FK→sessions.id
- role: varchar(20), 角色(user/assistant)
- content: text, 消息内容
- created_at: timestamp, 时间

表 knowledge_points (知识点列表):
- id: varchar(50), PK, 知识点ID(如array, tree)
- name: varchar(100), 名称
- description: text, 描述
- is_custom: tinyint(1), 是否自定义
- created_by: varchar(50), FK→students.student_id

表 student_knowledge_progress (知识点学习进度):
- id: int, PK, AUTO_INCREMENT
- student_id: varchar(50), FK→students.student_id
- knowledge_point_id: varchar(50), FK→knowledge_points.id
- mastery: int, 掌握程度(0-100)
- stage: varchar(50), 当前阶段
- history: json, 对话历史
- created_at: timestamp
- updated_at: timestamp

== 学生信息补充(xlsx) ==
stus1.xlsx 中包含完整的学号→姓名/班级/专业/院系映射，共约1200条记录。
当用户用姓名或班级查询时，需要先通过学号匹配数据库中的数据。
注意: 数据库中可能存在xlsx中没有的学生(如anonymous)，反之亦然。
"""

STUDENT_LOOKUP_PROMPT = """
你是一个数据库查询助手。用户会用自然语言提问，你需要将问题转换为SQL查询。

当前有两个数据库:
- hangfudao: 编程题目练习系统(答题记录、知识点掌握)
- ai_assistant: AI问答助手系统(对话会话、消息记录、知识点学习进度)

数据库schema如下:
{schema}

学生信息补充说明:
- 数据库中的学生表有 student_id(学号)、name(姓名)、class_name(班级)
- 数据库中的name字段可能是占位符(如"Student 25371041")或不准确
- stus1.xlsx 才是权威的学生信息来源，包含准确的姓名、班级、专业、院系
- 当用户输入中已包含学号时(如student_id_list)，请直接用 IN 子句匹配 student_id
- 当用户输入中没有提供学号时，可以用 LIKE 模糊匹配 name 或 class_name 字段作为备选

请根据用户的问题，为相关数据库生成SQL查询。如果问题不涉及特定系统的数据，则两个库都查。

返回JSON格式:
{{
  "queries": [
    {{
      "database": "hangfudao" 或 "ai_assistant",
      "sql": "SELECT ... SQL语句 ...",
      "explanation": "简要说明"
    }}
  ],
  "explanation": "整体查询思路说明"
}}

重要规则:
1. 只能生成 SELECT 查询，禁止任何修改操作
2. 查询 hangfudao 数据库时，关联学生信息用: LEFT JOIN students st ON ar.student_db_id = st.id
3. 查询 ai_assistant 数据库时，关联学生信息用: LEFT JOIN students st ON s.student_id = st.student_id
4. 时间字段需要加8小时时区偏移: DATE_ADD(字段, INTERVAL 8 HOUR)
5. 如果查询涉及消息内容(content)等大文本字段，请限制长度: LEFT(content, 200)
6. 对于可能返回大量结果的查询，请加 LIMIT (默认最多100条)
7. 只返回JSON，不要返回其他内容
8. 如果问题涉及学生基本信息(姓名/班级)，或者不确定属于哪个系统，两个数据库都应该查询
9. 如果附加上下文中已经明确给出了 student_id 或 class_name，请优先使用这些信息，不要再自己猜测
10. 如果问题是在做“单个学生学习诊断”，优先生成能支撑活跃度、学习效果、难点定位的查询，尽量使用现有表的聚合结果，不要查询无关明细
11. 如果问题是在做“班级风险学生筛查”，优先生成班级范围内的学生列表、近期活跃度、正确率、知识点薄弱项等查询，结果应便于后续识别需要重点关注的学生
"""

SUMMARY_SYSTEM = """
你是一个数据分析助手，请根据用户的问题和SQL查询结果，用中文进行清晰的总结。

输出要求:
1. 直接进入结论，不要添加自我介绍、产品名、研发单位、欢迎语
2. 不要写“小航”“由北京航空航天大学研发”等开场白
3. 可以使用 Markdown 的标题、加粗和列表
"""

SUMMARY_USER_TEMPLATE = """
用户的问题: {question}

执行的SQL: {sql}

查询结果:
{data}

请对查询结果进行总结，要点:
1. 直接回答用户的问题
2. 列出关键数据和发现
3. 如果结果为空，说明可能的原因
4. 保持简洁，不要编造数据中不存在的信息
"""

DIAGNOSIS_KEYWORDS = (
    "学习情况",
    "学习状况",
    "学习状态",
    "学习分析",
    "学习诊断",
    "评价",
    "评估",
    "是否遇到问题",
    "有没有问题",
    "难点",
    "薄弱",
    "掌握情况",
    "问题在哪里",
    "卡在哪里",
)

CLASS_SCREENING_KEYWORDS = (
    "哪些学生",
    "哪些同学",
    "谁",
    "状态不太好",
    "状态不好",
    "需要关注",
    "值得关注",
    "筛查",
    "找出",
    "风险",
)

DIAGNOSIS_SUMMARY_SYSTEM = """
你是一个学生学习分析助手。你会基于SQL查询结果和诊断指标，对学生做较专业的学习分析。

本次请重点围绕两个维度输出结论:
1. 学习活跃度与参与度
2. 学习效果与难点定位

输出风格要求:
1. 整体风格接近教师的学习诊断说明，内容要比简短模板更详细，但不要写成僵硬的条目式公文
2. 可以分成“整体判断、学习活跃度、学习效果与难点、建议”这几个自然段或小标题，不强制固定模板
3. 每个判断尽量写成“现象 + 数据证据 + 可能说明”的形式
4. 必须引用关键数字，不要空泛
5. 如果某个平台没有记录，直接说明“该平台暂无记录，无法据此评判”，不要过度引申
6. 如果整体平台数据很少，也直接说明“当前平台数据不足，暂时无法依据线上记录判断掌握水平”
7. 不要把缺少数据解释成“不会”或“没学”
8. 最后给出2-3条简短、具体、可执行的建议
9. 尽量使用“中文（英文原文）”的表达方式介绍关键字段或指标，例如“掌握度（mastery）”“知识点（topic）”“会话（session）”
10. 保持中文、专业、克制，不编造不存在的信息
11. 直接开始分析，不要添加自我介绍、产品名、研发单位、欢迎语
12. 不要写“小航”“由北京航空航天大学研发”等开场白
"""

DIAGNOSIS_SUMMARY_TEMPLATE = """
用户的问题: {question}
目标学生: {student_profile}

执行的SQL:
{sql}

查询结果:
{data}

诊断规则:
{rules}
"""

CLASS_SCREENING_SUMMARY_SYSTEM = """
你是一个教学分析助手。你会根据班级范围内的学生筛查结果，帮助老师快速定位近期值得关注的学生。

输出要求:
1. 先用一小段概述班级整体筛查结果，例如班级人数、查到平台记录的人数、需要重点关注的人数
2. 然后列出建议重点关注的学生，优先展示最需要关注的前5名
3. 每个学生都要写出简短原因，格式自然，像老师看得懂的点名说明
4. 对“平台没有记录”的学生，要直接写“暂无平台记录，无法据此判断掌握水平”，不要写成不会
5. 风险原因优先围绕：近期参与不足、正确率偏低、近期下滑、知识点卡点、活跃但效果一般
6. 最后补一句建议老师如何继续追问，例如可以进一步点名某个学生做详细诊断
7. 保持中文、专业、克制，尽量使用中文（英文原文）的方式介绍必要字段
8. 直接进入分析，不要添加自我介绍、产品名、研发单位、欢迎语
9. 不要写“小航”“由北京航空航天大学研发”等开场白
"""

CLASS_SCREENING_SUMMARY_TEMPLATE = """
用户的问题: {question}
班级信息: {class_info}

执行的SQL:
{sql}

查询结果:
{data}

诊断规则:
{rules}
"""


def load_student_map():
    student_map = {}
    name_to_ids = {}
    class_to_ids = {}
    try:
        import openpyxl
        wb = openpyxl.load_workbook(XLSX_PATH, read_only=True)
        ws = wb.active
        headers = None
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:
                headers = row
                continue
            if row[0] is None:
                continue
            student_id = str(row[0]).strip()
            name = str(row[1]).strip() if row[1] else ""
            class_name = str(row[6]).strip() if row[6] else ""
            student_map[student_id] = {
                "name": name,
                "class_name": class_name,
                "major": str(row[4]).strip() if row[4] else "",
                "department": str(row[5]).strip() if row[5] else "",
            }
            if name:
                name_to_ids.setdefault(name, []).append(student_id)
            if class_name:
                class_to_ids.setdefault(class_name, []).append(student_id)
        wb.close()
    except Exception as e:
        print(f"[警告] 加载 stus1.xlsx 失败: {e}")
    return student_map, name_to_ids, class_to_ids


def load_diagnosis_rules():
    try:
        with open(RULES_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "rules.md 未找到，本次仅按内置规则生成诊断。"
    except Exception as e:
        return f"rules.md 读取失败: {e}"


@lru_cache(maxsize=1)
def get_runtime_context():
    student_map, name_to_ids, class_to_ids = load_student_map()
    diagnosis_rules = load_diagnosis_rules()
    return {
        "student_map": student_map,
        "name_to_ids": name_to_ids,
        "class_to_ids": class_to_ids,
        "diagnosis_rules": diagnosis_rules,
    }


def get_db_connection(db_name):
    config = DATABASES[db_name]
    return pymysql.connect(
        host=config["host"],
        port=config["port"],
        user=config["user"],
        password=config["password"],
        database=config["db"],
        cursorclass=pymysql.cursors.DictCursor,
        charset="utf8mb4",
        connect_timeout=MYSQL_CONNECT_TIMEOUT,
        read_timeout=MYSQL_READ_TIMEOUT,
        write_timeout=MYSQL_WRITE_TIMEOUT,
        autocommit=True,
    )


def execute_sql(db_name, sql, params=None):
    last_error = None
    for attempt in range(2):
        conn = get_db_connection(db_name)
        try:
            conn.ping(reconnect=True)
            with conn.cursor() as cursor:
                cursor.execute(sql, params or ())
                rows = cursor.fetchall()
                return rows
        except OperationalError as exc:
            last_error = exc
            error_code = exc.args[0] if exc.args else None
            if error_code not in MYSQL_RETRY_ERROR_CODES or attempt == 1:
                raise
        finally:
            conn.close()
    raise last_error


def call_llm(system_prompt, user_message, temperature=0.3):
    client = OpenAI(api_key=API_KEY, base_url=API_BASE)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()


def parse_sql_response(llm_output):
    cleaned = llm_output.strip()
    json_match = re.search(r"\{[\s\S]*\}", cleaned)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    code_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", cleaned)
    if code_match:
        try:
            return json.loads(code_match.group(1))
        except json.JSONDecodeError:
            pass

    return None


def enrich_with_xlsx(rows, student_map):
    if not rows or not student_map:
        return rows
    enriched = []
    for row in rows:
        row = dict(row)
        sid = str(row.get("student_id", ""))
        if sid and sid in student_map:
            info = student_map[sid]
            row["name"] = info["name"] or row.get("name", "")
            row["class_name"] = info["class_name"] or row.get("class_name", "")
            row["major"] = info.get("major", "")
            row["department"] = info.get("department", "")
        enriched.append(row)
    return enriched


def format_data_for_llm(rows, max_rows=50):
    if not rows:
        return "(查询结果为空)"
    display = rows[:max_rows]
    result = []
    for row in display:
        formatted = {}
        for k, v in row.items():
            if isinstance(v, datetime):
                formatted[k] = (v + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(v, bytes):
                formatted[k] = str(v, encoding="utf-8", errors="replace")[:200]
            elif v is None:
                formatted[k] = "NULL"
            elif isinstance(v, (int, float)):
                formatted[k] = round(v, 2) if isinstance(v, float) else v
            elif isinstance(v, str) and len(v) > 200:
                formatted[k] = v[:200] + "..."
            else:
                formatted[k] = str(v)
        result.append(formatted)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if len(rows) > max_rows:
        output += f"\n\n(共 {len(rows)} 条结果，仅显示前 {max_rows} 条)"
    return output


def should_run_diagnosis(question):
    return any(keyword in question for keyword in DIAGNOSIS_KEYWORDS)


def should_run_class_screening(question, matched_classes):
    return bool(matched_classes) and any(keyword in question for keyword in CLASS_SCREENING_KEYWORDS)


def detect_query_mode(question, matched_student_ids, matched_classes):
    if should_run_class_screening(question, matched_classes):
        return "class_screening"
    if should_run_diagnosis(question) and matched_student_ids:
        return "student_diagnosis"
    return "general"


def describe_student_candidates(student_ids, student_map):
    descriptions = []
    for student_id in sorted(student_ids):
        profile = build_student_profile(student_id, student_map)
        descriptions.append(
            {
                "student_id": profile["student_id"],
                "name": profile.get("name", ""),
                "class_name": profile.get("class_name", ""),
                "major": profile.get("major", ""),
                "department": profile.get("department", ""),
            }
        )
    return descriptions


def build_query_context(question, query_mode, matched_student_ids, matched_classes, student_map, diagnosis_rules):
    context_lines = []
    if query_mode == "student_diagnosis":
        context_lines.append("这是一个单个学生学习诊断问题。请优先围绕学习活跃度、学习效果、难点定位来设计查询。")
        context_lines.append("如果已经给出明确学号，请优先按学号查询，不要再使用模糊姓名搜索。")
        context_lines.append("建议优先查询答题记录、知识点掌握、AI会话与知识点进度，避免无关明细。")
        context_lines.append("已识别到的学生候选如下：")
        context_lines.append(json.dumps(describe_student_candidates(matched_student_ids, student_map), ensure_ascii=False, indent=2))
    elif query_mode == "class_screening":
        context_lines.append("这是一个班级范围内的风险学生筛查问题。请生成便于识别需要重点关注学生的查询。")
        context_lines.append("请优先使用已识别出的班级和学号列表，不要重新猜测班级。")
        context_lines.append("建议查询方向：班级学生范围、近期答题/会话活跃度、正确率、薄弱知识点、无记录学生。")
        class_descriptions = []
        for class_name, student_ids in matched_classes.items():
            class_descriptions.append(
                {
                    "class_name": class_name,
                    "student_count": len(student_ids),
                    "student_id_list": list(student_ids),
                }
            )
        context_lines.append("已识别到的班级范围如下：")
        context_lines.append(json.dumps(class_descriptions, ensure_ascii=False, indent=2))
    else:
        if matched_student_ids:
            context_lines.append("已从附加信息中识别到以下学生候选，可优先使用学号匹配：")
            context_lines.append(json.dumps(describe_student_candidates(matched_student_ids, student_map), ensure_ascii=False, indent=2))
        if matched_classes:
            class_descriptions = []
            for class_name, student_ids in matched_classes.items():
                class_descriptions.append(
                    {"class_name": class_name, "student_count": len(student_ids), "student_id_list": list(student_ids)}
                )
            context_lines.append("已从附加信息中识别到以下班级候选，可优先使用 class_name 或学号列表匹配：")
            context_lines.append(json.dumps(class_descriptions, ensure_ascii=False, indent=2))

    if query_mode in ("student_diagnosis", "class_screening"):
        context_lines.append("以下是学习诊断规则摘要，供你理解老师意图：")
        context_lines.append(diagnosis_rules[:4000])

    if not context_lines:
        return question
    return question + "\n\n附加上下文:\n" + "\n".join(context_lines)


def build_clarification_message(query_mode, matched_classes=None):
    if query_mode == "student_diagnosis":
        return (
            "这次问题更像是在做单个学生的学习分析，但我还不能稳定定位到具体学生。"
            "请补充学号，或者提供能唯一定位的姓名和班级信息。"
        )
    if query_mode == "class_screening":
        if matched_classes and len(matched_classes) > 1:
            return "这次问题里识别到了多个班级，请先明确一个班级名称，我再帮你筛查需要重点关注的学生。"
        return "想做班级范围的筛查时，请先提供明确班级名称，例如“23计科1班哪些学生最近需要重点关注？”"
    return "这次问题里的对象还不够明确，请补充学生或班级信息后再试。"


def sanitize_database_error(exc):
    error_code = exc.args[0] if getattr(exc, "args", None) else None
    if error_code in {2006, 2013}:
        return "数据库连接在查询过程中中断了，请重试；如果仍然失败，建议缩小查询范围。"
    if error_code == 1054:
        return "本次生成的查询没有成功命中数据库字段，建议换一种更明确的问法再试。"
    if error_code == 1146:
        return "本次查询访问的数据表不可用，请联系维护人员检查数据库配置。"
    if error_code == 1064:
        return "本次自动生成的查询语句执行失败了，建议把问题描述得更具体一些后重试。"
    return "数据库查询暂时失败了，建议稍后重试；如果反复出现，尽量缩小查询范围。"


def extract_student_ids_from_text(text):
    return set(re.findall(r"\b\d{6,12}\b", text))


def collect_candidate_student_ids(question, matched_student_ids, all_results):
    candidate_ids = set(matched_student_ids)
    candidate_ids.update(extract_student_ids_from_text(question))
    for result in all_results:
        for row in result["rows"]:
            student_id = row.get("student_id")
            if student_id:
                candidate_ids.add(str(student_id))
    return candidate_ids


def build_student_profile(student_id, student_map):
    info = student_map.get(student_id, {})
    return {
        "student_id": student_id,
        "name": info.get("name", ""),
        "class_name": info.get("class_name", ""),
        "major": info.get("major", ""),
        "department": info.get("department", ""),
    }


def process_question(question):
    if not question or not question.strip():
        raise UserFacingError("请输入想了解的问题。")

    runtime = get_runtime_context()
    student_map = runtime["student_map"]
    name_to_ids = runtime["name_to_ids"]
    class_to_ids = runtime["class_to_ids"]
    diagnosis_rules = runtime["diagnosis_rules"]

    question = question.strip()
    matched_info = []
    matched_student_ids = set()
    matched_classes = {}

    for name, ids in name_to_ids.items():
        if name in question:
            matched_info.append(f"姓名'{name}'对应学号: {ids}")
            matched_student_ids.update(ids)

    for cls, ids in class_to_ids.items():
        if cls in question:
            matched_info.append(f"班级'{cls}'对应学号: {ids}")
            matched_student_ids.update(ids)
            matched_classes[cls] = list(ids)

    explicit_student_ids = extract_student_ids_from_text(question)
    all_known_student_ids = set(matched_student_ids)
    all_known_student_ids.update(explicit_student_ids)
    query_mode = detect_query_mode(question, all_known_student_ids, matched_classes)

    if query_mode == "student_diagnosis" and not all_known_student_ids:
        raise ClarificationNeeded(build_clarification_message(query_mode))
    if query_mode == "class_screening" and not matched_classes:
        raise ClarificationNeeded(build_clarification_message(query_mode))
    if query_mode == "class_screening" and len(matched_classes) > 1:
        raise ClarificationNeeded(build_clarification_message(query_mode, matched_classes))

    enhanced_question = build_query_context(
        question,
        query_mode,
        all_known_student_ids,
        matched_classes,
        student_map,
        diagnosis_rules,
    )

    if matched_info:
        enhanced_question += "\n\n以下是从stus1.xlsx中匹配到的学号信息，请优先使用这些学号(student_id)进行查询:\n" + "\n".join(matched_info)

    system_prompt = STUDENT_LOOKUP_PROMPT.format(schema=DB_SCHEMAS)
    llm_response = call_llm(system_prompt, enhanced_question)
    parsed = parse_sql_response(llm_response)
    if not parsed:
        raise QueryGenerationError("这次问题没有成功生成可执行的查询，请换一种更明确的问法再试。")

    queries = parsed.get("queries", [])
    overall_explanation = parsed.get("explanation", "")

    if not queries:
        old_db = parsed.get("database", "")
        old_sql = parsed.get("sql", "").strip()
        if old_db and old_sql:
            queries = [{"database": old_db, "sql": old_sql, "explanation": parsed.get("explanation", "")}]

    if not queries:
        raise QueryGenerationError("这次问题没有成功生成可执行的查询，请补充更明确的对象或范围后再试。")

    all_results = []
    all_sqls = []
    executed_queries = []
    query_errors = []

    for q in queries:
        db_name = q.get("database", "")
        sql = q.get("sql", "").strip()
        q_explanation = q.get("explanation", "")

        if db_name not in DATABASES:
            continue

        stripped_sql = sql.upper().strip()
        if not (stripped_sql.startswith("SELECT") or stripped_sql.startswith("SHOW") or stripped_sql.startswith("DESCRIBE")):
            continue

        try:
            rows = execute_sql(db_name, sql)
            rows = enrich_with_xlsx(rows, student_map)
            all_results.append({"database": db_name, "rows": rows})
            all_sqls.append(f"-- {db_name}\n{sql}")
            executed_queries.append(
                {
                    "database": db_name,
                    "sql": sql,
                    "explanation": q_explanation,
                    "row_count": len(rows),
                }
            )
        except OperationalError as exc:
            query_errors.append(sanitize_database_error(exc))
        except Exception:
            query_errors.append("有一条自动生成的查询执行失败了，我已跳过该查询。")

    if not all_results:
        if query_errors:
            raise QueryExecutionError(query_errors[0])
        raise QueryExecutionError("这次查询没有取到有效结果，请尝试补充更明确的学生、班级或时间范围。")

    data_parts = []
    for result in all_results:
        data_str = format_data_for_llm(result["rows"])
        data_parts.append(f"=== 数据库: {result['database']} ===\n{data_str}")

    combined_data = "\n\n".join(data_parts)
    combined_sql = "\n\n".join(all_sqls)
    candidate_student_ids = collect_candidate_student_ids(question, all_known_student_ids, all_results)

    if query_mode == "class_screening":
        class_name = list(matched_classes.keys())[0] if len(matched_classes) == 1 else "未唯一确定"
        summary = call_llm(
            CLASS_SCREENING_SUMMARY_SYSTEM,
            CLASS_SCREENING_SUMMARY_TEMPLATE.format(
                question=question,
                class_info=json.dumps(
                    {
                        "班级（class_name）": class_name,
                        "班级候选数": len(matched_classes),
                        "已识别学生数": sum(len(ids) for ids in matched_classes.values()),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                sql=combined_sql,
                data=combined_data,
                rules=diagnosis_rules,
            ),
            temperature=0.4,
        )
    elif query_mode == "student_diagnosis" and len(candidate_student_ids) == 1:
        student_id = next(iter(candidate_student_ids))
        summary = call_llm(
            DIAGNOSIS_SUMMARY_SYSTEM,
            DIAGNOSIS_SUMMARY_TEMPLATE.format(
                question=question,
                student_profile=json.dumps(
                    build_student_profile(student_id, student_map),
                    ensure_ascii=False,
                    indent=2,
                ),
                sql=combined_sql,
                data=combined_data,
                rules=diagnosis_rules,
            ),
            temperature=0.4,
        )
    else:
        summary = call_llm(
            SUMMARY_SYSTEM,
            SUMMARY_USER_TEMPLATE.format(question=question, sql=combined_sql, data=combined_data),
            temperature=0.5,
        )

    if summary.startswith("<think"):
        end_tag = summary.find("</think")
        if end_tag != -1:
            summary = summary[end_tag + len("</think"):].strip()

    return {
        "question": question,
        "query_mode": query_mode,
        "matched_info": matched_info,
        "matched_classes": matched_classes,
        "candidate_student_ids": sorted(candidate_student_ids),
        "overall_explanation": overall_explanation,
        "executed_queries": executed_queries,
        "summary": summary,
        "raw_results": all_results,
        "combined_sql": combined_sql,
    }


def run_agent():
    runtime = get_runtime_context()
    print("=" * 60)
    print("  数据库查询 Agent")
    print("  支持: hangfudao(编程练习) / ai_assistant(AI问答)")
    print("  输入 exit 或 quit 退出")
    print("=" * 60)
    print()
    print(f"[信息] 已加载学生信息 {len(runtime['student_map'])} 条 (来自 stus1.xlsx)")
    print()

    while True:
        try:
            question = input("🤖 请输入问题: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not question:
            continue
        if question.lower() in ("exit", "quit", "q"):
            print("再见！")
            break

        try:
            result = process_question(question)
            if result["matched_info"]:
                print("[匹配] 已从xlsx中识别到相关信息:")
                for info in result["matched_info"]:
                    print(f"  - {info}")
                print()
            if result["overall_explanation"]:
                print(f"[思路] {result['overall_explanation']}")
                print()
            for index, query in enumerate(result["executed_queries"], start=1):
                print(f"[查询{index}] {query['database']}")
                print(f"  SQL: {query['sql']}")
                if query["explanation"]:
                    print(f"  说明: {query['explanation']}")
                print(f"  结果: {query['row_count']} 条记录")
            print()
            total_rows = sum(item["row_count"] for item in result["executed_queries"])
            print(f"[结果] 共 {total_rows} 条记录 (来自 {len(result['executed_queries'])} 个数据库)")
            print()
            print(result["summary"])
        except Exception as e:
            print(f"[错误] {e}")

        print()
        print("-" * 60)
        print()


if __name__ == "__main__":
    run_agent()
