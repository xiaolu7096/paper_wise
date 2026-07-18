import { Send, Trash2 } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

import { askPaper, clearMessages, getMessages, type Message, type Paper } from "../../api/client";

export function ChatPanel({ paper, onNavigatePage }: {
  paper: Paper | null;
  onNavigatePage: (page: number) => void;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setMessages([]);
    setError(null);
    if (!paper) return;
    const controller = new AbortController();
    void getMessages(paper.paper_id, controller.signal)
      .then(setMessages)
      .catch((reason: unknown) => {
        if (!(reason instanceof DOMException && reason.name === "AbortError")) {
          setError(reason instanceof Error ? reason.message : "会话加载失败");
        }
      });
    return () => controller.abort();
  }, [paper?.paper_id]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!paper || paper.status !== "ready" || !question.trim()) return;
    const value = question.trim();
    setSending(true);
    setError(null);
    try {
      await askPaper(paper.paper_id, value);
      setQuestion("");
      setMessages(await getMessages(paper.paper_id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "提问失败");
    } finally {
      setSending(false);
    }
  };

  const clear = async () => {
    if (!paper) return;
    await clearMessages(paper.paper_id);
    setMessages([]);
  };

  return (
    <div className="chat-panel">
      <div className="chat-heading"><strong>论文问答</strong><button type="button" className="icon-button" aria-label="清空会话" title="清空会话" onClick={() => void clear()} disabled={!messages.length}><Trash2 size={16} /></button></div>
      <div className="message-list">
        {messages.map((message) => (
          <article key={message.message_id} className={`message ${message.role}`}>
            <div>{message.content}</div>
            {message.citations.length > 0 && <div className="citation-list">{message.citations.map((citation) => <button type="button" key={citation.source_id} onClick={() => onNavigatePage(citation.page)} title={citation.quote}>[{citation.source_id}] 第 {citation.page} 页</button>)}</div>}
          </article>
        ))}
      </div>
      {error && <div role="alert" className="error-banner">{error}</div>}
      <form className="chat-form" onSubmit={(event) => void submit(event)}>
        <textarea aria-label="向论文提问" value={question} maxLength={4000} onChange={(event) => setQuestion(event.target.value)} disabled={!paper || paper.status !== "ready" || sending} placeholder={paper?.status === "ready" ? "围绕当前论文提问" : "等待论文处理完成"} />
        <button type="submit" className="icon-button" aria-label="发送问题" title="发送" disabled={!question.trim() || paper?.status !== "ready" || sending}><Send size={17} /></button>
      </form>
    </div>
  );
}
