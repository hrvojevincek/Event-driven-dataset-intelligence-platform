export const projectKeys = {
  all: ["projects"] as const,
  detail: (projectId: string) => ["projects", projectId] as const,
} as const;
