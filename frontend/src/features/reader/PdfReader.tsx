import { ChevronLeft, ChevronRight, Scan, ZoomIn, ZoomOut } from "lucide-react";
import {
  GlobalWorkerOptions,
  TextLayer,
  getDocument,
  type PDFDocumentProxy,
  type PDFPageProxy,
} from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

GlobalWorkerOptions.workerSrc = workerUrl;

const MIN_SCALE = 0.5;
const MAX_SCALE = 2.5;
const SCALE_STEP = 0.25;

interface PdfReaderProps {
  fileUrl: string;
  filename: string;
  targetPage?: number | null;
  onTextSelection?: (selection: TextSelection | null) => void;
  onRegionSelection?: (selection: RegionSelection) => void;
}

export interface TextSelection {
  page: number;
  selectedText: string;
  contextBefore: string;
  contextAfter: string;
}

export interface RegionSelection {
  page: number;
  bbox: [number, number, number, number];
  viewportRotation: number;
  nearbyText: string;
  image: Blob;
}

export function backingStoreCrop(
  bbox: [number, number, number, number],
  width: number,
  height: number,
) {
  return {
    sx: Math.floor(bbox[0] * width),
    sy: Math.floor(bbox[1] * height),
    sw: Math.max(1, Math.ceil((bbox[2] - bbox[0]) * width)),
    sh: Math.max(1, Math.ceil((bbox[3] - bbox[1]) * height)),
  };
}

function PageCanvas({ page, scale, canvasRef }: { page: PDFPageProxy; scale: number; canvasRef: React.RefObject<HTMLCanvasElement | null> }) {

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const viewport = page.getViewport({ scale });
    const outputScale = window.devicePixelRatio || 1;
    const context = canvas.getContext("2d");
    if (!context) return;

    canvas.width = Math.floor(viewport.width * outputScale);
    canvas.height = Math.floor(viewport.height * outputScale);
    canvas.style.width = `${Math.floor(viewport.width)}px`;
    canvas.style.height = `${Math.floor(viewport.height)}px`;
    const renderTask = page.render({
      canvas,
      canvasContext: context,
      viewport,
      transform: outputScale === 1 ? undefined : [outputScale, 0, 0, outputScale, 0, 0],
    });

    void renderTask.promise.catch((error: unknown) => {
      if (!(error instanceof Error && error.name === "RenderingCancelledException")) {
        throw error;
      }
    });
    return () => renderTask.cancel();
  }, [page, scale]);

  return <canvas ref={canvasRef} aria-label={`PDF page ${page.pageNumber}`} />;
}

