import type { ReactNode } from "react";

import type { CardResponse } from "../../api/client";

type Citation = CardResponse["citations"][number];

interface Props {
  markdown: string;
  citations: Citation[];
  onNavigatePage: (page: number) => void;
}

interface Block {
  kind: "heading" | "paragraph" | "list";
  level?: number;
  lines: string[];
}

export function MarkdownReport({ markdown, citations, onNavigatePage }: Props) {
  const byId = new Map(citations.map((citation) => [citation.source_id, citation]));
  return (
    <article className="report-content">
      {blocks(markdown).map((block, index) => {
        if (block.kind === "heading") {
          const content = inline(block.lines[0], byId, onNavigatePage);
          if (block.level === 1) return <h1 key={index}>{content}</h1>;
          if (block.level === 2) return <h2 key={index}>{content}</h2>;
          return <h3 key={index}>{content}</h3>;
        }
        if (block.kind === "list") {
          return <ul key={index}>{block.lines.map((line, item) => (
            <li key={item}>{inline(line, byId, onNavigatePage)}</li>
          ))}</ul>;
        }
        return <p key={index}>{inline(block.lines.join(" "), byId, onNavigatePage)}</p>;
      })}
    </article>
  );
}

function blocks(markdown: string): Block[] {
  const result: Block[] = [];
  let paragraph: string[] = [];
  let list: string[] = [];
  const flush = () => {
    if (paragraph.length) result.push({ kind: "paragraph", lines: paragraph });
    if (list.length) result.push({ kind: "list", lines: list });
    paragraph = [];
    list = [];
  };
  for (const raw of markdown.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) {
      flush();
      continue;
    }
    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    if (heading) {
      flush();
      result.push({ kind: "heading", level: heading[1].length, lines: [heading[2]] });
    } else if (/^[-*]\s+/.test(line)) {
      if (paragraph.length) flush();
      list.push(line.replace(/^[-*]\s+/, ""));
    } else {
      if (list.length) flush();
      paragraph.push(line);
    }
  }
  flush();
  return result;
}

function inline(
  text: string,
  citations: Map<string, Citation>,
  onNavigatePage: (page: number) => void,
): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|\[S(?:[1-9]|1[0-2])\])/g).filter(Boolean).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    const citation = citations.get(part.slice(1, -1));
    if (citation) {
      return <button key={index} type="button" className="report-citation" title={citation.quote} onClick={() => onNavigatePage(citation.page)}>{part}</button>;
    }
    return part;
  });
}
