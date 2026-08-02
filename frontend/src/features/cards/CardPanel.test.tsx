import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { generateCard, getCard, PaperwiseApiError, type CardResponse, type Paper } from "../../api/client";
import { CardPanel } from "./CardPanel";

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  getCard: vi.fn(), generateCard: vi.fn(),
}));

const paper = { paper_id: "a".repeat(64), filename: "p.pdf", title: null, page_count: 2, status: "ready", stage: "completed", error: null, created_at: "now", updated_at: "now" } as Paper;
const response: CardResponse = {
  schema_version: 2,
  content_markdown: "# 论文速读\n\n## 一句话总结\n**中文总结** [S1]\n\n## 动态章节\n- 内容\n\n<script>alert(1)</script>",
  citations: [{ source_id: "S1", page: 2, chunk_id: "2-01", quote: "source" }],
  model: "model", cached: false, updated_at: "now",
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(getCard).mockRejectedValue(new PaperwiseApiError(404, { error: { code: "CARD_NOT_FOUND", message: "missing", details: null } }));
});
afterEach(cleanup);

it("renders one safe report, navigates citations, and regenerates", async () => {
  const navigate = vi.fn();
  vi.mocked(generateCard).mockResolvedValue(response);
  const view = render(<CardPanel paper={paper} textModelConfigured onNavigatePage={navigate} />);
  fireEvent.click(await screen.findByRole("button", { name: "生成速读报告" }));

  expect(await screen.findByRole("heading", { name: "论文速读" })).toBeInTheDocument();
  expect(screen.getByText("中文总结").tagName).toBe("STRONG");
  expect(view.container.querySelectorAll("article")).toHaveLength(1);
  expect(view.container.querySelector("script")).toBeNull();
  expect(screen.getByText("<script>alert(1)</script>")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "[S1]" }));
  expect(navigate).toHaveBeenCalledWith(2);

  fireEvent.click(screen.getByRole("button", { name: "重新生成速读报告" }));
  await waitFor(() => expect(generateCard).toHaveBeenLastCalledWith(paper.paper_id, true));
});

it("prevents duplicate generation while a report request is pending", async () => {
  let resolveGeneration!: (value: CardResponse) => void;
  vi.mocked(generateCard).mockReturnValue(new Promise((resolve) => { resolveGeneration = resolve; }));
  render(<CardPanel paper={paper} textModelConfigured onNavigatePage={vi.fn()} />);

  const generateButton = await screen.findByRole("button", { name: "生成速读报告" });
  fireEvent.click(generateButton);
  fireEvent.click(generateButton);
  expect(generateCard).toHaveBeenCalledTimes(1);
  expect(generateButton).toBeDisabled();

  resolveGeneration(response);
  expect(await screen.findByRole("heading", { name: "论文速读" })).toBeInTheDocument();
});
