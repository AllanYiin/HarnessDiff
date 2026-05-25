import { describe, expect, it, vi } from "vitest";

import { attachmentPromptBlock, ingestFiles } from "./fileIngestion";

describe("file ingestion", () => {
  it("reads text attachments into prompt context", async () => {
    vi.spyOn(crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000001");
    const [attachment] = await ingestFiles([
      new File(["hello\nworld"], "notes.txt", { type: "text/plain" })
    ]);

    expect(attachment).toMatchObject({
      id: "00000000-0000-4000-8000-000000000001",
      name: "notes.txt",
      kind: "text",
      status: "ready"
    });
    expect(attachment.content).toContain("hello\nworld");
    expect(attachmentPromptBlock([attachment])).toContain("Attachment 1: notes.txt");
  });

  it("builds a DataFrame-style preview for csv attachments", async () => {
    const [attachment] = await ingestFiles([
      new File(['name,score\n"Ada, A.",10\nLinus,9'], "scores.csv", { type: "text/csv" })
    ]);

    expect(attachment.kind).toBe("csv");
    expect(attachment.summary).toContain("CSV parsed into a DataFrame-style preview");
    expect(attachment.content).toContain("name | score");
    expect(attachment.content).toContain("Ada, A. | 10");
  });

  it("accepts office, pdf, and image files as readable attachment metadata", async () => {
    const createObjectURL = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:image");
    const attachments = await ingestFiles([
      new File(["fake"], "brief.docx"),
      new File(["fake"], "sheet.xlsx"),
      new File(["fake"], "deck.pptx"),
      new File(["fake"], "paper.pdf", { type: "application/pdf" }),
      new File(["fake"], "image.png", { type: "image/png" })
    ]);

    expect(attachments.map((attachment) => attachment.kind)).toEqual([
      "document",
      "spreadsheet",
      "presentation",
      "pdf",
      "image"
    ]);
    expect(attachments.every((attachment) => attachment.status === "ready")).toBe(true);
    expect(attachments.at(-1)?.url).toBe("blob:image");
    expect(createObjectURL).toHaveBeenCalledOnce();
  });
});
