# README.md

## 项目概述

这是一个教育数据查询工具集，包含两个独立的数据库系统：
- **hangfudao**（端口 3307）：编程练习系统，记录学生答题情况和知识点掌握程度
- **ai_assistant**（端口 3308）：AI 问答助手系统，记录学生对话会话和学习进度

## 核心架构

### 数据库连接配置
- 两个数据库都使用 pymysql 和 DictCursor 进行查询
- 连接参数可通过环境变量或 CLI 参数配置：
  - `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DB`
- 默认连接信息在各脚本的模块级常量中定义

### Agent 系统（`agent.py`）
智能查询 Agent 使用 LLM（通过 OpenAI 兼容 API 调用 Qwen 模型）来：
1. 解析自然语言问题
2. 为适当的数据库生成 SQL 查询
3. 执行查询并用 AI 总结结果

核心组件：
- `STUDENT_LOOKUP_PROMPT`：SQL 生成的系统提示词
- `load_student_map()`：从 `stus1.xlsx` 加载学生信息（约 1200 条记录）
- `enrich_with_xlsx()`：用 Excel 文件的数据增强查询结果
- LLM 端点：`http://10.70.247.113:4000/v1`（Qwen3-235B 模型）

**重要提示**：Agent 仅允许 SELECT 查询以确保安全。

### 命令行工具

`AIAssistant.py` 和 `Hangfudao.py` 遵循相同的模式：
- 基于子命令的 CLI（例如：`python AIAssistant.py students`）
- 常用导出选项：`--csv` 和 `--json`
- 通过 `sql` 子命令支持自定义 SQL（仅限 SELECT）
- 自动进行时区调整（datetime 字段 +8 小时）

## 数据结构说明

### 学生表差异
- **hangfudao.students**：使用自增 `id` 作为主键，`student_id` 是唯一字段
  - 联表时使用：`LEFT JOIN students st ON ar.student_db_id = st.id`
- **ai_assistant.students**：直接使用 `student_id` 作为主键
  - 联表时使用：`LEFT JOIN students st ON s.student_id = st.student_id`

### 核心数据表
- `answer_records`：学生代码提交记录，包含诊断结果
- `sessions`：对话会话（使用 `is_deleted` 标志进行软删除）
- `messages`：链接到会话的对话消息
- `student_knowledge_progress`：知识点掌握进度追踪（0-100 分制）

## 常用命令

### 运行智能 Agent
```bash
python agent.py
```

### 查询 AI 助手数据库
```bash
# 列出所有学生及其会话/消息数
python AIAssistant.py students

# 查看特定学生的会话
python AIAssistant.py sessions --student 25371041

# 获取会话的消息
python AIAssistant.py messages <session_id>

# 检查知识点学习进度
python AIAssistant.py progress
```

### 查询 hangfudao 数据库
```bash
# 总体统计
python Hangfudao.py stats

# 列出答题记录（默认：最近 50 条）
python Hangfudao.py records

# 按学生或正确性筛选
python Hangfudao.py records --student 25371432 --wrong --limit 100

# 查看完整记录详情
python Hangfudao.py detail 1234

# 检查知识点掌握情况
python Hangfudao.py mastery
```

### 导出数据
```bash
# 导出到 CSV（UTF-8-BOM 编码）
python AIAssistant.py students --csv output.csv

# 导出到 JSON
python Hangfudao.py records --json
```

## 依赖项

- `pymysql`：MySQL 数据库连接
- `openpyxl`：Excel 文件读取（用于 `stus1.xlsx`）
- `openai`：LLM API 客户端
- `tabulate`：美化表格输出

## Web 界面

项目新增了一个基于 Flask + React 的聊天式 Web 界面：

- 后端入口：`app.py`
- 前端目录：`frontend/`

### 启动后端

```bash
pip install -r requirements.txt
python app.py
```

默认启动在 `http://127.0.0.1:5000`

### 启动前端开发环境

```bash
cd frontend
npm install
npm run dev
```

默认启动在 `http://127.0.0.1:5173`

前端会把 `/api` 请求代理到 Flask 后端，界面采用聊天式布局，便于后续迁移到移动端。

## 当前目录结构

```text
.
├─backend/
│  ├─app.py
│  ├─agent.py
│  ├─requirements.txt
│  ├─rules.md
│  ├─stus1.xlsx
│  ├─AIAssistant.py
│  ├─Hangfudao.py
│  └─...
├─frontend/
│  ├─src/
│  ├─package.json
│  └─vite.config.js
└─README.md
```

## 最新启动方式

### 后端

```bash
cd backend
pip install -r requirements.txt
python app.py
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

如果需要构建前端静态文件给 Flask 托管：

```bash
cd frontend
npm run build
```

构建完成后，再在 `backend/` 目录运行：

```bash
python app.py
```
