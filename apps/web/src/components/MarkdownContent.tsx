import { useEffect, useId, useState, type ReactNode } from "react";
import mermaid from "mermaid";

type MarkdownContentProps = {
  source: string;
};

type RequestedSkillDetail = {
  id: string;
  content: string;
};

type ContentPart =
  | { type: "markdown"; source: string }
  | { type: "skillDetails"; details: RequestedSkillDetail[] };

type Block =
  | { type: "heading"; level: 1 | 2 | 3; text: string }
  | { type: "paragraph"; text: string }
  | { type: "blockquote"; text: string }
  | { type: "code"; code: string; language?: string }
  | { type: "table"; headers: string[]; rows: string[][] }
  | { type: "list"; ordered: boolean; items: string[] };

let mermaidInitialized = false;

function ensureMermaidInitialized() {
  if (mermaidInitialized) {
    return;
  }
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: "strict",
    theme: "default"
  });
  mermaidInitialized = true;
}

function isSafeUrl(url: string) {
  return /^(https?:|mailto:)/i.test(url);
}

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  const inlinePattern = /(\[[^\]]+\]\([^)]+\)|`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g;

  while ((match = inlinePattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }

    const token = match[0];
    const key = `${keyPrefix}-${match.index}`;
    const linkMatch = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);

    if (linkMatch) {
      const [, label, href] = linkMatch;
      nodes.push(
        isSafeUrl(href) ? (
          <a href={href} key={key} rel="noreferrer" target="_blank">
            {label}
          </a>
        ) : (
          token
        )
      );
    } else if (token.startsWith("`")) {
      nodes.push(<code key={key}>{token.slice(1, -1)}</code>);
    } else if (token.startsWith("**")) {
      nodes.push(<strong key={key}>{renderInline(token.slice(2, -2), `${key}-strong`)}</strong>);
    } else if (token.startsWith("*")) {
      nodes.push(<em key={key}>{renderInline(token.slice(1, -1), `${key}-em`)}</em>);
    }

    lastIndex = match.index + token.length;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return nodes;
}

function renderInlineWithBreaks(text: string, keyPrefix: string) {
  return text.split("\n").flatMap((line, index, lines) => {
    const nodes = renderInline(line, `${keyPrefix}-${index}`);
    return index < lines.length - 1 ? [...nodes, <br key={`${keyPrefix}-br-${index}`} />] : nodes;
  });
}

