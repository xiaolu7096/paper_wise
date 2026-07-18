import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { createAnnotation, deleteAnnotation, getAnnotations, type Paper } from "../../api/client";
import { NotesPanel } from "./NotesPanel";

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  getAnnotations: vi.fn(), createAnnotation: vi.fn(), deleteAnnotation: vi.fn(),
}));

const paper = { paper_id: "a".repeat(64), filename: "p.pdf", title: null, page_count: 1, status: "ready", stage: "completed", error: null, created_at: "now", updated_at: "now" } as Paper;

beforeEach(() => { vi.resetAllMocks(); vi.mocked(getAnnotations).mockResolvedValue([]); });
afterEach(cleanup);

it("loads, creates, and deletes notes for the selected paper", async () => {
  const created = { annotation_id: "11111111-1111-4111-8111-111111111111", paper_id: paper.paper_id, kind: "note", page: null, bbox: null, viewport_rotation: null, selected_text: null, asset_id: null, ai_explanation: null, note: "remember", created_at: "now", updated_at: "now" } as const;
  vi.mocked(createAnnotation).mockResolvedValue(created);
  vi.mocked(deleteAnnotation).mockResolvedValue();
  render(<NotesPanel paper={paper} />);
  await waitFor(() => expect(getAnnotations).toHaveBeenCalledWith(paper.paper_id));
  fireEvent.change(screen.getByLabelText("新笔记"), { target: { value: "remember" } });
  fireEvent.click(screen.getByRole("button", { name: "添加笔记" }));
  expect(await screen.findByText("remember")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "删除笔记" }));
  await waitFor(() => expect(screen.queryByText("remember")).not.toBeInTheDocument());
});
