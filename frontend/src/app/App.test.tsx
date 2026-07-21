import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Paper } from "../api/client";
import { App } from "./App";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    listPapers: vi.fn(),
    deletePaper: vi.fn(),
    getPaper: vi.fn(),
    getTask: vi.fn(),
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

import { deletePaper, getPaper, getTask, listPapers, uploadPaper } from "../api/client";

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

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

beforeEach(() => {
  vi.resetAllMocks();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  vi.mocked(deletePaper).mockResolvedValue(undefined);
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
