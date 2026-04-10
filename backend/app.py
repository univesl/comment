from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from pymysql.err import OperationalError

from agent import (
    ClarificationNeeded,
    QueryExecutionError,
    QueryGenerationError,
    UserFacingError,
    process_question,
)


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"

app = Flask(__name__, static_folder=str(FRONTEND_DIST), static_url_path="")


@app.post("/api/chat")
def chat():
    payload = request.get_json(silent=True) or {}
    question = (payload.get("message") or "").strip()
    if not question:
        return jsonify({"error": "message 不能为空"}), 400

    try:
        result = process_question(question)
    except ClarificationNeeded as exc:
        return jsonify({"error": str(exc), "type": "clarification_needed"}), 400
    except (QueryGenerationError, QueryExecutionError, UserFacingError) as exc:
        return jsonify({"error": str(exc), "type": "user_facing_error"}), 400
    except OperationalError as exc:
        error_code = exc.args[0] if exc.args else None
        if error_code in {2006, 2013}:
            return jsonify({"error": "数据库连接在查询过程中中断了，请重试；如果仍然失败，建议缩小查询范围。"}), 502
        return jsonify({"error": "数据库查询失败了，请稍后重试。"}), 500
    except Exception:
        return jsonify({"error": "这次处理没有成功完成，请稍后重试或换一种更明确的问法。"}), 500

    response = {
        "question": result["question"],
        "queryMode": result["query_mode"],
        "matchedInfo": result["matched_info"],
        "matchedClasses": result["matched_classes"],
        "candidateStudentIds": result["candidate_student_ids"],
        "overallExplanation": result["overall_explanation"],
        "executedQueries": result["executed_queries"],
        "summary": result["summary"],
    }
    return jsonify(response)


@app.get("/")
def index():
    index_file = FRONTEND_DIST / "index.html"
    if index_file.exists():
        return send_from_directory(FRONTEND_DIST, "index.html")
    return jsonify(
        {
            "message": "前端尚未构建。请先在 frontend 目录执行 npm install 和 npm run build，或单独启动前端开发服务器。"
        }
    )


@app.get("/<path:path>")
def spa_assets(path: str):
    target = FRONTEND_DIST / path
    if target.exists():
        return send_from_directory(FRONTEND_DIST, path)
    index_file = FRONTEND_DIST / "index.html"
    if index_file.exists():
        return send_from_directory(FRONTEND_DIST, "index.html")
    return jsonify({"error": "前端资源不存在"}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
