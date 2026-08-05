"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import { AlertCircle, CheckCircle2, Circle, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
import type { StageStatus } from "@/types/job-stream";

export type PipelineNodeData = {
  label: string;
  agentName: string;
  status: StageStatus;
  stageId: string;
  selected?: boolean;
};

function StatusIcon({ status }: { status: StageStatus }) {
  switch (status) {
    case "running":
      return <Loader2 className="size-4 animate-spin text-primary" />;
    case "completed":
      return <CheckCircle2 className="size-4 text-secondary" />;
    case "failed":
      return <AlertCircle className="size-4 text-destructive" />;
    default:
      return <Circle className="size-4 text-muted-foreground/50" />;
  }
}

const statusRing: Record<StageStatus, string> = {
  pending: "ring-border",
  running: "ring-primary",
  completed: "ring-secondary/40",
  failed: "ring-destructive/50",
};

export function PipelineNode({ data, selected }: NodeProps) {
  const nodeData = data as PipelineNodeData;
  const { label, agentName, status } = nodeData;

  return (
    <>
      <Handle
        type="target"
        position={Position.Left}
        className="!size-2 !border-border !bg-muted"
      />
      <div
        className={cn(
          "min-w-[180px] h-[130px] rounded-lg border bg-card px-3 py-2.5 ring-2 gap-4 flex flex-col",
          statusRing[status],
          status === "running" && "pipeline-node-running",
          selected && "border-primary",
        )}
      >
        <div className="flex items-center gap-2">
          <StatusIcon status={status} />
          <span className="text-sm font-medium leading-tight">{label}</span>
        </div>
        <div className="flex flex-col gap-2">
          <p className="mt-1 truncate font-mono text-sm uppercase tracking-wide text-muted-foreground">
            {agentName}
          </p>
          <p className="mt-1 font-mono text-sm uppercase text-muted-foreground">
            {status}
          </p>
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        className="!size-2 !border-border !bg-muted"
      />
    </>
  );
}