function PdfPage({ document, pageNumber, scale, onTextSelection, regionMode, onRegionSelection }: {
  document: PDFDocumentProxy;
  pageNumber: number;
  scale: number;
  onTextSelection?: (selection: TextSelection | null) => void;
  regionMode: boolean;
  onRegionSelection?: (selection: RegionSelection) => void;
}) {
  const [page, setPage] = useState<PDFPageProxy | null>(null);
  const [plainText, setPlainText] = useState("");
  const textLayerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const startRef = useRef<{ x: number; y: number } | null>(null);
  const [draft, setDraft] = useState<[number, number, number, number] | null>(null);

  useEffect(() => {
    let active = true;
    setPage(null);
    void document.getPage(pageNumber).then((loadedPage) => {
      if (active) {
        setPage(loadedPage);
        void loadedPage.getTextContent().then((content) => {
          if (active) {
            setPlainText(content.items.map((item) => "str" in item ? item.str : "").join(" "));
          }
        });
      }
    });
    return () => {
      active = false;
    };
  }, [document, pageNumber]);

  useEffect(() => {
    const container = textLayerRef.current;
    if (!page || !container) return;
    container.replaceChildren();
    let layer: TextLayer | null = null;
    void page.getTextContent().then((content) => {
      layer = new TextLayer({
        textContentSource: content,
        container,
        viewport: page.getViewport({ scale }),
      });
      return layer.render();
    });
    return () => layer?.cancel();
  }, [page, scale]);

  const captureSelection = () => {
    if (regionMode) return;
    const selection = window.getSelection();
    const selectedText = selection?.toString().trim() ?? "";
    if (!selectedText || !selection?.anchorNode || !textLayerRef.current?.contains(selection.anchorNode)) {
      onTextSelection?.(null);
      return;
    }
    const index = plainText.indexOf(selectedText);
    onTextSelection?.({
      page: pageNumber,
      selectedText,
      contextBefore: index < 0 ? "" : plainText.slice(Math.max(0, index - 3000), index),
      contextAfter: index < 0 ? "" : plainText.slice(index + selectedText.length, index + selectedText.length + 3000),
    });
  };

  const point = (event: ReactPointerEvent<HTMLElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    return {
      x: Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width)),
      y: Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height)),
    };
  };

  const beginRegion = (event: ReactPointerEvent<HTMLElement>) => {
    if (!regionMode) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    startRef.current = point(event);
  };

  const moveRegion = (event: ReactPointerEvent<HTMLElement>) => {
    if (!startRef.current) return;
    const end = point(event);
    setDraft([
      Math.min(startRef.current.x, end.x), Math.min(startRef.current.y, end.y),
      Math.max(startRef.current.x, end.x), Math.max(startRef.current.y, end.y),
    ]);
  };

  const finishRegion = (event: ReactPointerEvent<HTMLElement>) => {
    const start = startRef.current;
    startRef.current = null;
    if (!start || !page || !canvasRef.current) return;
    const end = point(event);
    const bbox: [number, number, number, number] = [
      Math.min(start.x, end.x), Math.min(start.y, end.y),
      Math.max(start.x, end.x), Math.max(start.y, end.y),
    ];
    setDraft(bbox);
    if ((bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) < 0.0001) return;
    const canvas = canvasRef.current;
    const { sx, sy, sw, sh } = backingStoreCrop(bbox, canvas.width, canvas.height);
    const ratio = Math.min(1, 1600 / Math.max(sw, sh));
    const crop = window.document.createElement("canvas");
    crop.width = Math.max(1, Math.round(sw * ratio));
    crop.height = Math.max(1, Math.round(sh * ratio));
    crop.getContext("2d")?.drawImage(canvas, sx, sy, sw, sh, 0, 0, crop.width, crop.height);
    const pageRect = event.currentTarget.getBoundingClientRect();
    const selectionRect = {
      left: pageRect.left + bbox[0] * pageRect.width - 40,
      top: pageRect.top + bbox[1] * pageRect.height - 40,
      right: pageRect.left + bbox[2] * pageRect.width + 40,
      bottom: pageRect.top + bbox[3] * pageRect.height + 40,
    };
    const nearbyText = Array.from(textLayerRef.current?.querySelectorAll("span") ?? [])
      .filter((span) => {
        const rect = span.getBoundingClientRect();
        return rect.right >= selectionRect.left && rect.left <= selectionRect.right
          && rect.bottom >= selectionRect.top && rect.top <= selectionRect.bottom;
      })
      .map((span) => span.textContent ?? "").join(" ").slice(0, 6000);
    crop.toBlob((image) => {
      if (image) onRegionSelection?.({
        page: pageNumber,
        bbox,
        viewportRotation: page.getViewport({ scale }).rotation,
        nearbyText,
        image,
      });
    }, "image/png");
  };

  return (
    <section className={`pdf-page${regionMode ? " region-mode" : ""}`} data-page-number={pageNumber} aria-label={`第 ${pageNumber} 页`} onMouseUp={captureSelection} onPointerDown={beginRegion} onPointerMove={moveRegion} onPointerUp={finishRegion}>
      {page ? <PageCanvas page={page} scale={scale} canvasRef={canvasRef} /> : <div className="page-loading" />}
      {page && <div ref={textLayerRef} className="text-layer" />}
      {draft && <div className="region-draft" style={{ left: `${draft[0] * 100}%`, top: `${draft[1] * 100}%`, width: `${(draft[2] - draft[0]) * 100}%`, height: `${(draft[3] - draft[1]) * 100}%` }} />}
    </section>
  );
}

