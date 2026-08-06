"use client";

import { useState } from "react";

import { useLabelSummary } from "@/hooks/use-label-summary";
import {
  formatLabelCount,
  formatLabelFieldTitle,
  getHiddenLabelCount,
  getVisibleLabelItems,
  type LabelFieldSummary,
} from "@/lib/label-summary";

type LabelSummaryProps = {
  projectId: string;
  exportReady: boolean;
};

function LabelFieldSummaryBlock({ summary }: { summary: LabelFieldSummary }) {
  const [expanded, setExpanded] = useState(false);
  const hiddenCount = getHiddenLabelCount(summary);
  const visibleItems = getVisibleLabelItems(summary, expanded);

  return (
    <div className="space-y-1.5">
      <p className="text-xs font-semibold">{formatLabelFieldTitle(summary)}</p>
      <dl className="space-y-1 text-xs text-muted-foreground">
        {visibleItems.map((item) => (
          <div
            key={item.value}
            className="grid grid-cols-[minmax(0,1fr)_auto] gap-3"
          >
            <dt className="truncate">{item.value}</dt>
            <dd className="shrink-0 text-right font-mono">
              {formatLabelCount(item.count, item.percentage)}
            </dd>
          </div>
        ))}
      </dl>
      {hiddenCount > 0 && !expanded ? (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="font-mono text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          +{hiddenCount} more
        </button>
      ) : null}
    </div>
  );
}

/** Compact label distribution summary from completed export rows. */
export function LabelSummary({ projectId, exportReady }: LabelSummaryProps) {
  const { summaries, error, isLoading } = useLabelSummary(projectId, exportReady);

  if (!exportReady || isLoading) {
    return null;
  }

  if (error) {
    return <p className="text-xs text-destructive">{error}</p>;
  }

  if (summaries.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3 border-t border-border pt-4">
      <p className="text-xs font-medium text-muted-foreground">Label summary</p>
      <div className="space-y-3">
        {summaries.map((summary) => (
          <LabelFieldSummaryBlock key={summary.field} summary={summary} />
        ))}
      </div>
    </div>
  );
}
