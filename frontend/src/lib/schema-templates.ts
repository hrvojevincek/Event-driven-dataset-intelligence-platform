export type SchemaTemplateId =
  | "support_call"
  | "support_call_audio"
  | "document_classification";

export type SchemaTemplate = {
  id: SchemaTemplateId;
  label: string;
  description: string;
  schema: Record<string, unknown>;
  acceptedExtensions: string[];
  acceptMime: string;
};

const SUPPORT_CALL_SCHEMA = {
  type: "object",
  properties: {
    emotion: { type: "string" },
    intent: { type: "string" },
    topic: { type: "string" },
    resolution_status: { type: "string" },
  },
  required: ["emotion", "intent", "topic", "resolution_status"],
} as const;

export const SCHEMA_TEMPLATES: SchemaTemplate[] = [
  {
    id: "support_call",
    label: "Support call annotation",
    description: "emotion, intent, topic, resolution_status (.txt, .md)",
    schema: SUPPORT_CALL_SCHEMA,
    acceptedExtensions: [".txt", ".md"],
    acceptMime: ".txt,.md,text/plain,text/markdown",
  },
  {
    id: "support_call_audio",
    label: "Support call (audio)",
    description: "same labels from .wav via ASR",
    schema: SUPPORT_CALL_SCHEMA,
    acceptedExtensions: [".wav"],
    acceptMime: ".wav,audio/wav",
  },
  {
    id: "document_classification",
    label: "Document classification",
    description: "category, summary, sensitivity_flag",
    schema: {
      type: "object",
      properties: {
        category: { type: "string" },
        summary: { type: "string" },
        sensitivity_flag: { type: "string" },
      },
      required: ["category", "summary", "sensitivity_flag"],
    },
    acceptedExtensions: [".txt", ".md", ".pdf"],
    acceptMime: ".txt,.md,.pdf,text/plain,text/markdown,application/pdf",
  },
];

export function templateById(id: string | null): SchemaTemplate | undefined {
  if (!id) {
    return undefined;
  }
  return SCHEMA_TEMPLATES.find((template) => template.id === id);
}
