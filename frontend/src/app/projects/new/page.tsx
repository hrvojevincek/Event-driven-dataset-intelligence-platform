import { Badge } from "@/components/ui/badge";
import { ProjectSubmitForm } from "@/components/dashboard/project-submit-form";

export default function NewProjectPage() {
  return (
    <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 p-6 md:p-10">
      <div className="space-y-2">
        <Badge variant="secondary" className="font-mono text-[10px] uppercase">
          New project
        </Badge>
        <h1 className="text-xl font-semibold tracking-tight">
          Upload files and define labels
        </h1>
        <p className="text-sm text-muted-foreground">
          Pick a schema template, upload documents or transcripts, and start the
          dataset pipeline.
        </p>
      </div>

      <ProjectSubmitForm />
    </div>
  );
}
