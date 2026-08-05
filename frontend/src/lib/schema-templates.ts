export type SchemaTemplateId = "support_call" | "document_classification";

export type SchemaTemplate = {
  id: SchemaTemplateId;
  label: string;
  description: string;
  schema: Record<string, unknown>;
};

export const SCHEMA_TEMPLATES: SchemaTemplate[] = [
  {
    id: "support_call",
    label: "Support call annotation",
    description: "emotion, intent, topic, resolution_status",
    schema: {
      type: "object",
      properties: {
        emotion: { type: "string" },
        intent: { type: "string" },
        topic: { type: "string" },
        resolution_status: { type: "string" },
      },
      required: ["emotion", "intent", "topic", "resolution_status"],
    },
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
  },
];

export function templateById(id: string | null): SchemaTemplate | undefined {
  if (!id) {
    return undefined;
  }
  return SCHEMA_TEMPLATES.find((template) => template.id === id);
}
