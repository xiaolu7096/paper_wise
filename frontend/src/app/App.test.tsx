import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AuthUser, Paper } from "../api/client";
import { App } from "./App";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    getCurrentUser: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    register: vi.fn(),
    listPapers: vi.fn(),
    deletePaper: vi.fn(),
    getPaper: vi.fn(),
    getTask: vi.fn(),
    getMessages: vi.fn(),
    getSettingsStatus: vi.fn(),
    retryPaper: vi.fn(),
    uploadPaper: vi.fn(),
    paperFileUrl: (paperId: string) => `http://test/api/papers/${paperId}/file`,
  };
});

vi.mock("../features/reader/PdfReader", () => ({
  PdfReader: ({ fileUrl, filename }: { fileUrl: string; filename: string }) => (
    <div data-testid="pdf-reader" data-file-url={fileUrl}>{filename}</div>
  ),
}));

import {
  deletePaper,
  getCurrentUser,
  getPaper,
  getMessages,
  getSettingsStatus,
  getTask,
  listPapers,
  login,
  logout,
  PaperwiseApiError,
  uploadPaper,
} from "../api/client";

const first: Paper = {
  paper_id: "a".repeat(64),
  filename: "first.pdf",
  title: null,
  page_count: 2,
  status: "queued",
  stage: "queued",
  error: null,
  created_at: "2026-07-15T00:00:00Z",
  updated_at: "2026-07-15T00:00:00Z",
};

const second: Paper = { ...first, paper_id: "b".repeat(64), filename: "second.pdf" };