function parseMarkdown(source: string): Block[] {
  const blocks: Block[] = [];
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];

    if (!line.trim()) {
      index += 1;
      continue;
    }

    const fenceMatch = line.match(/^```([\w-]+)?\s*$/);
    if (fenceMatch) {
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].match(/^```\s*$/)) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push({ type: "code", code: codeLines.join("\n"), language: fenceMatch[1] });
      continue;
    }

    const headingMatch = line.match(/^(#{1,3})\s+(.+)$/);
    if (headingMatch) {
      blocks.push({
        type: "heading",
        level: headingMatch[1].length as 1 | 2 | 3,
        text: headingMatch[2]
      });
      index += 1;
      continue;
    }

    if (isTableStart(lines, index)) {
      const headers = splitTableRow(lines[index]);
      index += 2;
      const rows: string[][] = [];
      while (index < lines.length && isTableRow(lines[index])) {
        rows.push(normalizeTableRow(splitTableRow(lines[index]), headers.length));
        index += 1;
      }
      blocks.push({ type: "table", headers, rows });
      continue;
    }

    if (/^>\s?/.test(line)) {
      const quoteLines: string[] = [];
      while (index < lines.length && /^>\s?/.test(lines[index])) {
        quoteLines.push(lines[index].replace(/^>\s?/, ""));
        index += 1;
      }
      blocks.push({ type: "blockquote", text: quoteLines.join("\n") });
      continue;
    }

    const unorderedMatch = line.match(/^\s*[-*]\s+(.+)$/);
    const orderedMatch = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (unorderedMatch || orderedMatch) {
      const ordered = Boolean(orderedMatch);
      const items: string[] = [];
      while (index < lines.length) {
        const itemMatch = ordered
          ? lines[index].match(/^\s*\d+[.)]\s+(.+)$/)
          : lines[index].match(/^\s*[-*]\s+(.+)$/);
        if (!itemMatch) break;
        items.push(itemMatch[1]);
        index += 1;
      }
      blocks.push({ type: "list", ordered, items });
      continue;
    }

    const paragraphLines = [line];
    index += 1;
    while (
      index < lines.length &&
      lines[index].trim() &&
      !lines[index].match(/^```/) &&
      !lines[index].match(/^(#{1,3})\s+/) &&
      !isTableStart(lines, index) &&
      !lines[index].match(/^>\s?/) &&
      !lines[index].match(/^\s*[-*]\s+/) &&
      !lines[index].match(/^\s*\d+[.)]\s+/)
    ) {
      paragraphLines.push(lines[index]);
      index += 1;
    }
    blocks.push({ type: "paragraph", text: paragraphLines.join("\n") });
  }

  return blocks;
}

function isTableStart(lines: string[], index: number) {
  return (
    index + 1 < lines.length &&
    isTableRow(lines[index]) &&
    isTableDelimiter(lines[index + 1]) &&
    splitTableRow(lines[index]).length === splitTableRow(lines[index + 1]).length
  );
}

function isTableRow(line: string) {
  return line.includes("|") && line.trim().length > 0;
}

function isTableDelimiter(line: string) {
  const cells = splitTableRow(line);
  return (
    cells.length > 0 &&
    cells.every((cell) => /^:?-{3,}:?$/.test(cell.replace(/\s+/g, "")))
  );
}

function splitTableRow(line: string) {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split(/(?<!\\)\|/).map((cell) => cell.replace(/\\\|/g, "|").trim());
}

function normalizeTableRow(cells: string[], length: number) {
  if (cells.length === length) {
    return cells;
  }
  if (cells.length > length) {
    return cells.slice(0, length);
  }
  return [...cells, ...Array.from({ length: length - cells.length }, () => "")];
}

export function splitRequestedSkillDetails(source: string): ContentPart[] {
  const parts: ContentPart[] = [];
  const skillBlockPattern = /(?:^|\n)---\nRequested skill details:\n([\s\S]*?)\n---(?=\n|$)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = skillBlockPattern.exec(source)) !== null) {
    const blockStart = match.index + (match[0].startsWith("\n") ? 1 : 0);
    const before = source.slice(lastIndex, blockStart).trimEnd();
    if (before) {
      parts.push({ type: "markdown", source: before });
    }
    parts.push({ type: "skillDetails", details: parseRequestedSkillDetails(match[1]) });
    lastIndex = match.index + match[0].length;
  }

  const after = source.slice(lastIndex).trim();
  if (after) {
    parts.push({ type: "markdown", source: after });
  }
  return parts.length ? parts : [{ type: "markdown", source }];
}

function parseRequestedSkillDetails(source: string): RequestedSkillDetail[] {
  const details: RequestedSkillDetail[] = [];
  const detailPattern =
    /^### Requested skill \d+: ([^\n]+)\n```markdown\n([\s\S]*?)\n```(?=\n### Requested skill|\s*$)/gm;
  let match: RegExpExecArray | null;
  while ((match = detailPattern.exec(source)) !== null) {
    details.push({ id: match[1].trim(), content: match[2] });
  }
  return details.length ? details : [{ id: "requested skill", content: source.trim() }];
}

function renderMarkdownBlocks(source: string, keyPrefix: string) {
  return parseMarkdown(source).map((block, index) => {
    const key = `${keyPrefix}-${index}`;
    if (block.type === "heading") {
      const Heading = `h${block.level + 2}` as "h3" | "h4" | "h5";
      return <Heading key={key}>{renderInline(block.text, `heading-${key}`)}</Heading>;
    }
    if (block.type === "blockquote") {
      return <blockquote key={key}>{renderInlineWithBreaks(block.text, `quote-${key}`)}</blockquote>;
    }
    if (block.type === "code") {
      if ((block.language ?? "").toLowerCase() === "mermaid") {
        return <MermaidDiagram code={block.code} key={key} />;
      }
      return (
        <pre key={key}>
          <code>{block.code}</code>
        </pre>
      );
    }
    if (block.type === "list") {
      const List = block.ordered ? "ol" : "ul";
      return (
        <List key={key}>
          {block.items.map((item, itemIndex) => (
            <li key={itemIndex}>{renderInlineWithBreaks(item, `list-${key}-${itemIndex}`)}</li>
          ))}
        </List>
      );
    }
    if (block.type === "table") {
      return (
        <div className="markdownTableScroller" key={key}>
          <table>
            <thead>
              <tr>
                {block.headers.map((header, headerIndex) => (
                  <th key={headerIndex}>{renderInline(header, `table-${key}-header-${headerIndex}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {row.map((cell, cellIndex) => (
                    <td key={cellIndex}>
                      {renderInlineWithBreaks(cell, `table-${key}-${rowIndex}-${cellIndex}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    return <p key={key}>{renderInlineWithBreaks(block.text, `paragraph-${key}`)}</p>;
  });
}

function renderSkillDisclosure(details: RequestedSkillDetail[], key: string) {
  return (
    <details className="skillDisclosure" key={key}>
      <summary>
        <span className="skillDisclosureBadge">Skill</span>
        <span className="skillDisclosureTitle">已載入技能內容</span>
        <span className="skillDisclosureCount">{details.length}</span>
      </summary>
      <div className="skillDisclosureBody">
        {details.map((detail, index) => (
          <section className="skillDisclosureItem" key={`${detail.id}-${index}`}>
            <header className="skillDisclosureItemHeader">{detail.id}</header>
            <pre>
              <code>{detail.content}</code>
            </pre>
          </section>
        ))}
      </div>
    </details>
  );
}

function MermaidDiagram({ code }: { code: string }) {
  const reactId = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const [svg, setSvg] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const renderId = `mermaid-${reactId}-${hashString(code)}`;

    ensureMermaidInitialized();
    setSvg("");
    setError("");

    mermaid
      .render(renderId, code)
      .then((result) => {
        if (!cancelled) {
          setSvg(result.svg);
        }
      })
      .catch((renderError: unknown) => {
        if (!cancelled) {
          setError(renderError instanceof Error ? renderError.message : String(renderError));
        }
      });

    return () => {
      cancelled = true;
    };
  }, [code, reactId]);

  if (error) {
    return (
      <figure className="mermaidDiagram mermaidDiagramError">
        <figcaption>Mermaid render failed</figcaption>
        <pre>
          <code>{code}</code>
        </pre>
      </figure>
    );
  }

  if (!svg) {
    return <div className="mermaidDiagram mermaidDiagramLoading" aria-label="Rendering Mermaid diagram" />;
  }

  return (
    <figure className="mermaidDiagram">
      <div
        aria-label="Mermaid diagram preview"
        className="mermaidDiagramSvg"
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    </figure>
  );
}

function hashString(value: string) {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash.toString(36);
}

export function MarkdownContent({ source }: MarkdownContentProps) {
  const parts = splitRequestedSkillDetails(source);

  return (
    <div className="markdownContent">
      {parts.flatMap((part, index) =>
        part.type === "skillDetails"
          ? [renderSkillDisclosure(part.details, `skill-${index}`)]
          : renderMarkdownBlocks(part.source, `markdown-${index}`)
      )}
    </div>
  );
}
