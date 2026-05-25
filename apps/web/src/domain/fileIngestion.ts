import type { AttachmentPreview } from "../types";

const maxTextCharacters = 24_000;
const maxCsvRows = 40;
const supportedExtensions = new Set([
  ".txt",
  ".csv",
  ".docx",
  ".xlsx",
  ".pptx",
  ".md",
  ".pdf",
  ".png",
  ".jpg",
  ".jpeg",
  ".gif",
  ".webp",
  ".bmp"
]);

type AttachmentKind = AttachmentPreview["kind"];

export async function ingestFiles(files: FileList | File[]): Promise<AttachmentPreview[]> {
  return Promise.all(Array.from(files).map(ingestFile));
}

export function attachmentPromptBlock(attachments: AttachmentPreview[]): string {
  const ready = attachments.filter((attachment) => attachment.status === "ready");
  if (!ready.length) {
    return "";
  }
  const blocks = ready.map((attachment, index) => {
    const lines = [
      `### Attachment ${index + 1}: ${attachment.name}`,
      `- kind: ${attachment.kind}`,
      `- mime: ${attachment.type || "unknown"}`,
      `- size_bytes: ${attachment.size}`,
      attachment.summary
    ];
    if (attachment.content) {
      lines.push("", attachment.content);
    }
    return lines.join("\n");
  });
  return ["", "---", "User-provided attachments:", ...blocks, "---"].join("\n");
}

async function ingestFile(file: File): Promise<AttachmentPreview> {
  const kind = detectKind(file);
  const base = {
    id: crypto.randomUUID(),
    name: file.name,
    type: file.type,
    size: file.size,
    kind,
    status: "ready" as const
  };
  try {
    if (kind === "text") {
      const text = await readLimitedText(file);
      return {
        ...base,
        summary: `Plain text read as UTF-8-compatible text. Characters included: ${text.length}.`,
        content: fence("text", text)
      };
    }
    if (kind === "csv") {
      const text = await readLimitedText(file);
      const preview = csvDataFramePreview(text);
      return {
        ...base,
        summary: [
          "CSV parsed into a DataFrame-style preview.",
          `Columns: ${preview.columns.length ? preview.columns.join(", ") : "(none)"}.`,
          `Rows included: ${preview.rows.length}.`
        ].join("\n"),
        content: fence("text", preview.table)
      };
    }
    if (kind === "image") {
      return {
        ...base,
        summary:
          "Image file accepted and previewed in the browser. The original bytes are PIL-compatible for backend Image.open(file) ingestion.",
        url: URL.createObjectURL(file)
      };
    }
    if (kind === "document" || kind === "spreadsheet" || kind === "presentation" || kind === "pdf") {
      return {
        ...base,
        summary:
          "File accepted for attachment context. Binary document text extraction is not performed in this browser-only pass; backend parsing can read the original file bytes in a future upload endpoint."
      };
    }
    return {
      ...base,
      status: "error",
      summary: "Unsupported file type.",
      error: `Unsupported extension. Supported: ${Array.from(supportedExtensions).join(", ")}`
    };
  } catch (error) {
    return {
      ...base,
      status: "error",
      summary: "File could not be read.",
      error: error instanceof Error ? error.message : String(error)
    };
  }
}

function detectKind(file: File): AttachmentKind {
  const name = file.name.toLowerCase();
  const extension = extensionOf(name);
  if (file.type.startsWith("image/") || [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"].includes(extension)) {
    return "image";
  }
  if (extension === ".csv" || file.type === "text/csv") {
    return "csv";
  }
  if (extension === ".txt" || file.type.startsWith("text/plain")) {
    return "text";
  }
  if (extension === ".md" || file.type === "text/markdown") {
    return "text";
  }
  if (extension === ".docx") {
    return "document";
  }
  if (extension === ".xlsx") {
    return "spreadsheet";
  }
  if (extension === ".pptx") {
    return "presentation";
  }
  if (extension === ".pdf" || file.type === "application/pdf") {
    return "pdf";
  }
  return "unsupported";
}

function extensionOf(name: string) {
  const index = name.lastIndexOf(".");
  return index >= 0 ? name.slice(index) : "";
}

async function readLimitedText(file: File) {
  const text = await file.text();
  return text.length > maxTextCharacters
    ? `${text.slice(0, maxTextCharacters)}\n[truncated after ${maxTextCharacters} characters]`
    : text;
}

function csvDataFramePreview(text: string) {
  const rows = parseCsv(text).slice(0, maxCsvRows + 1);
  const columns = rows[0] ?? [];
  const dataRows = rows.slice(1);
  const table = [
    "pandas.DataFrame preview:",
    columns.length ? columns.join(" | ") : "(no columns)",
    columns.length ? columns.map(() => "---").join(" | ") : "",
    ...dataRows.map((row) => columns.map((_, index) => row[index] ?? "").join(" | "))
  ]
    .filter(Boolean)
    .join("\n");
  return { columns, rows: dataRows, table };
}

function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];
    if (quoted) {
      if (char === '"' && next === '"') {
        cell += '"';
        index += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        cell += char;
      }
      continue;
    }
    if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(cell);
      cell = "";
    } else if (char === "\n") {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else if (char !== "\r") {
      cell += char;
    }
  }
  row.push(cell);
  if (row.length > 1 || row[0]) {
    rows.push(row);
  }
  return rows;
}

function fence(language: string, content: string) {
  return ["```" + language, content.replaceAll("```", "`\u200b``"), "```"].join("\n");
}
