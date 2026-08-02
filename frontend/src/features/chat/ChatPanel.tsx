import { LoaderCircle, Send, Trash2 } from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";

import { askPaper, clearMessages, getMessages, type Message, type Paper } from "../../api/client";

export function ChatPanel({ paper, onNavigatePage, textModelConfigured }: {
  paper: Paper | null;
  onNavigatePage: (page: number) => void;
  textModelConfigured: boolean | null;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [confirmingClear, setConfirmingClear] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const clearButtonRef = useRef<HTMLButtonElement>(null);
  const cancelClearRef = useRef<HTMLButtonElement>(null);

  const disabledReason = !paper
    ? "请先选择论文"
    : paper.status !== "ready"
      ? `论文${paper.status === "failed" ? "处理失败" : "尚未处理完成"}`
      : textModelConfigured === null
        ? "正在读取文本模型配置"
        : !textModelConfigured
          ? "请先在 API 配置中启用文本模型"
          : null;

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

  useEffect(() => {
    if (!confirmingClear) return;
    cancelClearRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setConfirmingClear(false);
        clearButtonRef.current?.focus();
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [confirmingClear]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!paper || disabledReason || !question.trim() || sending) return;
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
    if (!paper || clearing) return;
    setClearing(true);
    setError(null);
    try {
      await clearMessages(paper.paper_id);
      setMessages([]);
      setConfirmingClear(false);
      clearButtonRef.current?.focus();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "清空会话失败");
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="chat-panel">
      <div className="chat-heading">
        <strong>论文问答</strong>
        <div className="clear-control">
          <button ref={clearButtonRef} type="button" className="icon-button danger" aria-label="清空当前会话" title="清空当前会话" aria-expanded={confirmingClear} onClick={() => setConfirmingClear(true)} disabled={!messages.length || clearing}><Trash2 size={16} /></button>
          {confirmingClear && <div className="clear-confirmation" role="alertdialog" aria-label="确认清空当前会话">
            <p>清空后无法恢复</p>
            <div><button ref={cancelClearRef} type="button" onClick={() => { setConfirmingClear(false); clearButtonRef.current?.focus(); }}>取消</button><button type="button" className="danger-confirm" disabled={clearing} onClick={() => void clear()}>{clearing ? "清空中" : "确认清空"}</button></div>
          </div>}
        </div>
      </div>
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
        <textarea aria-label="向论文提问" value={question} maxLength={4000} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => {
          if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
            event.preventDefault();
            event.currentTarget.form?.requestSubmit();
          }
        }} disabled={Boolean(disabledReason) || sending} placeholder={disabledReason ?? "围绕当前论文提问"} />
        <button type="submit" className="icon-button primary composer-send" aria-label="发送问题" title={disabledReason ?? "发送问题（Ctrl/Cmd+Enter）"} disabled={!question.trim() || Boolean(disabledReason) || sending}>{sending ? <LoaderCircle className="spin" size={17} /> : <Send size={17} />}</button>
      </form>
    </div>
  );
}
