"use client";

import { useMemo } from "react";

import type { ProjectDetail } from "@/lib/api-client";

type CostPanelProps = {
  detail: ProjectDetail | undefined;
  isLoading: boolean;
};

type AggregatedAgentUsage = {
  agentName: string;
  inputTokens: number;
  outputTokens: number;
  costUsd: number;
};

const LEGACY_AGENT_ALIASES: Record<string, string> = {
  research: "annotation",
};

function displayAgentName(agentName: string): string {
  return LEGACY_AGENT_ALIASES[agentName] ?? agentName;
}

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

function aggregateByAgent(
  calls: ProjectDetail["llm_usage"]["calls"],
): AggregatedAgentUsage[] {
  const byAgent = new Map<string, AggregatedAgentUsage>();

  for (const call of calls) {
    const agentName = displayAgentName(call.agent_name);
    const existing = byAgent.get(agentName) ?? {
      agentName,
      inputTokens: 0,
      outputTokens: 0,
      costUsd: 0,
    };
    existing.inputTokens += call.input_tokens;
    existing.outputTokens += call.output_tokens;
    existing.costUsd += call.cost_usd;
    byAgent.set(agentName, existing);
  }

  return Array.from(byAgent.values()).sort((left, right) => {
    if (right.costUsd !== left.costUsd) {
      return right.costUsd - left.costUsd;
    }
    return left.agentName.localeCompare(right.agentName);
  });
}

const BREAKDOWN_COLLAPSE_THRESHOLD = 5;

export function CostPanel({ detail, isLoading }: CostPanelProps) {
  const usage = detail?.llm_usage;
  const calls = useMemo(() => usage?.calls ?? [], [usage?.calls]);
  const hasUsage = calls.length > 0;
  const aggregated = useMemo(() => aggregateByAgent(calls), [calls]);
  const collapsedAgents = aggregated.slice(0, BREAKDOWN_COLLAPSE_THRESHOLD);
  const hiddenAgentCount = Math.max(
    0,
    aggregated.length - BREAKDOWN_COLLAPSE_THRESHOLD,
  );

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
        <div className="mt-3 space-y-2">
          <p className="text-xs font-medium text-muted-foreground">Breakdown</p>
          <ul className="space-y-1.5 text-xs text-muted-foreground">
            {collapsedAgents.map((row) => (
              <li
                key={row.agentName}
                className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3 font-mono"
              >
                <span className="truncate">{row.agentName}</span>
                <span className="shrink-0 text-right">
                  {(row.inputTokens + row.outputTokens).toLocaleString()}
                </span>
                <span className="shrink-0 text-right">
                  {formatUsd(row.costUsd, true)}
                </span>
              </li>
            ))}
          </ul>
          {hiddenAgentCount > 0 ? (
            <p className="text-xs text-muted-foreground">
              +{hiddenAgentCount} more agent
              {hiddenAgentCount === 1 ? "" : "s"} in usage log
            </p>
          ) : null}
        </div>
      ) : null}
    </>
  );
}
