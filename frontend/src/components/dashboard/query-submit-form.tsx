"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useSubmitQuery } from "@/hooks/use-queries";
import { ApiError } from "@/lib/api-client";
import type { SubmitQueryRequest } from "@/lib/api-client";

const depthOptions = [
  { value: "quick", label: "Quick", hint: "~1 min · fewer sources" },
  { value: "standard", label: "Standard", hint: "~3 min · balanced" },
  { value: "deep", label: "Deep", hint: "~5 min · thorough" },
] as const;

export function QuerySubmitForm() {
  const router = useRouter();
  const submit = useSubmitQuery();
  const [topic, setTopic] = useState("");
  const [depth, setDepth] = useState<SubmitQueryRequest["depth"]>("standard");
  const [maxSources, setMaxSources] = useState("");

  async function handleSubmit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmedTopic = topic.trim();
    if (!trimmedTopic) {
      return;
    }

    const body: SubmitQueryRequest = {
      topic: trimmedTopic,
      depth,
    };

    const parsedMax = maxSources.trim();
    if (parsedMax) {
      const value = Number.parseInt(parsedMax, 10);
      if (!Number.isNaN(value)) {
        body.max_sources = value;
      }
    }

    try {
      const result = await submit.mutateAsync(body);
      router.push(`/queries/${result.job_id}`);
    } catch {
      // Error surfaced via submit.error below
    }
  }

  const errorMessage =
    submit.error instanceof ApiError
      ? submit.error.message
      : submit.error
        ? "Failed to submit query"
        : null;

  return (
    <form onSubmit={handleSubmit}>
      <Card>
        <CardHeader>
          <CardTitle>Query parameters</CardTitle>
          <CardDescription>
            Topic is required. Depth and source limits are optional constraints.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-2">
            <Label htmlFor="topic">Topic</Label>
            <Input
              id="topic"
              name="topic"
              required
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
              placeholder="e.g. Impact of event-driven architectures on agent orchestration"
            />
          </div>

          <fieldset className="space-y-3">
            <legend className="text-sm font-medium">Depth</legend>
            <div className="grid gap-2 sm:grid-cols-3">
              {depthOptions.map((option) => (
                <label
                  key={option.value}
                  className="flex cursor-pointer flex-col gap-1 rounded-lg border border-border p-3 has-checked:border-primary has-checked:bg-primary/5"
                >
                  <span className="flex items-center gap-2 text-sm font-medium">
                    <input
                      type="radio"
                      name="depth"
                      value={option.value}
                      checked={depth === option.value}
                      onChange={() => setDepth(option.value)}
                      className="accent-primary"
                    />
                    {option.label}
                  </span>
                  <span className="pl-5 text-xs text-muted-foreground">
                    {option.hint}
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          <div className="space-y-2">
            <Label htmlFor="max_sources">Max sources (optional)</Label>
            <Input
              id="max_sources"
              name="max_sources"
              type="number"
              min={1}
              max={50}
              placeholder="20"
              value={maxSources}
              onChange={(event) => setMaxSources(event.target.value)}
            />
          </div>

          {errorMessage ? (
            <p className="text-sm text-destructive">{errorMessage}</p>
          ) : null}
        </CardContent>
        <CardFooter className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground">
            Queries are scoped to the local mock user account.
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              nativeButton={false}
              render={<Link href="/" />}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={submit.isPending || !topic.trim()}>
              {submit.isPending ? "Submitting…" : "Submit query"}
            </Button>
          </div>
        </CardFooter>
      </Card>
    </form>
  );
}
