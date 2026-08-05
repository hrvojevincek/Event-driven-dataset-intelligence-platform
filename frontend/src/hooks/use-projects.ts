"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  deleteProject,
  getProjectDetail,
  listProjects,
  submitProject,
} from "@/lib/api-client";
import { projectKeys } from "@/lib/project-keys";

export function useProjectList() {
  return useQuery({
    queryKey: projectKeys.all,
    queryFn: listProjects,
  });
}

export function useProjectDetail(projectId: string, jobStatus: string | null) {
  return useQuery({
    queryKey: projectKeys.detail(projectId),
    queryFn: () => getProjectDetail(projectId),
    refetchInterval: () => {
      if (jobStatus === "completed" || jobStatus === "failed") {
        return false;
      }
      return 5_000;
    },
  });
}

export function useSubmitProject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (formData: FormData) => submitProject(formData),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: projectKeys.all });
    },
  });
}

export function useDeleteProject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (projectId: string) => deleteProject(projectId),
    onSuccess: (_data, projectId) => {
      void queryClient.invalidateQueries({ queryKey: projectKeys.all });
      void queryClient.removeQueries({ queryKey: projectKeys.detail(projectId) });
    },
  });
}
