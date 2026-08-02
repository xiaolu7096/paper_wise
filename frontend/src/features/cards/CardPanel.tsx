import { LoaderCircle, RefreshCw } from "lucide-react";
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
  textModelConfigured: boolean | null;
}

export function CardPanel({ paper, onNavigatePage, textModelConfigured }: Props) {
  const [value, setValue] = useState<CardResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setValue(null);
    setError(null);
    if (!paper) return;
    void getCard(paper.paper_id).then((card) => {
      if (active) setValue(card);
    }).catch((reason: unknown) => {
      if (active && !(reason instanceof PaperwiseApiError && reason.code === "CARD_NOT_FOUND")) {
        setError(reason instanceof Error ? reason.message : "速读报告加载失败");
      }
    });
    return () => { active = false; };
  }, [paper?.paper_id]);

  const disabledReason = !paper
    ? "请先选择论文"
    : paper.status !== "ready"
      ? `论文${paper.status === "failed" ? "处理失败" : "尚未处理完成"}`
      : textModelConfigured === null
        ? "正在读取文本模型配置"
        : !textModelConfigured
          ? "请先在 API 配置中启用文本模型"
          : null;

  const generate = async (regenerate: boolean) => {
    if (!paper || disabledReason || busy) return;
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
    {disabledReason && <p className="model-notice">{disabledReason}</p>}
    <button type="button" title={disabledReason ?? "生成速读报告"} disabled={busy || Boolean(disabledReason)} onClick={() => void generate(false)}>{busy ? <><LoaderCircle className="spin" size={16} />生成中…</> : "生成速读报告"}</button>
  </div>;
  return <div className="report-panel">
    <header>
      <small>{value.model} · {value.cached ? "已缓存" : "刚生成"}</small>
      <button type="button" className="icon-button ghost" aria-label="重新生成速读报告" title={disabledReason ?? "重新生成速读报告"} disabled={busy || Boolean(disabledReason)} onClick={() => void generate(true)}><RefreshCw className={busy ? "spin" : undefined} size={16} /></button>
    </header>
    {error && <div role="alert" className="error-banner">{error}</div>}
    <MarkdownReport markdown={value.content_markdown} citations={value.citations} onNavigatePage={onNavigatePage} />
  </div>;
}
