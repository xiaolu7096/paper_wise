import { LoaderCircle, Send } from "lucide-react";
import { useState } from "react";

import { assetUrl, createAnnotation, explainRegion, type ExplainRegionResponse, type Paper } from "../../api/client";
import type { RegionSelection } from "../reader/PdfReader";

interface Props {
  paper: Paper;
  selection: RegionSelection;
  visionModelConfigured: boolean | null;
}

export function RegionExplanationPanel({ paper, selection, visionModelConfigured }: Props) {
  const [question, setQuestion] = useState("请解释这个区域");
  const [result, setResult] = useState<ExplainRegionResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const disabledReason = visionModelConfigured === null
    ? "正在读取视觉模型配置"
    : !visionModelConfigured
      ? "请先在 API 配置中启用视觉模型"
      : null;

  const run = async () => {
    if (!question.trim() || disabledReason || busy) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await explainRegion(paper.paper_id, { ...selection, question }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "区域解释失败");
    } finally {
      setBusy(false);
    }
  };

  return <div className="explanation-panel">
    <div className="selection-preview"><div className="selection-meta"><span>区域选区</span><span>第 {selection.page} 页</span></div></div>
    {disabledReason && <p className="model-notice">{disabledReason}</p>}
    <div className="explanation-composer">
      <textarea aria-label="区域问题" value={question} maxLength={2000} onChange={(event) => setQuestion(event.target.value)} disabled={Boolean(disabledReason) || busy} />
      <button type="button" className="icon-button primary composer-send" aria-label="解释区域" title={disabledReason ?? "解释区域"} disabled={busy || Boolean(disabledReason) || !question.trim()} onClick={() => void run()}>{busy ? <LoaderCircle className="spin" size={17} /> : <Send size={17} />}</button>
    </div>
    {error && <div role="alert" className="error-banner">{error}</div>}
    {result && <div className="explanation-result">
      <img src={assetUrl(paper.paper_id, result.asset_id)} alt="已选择的论文区域" />
      <p>{result.explanation}</p><small>{result.model}</small>
      <button type="button" disabled={saved} onClick={() => void createAnnotation(paper.paper_id, { kind: "region", page: result.page, bbox: result.bbox, viewport_rotation: result.viewport_rotation, asset_id: result.asset_id, ai_explanation: result.explanation }).then(() => setSaved(true)).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "保存失败"))}>{saved ? "已保存" : "保存"}</button>
    </div>}
  </div>;
}
