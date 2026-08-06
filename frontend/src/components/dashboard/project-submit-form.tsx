"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { Controller, useForm, useWatch } from "react-hook-form";

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
  acceptAttributeForTemplate,
  buildProjectSubmitFormData,
  projectSubmitSchema,
  supportedFormatsLabel,
  type ProjectSubmitInput,
} from "@/lib/project-submit-schema";
import {
  SCHEMA_TEMPLATES,
  type SchemaTemplateId,
} from "@/lib/schema-templates";

export function ProjectSubmitForm() {
  const router = useRouter();
  const submit = useSubmitProject();

  const {
    control,
    register,
    handleSubmit,
    setValue,
    trigger,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(projectSubmitSchema),
    defaultValues: {
      name: "",
      templateId: "support_call" as SchemaTemplateId,
      schemaOverride: "",
      showJsonEditor: false,
    },
  });

  const [name, templateId, showJsonEditor, files] = useWatch({
    control,
    name: ["name", "templateId", "showJsonEditor", "files"],
  });

  const selectedTemplate = SCHEMA_TEMPLATES.find((t) => t.id === templateId);
  const fileAccept = acceptAttributeForTemplate(templateId);
  const supportedFormats = supportedFormatsLabel(templateId);

  function handleTemplateChange(id: SchemaTemplateId) {
    setValue("templateId", id);
    if (showJsonEditor) {
      const template = SCHEMA_TEMPLATES.find((t) => t.id === id);
      if (template) {
        setValue("schemaOverride", JSON.stringify(template.schema, null, 2));
      }
    }
    if (files?.length) {
      void trigger("files");
    }
  }

  function handleToggleJsonEditor() {
    const next = !showJsonEditor;
    if (next && selectedTemplate) {
      setValue(
        "schemaOverride",
        JSON.stringify(selectedTemplate.schema, null, 2),
      );
    }
    setValue("showJsonEditor", next, {
      shouldValidate: errors.schemaOverride != null,
    });
  }

  async function onSubmit(data: ProjectSubmitInput) {
    try {
      const result = await submit.mutateAsync(buildProjectSubmitFormData(data));
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
    (name ?? "").trim().length > 0 && files != null && files.length > 0;

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate>
      <Card>
        <CardHeader>
          <CardTitle>Project setup</CardTitle>
          <CardDescription>
            Upload files and pick an annotation schema template. Supported for
            this template: {supportedFormats}.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-2">
            <Label htmlFor="name">Project name</Label>
            <Input
              id="name"
              placeholder="e.g. Support calls batch 1"
              aria-invalid={errors.name ? true : undefined}
              {...register("name")}
            />
            {errors.name ? (
              <p className="text-xs text-destructive">{errors.name.message}</p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="files">Files</Label>
            <Controller
              control={control}
              name="files"
              render={({ field: { onChange, name: fieldName, ref } }) => (
                <Input
                  id="files"
                  name={fieldName}
                  ref={ref}
                  type="file"
                  multiple
                  accept={fileAccept}
                  onChange={(event) => onChange(event.target.files)}
                  aria-invalid={errors.files ? true : undefined}
                />
              )}
            />
            {errors.files ? (
              <p className="text-xs text-destructive">{errors.files.message}</p>
            ) : files && files.length > 0 ? (
              <p className="text-xs text-muted-foreground">
                {files.length} file{files.length === 1 ? "" : "s"} selected
              </p>
            ) : null}
          </div>

          <fieldset className="space-y-3">
            <legend className="text-sm font-medium">Schema template</legend>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
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
            {errors.templateId ? (
              <p className="text-xs text-destructive">
                {errors.templateId.message}
              </p>
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
              <Controller
                control={control}
                name="schemaOverride"
                render={({ field }) => (
                  <textarea
                    id="schema_json"
                    rows={8}
                    className="w-full rounded-lg border border-border bg-muted/20 p-3 font-mono text-xs aria-invalid:border-destructive"
                    aria-invalid={errors.schemaOverride ? true : undefined}
                    {...field}
                  />
                )}
              />
            ) : (
              <p className="rounded-lg border border-dashed border-border p-3 text-xs text-muted-foreground">
                Using built-in template fields. Enable JSON override to
                customize.
              </p>
            )}
            {errors.schemaOverride ? (
              <p className="text-xs text-destructive">
                {errors.schemaOverride.message}
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
