import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getDocument, TextLayer } from "pdfjs-dist";
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
  pages: FakePage[];
}

interface FakePage {
  pageNumber: number;
  getViewport: ReturnType<typeof vi.fn>;
  render: ReturnType<typeof vi.fn>;
  getTextContent: ReturnType<typeof vi.fn>;
}

function fakeDocument(pageCount = 2): FakeDocument {
  const pages = Array.from({ length: pageCount }, (_, index): FakePage => ({
    pageNumber: index + 1,
    getViewport: vi.fn(({ scale }: { scale: number }) => ({
      width: 600.25 * scale,
      height: 800.5 * scale,
      scale,
      rotation: 0,
      userUnit: 1,
      rawDims: { pageWidth: 600.25, pageHeight: 800.5, pageX: 0, pageY: 0 },
    })),
    render: vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() })),
    getTextContent: vi.fn().mockResolvedValue({ items: [] }),
  }));
  return {
    numPages: pageCount,
    destroy: vi.fn().mockResolvedValue(undefined),
    getPage: vi.fn(async (pageNumber: number) => pages[pageNumber - 1]),
    pages,
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

  it("shares one viewport and one text-content load between canvas and text layer", async () => {
    const document = fakeDocument(1);
    vi.mocked(getDocument).mockReturnValue(loadingTask(document) as never);

    const view = render(<PdfReader fileUrl="paper.pdf" filename="paper.pdf" />);
    await screen.findByLabelText("PDF page 1");
    await waitFor(() => expect(TextLayer).toHaveBeenCalledTimes(1));

    const page = document.pages[0];
    const viewport = page.getViewport.mock.results[0]?.value;
    expect(page.getViewport).toHaveBeenCalledTimes(1);
    expect(page.getTextContent).toHaveBeenCalledTimes(1);
    expect(page.render.mock.calls[0]?.[0].viewport).toBe(viewport);
    expect(vi.mocked(TextLayer).mock.calls[0]?.[0].viewport).toBe(viewport);
    const section = view.container.querySelector<HTMLElement>(".pdf-page");
    expect(section?.style.getPropertyValue("--scale-factor")).toBe("1");
    expect(section?.style.getPropertyValue("--user-unit")).toBe("1");
    expect(section?.style.getPropertyValue("--total-scale-factor")).toContain("--scale-factor");
    expect(section?.style.getPropertyValue("--scale-round-x")).toBe("0.01px");
    expect(section?.style.getPropertyValue("--scale-round-y")).toBe("0.01px");
    expect(view.container.querySelector(".textLayer")).toBeInTheDocument();
  });

  it("uses exact CSS dimensions and backing-store ratios after pixel rounding", async () => {
    vi.spyOn(window, "devicePixelRatio", "get").mockReturnValue(2);
    const document = fakeDocument(1);
    vi.mocked(getDocument).mockReturnValue(loadingTask(document) as never);

    render(<PdfReader fileUrl="paper.pdf" filename="paper.pdf" />);
    const canvas = await screen.findByLabelText("PDF page 1") as HTMLCanvasElement;
    await waitFor(() => expect(document.pages[0].render).toHaveBeenCalled());

    expect(canvas.style.width).toBe("600.25px");
    expect(canvas.style.height).toBe("800.5px");
    expect(canvas.width).toBe(1201);
    expect(canvas.height).toBe(1601);
    const options = document.pages[0].render.mock.calls[0]?.[0];
    expect(options.transform).toEqual([
      1201 / 600.25, 0, 0, 1601 / 800.5, 0, 0,
    ]);
  });

  it("supports zoom and page jumps", async () => {
    const document = fakeDocument(2);
    vi.mocked(getDocument).mockReturnValue(loadingTask(document) as never);
    render(<PdfReader fileUrl="paper.pdf" filename="paper.pdf" />);
    await screen.findAllByRole("region");
    await screen.findByLabelText("PDF page 2");

    fireEvent.click(screen.getByRole("button", { name: "放大" }));
    expect(screen.getByText("125%")).toBeInTheDocument();
    for (let index = 0; index < 5; index += 1) {
      fireEvent.click(screen.getByRole("button", { name: "放大" }));
    }
    expect(screen.getByText("250%")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "放大" })).toBeDisabled();
    for (let index = 0; index < 8; index += 1) {
      fireEvent.click(screen.getByRole("button", { name: "缩小" }));
    }
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "缩小" })).toBeDisabled();
    await waitFor(() => expect(document.pages[0].getTextContent).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText("当前页"), { target: { value: "2" } });
    expect(HTMLElement.prototype.scrollIntoView).not.toHaveBeenCalled();
    fireEvent.keyDown(screen.getByLabelText("当前页"), { key: "Enter" });
    expect(HTMLElement.prototype.scrollIntoView).toHaveBeenCalled();
    expect(screen.getByLabelText("当前页")).toHaveValue(2);
  });

  it("exits region selection with Escape", async () => {
    const document = fakeDocument(1);
    vi.mocked(getDocument).mockReturnValue(loadingTask(document) as never);
    render(<PdfReader fileUrl="paper.pdf" filename="paper.pdf" />);
    await screen.findByLabelText("PDF page 1");

    const regionButton = screen.getByRole("button", { name: "框选区域" });
    fireEvent.click(regionButton);
    expect(regionButton).toHaveAttribute("aria-pressed", "true");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(regionButton).toHaveAttribute("aria-pressed", "false");
  });
});
