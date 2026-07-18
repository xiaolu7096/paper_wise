import { useState } from "react";

import { assetUrl, createAnnotation, explainRegion, type ExplainRegionResponse, type Paper } from "../../api/client";
import type { RegionSelection } from "../reader/PdfReader";

interface Props {
  paper: Paper;
  selection: RegionSelection;
}

export function RegionExplanationPanel({ paper, selection }: Props) {
  const [question, setQuestion] = useState("请解释这个区域");
  const [result, setResult] = useState<ExplainRegionResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const run = async () => {
    if (!question.trim()) return;
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
    <div className="selection-preview"><strong>第 {selection.page} 页区域</strong></div>
    <textarea aria-label="区域问题" value={question} maxLength={2000} onChange={(event) => setQuestion(event.target.value)} />
    <button type="button" disabled={busy || !question.trim()} onClick={() => void run()}>{busy ? "解释中…" : "解释区域"}</button>
    {error && <div role="alert" className="error-banner">{error}</div>}
    {result && <div className="explanation-result">
      <img src={assetUrl(paper.paper_id, result.asset_id)} alt="已选择的论文区域" />
      <p>{result.explanation}</p><small>{result.model}</small>
      <button type="button" disabled={saved} onClick={() => void createAnnotation(paper.paper_id, { kind: "region", page: result.page, bbox: result.bbox, viewport_rotation: result.viewport_rotation, asset_id: result.asset_id, ai_explanation: result.explanation }).then(() => setSaved(true)).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "保存失败"))}>{saved ? "已保存" : "保存"}</button>
    </div>}
  </div>;
}
