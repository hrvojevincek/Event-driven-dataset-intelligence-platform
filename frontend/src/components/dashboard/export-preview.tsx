"use client";

import { Download } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useProjectExport } from "@/hooks/use-project-export";
import {
  projectExportDownloadUrl,
  type ProjectDetail,
} from "@/lib/api-client";
import { formatExportPreview } from "@/lib/export-rows";

type ExportPreviewProps = {
  projectId: string;
  detail: ProjectDetail | undefined;
  jobStatus: string | null;
  isLoading: boolean;
};

const PREVIEW_LINES = 5;

type ExportPreviewLoadedProps = {
  projectId: string;
  lineCount: number;
  content: string | null;
  previewError: string | null;
  loadingPreview: boolean;
  isAudioProject: boolean;
};

function ExportPreviewLoaded({
  projectId,
  lineCount,
  content,
  previewError,
  loadingPreview,
  isAudioProject,
}: ExportPreviewLoadedProps) {
  const preview = content ? formatExportPreview(content, PREVIEW_LINES) : null;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          <span className="font-mono">{lineCount}</span> labeled rows in JSONL
          {isAudioProject ? " (includes start_ms / end_ms per row)" : null}
        </p>
        <Button
          variant="outline"
          size="sm"
          nativeButton={false}
          render={
            <a
              href={projectExportDownloadUrl(projectId)}
              download
              rel="noopener noreferrer"
            />
          }
        >
          <Download data-icon="inline-start" />
          Download JSONL
        </Button>
      </div>

      {loadingPreview ? (
        <p className="text-sm text-muted-foreground">Loading preview…</p>
      ) : null}
      {previewError ? (
        <p className="text-sm text-destructive">{previewError}</p>
      ) : null}
      {preview ? (
        <pre className="min-h-0 flex-1 overflow-auto rounded-lg border border-border bg-muted/20 p-3 font-mono text-xs leading-relaxed">
          {preview}
        </pre>
      ) : null}
    </div>
  );
}

export function ExportPreview({
  projectId,
  detail,
  jobStatus,
  isLoading,
}: ExportPreviewProps) {
  const hasExport = detail?.dataset_export != null;
  const lineCount = detail?.dataset_export?.line_count ?? 0;
  const exportReady = hasExport && jobStatus === "completed";
  const { content, error, isLoading: loadingPreview } = useProjectExport(
    projectId,
    exportReady,
  );

  if (isLoading && !detail) {
    return (
      <p className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
        Loading export…
      </p>
    );
  }

  if (exportReady) {
    return (
      <ExportPreviewLoaded
        projectId={projectId}
        lineCount={lineCount}
        content={content}
        previewError={error}
        loadingPreview={loadingPreview}
        isAudioProject={detail?.domain === "audio"}
      />
    );
  }

  if (hasExport) {
    return (
      <p className="flex flex-1 items-start rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
        JSONL preview and download appear when export completes.
      </p>
    );
  }

  if (jobStatus === "failed") {
    return (
      <p className="flex flex-1 items-start rounded-lg border border-dashed border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
        Pipeline failed before JSONL export was produced.
      </p>
    );
  }

  return (
    <p className="flex flex-1 items-start rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
      JSONL preview and download appear when export completes.
    </p>
  );
}
