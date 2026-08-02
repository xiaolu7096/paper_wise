import {
  BookOpen,
  ChevronLeft,
  ChevronRight,
  FileText,
  Library,
  LoaderCircle,
  LogOut,
  Search,
  Settings,
  Trash2,
  Upload,
  UserRound,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import {
  listPapers,
  deletePaper,
  getCurrentUser,
  getPaper,
  getSettingsStatus,
  getTask,
  login,
  logout,
  paperFileUrl,
  PaperwiseApiError,
  register,
  type AuthUser,
  type Paper,
  type SettingsStatus,
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

const NAVIGATION_STORAGE_KEY = "paperwise-navigation-open";

function initialNavigationOpen(): boolean {
  const stored = window.localStorage.getItem(NAVIGATION_STORAGE_KEY);
  if (stored !== null) return stored === "true";
  return typeof window.matchMedia !== "function" || !window.matchMedia("(max-width: 760px)").matches;
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
  const [settingsStatus, setSettingsStatus] = useState<SettingsStatus | null>(null);
  const [navigationOpen, setNavigationOpen] = useState(initialNavigationOpen);
  const [navigationView, setNavigationView] = useState<"library" | "account">("library");
  const [paperQuery, setPaperQuery] = useState("");
  const [sideTab, setSideTab] = useState<"chat" | "explain" | "notes" | "card">("chat");
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
    setSettingsStatus(null);
    setNavigationView("library");
    setPaperQuery("");
    setSideTab("chat");
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
    window.localStorage.setItem(NAVIGATION_STORAGE_KEY, String(navigationOpen));
  }, [navigationOpen]);

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

  useEffect(() => {
    let active = true;
    setSettingsStatus(null);
    if (!currentUser) return;
    void getSettingsStatus()
      .then((status) => { if (active) setSettingsStatus(status); })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "模型配置状态读取失败"); });
    return () => { active = false; };
  }, [currentUser?.user_id]);

  const selectedPaper = papers.find((paper) => paper.paper_id === selectedId) ?? null;
  const normalizedPaperQuery = paperQuery.trim().toLocaleLowerCase();
  const visiblePapers = normalizedPaperQuery
    ? papers.filter((paper) => paper.filename.toLocaleLowerCase().includes(normalizedPaperQuery))
    : papers;

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
    <div className={`app-shell ${navigationOpen ? "navigation-open" : "navigation-hidden"}`}>
      <header className="topbar">
        <div className="brand"><BookOpen size={22} /><span>PaperWise</span></div>
        <div className="topbar-actions"><div className="topbar-status" title={selectedPaper?.filename}>{selectedPaper?.filename ?? currentUser.username}</div><button type="button" className="icon-button ghost" title="退出登录" aria-label="退出登录" onClick={() => void handleLogout()}><LogOut size={18} /></button></div>
      </header>
      <main className="workspace">
        <aside
          id="workspace-navigation"
          className="workspace-navigation"
          aria-label="全局导航"
          aria-hidden={!navigationOpen}
          inert={!navigationOpen}
        >
          <div className="navigation-inner">
            <nav className="navigation-menu" aria-label="PaperWise 导航">
              <button
                type="button"
                className={navigationView === "library" && !settingsOpen ? "active" : ""}
                onClick={() => { setSettingsOpen(false); setNavigationView("library"); }}
              ><Library size={18} /><span>论文库</span></button>
              <button
                type="button"
                className={settingsOpen ? "active" : ""}
                onClick={() => setSettingsOpen(true)}
              ><Settings size={18} /><span>API 配置</span></button>
              <button
                type="button"
                className={navigationView === "account" && !settingsOpen ? "active" : ""}
                onClick={() => { setSettingsOpen(false); setNavigationView("account"); }}
              ><UserRound size={18} /><span>账号</span></button>
            </nav>

            {error && <div role="alert" className="error-banner">{error}</div>}

            {navigationView === "library" ? (
              <section className="navigation-view" aria-labelledby="library-title">
                <div className="panel-heading compact">
                  <div><span className="eyebrow">LIBRARY</span><h1 id="library-title">论文库</h1></div>
                  <button type="button" className="upload-button" onClick={() => fileInputRef.current?.click()} disabled={uploading} aria-label="上传 PDF">
                    {uploading ? <LoaderCircle className="spin" size={16} /> : <Upload size={16} />}
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

                {uploading && (
                  <div className="upload-progress indeterminate" role="status" aria-label="PDF 上传中">
                    <span className="progress-fill" />
                    <span className="progress-label">上传中</span>
                  </div>
                )}

                <label className="paper-search">
                  <Search size={15} aria-hidden="true" />
                  <span className="sr-only">搜索论文</span>
                  <input value={paperQuery} placeholder="搜索论文" onChange={(event) => setPaperQuery(event.target.value)} />
                </label>

                {selectedPaper?.status === "failed" && (
                  <button type="button" className="retry-button" onClick={() => void handleRetry()}>
                    重新处理
                  </button>
                )}

                <div className="paper-list">
                  {visiblePapers.map((paper) => {
                    const showProgress = paper.paper_id === selectedId
                      && activeTaskId !== null
                      && ["queued", "processing"].includes(paper.status);
                    return (
                      <div className="paper-row" key={paper.paper_id}>
                        <button
                          type="button"
                          className={`paper-item${paper.paper_id === selectedId ? " selected" : ""}`}
                          aria-label={`打开 ${paper.filename}`}
                          onClick={() => setSelectedId(paper.paper_id)}
                        >
                          <FileText size={18} />
                          <span className="paper-copy">
                            <strong title={paper.filename}>{paper.filename}</strong>
                            <span className="paper-meta">
                              <span>{paper.page_count} 页</span>
                              <span className={`status-badge ${paper.status}`}>{statusLabel(paper.status)}</span>
                            </span>
                            {showProgress && (
                              <span
                                className="task-progress"
                                role="progressbar"
                                aria-label={`${paper.filename} 解析进度`}
                                aria-valuemin={0}
                                aria-valuemax={100}
                                aria-valuenow={taskProgress ?? 0}
                              >
                                <span className="progress-fill" style={{ width: `${taskProgress ?? 0}%` }} />
                                <span className="progress-label">{taskProgress === null ? statusLabel(paper.status) : `${taskProgress}%`}</span>
                              </span>
                            )}
                          </span>
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
                    );
                  })}
                  {!loading && visiblePapers.length === 0 && (
                    <p className="navigation-empty">{papers.length === 0 ? "尚未添加论文" : "没有匹配的论文"}</p>
                  )}
                </div>
              </section>
            ) : (
              <section className="navigation-view account-view" aria-labelledby="account-title">
                <div className="account-avatar"><UserRound size={24} /></div>
                <div><span className="eyebrow">ACCOUNT</span><h1 id="account-title">{currentUser.username}</h1></div>
                <dl><div><dt>角色</dt><dd>{currentUser.role === "admin" ? "管理员" : currentUser.role}</dd></div><div><dt>状态</dt><dd>已登录</dd></div></dl>
                <button type="button" className="account-logout" aria-label="从账号退出登录" onClick={() => void handleLogout()}><LogOut size={16} />退出登录</button>
              </section>
            )}
          </div>
        </aside>

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
        <aside className="assistant-panel" aria-label="AI 阅读助手">
          <div className="side-tabs"><button type="button" className={sideTab === "chat" ? "active" : ""} onClick={() => setSideTab("chat")}>问答</button><button type="button" className={sideTab === "explain" ? "active" : ""} onClick={() => setSideTab("explain")}>解释</button><button type="button" className={sideTab === "notes" ? "active" : ""} onClick={() => setSideTab("notes")}>笔记</button><button type="button" className={sideTab === "card" ? "active" : ""} onClick={() => setSideTab("card")}>速读</button></div>
          {sideTab === "chat" ? <ChatPanel paper={selectedPaper} textModelConfigured={settingsStatus?.text_model.configured ?? null} onNavigatePage={(page) => { setTargetPage(page); }} /> : sideTab === "notes" ? <NotesPanel paper={selectedPaper} onNavigatePage={(page) => setTargetPage(page)} /> : sideTab === "card" ? <CardPanel paper={selectedPaper} textModelConfigured={settingsStatus?.text_model.configured ?? null} onNavigatePage={(page) => setTargetPage(page)} /> : regionSelection && selectedPaper ? <RegionExplanationPanel key={`${selectedId}:${regionSelection.page}:${regionSelection.bbox.join(",")}`} paper={selectedPaper} selection={regionSelection} visionModelConfigured={settingsStatus?.vision_model.configured ?? null} /> : <TextExplanationPanel key={`${selectedId ?? "none"}:${textSelection?.page ?? "none"}:${textSelection?.selectedText ?? ""}`} paper={selectedPaper} selection={textSelection} textModelConfigured={settingsStatus?.text_model.configured ?? null} />}
        </aside>
      </main>
      <button
        type="button"
        className="navigation-edge-toggle"
        aria-label={navigationOpen ? "隐藏左侧导航" : "展开左侧导航"}
        aria-controls="workspace-navigation"
        aria-expanded={navigationOpen}
        title={navigationOpen ? "隐藏导航" : "展开导航"}
        onClick={() => setNavigationOpen((open) => !open)}
      ><span>{navigationOpen ? <ChevronLeft size={15} /> : <ChevronRight size={15} />}</span></button>
      {settingsOpen && <SettingsPanel onClose={() => setSettingsOpen(false)} onStatusChange={setSettingsStatus} />}
    </div>
  );
}
