"use client";

import { useEffect, useState } from "react";
import { Download } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  fetchProjectExport,
  projectExportDownloadUrl,
  type ProjectDetail,
} from "@/lib/api-client";

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
};

/** Fetches and shows JSONL preview once export exists (mounted only when ready). */
function ExportPreviewLoaded({
  projectId,
  lineCount,
}: ExportPreviewLoadedProps) {
  const [preview, setPreview] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(true);

  useEffect(() => {
    let cancelled = false;

    void fetchProjectExport(projectId)
      .then((content) => {
        if (cancelled) {
          return;
        }
        const lines = content
          .split("\n")
          .map((line) => line.trim())
          .filter(Boolean)
          .slice(0, PREVIEW_LINES);
        setPreview(lines.join("\n"));
      })
      .catch(() => {
        if (!cancelled) {
          setPreviewError("Failed to load JSONL preview");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingPreview(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [projectId]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          <span className="font-mono">{lineCount}</span> labeled rows in JSONL
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
        <pre className="max-h-64 overflow-auto rounded-lg border border-border bg-muted/20 p-3 font-mono text-xs leading-relaxed">
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
        key={projectId}
        projectId={projectId}
        lineCount={lineCount}
      />
    );
  }

  if (hasExport) {
    return (
      <p className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
        JSONL preview and download appear when export completes.
      </p>
    );
  }

  if (jobStatus === "failed") {
    return (
      <p className="rounded-lg border border-dashed border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
        Pipeline failed before JSONL export was produced.
      </p>
    );
  }

  return (
    <p className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
      JSONL preview and download appear when export completes.
    </p>
  );
}
