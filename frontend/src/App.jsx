import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

const quickPrompts = [
  "分析一下学号25371432最近的学习情况",
  "23计科1班哪些学生最近学习状态不太好？",
  "这个班最近主要卡在哪些知识点？"
];

function compactMarkdown(text) {
  return text
    .replace(/\r\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .replace(/[ \t]+\n/g, "\n")
    .trim();
}

export default function App() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([
    {
      id: "welcome",
      role: "assistant",
      text: "可以直接问学生诊断、班级筛查或整体学习情况。我会尽量用老师更容易看的方式整理结果。"
    }
  ]);
  const [loading, setLoading] = useState(false);
  const listRef = useRef(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  async function sendMessage(text) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    const userMessage = { id: `user-${Date.now()}`, role: "user", text: trimmed };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: trimmed })
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "请求失败");
      }

      setMessages((prev) => [
        ...prev,
        {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          text: data.summary
        }
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          id: `error-${Date.now()}`,
          role: "assistant",
          text: `处理失败：${error.message}`
        }
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    void sendMessage(input);
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
          <p className="sidebar-eyebrow">Teaching Copilot</p>
          <h1>教学数据助手</h1>
          <p className="sidebar-copy">
            基于 Flask + React 的聊天式查询界面，适合老师直接提问，也方便后续迁移到手机端。
          </p>
        </div>
        <div className="quick-prompts">
          <div className="section-title">快捷问题</div>
          {quickPrompts.map((prompt) => (
            <button key={prompt} type="button" onClick={() => void sendMessage(prompt)}>
              {prompt}
            </button>
          ))}
        </div>
      </aside>

      <main className="chat-panel">
        <header className="chat-header">
          <div>
            <h2>聊天诊断</h2>
            <p>像发消息一样提问，支持学生诊断和班级风险筛查。</p>
          </div>
          <div className={`status-badge ${loading ? "busy" : "idle"}`}>
            {loading ? "处理中" : "已就绪"}
          </div>
        </header>

        <section className="message-list" ref={listRef}>
          {messages.map((message) => (
            <article key={message.id} className={`message-row ${message.role}`}>
              <div className="avatar">{message.role === "user" ? "师" : "助"}</div>
              <div className="bubble-wrap">
                <div className="bubble">
                  <div
                    className={
                      message.role === "assistant"
                        ? "bubble-text markdown-body assistant-text"
                        : "bubble-text user-text"
                    }
                  >
                    {message.role === "assistant" ? (
                      <ReactMarkdown>{compactMarkdown(message.text)}</ReactMarkdown>
                    ) : (
                      message.text
                    )}
                  </div>
                </div>
              </div>
            </article>
          ))}
          {loading ? (
            <article className="message-row assistant">
              <div className="avatar">助</div>
              <div className="bubble-wrap">
                <div className="bubble loading-bubble">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
            </article>
          ) : null}
        </section>

        <form className="composer" onSubmit={handleSubmit}>
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="输入老师想了解的问题，比如：23计科1班哪些学生最近需要重点关注？"
            rows={1}
          />
          <button type="submit" disabled={loading || !input.trim()}>
            发送
          </button>
        </form>
      </main>
    </div>
  );
}
