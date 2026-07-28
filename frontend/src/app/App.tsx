import { BookOpen, FileText, LoaderCircle, LogOut, Settings, Trash2, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import {
  listPapers,
  deletePaper,
  getCurrentUser,
  getPaper,
  getTask,
  login,
  logout,
  paperFileUrl,
  PaperwiseApiError,
  register,
  type AuthUser,
  type Paper,
  retryPaper,
  uploadPaper,
} from "../api/client";
import { PdfReader } from "../features/reader/PdfReader";
import { ChatPanel } from "../features/chat/ChatPanel";
import { SettingsPanel } from "../features/settings/SettingsPanel";
import { TextExplanationPanel } from "../features/annotations/TextExplanationPanel";
import type { TextSelection } from "../features/reader/PdfReader";
import type { RegionSelection } from "../features/reader/PdfReader";
import { RegionExplanationPanel } from "../features/annotations/RegionExplanationPanel";
import { NotesPanel } from "../features/annotations/NotesPanel";
import { CardPanel } from "../features/cards/CardPanel";

function statusLabel(status: Paper["status"]): string {
  return {
    queued: "等待处理",
    processing: "处理中",
    ready: "已就绪",
    failed: "处理失败",
  }[status];
}

function AuthView({ onAuthenticated }: { onAuthenticated: (user: AuthUser) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = mode === "login"
        ? await login({ username, password })
        : await register({ username, password });
      onAuthenticated(user);
    } catch (reason) {
      if (reason instanceof PaperwiseApiError && reason.code === "AUTH_REQUIRED") {
        setError("已有管理员账号，请登录或联系管理员创建受邀用户。");
      } else {
        setError(reason instanceof Error ? reason.message : "认证失败");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={(event) => void submit(event)}>
        <div className="brand auth-brand"><BookOpen size={24} /><span>PaperWise</span></div>
        <p className="auth-copy">请先登录。首次公开部署时，可创建第一个管理员账号。</p>
        <div className="auth-tabs">
          <button type="button" className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>登录</button>
          <button type="button" className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>创建账号</button>
        </div>
        {error && <div role="alert" className="error-banner">{error}</div>}
        <label>
          用户名
          <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required minLength={3} />
        </label>
        <label>
          密码
          <input value={password} onChange={(event) => setPassword(event.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} required minLength={8} type="password" />
        </label>
        <button type="submit" className="auth-submit" disabled={busy}>
          {busy ? "处理中…" : mode === "login" ? "登录进入" : "创建并登录"}
        </button>
      </form>
    </div>
  );
}

export function App() {
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [taskProgress, setTaskProgress] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const deletingIdRef = useRef<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [sideTab, setSideTab] = useState<"library" | "chat" | "explain" | "notes" | "card">("library");
  const [targetPage, setTargetPage] = useState<number | null>(null);
  const [textSelection, setTextSelection] = useState<TextSelection | null>(null);
  const [regionSelection, setRegionSelection] = useState<RegionSelection | null>(null);

  const clearWorkspace = () => {
    setPapers([]);
    setSelectedId(null);
    setActiveTaskId(null);
    setTaskProgress(null);
    setTargetPage(null);
    setTextSelection(null);
    setRegionSelection(null);
    setSettingsOpen(false);
    setSideTab("library");
  };

  const handleAuthError = (reason: unknown): boolean => {
    if (reason instanceof PaperwiseApiError && reason.code === "AUTH_REQUIRED") {
      setCurrentUser(null);
      clearWorkspace();
      setError("登录已失效，请重新登录。");
      return true;
    }
    return false;
  };

  useEffect(() => {
    setTextSelection(null);
    setRegionSelection(null);
  }, [selectedId]);

  useEffect(() => {
    const controller = new AbortController();
    void getCurrentUser(controller.signal)
      .then((user) => setCurrentUser(user))
      .catch((reason: unknown) => {
        if (!(reason instanceof DOMException && reason.name === "AbortError")) {
          if (reason instanceof PaperwiseApiError && reason.code === "AUTH_REQUIRED") {
            setCurrentUser(null);
          } else {
            setError(reason instanceof Error ? reason.message : "登录状态检查失败");
          }
        }
      })
      .finally(() => setAuthChecked(true));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!currentUser) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    void listPapers(controller.signal)
      .then((items) => {
        setPapers(items);
        setSelectedId((current) =>
          current && items.some((paper) => paper.paper_id === current)
            ? current
            : (items[0]?.paper_id ?? null),
        );
      })
      .catch((reason: unknown) => {
        if (!(reason instanceof DOMException && reason.name === "AbortError")) {
          if (!handleAuthError(reason)) {
            setError(reason instanceof Error ? reason.message : "论文列表加载失败");
          }
        }
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [currentUser?.user_id]);

  const selectedPaper = papers.find((paper) => paper.paper_id === selectedId) ?? null;

  useEffect(() => {
    if (!selectedPaper || !["queued", "processing"].includes(selectedPaper.status)) {
      setTaskProgress(null);
      return;
    }
    const controller = new AbortController();
    const refresh = async () => {
      try {
        if (activeTaskId) {
          const task = await getTask(activeTaskId, controller.signal);
          setTaskProgress(task.progress);
          if (["succeeded", "failed"].includes(task.status)) setActiveTaskId(null);
        }
        const paper = await getPaper(selectedPaper.paper_id, controller.signal);
        setPapers((items) => items.map((item) => item.paper_id === paper.paper_id ? paper : item));
      } catch (reason) {
        if (
          reason instanceof PaperwiseApiError
          && reason.code === "PAPER_NOT_FOUND"
          && deletingIdRef.current === selectedPaper.paper_id
        ) return;
        if (!(reason instanceof DOMException && reason.name === "AbortError")) {
          if (!handleAuthError(reason)) {
            setError(reason instanceof Error ? reason.message : "任务状态刷新失败");
          }
        }
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 1000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [activeTaskId, selectedPaper?.paper_id, selectedPaper?.status]);

  const handleUpload = async (file: File) => {
    setUploading(true);
    setError(null);
    try {
      const result = await uploadPaper(file);
      const items = await listPapers();
      setPapers(items);
      setSelectedId(result.paper.paper_id);
      setActiveTaskId(result.task_id);
    } catch (reason) {
      if (!handleAuthError(reason)) {
        setError(
          reason instanceof PaperwiseApiError || reason instanceof Error
            ? reason.message
            : "PDF 上传失败",
        );
      }
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleRetry = async () => {
    if (!selectedPaper) return;
    setError(null);
    try {
      const result = await retryPaper(selectedPaper.paper_id);
      setActiveTaskId(result.task_id);
      const paper = await getPaper(selectedPaper.paper_id);
      setPapers((items) => items.map((item) => item.paper_id === paper.paper_id ? paper : item));
    } catch (reason) {
      if (!handleAuthError(reason)) {
        setError(reason instanceof Error ? reason.message : "重试失败");
      }
    }
  };

  const handleDelete = async (paper: Paper) => {
    if (!window.confirm(`确定永久删除“${paper.filename}”吗？\n\n原始 PDF、问答、速读、笔记和截图都将删除，且无法恢复。`)) return;
    setError(null);
    setDeletingId(paper.paper_id);
    deletingIdRef.current = paper.paper_id;
    let deleted = false;
    try {
      await deletePaper(paper.paper_id);
      deleted = true;
    } catch (reason) {
      if (reason instanceof PaperwiseApiError && reason.code === "PAPER_NOT_FOUND") {
        deleted = true;
      } else {
        if (!handleAuthError(reason)) {
          setError(reason instanceof Error ? reason.message : "论文删除失败");
        }
      }
    } finally {
      deletingIdRef.current = null;
      setDeletingId(null);
    }
    if (!deleted) return;
    const remaining = papers.filter((item) => item.paper_id !== paper.paper_id);
    setPapers(remaining);
    if (selectedId === paper.paper_id) {
      setSelectedId(remaining[0]?.paper_id ?? null);
      setActiveTaskId(null);
      setTaskProgress(null);
      setTargetPage(null);
      setTextSelection(null);
      setRegionSelection(null);
    }
  };

  const handleLogout = async () => {
    setError(null);
    try {
      await logout();
    } catch (reason) {
      if (!handleAuthError(reason)) {
        setError(reason instanceof Error ? reason.message : "退出登录失败");
        return;
      }
    }
    setCurrentUser(null);
    clearWorkspace();
  };

  if (!authChecked) {
    return (
      <div className="auth-page">
        <div className="reader-state"><LoaderCircle className="spin" />正在检查登录状态…</div>
      </div>
    );
  }

  if (!currentUser) {
    return <AuthView onAuthenticated={(user) => { setError(null); setCurrentUser(user); }} />;
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand"><BookOpen size={22} /><span>PaperWise</span></div>
        <div className="topbar-actions"><div className="topbar-status">{selectedPaper?.filename ?? currentUser.username}</div><button type="button" className="icon-button" title="设置" aria-label="打开设置" onClick={() => setSettingsOpen(true)}><Settings size={18} /></button><button type="button" className="icon-button" title="退出登录" aria-label="退出登录" onClick={() => void handleLogout()}><LogOut size={18} /></button></div>
      </header>
      <main className="workspace">
        <section className="reader-region" aria-label="PDF 阅读器">
          {selectedPaper ? (
            <PdfReader
              key={selectedPaper.paper_id}
              fileUrl={paperFileUrl(selectedPaper.paper_id)}
              filename={selectedPaper.filename}
              targetPage={targetPage}
              onTextSelection={(selection) => {
                setTextSelection(selection);
                if (selection) {
                  setRegionSelection(null);
                  setSideTab("explain");
                }
              }}
              onRegionSelection={(selection) => {
                setRegionSelection(selection);
                setTextSelection(null);
                setSideTab("explain");
              }}
            />
          ) : (
            <div className="empty-reader">
              <FileText size={40} strokeWidth={1.5} />
              <p>{loading ? "正在读取本地论文…" : "尚未添加论文"}</p>
            </div>
          )}
        </section>
        <aside className="library-panel" aria-label="论文库">
          <div className="side-tabs"><button type="button" className={sideTab === "library" ? "active" : ""} onClick={() => setSideTab("library")}>论文库</button><button type="button" className={sideTab === "chat" ? "active" : ""} onClick={() => setSideTab("chat")}>问答</button><button type="button" className={sideTab === "explain" ? "active" : ""} onClick={() => setSideTab("explain")}>解释</button><button type="button" className={sideTab === "notes" ? "active" : ""} onClick={() => setSideTab("notes")}>笔记</button><button type="button" className={sideTab === "card" ? "active" : ""} onClick={() => setSideTab("card")}>速读</button></div>
          {sideTab === "library" ? <>
          <div className="panel-heading">
            <div><span className="eyebrow">LIBRARY</span><h1>论文库</h1></div>
            <button type="button" className="upload-button" onClick={() => fileInputRef.current?.click()} disabled={uploading} aria-label="上传 PDF">
              {uploading ? <LoaderCircle className="spin" size={18} /> : <Upload size={18} />}
              <span>{uploading ? "上传中" : "上传"}</span>
            </button>
            <input
              ref={fileInputRef}
              className="sr-only"
              type="file"
              accept="application/pdf,.pdf"
              aria-label="选择 PDF 文件"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void handleUpload(file);
              }}
            />
          </div>
          {error && <div role="alert" className="error-banner">{error}</div>}
          {selectedPaper && ["queued", "processing"].includes(selectedPaper.status) && (
            <div className="task-strip">
              <span>{statusLabel(selectedPaper.status)}</span>
              <span>{taskProgress === null ? "—" : `${taskProgress}%`}</span>
            </div>
          )}
          {selectedPaper?.status === "failed" && (
            <button type="button" className="retry-button" onClick={() => void handleRetry()}>
              重新处理
            </button>
          )}
          <div className="paper-list">
            {papers.map((paper) => (
              <div className="paper-row" key={paper.paper_id}>
                <button
                  type="button"
                  className={`paper-item${paper.paper_id === selectedId ? " selected" : ""}`}
                  aria-label={`打开 ${paper.filename}`}
                  onClick={() => setSelectedId(paper.paper_id)}
                >
                  <FileText size={18} />
                  <span className="paper-copy">
                    <strong>{paper.filename}</strong>
                    <span>{paper.page_count} 页</span>
                  </span>
                  <span className={`status-dot ${paper.status}`} title={statusLabel(paper.status)} />
                </button>
                <button
                  type="button"
                  className="paper-delete"
                  title={`删除 ${paper.filename}`}
                  aria-label={`删除 ${paper.filename}`}
                  disabled={deletingId === paper.paper_id}
                  onClick={() => void handleDelete(paper)}
                >
                  {deletingId === paper.paper_id ? <LoaderCircle className="spin" size={16} /> : <Trash2 size={16} />}
                </button>
              </div>
            ))}
          </div>
          </> : sideTab === "chat" ? <ChatPanel paper={selectedPaper} onNavigatePage={(page) => { setTargetPage(page); }} /> : sideTab === "notes" ? <NotesPanel paper={selectedPaper} /> : sideTab === "card" ? <CardPanel paper={selectedPaper} onNavigatePage={(page) => setTargetPage(page)} /> : regionSelection && selectedPaper ? <RegionExplanationPanel key={`${selectedId}:${regionSelection.page}:${regionSelection.bbox.join(",")}`} paper={selectedPaper} selection={regionSelection} /> : <TextExplanationPanel key={`${selectedId ?? "none"}:${textSelection?.selectedText ?? ""}`} paper={selectedPaper} selection={textSelection} />}
        </aside>
      </main>
      {settingsOpen && <SettingsPanel onClose={() => setSettingsOpen(false)} />}
    </div>
  );
}
