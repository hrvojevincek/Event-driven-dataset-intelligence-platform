"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchProjectExport } from "@/lib/api-client";
import { projectKeys } from "@/lib/project-keys";

/** Fetch project JSONL export when enabled (completed jobs with export data). */
export function useProjectExport(projectId: string, enabled: boolean) {
  const query = useQuery({
    queryKey: [...projectKeys.detail(projectId), "export"] as const,
    queryFn: () => fetchProjectExport(projectId),
    enabled,
    staleTime: Infinity,
  });

  return {
    content: query.data ?? null,
    error: query.error ? "Failed to load export" : null,
    isLoading: query.isLoading,
  };
}