const user: AuthUser = {
  user_id: "11111111-1111-4111-8111-111111111111",
  username: "admin",
  role: "admin",
  created_at: "2026-07-15T00:00:00Z",
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

beforeEach(() => {
  vi.resetAllMocks();
  window.localStorage.clear();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  vi.mocked(getCurrentUser).mockResolvedValue(user);
  vi.mocked(login).mockResolvedValue(user);
  vi.mocked(logout).mockResolvedValue(undefined);
  vi.mocked(deletePaper).mockResolvedValue(undefined);
  vi.mocked(getMessages).mockResolvedValue([]);
  vi.mocked(getSettingsStatus).mockResolvedValue({
    text_model: { configured: false, base_url: null, model: null, source: null },
    vision_model: { configured: false, base_url: null, model: null, source: null },
  });
  vi.mocked(getPaper).mockImplementation(async (paperId) =>
    paperId === second.paper_id ? second : first,
  );
  vi.mocked(getTask).mockResolvedValue({
    task_id: "11111111-1111-4111-8111-111111111111",
    paper_id: first.paper_id,
    kind: "ingest",
    status: "queued",
    stage: "queued",
    progress: 0,
    error: null,
    created_at: first.created_at,
    updated_at: first.updated_at,
  });
});

describe("App", () => {
  it("shows the login form and delays paper loading when unauthenticated", async () => {
    vi.mocked(getCurrentUser).mockRejectedValue(new PaperwiseApiError(401, {
      error: { code: "AUTH_REQUIRED", message: "Auth required", details: null },
    }));

    render(<App />);

    expect(await screen.findByRole("button", { name: "登录" })).toBeInTheDocument();
    expect(listPapers).not.toHaveBeenCalled();
  });

  it("loads papers after login succeeds", async () => {
    vi.mocked(getCurrentUser).mockRejectedValue(new PaperwiseApiError(401, {
      error: { code: "AUTH_REQUIRED", message: "Auth required", details: null },
    }));
    vi.mocked(listPapers).mockResolvedValue([first]);

    render(<App />);
    fireEvent.change(await screen.findByLabelText("用户名"), { target: { value: "admin" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: "登录进入" }));

    expect(await screen.findByTestId("pdf-reader")).toHaveTextContent("first.pdf");
    expect(login).toHaveBeenCalledWith({ username: "admin", password: "password123" });
  });

  it("clears the workspace on logout", async () => {
    vi.mocked(listPapers).mockResolvedValue([first]);
    render(<App />);
    expect(await screen.findByTestId("pdf-reader")).toHaveTextContent("first.pdf");

    fireEvent.click(screen.getByRole("button", { name: "退出登录" }));

    await waitFor(() => expect(logout).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole("button", { name: "登录" })).toBeInTheDocument();
    expect(screen.queryByTestId("pdf-reader")).not.toBeInTheDocument();
  });

  it("restores the paper list and selects the most recent paper", async () => {
    vi.mocked(listPapers).mockResolvedValue([first, second]);

    render(<App />);

    expect(await screen.findByTestId("pdf-reader")).toHaveTextContent("first.pdf");
    expect(screen.getByTestId("pdf-reader")).toHaveAttribute(
      "data-file-url",
      `http://test/api/papers/${first.paper_id}/file`,
    );
    fireEvent.click(screen.getByRole("button", { name: "打开 second.pdf" }));
    expect(screen.getByTestId("pdf-reader")).toHaveTextContent("second.pdf");
  });

  it("selects an uploaded paper after refreshing the list", async () => {
    vi.mocked(listPapers).mockResolvedValueOnce([]).mockResolvedValueOnce([second]);
    vi.mocked(uploadPaper).mockResolvedValue({
      paper: second,
      task_id: "11111111-1111-4111-8111-111111111111",
      deduplicated: false,
    });
    render(<App />);
    await waitFor(() => expect(listPapers).toHaveBeenCalledTimes(1));

    const input = screen.getByLabelText("选择 PDF 文件");
    fireEvent.change(input, {
      target: { files: [new File(["pdf"], "second.pdf", { type: "application/pdf" })] },
    });

    expect(await screen.findByTestId("pdf-reader")).toHaveTextContent("second.pdf");
    expect(uploadPaper).toHaveBeenCalledTimes(1);
    expect(listPapers).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("progressbar", { name: "second.pdf 解析进度" })).toBeInTheDocument();
  });

  it("hides and restores the navigation from the edge control", async () => {
    vi.mocked(listPapers).mockResolvedValue([first]);
    render(<App />);
    await screen.findByTestId("pdf-reader");

    const navigation = screen.getByRole("complementary", { name: "全局导航" });
    fireEvent.click(screen.getByRole("button", { name: "隐藏左侧导航" }));

    expect(navigation).toHaveAttribute("aria-hidden", "true");
    expect(window.localStorage.getItem("paperwise-navigation-open")).toBe("false");
    fireEvent.click(screen.getByRole("button", { name: "展开左侧导航" }));
    expect(navigation).toHaveAttribute("aria-hidden", "false");

    for (let index = 0; index < 18; index += 1) {
      fireEvent.click(screen.getByRole("button", {
        name: index % 2 === 0 ? "隐藏左侧导航" : "展开左侧导航",
      }));
    }
    expect(navigation).toHaveAttribute("aria-hidden", "false");
    expect(screen.getByTestId("pdf-reader")).toHaveTextContent("first.pdf");
  });

  it("opens settings from the navigation and has no top settings button", async () => {
    vi.mocked(listPapers).mockResolvedValue([]);
    render(<App />);
    await waitFor(() => expect(listPapers).toHaveBeenCalledTimes(1));

    expect(screen.queryByRole("button", { name: "打开设置" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "API 配置" }));
    expect(await screen.findByRole("dialog", { name: "模型设置" })).toBeInTheDocument();
  });

  it("links to the standalone usage guide from the navigation", async () => {
    vi.mocked(listPapers).mockResolvedValue([]);
    render(<App />);
    await waitFor(() => expect(listPapers).toHaveBeenCalledTimes(1));

    expect(screen.getByRole("link", { name: "使用指南" })).toHaveAttribute("href", "/tutorial.html");
  });

  it("filters the paper list without changing the selected paper", async () => {
    vi.mocked(listPapers).mockResolvedValue([first, second]);
    render(<App />);
    await screen.findByTestId("pdf-reader");

    fireEvent.change(screen.getByLabelText("搜索论文"), { target: { value: "second" } });

    expect(screen.queryByRole("button", { name: "打开 first.pdf" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "打开 second.pdf" })).toBeInTheDocument();
    expect(screen.getByTestId("pdf-reader")).toHaveTextContent("first.pdf");
  });

  it("deletes the selected paper and opens the first remaining paper", async () => {
    vi.mocked(listPapers).mockResolvedValue([first, second]);
    render(<App />);
    expect(await screen.findByTestId("pdf-reader")).toHaveTextContent("first.pdf");

    fireEvent.click(screen.getByRole("button", { name: "删除 first.pdf" }));

    await waitFor(() => expect(deletePaper).toHaveBeenCalledWith(first.paper_id));
    expect(screen.getByTestId("pdf-reader")).toHaveTextContent("second.pdf");
    expect(screen.queryByRole("button", { name: "打开 first.pdf" })).not.toBeInTheDocument();
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining("无法恢复"));
  });

  it("deletes a non-selected paper without switching the reader", async () => {
    vi.mocked(listPapers).mockResolvedValue([first, second]);
    render(<App />);
    expect(await screen.findByTestId("pdf-reader")).toHaveTextContent("first.pdf");

    fireEvent.click(screen.getByRole("button", { name: "删除 second.pdf" }));

    await waitFor(() => expect(deletePaper).toHaveBeenCalledWith(second.paper_id));
    expect(screen.getByTestId("pdf-reader")).toHaveTextContent("first.pdf");
    expect(screen.queryByRole("button", { name: "打开 second.pdf" })).not.toBeInTheDocument();
  });

  it("does not delete when confirmation is cancelled", async () => {
    vi.mocked(listPapers).mockResolvedValue([first]);
    vi.mocked(window.confirm).mockReturnValue(false);
    render(<App />);
    await screen.findByTestId("pdf-reader");

    fireEvent.click(screen.getByRole("button", { name: "删除 first.pdf" }));

    expect(deletePaper).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "打开 first.pdf" })).toBeInTheDocument();
  });

  it("keeps the paper and shows an error when deletion fails", async () => {
    vi.mocked(listPapers).mockResolvedValue([first]);
    vi.mocked(deletePaper).mockRejectedValue(new Error("删除失败"));
    render(<App />);
    await screen.findByTestId("pdf-reader");

    fireEvent.click(screen.getByRole("button", { name: "删除 first.pdf" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("删除失败");
    expect(screen.getByRole("button", { name: "打开 first.pdf" })).toBeInTheDocument();
  });
});
