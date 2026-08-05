import { Badge } from "@/components/ui/badge";
import { ProjectHistory } from "@/components/dashboard/project-history";
import Link from "next/link";
import { ArrowRight, FileJson, GitBranch, Layers } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const stages = [
  "Intake",
  "Preprocessing",
  "Planning",
  "Annotation",
  "Export",
];

export default function HomePage() {
  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-10 p-6 md:p-10">
      <section className="space-y-4">
        <Badge variant="secondary" className="font-mono text-[10px] uppercase">
          Dataset intelligence
        </Badge>
        <div className="max-w-2xl space-y-3">
          <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
            Files in, labeled JSONL out
          </h1>
          <p className="text-sm leading-relaxed text-muted-foreground">
            Upload documents or transcripts, pick an annotation schema, and watch
            an event-driven pipeline extract segments, label them in parallel, and
            deliver JSONL with QC metrics — live in React Flow.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button nativeButton={false} render={<Link href="/projects/new" />}>
            New project
            <ArrowRight data-icon="inline-end" />
          </Button>
        </div>
      </section>

      <ProjectHistory />

      <section className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <Layers className="mb-1 size-4 text-primary" />
            <CardTitle>Schema templates</CardTitle>
            <CardDescription>
              Support-call and document-classification presets with optional JSON
              override.
            </CardDescription>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <FileJson className="mb-1 size-4 text-secondary" />
            <CardTitle>JSONL + QC</CardTitle>
            <CardDescription>
              Coverage, compliance, confidence flags, and downloadable labeled
              rows with provenance.
            </CardDescription>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <GitBranch className="mb-1 size-4 text-primary" />
            <CardTitle>Live pipeline</CardTitle>
            <CardDescription>
              SSE-driven React Flow as intake → export stages complete.
            </CardDescription>
          </CardHeader>
        </Card>
      </section>

      <section className="space-y-4">
        <div className="flex items-end justify-between gap-4">
          <div>
            <h2 className="text-base font-medium">Pipeline stages</h2>
            <p className="text-sm text-muted-foreground">
              Five stages from upload to labeled export.
            </p>
          </div>
        </div>
        <Card>
          <CardContent className="flex flex-wrap gap-2 pt-4">
            {stages.map((stage, index) => (
              <div key={stage} className="flex items-center gap-2">
                <Badge variant="outline" className="font-mono text-xs">
                  {String(index + 1).padStart(2, "0")}
                </Badge>
                <span className="text-sm">{stage}</span>
                {index < stages.length - 1 ? (
                  <ArrowRight className="size-3.5 text-muted-foreground" />
                ) : null}
              </div>
            ))}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
