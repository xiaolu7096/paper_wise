import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";

import {
  generateCard,
  getCard,
  PaperwiseApiError,
  type CardResponse,
  type Paper,
} from "../../api/client";
import { MarkdownReport } from "./MarkdownReport";

interface Props {
  paper: Paper | null;
  onNavigatePage: (page: number) => void;
}

export function CardPanel({ paper, onNavigatePage }: Props) {
  const [value, setValue] = useState<CardResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setValue(null);
    setError(null);
    if (!paper) return;
    void getCard(paper.paper_id).then(setValue).catch((reason: unknown) => {
      if (!(reason instanceof PaperwiseApiError && reason.code === "CARD_NOT_FOUND")) {
        setError(reason instanceof Error ? reason.message : "速读报告加载失败");
      }
    });
  }, [paper?.paper_id]);

  const generate = async (regenerate: boolean) => {
    if (!paper) return;
    setBusy(true);
    setError(null);
    try {
      setValue(await generateCard(paper.paper_id, regenerate));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "速读报告生成失败");
    } finally {
      setBusy(false);
    }
  };

  if (!paper) return <div className="panel-empty">请先选择论文</div>;
  if (!value) return <div className="card-empty">
    {error && <div role="alert" className="error-banner">{error}</div>}
    <button type="button" disabled={busy || paper.status !== "ready"} onClick={() => void generate(false)}>{busy ? "生成中…" : "生成速读报告"}</button>
  </div>;
  return <div className="report-panel">
    <header>
      <small>{value.model} · {value.cached ? "已缓存" : "刚生成"}</small>
      <button type="button" aria-label="重新生成速读报告" disabled={busy} onClick={() => void generate(true)}><RefreshCw size={15} /></button>
    </header>
    {error && <div role="alert" className="error-banner">{error}</div>}
    <MarkdownReport markdown={value.content_markdown} citations={value.citations} onNavigatePage={onNavigatePage} />
  </div>;
}
