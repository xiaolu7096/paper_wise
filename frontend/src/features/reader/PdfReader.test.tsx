import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getDocument } from "pdfjs-dist";
import { backingStoreCrop, PdfReader } from "./PdfReader";

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: vi.fn(),
  TextLayer: vi.fn(function () { return { render: vi.fn().mockResolvedValue(undefined), cancel: vi.fn() }; }),
}));

interface FakeDocument {
  numPages: number;
  getPage: ReturnType<typeof vi.fn>;
  destroy: ReturnType<typeof vi.fn>;
}

function fakeDocument(pageCount = 2): FakeDocument {
  return {
    numPages: pageCount,
    destroy: vi.fn().mockResolvedValue(undefined),
    getPage: vi.fn(async (pageNumber: number) => ({
      pageNumber,
      getViewport: ({ scale }: { scale: number }) => ({
        width: 600 * scale,
        height: 800 * scale,
      }),
      render: vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() })),
      getTextContent: vi.fn().mockResolvedValue({ items: [] }),
    })),
  };
}

function loadingTask(document: FakeDocument) {
  return {
    promise: Promise.resolve(document),
    destroy: vi.fn().mockResolvedValue(undefined),
  };
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({} as CanvasRenderingContext2D);
  HTMLElement.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("PdfReader", () => {
  it("maps normalized viewport boxes to backing-store pixels at any DPR", () => {
    const bbox: [number, number, number, number] = [0.1, 0.2, 0.6, 0.7];
    expect(backingStoreCrop(bbox, 600, 800)).toEqual({ sx: 60, sy: 160, sw: 300, sh: 400 });
    expect(backingStoreCrop(bbox, 1200, 1600)).toEqual({ sx: 120, sy: 320, sw: 600, sh: 800 });
  });
  it("destroys the previous PDF document when the file changes", async () => {
    const first = fakeDocument(1);
    const second = fakeDocument(1);
    vi.mocked(getDocument)
      .mockReturnValueOnce(loadingTask(first) as never)
      .mockReturnValueOnce(loadingTask(second) as never);

    const view = render(<PdfReader fileUrl="first.pdf" filename="first.pdf" />);
    expect(await screen.findByLabelText("PDF page 1")).toBeInTheDocument();
    view.rerender(<PdfReader fileUrl="second.pdf" filename="second.pdf" />);

    await waitFor(() => expect(first.destroy).toHaveBeenCalledTimes(1));
    expect(await screen.findByLabelText("PDF page 1")).toBeInTheDocument();
  });

  it("supports zoom and page jumps", async () => {
    const document = fakeDocument(2);
    vi.mocked(getDocument).mockReturnValue(loadingTask(document) as never);
    render(<PdfReader fileUrl="paper.pdf" filename="paper.pdf" />);
    await screen.findAllByRole("region");
    await screen.findByLabelText("PDF page 2");

    fireEvent.click(screen.getByRole("button", { name: "放大" }));
    expect(screen.getByText("125%")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("当前页"), { target: { value: "2" } });
    expect(HTMLElement.prototype.scrollIntoView).toHaveBeenCalled();
    expect(screen.getByLabelText("当前页")).toHaveValue(2);
  });
});
