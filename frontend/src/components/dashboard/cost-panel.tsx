"use client";

import type { ProjectDetail } from "@/lib/api-client";

type CostPanelProps = {
  detail: ProjectDetail | undefined;
  isLoading: boolean;
};

function formatUsd(value: number | undefined, hasUsage: boolean): string {
  if (!hasUsage || value === undefined) {
    return "—";
  }
  if (value >= 0.01) {
    return `$${value.toFixed(4)}`;
  }
  if (value > 0) {
    return `$${value.toFixed(6)}`;
  }
  return "$0.0000";
}

function formatTokens(calls: ProjectDetail["llm_usage"]["calls"]): string {
  if (calls.length === 0) {
    return "—";
  }
  const total = calls.reduce(
    (sum, call) => sum + call.input_tokens + call.output_tokens,
    0,
  );
  return total.toLocaleString();
}

export function CostPanel({ detail, isLoading }: CostPanelProps) {
  const usage = detail?.llm_usage;
  const calls = usage?.calls ?? [];
  const hasUsage = calls.length > 0;

  return (
    <>
      <dl className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-muted-foreground">Tokens</dt>
          <dd className="font-mono">
            {isLoading && !detail ? "…" : formatTokens(calls)}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Est. cost</dt>
          <dd className="font-mono">
            {isLoading && !detail
              ? "…"
              : formatUsd(usage?.total_cost_usd, hasUsage)}
          </dd>
        </div>
      </dl>
      {hasUsage ? (
        <ul className="mt-3 space-y-1.5 text-xs text-muted-foreground">
          {calls.map((call) => (
            <li
              key={call.id}
              className="flex items-center justify-between gap-2 font-mono"
            >
              <span className="truncate">{call.agent_name}</span>
              <span className="shrink-0">
                {formatUsd(call.cost_usd, true)}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );
}
