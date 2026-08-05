export type StageStatus = "pending" | "running" | "completed" | "failed";

export type JobStageSnapshot = {
  stage: string;
  status: StageStatus;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  error_detail: string | null;
};

export type JobStreamEventType = "snapshot" | "stage_update" | "job_complete";

export type JobStreamEvent = {
  event: JobStreamEventType;
  job_id: string;
  correlation_id: string;
  timestamp: string;
  job_status?: string;
  stage?: string;
  status?: StageStatus;
  detail?: string | null;
  duration_ms?: number | null;
  stages?: JobStageSnapshot[];
};

export const PIPELINE_STAGES = [
  { id: "intake", label: "Intake" },
  { id: "preprocessing", label: "Preprocessing" },
  { id: "planning", label: "Planning" },
  { id: "annotation", label: "Annotation" },
  { id: "export", label: "Export" },
] as const;

export function stageLabel(stageId: string): string {
  return PIPELINE_STAGES.find((stage) => stage.id === stageId)?.label ?? stageId;
}

export function buildStageMap(
  stages: JobStageSnapshot[] | undefined,
): Record<string, JobStageSnapshot> {
  if (!stages) {
    return {};
  }
  return Object.fromEntries(stages.map((stage) => [stage.stage, stage]));
}
