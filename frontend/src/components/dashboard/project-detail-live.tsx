"use client";

import { useEffect, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { CostPanel } from "@/components/dashboard/cost-panel";
import { ExportPreview } from "@/components/dashboard/export-preview";
import { QcPanel } from "@/components/dashboard/qc-panel";
import { PipelineGraph } from "@/components/workflow/pipeline-graph";
import { useProjectDetail } from "@/hooks/use-projects";
import { useJobStream } from "@/hooks/useJobStream";
import { projectKeys } from "@/lib/project-keys";
import { templateById } from "@/lib/schema-templates";
import {
  buildStageMap,
  type JobStageSnapshot,
  type StageStatus,
} from "@/types/job-stream";

type ProjectDetailLiveProps = {
  projectId: string;
};

function jobStatusLabel(status: string | null): string {
  if (!status) {
    return "connecting…";
  }
  return status.replaceAll("_", " ");
}

export function ProjectDetailLive({ projectId }: ProjectDetailLiveProps) {
  const stream = useJobStream(projectId);
  const queryClient = useQueryClient();
  const jobStatus = stream.jobStatus ?? null;
  const detailQuery = useProjectDetail(projectId, jobStatus);

  useEffect(() => {
    if (jobStatus === "completed" || jobStatus === "failed") {
      void queryClient.invalidateQueries({
        queryKey: projectKeys.detail(projectId),
      });
    }
  }, [projectId, jobStatus, queryClient]);

  const displayStatus = jobStatus ?? detailQuery.data?.status ?? null;
  const templateLabel =
    templateById(detailQuery.data?.schema_template ?? null)?.label ??
    detailQuery.data?.schema_template ??
    "custom schema";

  const mergedStages = useMemo(() => {
    const fromApi = buildStageMap(
      detailQuery.data?.stages?.map(
        (stage): JobStageSnapshot => ({
          stage: stage.stage,
          status: stage.status as StageStatus,
          started_at: stage.started_at ?? null,
          completed_at: stage.completed_at ?? null,
          duration_ms: stage.duration_ms ?? null,
          error_detail: stage.error_detail ?? null,
        }),
      ),
    );
    return { ...fromApi, ...stream.stages };
  }, [detailQuery.data?.stages, stream.stages]);

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 p-6 md:p-10">
      <div className="space-y-2">
        <Badge variant="secondary" className="font-mono text-[10px] uppercase">
          Project detail
        </Badge>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold tracking-tight">
            {detailQuery.data?.name ?? "Dataset project"}
          </h1>
          <Badge variant="outline" className="font-mono text-xs">
            {projectId}
          </Badge>
          <Badge
            variant={stream.connected ? "secondary" : "outline"}
            className="font-mono text-[10px] uppercase"
          >
            {stream.connected ? "Live" : "Reconnecting"}
          </Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          {templateLabel} · pipeline updates via SSE. Click a stage for details.
        </p>
        {stream.correlationId ? (
          <p className="font-mono text-xs text-muted-foreground">
            correlation_id: {stream.correlationId}
          </p>
        ) : null}
        {stream.error ? (
          <p className="text-sm text-destructive">{stream.error}</p>
        ) : null}
        {detailQuery.error ? (
          <p className="text-sm text-destructive">
            Failed to load project detail from API.
          </p>
        ) : null}
      </div>

      <div className="grid gap-6 lg:grid-cols-3 lg:items-start">
        <Card className="h-fit lg:col-span-2">
          <CardHeader>
            <CardTitle>Pipeline</CardTitle>
            <CardDescription>
              Job status:{" "}
              <span className="font-mono uppercase">
                {jobStatusLabel(displayStatus)}
              </span>
            </CardDescription>
          </CardHeader>
          <CardContent>
            <PipelineGraph
              stages={mergedStages}
              jobStatus={displayStatus}
            />
          </CardContent>
        </Card>

        <Card className="h-fit">
          <CardHeader>
            <CardTitle>Cost</CardTitle>
            <CardDescription>
              Token usage and estimated spend from{" "}
              <code className="font-mono text-xs">llm_usage</code>.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <CostPanel
              detail={detailQuery.data}
              isLoading={detailQuery.isLoading}
            />
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2 lg:items-stretch">
        <Card className="h-full">
          <CardHeader>
            <CardTitle>Quality control</CardTitle>
            <CardDescription>
              Coverage, schema compliance, and confidence flags.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex-1">
            <QcPanel
              projectId={projectId}
              detail={detailQuery.data}
              jobStatus={displayStatus}
              isLoading={detailQuery.isLoading}
            />
          </CardContent>
        </Card>

        <Card className="h-full">
          <CardHeader>
            <CardTitle>JSONL export</CardTitle>
            <CardDescription>
              Labeled dataset with provenance fields per line.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex min-h-0 flex-1 flex-col">
            <ExportPreview
              projectId={projectId}
              detail={detailQuery.data}
              jobStatus={displayStatus}
              isLoading={detailQuery.isLoading}
            />
          </CardContent>
        </Card>
      </div>

      {detailQuery.data?.assets && detailQuery.data.assets.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Uploaded assets</CardTitle>
            <CardDescription>
              Files registered during intake.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="divide-y divide-border text-sm">
              {detailQuery.data.assets.map((asset) => (
                <li
                  key={asset.id}
                  className="flex flex-wrap items-center justify-between gap-2 py-2"
                >
                  <span className="font-medium">{asset.filename}</span>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Badge variant="outline" className="font-mono text-[10px] uppercase">
                      {asset.fetch_status}
                    </Badge>
                    <span className="font-mono">{asset.mime_type}</span>
                    {asset.byte_size != null ? (
                      <span>{asset.byte_size.toLocaleString()} B</span>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
