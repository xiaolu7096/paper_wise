import { Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { assetUrl, createAnnotation, deleteAnnotation, getAnnotations, type Annotation, type Paper } from "../../api/client";

export function NotesPanel({ paper }: { paper: Paper | null }) {
  const [items, setItems] = useState<Annotation[]>([]);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    if (!paper) return;
    try { setItems(await getAnnotations(paper.paper_id)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "笔记加载失败"); }
  };

  useEffect(() => { setItems([]); setNote(""); setError(null); void load(); }, [paper?.paper_id]);

  if (!paper) return <div className="panel-empty">请先选择论文</div>;
  return <div className="notes-panel">
    <form onSubmit={(event) => {
      event.preventDefault();
      if (!note.trim()) return;
      void createAnnotation(paper.paper_id, { kind: "note", note }).then((created) => {
        setItems((current) => [...current, created]); setNote("");
      }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "保存失败"));
    }}>
      <textarea aria-label="新笔记" maxLength={20000} value={note} onChange={(event) => setNote(event.target.value)} />
      <button type="submit" disabled={!note.trim()}>添加笔记</button>
    </form>
    {error && <div role="alert" className="error-banner">{error}</div>}
    <div className="annotation-list">{items.map((item) => <article key={item.annotation_id}>
      <header><span>{item.page ? `第 ${item.page} 页` : "论文笔记"}</span><button type="button" aria-label="删除笔记" onClick={() => void deleteAnnotation(paper.paper_id, item.annotation_id).then(() => setItems((current) => current.filter((value) => value.annotation_id !== item.annotation_id)))}><Trash2 size={14} /></button></header>
      {item.selected_text && <blockquote>{item.selected_text}</blockquote>}
      {item.ai_explanation && <p>{item.ai_explanation}</p>}
      {item.note && <p>{item.note}</p>}
      {item.asset_id && <img src={assetUrl(paper.paper_id, item.asset_id)} alt="论文区域笔记" />}
    </article>)}</div>
  </div>;
}
