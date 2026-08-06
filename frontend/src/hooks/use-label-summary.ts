"use client";

import { useMemo } from "react";

import { useProjectExport } from "@/hooks/use-project-export";
import {
  summarizeLabelsFromExport,
  type LabelFieldSummary,
} from "@/lib/label-summary";

type UseLabelSummaryResult = {
  summaries: LabelFieldSummary[];
  error: string | null;
  isLoading: boolean;
};

/** Load export JSONL and compute label distribution summaries. */
export function useLabelSummary(
  projectId: string,
  enabled: boolean,
): UseLabelSummaryResult {
  const { content, error, isLoading } = useProjectExport(projectId, enabled);
  const summaries = useMemo(() => {
    if (!content) {
      return [];
    }
    return summarizeLabelsFromExport(content);
  }, [content]);

  return { summaries, error, isLoading };
}
