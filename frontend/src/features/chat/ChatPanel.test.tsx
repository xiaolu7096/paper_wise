import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { askPaper, clearMessages, getMessages, type Message, type Paper } from "../../api/client";
import { ChatPanel } from "./ChatPanel";

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  askPaper: vi.fn(), clearMessages: vi.fn(), getMessages: vi.fn(),
}));

const paper = { paper_id: "a".repeat(64), filename: "p.pdf", title: null, page_count: 1, status: "ready", stage: "completed", error: null, created_at: "now", updated_at: "now" } as Paper;
const message = { message_id: "11111111-1111-4111-8111-111111111111", paper_id: paper.paper_id, role: "assistant", content: "answer", citations: [], created_at: "now" } as Message;

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(getMessages).mockResolvedValue([message]);
  vi.mocked(askPaper).mockResolvedValue({ user_message_id: "11111111-1111-4111-8111-111111111113", assistant_message_id: "11111111-1111-4111-8111-111111111114", answer: "answer", citations: [] });
  vi.mocked(clearMessages).mockResolvedValue();
});
afterEach(cleanup);

it("requires confirmation before clearing the current conversation", async () => {
  render(<ChatPanel paper={paper} textModelConfigured onNavigatePage={vi.fn()} />);
  const clearButton = await screen.findByRole("button", { name: "清空当前会话" });
  fireEvent.click(clearButton);
  expect(clearMessages).not.toHaveBeenCalled();
  fireEvent.keyDown(window, { key: "Escape" });
  expect(screen.queryByRole("alertdialog", { name: "确认清空当前会话" })).not.toBeInTheDocument();
  expect(clearButton).toHaveFocus();
  fireEvent.click(clearButton);
  fireEvent.click(screen.getByRole("button", { name: "确认清空" }));
  await waitFor(() => expect(clearMessages).toHaveBeenCalledWith(paper.paper_id));
  expect(screen.queryByText("answer")).not.toBeInTheDocument();
});

it("sends with Ctrl+Enter and prevents a duplicate submission", async () => {
  let resolveQuestion!: () => void;
  vi.mocked(askPaper).mockReturnValue(new Promise((resolve) => { resolveQuestion = () => resolve({ user_message_id: "11111111-1111-4111-8111-111111111113", assistant_message_id: "11111111-1111-4111-8111-111111111114", answer: "answer", citations: [] }); }));
  render(<ChatPanel paper={paper} textModelConfigured onNavigatePage={vi.fn()} />);
  const input = screen.getByLabelText("向论文提问");
  fireEvent.change(input, { target: { value: "question" } });
  fireEvent.keyDown(input, { key: "Enter", ctrlKey: true });
  fireEvent.click(screen.getByRole("button", { name: "发送问题" }));
  expect(askPaper).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("button", { name: "发送问题" })).toBeDisabled();
  resolveQuestion();
  await waitFor(() => expect(askPaper).toHaveBeenCalledWith(paper.paper_id, "question"));
});

it("explains why chat is unavailable without a text model", async () => {
  render(<ChatPanel paper={paper} textModelConfigured={false} onNavigatePage={vi.fn()} />);
  expect(screen.getByLabelText("向论文提问")).toHaveAttribute("placeholder", "请先在 API 配置中启用文本模型");
  expect(screen.getByRole("button", { name: "发送问题" })).toBeDisabled();
});
