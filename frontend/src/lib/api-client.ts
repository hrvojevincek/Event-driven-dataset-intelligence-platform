import type { components, paths } from "@/types/api";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public body?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}

async function parseJson<T>(response: Response): Promise<T> {
  const text = await response.text();
  if (!text) {
    return undefined as T;
  }
  return JSON.parse(text) as T;
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const url = `${getApiBaseUrl()}${normalizedPath}`;
  const headers = new Headers(init?.headers);

  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(url, {
    ...init,
    headers,
  });

  if (!response.ok) {
    let body: unknown;
    try {
      body = await parseJson(response);
    } catch {
      body = undefined;
    }
    throw new ApiError(
      `API ${response.status}: ${response.statusText}`,
      response.status,
      body,
    );
  }

  return parseJson<T>(response);
}

export type HealthResponse =
  paths["/health"]["get"]["responses"][200]["content"]["application/json"];

export type ProjectSummary =
  paths["/api/v1/projects"]["get"]["responses"][200]["content"]["application/json"][number];

export type ProjectDetail =
  paths["/api/v1/projects/{project_id}"]["get"]["responses"][200]["content"]["application/json"];

export type SubmitProjectResponse =
  paths["/api/v1/projects"]["post"]["responses"][201]["content"]["application/json"];

export type QCReport = components["schemas"]["QCReportResponse"];

export async function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health");
}

export async function listProjects(): Promise<ProjectSummary[]> {
  return apiFetch<ProjectSummary[]>("/api/v1/projects");
}

export async function getProjectDetail(projectId: string): Promise<ProjectDetail> {
  return apiFetch<ProjectDetail>(`/api/v1/projects/${projectId}`);
}

export async function submitProject(formData: FormData): Promise<SubmitProjectResponse> {
  const url = `${getApiBaseUrl()}/api/v1/projects`;
  const response = await fetch(url, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    let body: unknown;
    try {
      body = await parseJson(response);
    } catch {
      body = undefined;
    }
    throw new ApiError(
      `API ${response.status}: ${response.statusText}`,
      response.status,
      body,
    );
  }

  return parseJson<SubmitProjectResponse>(response);
}

export async function deleteProject(projectId: string): Promise<void> {
  await apiFetch<void>(`/api/v1/projects/${projectId}`, {
    method: "DELETE",
  });
}

export async function fetchProjectExport(projectId: string): Promise<string> {
  const url = `${getApiBaseUrl()}/api/v1/projects/${projectId}/export`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new ApiError(
      `API ${response.status}: ${response.statusText}`,
      response.status,
    );
  }
  return response.text();
}

export async function fetchProjectQcReport(projectId: string): Promise<QCReport> {
  return apiFetch<QCReport>(`/api/v1/projects/${projectId}/export?format=qc`);
}

export function projectExportDownloadUrl(projectId: string): string {
  return `${getApiBaseUrl()}/api/v1/projects/${projectId}/export`;
}
