"use client";

import { useMemo } from "react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { useProjectExport } from "@/hooks/use-project-export";
import type { ProjectDetail } from "@/lib/api-client";
import { parseExportJsonl, summarizeLabelFields } from "@/lib/export-rows";

type QcPanelProps = {
  projectId: string;
  detail: ProjectDetail | undefined;
  jobStatus: string | null;
  isLoading: boolean;
};

function flagLabel(flag: string): string {
  return flag.replaceAll("_", " ");
}

function LabelSummary({
  projectId,
  exportReady,
}: {
  projectId: string;
  exportReady: boolean;
}) {
  const { content, error, isLoading } = useProjectExport(projectId, exportReady);
  const summaries = useMemo(() => {
    if (!content) {
      return [];
    }
    return summarizeLabelFields(parseExportJsonl(content));
  }, [content]);

  if (!exportReady || isLoading) {
    return null;
  }

  if (error) {
    return (
      <p className="text-xs text-destructive">{error}</p>
    );
  }

  if (summaries.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3 border-t border-border pt-4">
      <p className="text-xs font-medium text-muted-foreground">Label summary</p>
      <div className="space-y-3">
        {summaries.map((summary) => (
          <div key={summary.field} className="space-y-1.5">
            <p className="text-xs font-medium">{summary.field}</p>
            {summary.kind === "unique" ? (
              <p className="font-mono text-xs text-muted-foreground">
                {summary.uniqueCount} unique
              </p>
            ) : (
              <dl className="space-y-1 font-mono text-xs text-muted-foreground">
                {Object.entries(summary.counts)
                  .sort((left, right) => right[1] - left[1])
                  .map(([value, count]) => (
                    <div
                      key={value}
                      className="flex items-center justify-between gap-3"
                    >
                      <dt className="truncate">{value}</dt>
                      <dd className="shrink-0">{count}</dd>
                    </div>
                  ))}
              </dl>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export function QcPanel({
  projectId,
  detail,
  jobStatus,
  isLoading,
}: QcPanelProps) {
  const exportReady =
    detail?.dataset_export != null && jobStatus === "completed";

  if (isLoading && !detail) {
    return (
      <p className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
        Loading QC report…
      </p>
    );
  }

  const qc = detail?.dataset_export?.qc_report;

  if (qc) {
    const healthy =
      qc.flags.length === 0 &&
      qc.coverage_pct >= 100 &&
      qc.schema_compliance_pct >= 100;

    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          {healthy ? (
            <CheckCircle2 className="size-4 text-emerald-600" />
          ) : (
            <AlertTriangle className="size-4 text-amber-600" />
          )}
          <p className="text-sm font-medium">
            {healthy ? "Export passed QC checks" : "Review flagged items"}
          </p>
        </div>

        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-muted-foreground">Coverage</dt>
            <dd className="font-mono">{qc.coverage_pct.toFixed(1)}%</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Schema compliance</dt>
            <dd className="font-mono">{qc.schema_compliance_pct.toFixed(1)}%</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Segments</dt>
            <dd className="font-mono">
              {qc.labeled_count}/{qc.segment_count}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Batches</dt>
            <dd className="font-mono">{qc.batch_count}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Export cost</dt>
            <dd className="font-mono">${qc.total_cost_usd.toFixed(4)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Low confidence</dt>
            <dd className="font-mono">
              {qc.low_confidence_segment_ids.length}
            </dd>
          </div>
        </dl>

        {qc.flags.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {qc.flags.map((flag) => (
              <Badge key={flag} variant="outline" className="font-mono text-[10px] uppercase">
                {flagLabel(flag)}
              </Badge>
            ))}
          </div>
        ) : null}

        {qc.low_confidence_segment_ids.length > 0 ? (
          <div className="space-y-2">
            <p className="text-xs font-medium text-muted-foreground">
              Flagged segment IDs
            </p>
            <ul className="max-h-24 space-y-1 overflow-y-auto font-mono text-xs text-muted-foreground">
              {qc.low_confidence_segment_ids.map((segmentId) => (
                <li key={segmentId} className="truncate">{segmentId}</li>
              ))}
            </ul>
          </div>
        ) : null}

        <LabelSummary projectId={projectId} exportReady={exportReady} />
      </div>
    );
  }

  if (jobStatus === "failed") {
    return (
      <p className="rounded-lg border border-dashed border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
        Pipeline failed before export completed.
      </p>
    );
  }

  if (jobStatus === "completed") {
    return (
      <p className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
        Job finished but no export report was returned.
      </p>
    );
  }

  return (
    <p className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
      QC metrics appear when the export stage completes.
    </p>
  );
}
