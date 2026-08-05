/** Maps pipeline stage IDs to worker agent display names. */
export const STAGE_AGENT_NAMES: Record<string, string> = {
  intake: "Intake Agent",
  preprocessing: "Preprocessing Agent",
  planning: "Planning Agent",
  annotation: "Annotation Agent",
  export: "Export Agent",
};

export function agentNameForStage(stageId: string): string {
  return STAGE_AGENT_NAMES[stageId] ?? stageId;
}
