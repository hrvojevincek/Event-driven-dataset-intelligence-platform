"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, Trash2 } from "lucide-react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogMedia,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useDeleteProject, useProjectList } from "@/hooks/use-projects";
import { templateById } from "@/lib/schema-templates";

type PendingDelete = {
  projectId: string;
  name: string;
};

function statusVariant(
  status: string,
): "default" | "secondary" | "outline" | "destructive" {
  if (status === "completed") {
    return "secondary";
  }
  if (status === "failed") {
    return "destructive";
  }
  return "outline";
}

function formatRelativeTime(iso: string): string {
  const date = new Date(iso);
  const deltaMs = Date.now() - date.getTime();
  const minutes = Math.floor(deltaMs / 60_000);
  if (minutes < 1) {
    return "just now";
  }
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h ago`;
  }
  return date.toLocaleDateString();
}

export function ProjectHistory() {
  const { data, isLoading, error } = useProjectList();
  const deleteProject = useDeleteProject();
  const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(
    null,
  );

  async function confirmDelete() {
    if (!pendingDelete) {
      return;
    }
    await deleteProject.mutateAsync(pendingDelete.projectId);
    setPendingDelete(null);
  }

  return (
    <section className="space-y-4">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h2 className="text-base font-medium">Recent projects</h2>
          <p className="text-sm text-muted-foreground">
            Dataset jobs, newest first.
          </p>
        </div>
        <Link
          href="/projects/new"
          className="text-sm text-primary hover:underline"
        >
          New project
        </Link>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Project history</CardTitle>
          <CardDescription>
            Click a project to open the live pipeline view.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading projects…</p>
          ) : null}
          {error ? (
            <p className="text-sm text-destructive">
              Failed to load projects. Is the API running?
            </p>
          ) : null}
          {!isLoading && !error && (data?.length ?? 0) === 0 ? (
            <p className="text-sm text-muted-foreground">
              No projects yet.{" "}
              <Link
                href="/projects/new"
                className="text-primary hover:underline"
              >
                Upload your first files
              </Link>
              .
            </p>
          ) : null}
          {data && data.length > 0 ? (
            <ul className="divide-y divide-border">
              {data.map((project) => (
                <li key={project.job_id}>
                  <div className="group -mx-2 flex items-center justify-between gap-2 rounded-lg px-2 py-3 hover:bg-muted/30">
                    <Link
                      href={`/projects/${project.job_id}`}
                      className="flex min-w-0 flex-1 items-center justify-between gap-4"
                    >
                      <div className="min-w-0 space-y-1">
                        <p className="truncate text-sm font-medium">
                          {project.name}
                        </p>
                        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                          <Badge
                            variant={statusVariant(project.status)}
                            className="font-mono text-[10px] uppercase"
                          >
                            {project.status.replaceAll("_", " ")}
                          </Badge>
                          <span>
                            {templateById(project.schema_template)?.label ??
                              project.schema_template ??
                              "custom schema"}
                          </span>
                          <span>{project.asset_count} files</span>
                          <span>{formatRelativeTime(project.created_at)}</span>
                        </div>
                      </div>
                      <ArrowRight className="size-4 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                    </Link>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Delete ${project.name}`}
                      disabled={
                        deleteProject.isPending &&
                        deleteProject.variables === project.job_id
                      }
                      onClick={() => {
                        setPendingDelete({
                          projectId: project.job_id,
                          name: project.name,
                        });
                      }}
                      className="shrink-0 text-muted-foreground hover:text-destructive"
                    >
                      <Trash2 />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          ) : null}
        </CardContent>
      </Card>

      <AlertDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open && !deleteProject.isPending) {
            setPendingDelete(null);
          }
        }}
      >
        <AlertDialogContent size="default">
          <AlertDialogHeader>
            <AlertDialogMedia className="bg-destructive/10 text-destructive">
              <Trash2 />
            </AlertDialogMedia>
            <AlertDialogTitle>Delete this project?</AlertDialogTitle>
            <AlertDialogDescription>
              {pendingDelete ? (
                <>
                  <span className="font-medium text-foreground">
                    {pendingDelete.name}
                  </span>{" "}
                  will be permanently removed, including uploads, labels, and
                  exports. This cannot be undone.
                </>
              ) : null}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteProject.isPending}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={deleteProject.isPending}
              onClick={() => {
                void confirmDelete();
              }}
            >
              {deleteProject.isPending ? "Deleting…" : "Delete project"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
}
