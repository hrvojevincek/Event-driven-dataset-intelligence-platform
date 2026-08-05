import { z } from "zod";

import {
  SCHEMA_TEMPLATES,
  type SchemaTemplateId,
} from "@/lib/schema-templates";

const TEMPLATE_IDS = SCHEMA_TEMPLATES.map((template) => template.id) as [
  SchemaTemplateId,
  ...SchemaTemplateId[],
];

const ALLOWED_EXTENSIONS = [".txt", ".md", ".pdf"];
const MAX_FILE_BYTES = 50 * 1024 * 1024;
const MAX_FILES = 50;

function fileExtension(filename: string): string {
  const dot = filename.lastIndexOf(".");
  return dot >= 0 ? filename.slice(dot).toLowerCase() : "";
}

function isValidJsonObject(value: string): boolean {
  try {
    const parsed: unknown = JSON.parse(value);
    return (
      typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)
    );
  } catch {
    return false;
  }
}

export const projectSubmitSchema = z
  .object({
    name: z.string().trim().min(1, "Project name is required"),
    templateId: z.enum(TEMPLATE_IDS),
    files: z
      .custom<FileList>((value) => value instanceof FileList, {
        message: "Select at least one file",
      })
      .refine((files) => files.length > 0, "Select at least one file")
      .refine(
        (files) => files.length <= MAX_FILES,
        `Maximum ${MAX_FILES} files allowed`,
      )
      .superRefine((files, ctx) => {
        for (const file of files) {
          const extension = fileExtension(file.name);
          if (!ALLOWED_EXTENSIONS.includes(extension)) {
            ctx.addIssue({
              code: "custom",
              message: `Unsupported file type: ${file.name}`,
            });
            return;
          }
          if (file.size === 0) {
            ctx.addIssue({
              code: "custom",
              message: `File is empty: ${file.name}`,
            });
            return;
          }
          if (file.size > MAX_FILE_BYTES) {
            ctx.addIssue({
              code: "custom",
              message: `File exceeds 50 MB: ${file.name}`,
            });
            return;
          }
        }
      }),
    schemaOverride: z.string(),
    showJsonEditor: z.boolean(),
  })
  .superRefine((data, ctx) => {
    if (!data.showJsonEditor || !data.schemaOverride.trim()) {
      return;
    }
    if (!isValidJsonObject(data.schemaOverride.trim())) {
      ctx.addIssue({
        code: "custom",
        message: "Schema JSON must be a valid JSON object",
        path: ["schemaOverride"],
      });
    }
  });

export type ProjectSubmitInput = z.infer<typeof projectSubmitSchema>;

export function domainForTemplate(templateId: SchemaTemplateId): string {
  return templateId === "support_call" ? "support_calls" : "documents";
}

export function buildProjectSubmitFormData(data: ProjectSubmitInput): FormData {
  const formData = new FormData();
  formData.append("name", data.name);
  formData.append("schema_template", data.templateId);
  formData.append("domain", domainForTemplate(data.templateId));

  if (data.showJsonEditor && data.schemaOverride.trim()) {
    formData.append("schema_json_override", data.schemaOverride.trim());
  }

  for (const file of data.files) {
    formData.append("files", file);
  }

  return formData;
}
