import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Paper } from "../api/client";
import { App } from "./App";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    listPapers: vi.fn(),
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

import { getPaper, getTask, listPapers, uploadPaper } from "../api/client";

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

afterEach(cleanup);

beforeEach(() => {
  vi.resetAllMocks();
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
    fireEvent.click(screen.getByRole("button", { name: /second.pdf/ }));
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
});
