import { useState } from "react";

import { createAnnotation, explainText, type ExplainTextResponse, type Paper } from "../../api/client";
import type { TextSelection } from "../reader/PdfReader";

interface Props {
  paper: Paper | null;
  selection: TextSelection | null;
}

export function TextExplanationPanel({ paper, selection }: Props) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<ExplainTextResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const run = async (instruction: "explain" | "summarize" | "question") => {
    if (!paper || !selection) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await explainText(paper.paper_id, {
        page: selection.page,
        selected_text: selection.selectedText,
        instruction,
        question: instruction === "question" ? question : null,
        context_before: selection.contextBefore,
        context_after: selection.contextAfter,
      }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "解释失败");
    } finally {
      setBusy(false);
    }
  };

  if (!paper) return <div className="panel-empty">请先选择论文</div>;
  if (!selection) return <div className="panel-empty">请在 PDF 中选择文字</div>;
  return (
    <div className="explanation-panel">
      <div className="selection-preview"><strong>第 {selection.page} 页</strong><p>{selection.selectedText}</p></div>
      <div className="explanation-actions">
        <button type="button" disabled={busy} onClick={() => void run("explain")}>解释</button>
        <button type="button" disabled={busy} onClick={() => void run("summarize")}>总结</button>
      </div>
      <textarea aria-label="针对选中文字提问" value={question} maxLength={2000} onChange={(event) => setQuestion(event.target.value)} />
      <button type="button" disabled={busy || !question.trim()} onClick={() => void run("question")}>追问</button>
      {error && <div role="alert" className="error-banner">{error}</div>}
      {result && <div className="explanation-result"><p>{result.explanation}</p><small>{result.model}</small><button type="button" disabled={saved} onClick={() => void createAnnotation(paper.paper_id, { kind: "text", page: result.page, selected_text: result.selected_text, ai_explanation: result.explanation }).then(() => setSaved(true)).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "保存失败"))}>{saved ? "已保存" : "保存"}</button></div>}
    </div>
  );
}