export function PdfReader({ fileUrl, filename, targetPage, onTextSelection, onRegionSelection }: PdfReaderProps) {
  const [document, setDocument] = useState<PDFDocumentProxy | null>(null);
  const [scale, setScale] = useState(1);
  const [currentPage, setCurrentPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pagesRef = useRef<HTMLDivElement>(null);
  const [regionMode, setRegionMode] = useState(false);

  useEffect(() => {
    let active = true;
    let loaded: PDFDocumentProxy | null = null;
    const task = getDocument({ url: fileUrl });
    setDocument(null);
    setScale(1);
    setCurrentPage(1);
    setLoading(true);
    setError(null);

    void task.promise
      .then((nextDocument) => {
        loaded = nextDocument;
        if (active) {
          setDocument(nextDocument);
          setLoading(false);
        } else {
          void nextDocument.destroy();
        }
      })
      .catch(() => {
        if (active) {
          setError("PDF 加载失败");
          setLoading(false);
        }
      });

    return () => {
      active = false;
      void task.destroy();
      if (loaded) void loaded.destroy();
    };
  }, [fileUrl]);

  useEffect(() => {
    const root = pagesRef.current;
    if (!root || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible instanceof HTMLElement) {
          setCurrentPage(Number(visible.dataset.pageNumber));
        }
      },
      { root, threshold: [0.25, 0.5, 0.75] },
    );
    root.querySelectorAll<HTMLElement>("[data-page-number]").forEach((page) => observer.observe(page));
    return () => observer.disconnect();
  }, [document]);

  const goToPage = (pageNumber: number) => {
    if (!document) return;
    const page = Math.min(Math.max(pageNumber, 1), document.numPages);
    setCurrentPage(page);
    pagesRef.current
      ?.querySelector<HTMLElement>(`[data-page-number="${page}"]`)
      ?.scrollIntoView({ block: "start" });
  };

  useEffect(() => {
    if (targetPage) goToPage(targetPage);
  }, [targetPage, document]);

  return (
    <div className="reader-shell">
      <header className="reader-toolbar">
        <div className="reader-title" title={filename}>{filename}</div>
        <div className="toolbar-group" aria-label="页码控制">
          <button type="button" className="icon-button" title="上一页" aria-label="上一页" onClick={() => goToPage(currentPage - 1)} disabled={!document || currentPage <= 1}>
            <ChevronLeft size={18} />
          </button>
          <label className="page-counter">
            <span className="sr-only">当前页</span>
            <input
              aria-label="当前页"
              type="number"
              min={1}
              max={document?.numPages ?? 1}
              value={currentPage}
              onChange={(event) => goToPage(Number(event.target.value))}
            />
            <span>/ {document?.numPages ?? "—"}</span>
          </label>
          <button type="button" className="icon-button" title="下一页" aria-label="下一页" onClick={() => goToPage(currentPage + 1)} disabled={!document || currentPage >= document.numPages}>
            <ChevronRight size={18} />
          </button>
        </div>
        <div className="toolbar-group" aria-label="缩放控制">
          <button type="button" className="icon-button" title="框选区域" aria-label="框选区域" aria-pressed={regionMode} onClick={() => setRegionMode((value) => !value)} disabled={!document}>
            <Scan size={18} />
          </button>
          <button type="button" className="icon-button" title="缩小" aria-label="缩小" onClick={() => setScale((value) => Math.max(MIN_SCALE, value - SCALE_STEP))} disabled={scale <= MIN_SCALE}>
            <ZoomOut size={18} />
          </button>
          <span className="scale-value">{Math.round(scale * 100)}%</span>
          <button type="button" className="icon-button" title="放大" aria-label="放大" onClick={() => setScale((value) => Math.min(MAX_SCALE, value + SCALE_STEP))} disabled={scale >= MAX_SCALE}>
            <ZoomIn size={18} />
          </button>
        </div>
      </header>
      <div ref={pagesRef} className="pdf-pages" data-testid="pdf-pages">
        {loading && <div className="reader-state">正在加载 PDF…</div>}
        {error && <div className="reader-state error-text">{error}</div>}
        {document && Array.from({ length: document.numPages }, (_, index) => (
          <PdfPage key={index + 1} document={document} pageNumber={index + 1} scale={scale} onTextSelection={onTextSelection} regionMode={regionMode} onRegionSelection={onRegionSelection} />
        ))}
      </div>
    </div>
  );
}
