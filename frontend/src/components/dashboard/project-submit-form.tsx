"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useSubmitProject } from "@/hooks/use-projects";
import { ApiError } from "@/lib/api-client";
import {
  buildProjectSubmitFormData,
  projectSubmitSchema,
} from "@/lib/project-submit-schema";
import {
  SCHEMA_TEMPLATES,
  type SchemaTemplateId,
} from "@/lib/schema-templates";

type FieldErrors = {
  name?: string;
  files?: string;
  templateId?: string;
  schemaOverride?: string;
};

export function ProjectSubmitForm() {
  const router = useRouter();
  const submit = useSubmitProject();
  const [name, setName] = useState("");
  const [templateId, setTemplateId] =
    useState<SchemaTemplateId>("support_call");
  const [schemaOverride, setSchemaOverride] = useState("");
  const [files, setFiles] = useState<FileList | null>(null);
  const [showJsonEditor, setShowJsonEditor] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});

  const selectedTemplate = SCHEMA_TEMPLATES.find((t) => t.id === templateId);

  function clearFieldError(field: keyof FieldErrors) {
    setFieldErrors((current) => {
      if (!current[field]) {
        return current;
      }
      const next = { ...current };
      delete next[field];
      return next;
    });
  }

  function handleTemplateChange(id: SchemaTemplateId) {
    setTemplateId(id);
    clearFieldError("templateId");
    if (showJsonEditor) {
      const template = SCHEMA_TEMPLATES.find((t) => t.id === id);
      if (template) {
        setSchemaOverride(JSON.stringify(template.schema, null, 2));
      }
    }
  }

  function handleToggleJsonEditor() {
    if (!showJsonEditor && selectedTemplate) {
      setSchemaOverride(JSON.stringify(selectedTemplate.schema, null, 2));
    }
    setShowJsonEditor((value) => !value);
    clearFieldError("schemaOverride");
  }

  async function handleSubmit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setFieldErrors({});

    const parsed = projectSubmitSchema.safeParse({
      name,
      templateId,
      files,
      schemaOverride,
      showJsonEditor,
    });

    if (!parsed.success) {
      const errors: FieldErrors = {};
      for (const issue of parsed.error.issues) {
        const field = issue.path[0];
        if (
          field === "name" ||
          field === "files" ||
          field === "templateId" ||
          field === "schemaOverride"
        ) {
          errors[field] = issue.message;
        }
      }
      setFieldErrors(errors);
      return;
    }

    try {
      const result = await submit.mutateAsync(
        buildProjectSubmitFormData(parsed.data),
      );
      router.push(`/projects/${result.job_id}`);
    } catch {
      // Error surfaced via submit.error below
    }
  }

  const errorMessage =
    submit.error instanceof ApiError
      ? submit.error.message
      : submit.error
        ? "Failed to submit project"
        : null;

  const canSubmit =
    name.trim().length > 0 && files !== null && files.length > 0;

  return (
    <form onSubmit={handleSubmit} noValidate>
      <Card>
        <CardHeader>
          <CardTitle>Project setup</CardTitle>
          <CardDescription>
            Upload files and pick an annotation schema template. Supported:
            .txt, .md, .pdf.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-2">
            <Label htmlFor="name">Project name</Label>
            <Input
              id="name"
              name="name"
              value={name}
              onChange={(event) => {
                setName(event.target.value);
                clearFieldError("name");
              }}
              placeholder="e.g. Support calls batch 1"
              aria-invalid={fieldErrors.name ? true : undefined}
            />
            {fieldErrors.name ? (
              <p className="text-xs text-destructive">{fieldErrors.name}</p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="files">Files</Label>
            <Input
              id="files"
              name="files"
              type="file"
              multiple
              accept=".txt,.md,.pdf,text/plain,text/markdown,application/pdf"
              onChange={(event) => {
                setFiles(event.target.files);
                clearFieldError("files");
              }}
              aria-invalid={fieldErrors.files ? true : undefined}
            />
            {fieldErrors.files ? (
              <p className="text-xs text-destructive">{fieldErrors.files}</p>
            ) : files && files.length > 0 ? (
              <p className="text-xs text-muted-foreground">
                {files.length} file{files.length === 1 ? "" : "s"} selected
              </p>
            ) : null}
          </div>

          <fieldset className="space-y-3">
            <legend className="text-sm font-medium">Schema template</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {SCHEMA_TEMPLATES.map((template) => (
                <label
                  key={template.id}
                  className="flex cursor-pointer flex-col gap-1 rounded-lg border border-border p-3 has-checked:border-primary has-checked:bg-primary/5"
                >
                  <span className="flex items-center gap-2 text-sm font-medium">
                    <input
                      type="radio"
                      name="schema_template"
                      value={template.id}
                      checked={templateId === template.id}
                      onChange={() => handleTemplateChange(template.id)}
                      className="accent-primary"
                    />
                    {template.label}
                  </span>
                  <span className="pl-5 text-xs text-muted-foreground">
                    {template.description}
                  </span>
                </label>
              ))}
            </div>
            {fieldErrors.templateId ? (
              <p className="text-xs text-destructive">{fieldErrors.templateId}</p>
            ) : null}
          </fieldset>

          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <Label htmlFor="schema_json">Label schema JSON</Label>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-auto px-2 py-1 text-xs"
                onClick={handleToggleJsonEditor}
              >
                {showJsonEditor ? "Use template only" : "Edit JSON override"}
              </Button>
            </div>
            {showJsonEditor ? (
              <textarea
                id="schema_json"
                name="schema_json"
                rows={8}
                value={schemaOverride}
                onChange={(event) => {
                  setSchemaOverride(event.target.value);
                  clearFieldError("schemaOverride");
                }}
                className="w-full rounded-lg border border-border bg-muted/20 p-3 font-mono text-xs aria-invalid:border-destructive"
                aria-invalid={fieldErrors.schemaOverride ? true : undefined}
              />
            ) : (
              <p className="rounded-lg border border-dashed border-border p-3 text-xs text-muted-foreground">
                Using built-in template fields. Enable JSON override to
                customize.
              </p>
            )}
            {fieldErrors.schemaOverride ? (
              <p className="text-xs text-destructive">
                {fieldErrors.schemaOverride}
              </p>
            ) : null}
          </div>

          {errorMessage ? (
            <p className="text-sm text-destructive">{errorMessage}</p>
          ) : null}
        </CardContent>
        <CardFooter className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground">
            Projects are scoped to the local mock user account.
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              nativeButton={false}
              render={<Link href="/" />}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={submit.isPending || !canSubmit}>
              {submit.isPending ? "Uploading…" : "Start pipeline"}
            </Button>
          </div>
        </CardFooter>
      </Card>
    </form>
  );
}
