export type PaneId = "NoHarness" | "Harness";

export type InputMode = "integrated" | "independent";

export type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  status?: "streaming" | "done";
};

export type AttachmentPreview = {
  id: string;
  name: string;
  type: string;
  size: number;
  url?: string;
};

export type PaneState = {
  messages: Message[];
  draft: string;
  streaming: boolean;
};

