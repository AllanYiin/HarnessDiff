import { describe, expect, it, vi } from "vitest";

import {
  attachmentPromptBlock,
  attachmentRunInputs,
  attachmentVisionInputs,
  ingestFiles
} from "./fileIngestion";

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
      new File(["fake"], "image.png", { type: "image/png" }),
      new File(['<svg xmlns="http://www.w3.org/2000/svg"></svg>'], "icon.svg")
    ]);

    expect(attachments.map((attachment) => attachment.kind)).toEqual([
      "document",
      "spreadsheet",
      "presentation",
      "pdf",
      "image",
      "image"
    ]);
    expect(attachments.every((attachment) => attachment.status === "ready")).toBe(true);
    expect(attachments[4].url).toBe("blob:image");
    expect(attachments[4].dataUrl).toBe("data:image/png;base64,ZmFrZQ==");
    expect(attachments[5]).toMatchObject({
      name: "icon.svg",
      type: "image/svg+xml",
      url: "blob:image",
      visionSupported: false
    });
    expect(attachments[5].dataUrl).toBeUndefined();
    expect(attachmentVisionInputs(attachments)).toEqual([
      {
        kind: "image",
        name: "image.png",
        mime_type: "image/png",
        size_bytes: 4,
        image_url: "data:image/png;base64,ZmFrZQ==",
        detail: "auto"
      }
    ]);
    expect(attachmentRunInputs(attachments)).toEqual([
      {
        kind: "pdf",
        id: attachments[3].id,
        name: "paper.pdf",
        mime_type: "application/pdf",
        size_bytes: 4,
        data_base64: "ZmFrZQ=="
      },
      {
        kind: "image",
        name: "image.png",
        mime_type: "image/png",
        size_bytes: 4,
        image_url: "data:image/png;base64,ZmFrZQ==",
        detail: "auto"
      }
    ]);
    expect(createObjectURL).toHaveBeenCalledTimes(2);
  });
});
