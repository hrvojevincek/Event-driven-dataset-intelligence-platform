"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getApiBaseUrl } from "@/lib/api-client";
import { connectSse } from "@/lib/sse-client";
import type {
  JobStageSnapshot,
  JobStreamEvent,
  StageStatus,
} from "@/types/job-stream";
import { buildStageMap } from "@/types/job-stream";

const INITIAL_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 15_000;

export type UseJobStreamState = {
  connected: boolean;
  jobStatus: string | null;
  correlationId: string | null;
  stages: Record<string, JobStageSnapshot>;
  lastEvent: JobStreamEvent | null;
  error: string | null;
};

const initialState: UseJobStreamState = {
  connected: false,
  jobStatus: null,
  correlationId: null,
  stages: {},
  lastEvent: null,
  error: null,
};

function applyStreamEvent(
  previous: UseJobStreamState,
  event: JobStreamEvent,
): UseJobStreamState {
  if (event.event === "snapshot" || event.event === "job_complete") {
    return {
      ...previous,
      connected: true,
      jobStatus: event.job_status ?? previous.jobStatus,
      correlationId: event.correlation_id,
      stages: buildStageMap(event.stages),
      lastEvent: event,
      error: null,
    };
  }

  if (event.event === "stage_update" && event.stage && event.status) {
    const existing = previous.stages[event.stage];
    const nextStage: JobStageSnapshot = {
      stage: event.stage,
      status: event.status as StageStatus,
      started_at: existing?.started_at ?? null,
      completed_at: existing?.completed_at ?? null,
      duration_ms: event.duration_ms ?? existing?.duration_ms ?? null,
      error_detail: event.detail ?? existing?.error_detail ?? null,
    };

    return {
      ...previous,
      connected: true,
      jobStatus: event.job_status ?? previous.jobStatus,
      correlationId: event.correlation_id,
      stages: {
        ...previous.stages,
        [event.stage]: nextStage,
      },
      lastEvent: event,
      error: null,
    };
  }

  return {
    ...previous,
    connected: true,
    lastEvent: event,
    error: null,
  };
}

export function useJobStream(jobId: string): UseJobStreamState {
  const [state, setState] = useState<UseJobStreamState>(initialState);
  const backoffRef = useRef(INITIAL_BACKOFF_MS);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleEvent = useCallback((event: JobStreamEvent) => {
    setState((previous) => applyStreamEvent(previous, event));
  }, []);

  useEffect(() => {
    let cancelled = false;
    const abortController = new AbortController();
    let jobComplete = false;

    const connect = async () => {
      if (cancelled || jobComplete) {
        return;
      }

      const url = `${getApiBaseUrl()}/api/v1/projects/${jobId}/stream`;

      try {
        setState((previous) => ({ ...previous, connected: true, error: null }));
        backoffRef.current = INITIAL_BACKOFF_MS;

        await connectSse(
          url,
          (_eventName, data) => {
            try {
              const parsed = JSON.parse(data) as JobStreamEvent;
              handleEvent(parsed);
              if (parsed.event === "job_complete") {
                jobComplete = true;
                abortController.abort();
              }
            } catch {
              setState((previous) => ({
                ...previous,
                error: "Failed to parse stream event",
              }));
            }
          },
          abortController.signal,
        );

        if (!cancelled && !jobComplete) {
          setState((previous) => ({
            ...previous,
            connected: false,
            error: "Stream disconnected",
          }));
        }
      } catch {
        if (cancelled || abortController.signal.aborted || jobComplete) {
          return;
        }

        setState((previous) => ({
          ...previous,
          connected: false,
          error: "Stream disconnected",
        }));

        const delay = backoffRef.current;
        backoffRef.current = Math.min(delay * 2, MAX_BACKOFF_MS);
        reconnectTimerRef.current = setTimeout(() => {
          void connect();
        }, delay);
      }
    };

    void connect();

    return () => {
      cancelled = true;
      abortController.abort();
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
    };
  }, [handleEvent, jobId]);

  return state;
}
