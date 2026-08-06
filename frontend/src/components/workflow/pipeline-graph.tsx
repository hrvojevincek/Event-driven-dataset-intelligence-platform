"use client";

import {
  Background,
  BackgroundVariant,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  defaultStageId,
  type JobStageSnapshot,
} from "@/types/job-stream";

import { buildPipelineGraph } from "./build-pipeline-graph";
import { PipelineEdge } from "./pipeline-edge";
import { PipelineNode, type PipelineNodeData } from "./pipeline-node";
import { StageDetailPanel } from "./stage-detail-panel";

const nodeTypes = { pipeline: PipelineNode };
const edgeTypes = { pipeline: PipelineEdge };

type PipelineGraphProps = {
  stages: Record<string, JobStageSnapshot>;
  jobStatus: string | null;
};

function PipelineGraphCanvas({ stages, jobStatus }: PipelineGraphProps) {
  const { fitView } = useReactFlow();
  const [userSelectedStageId, setUserSelectedStageId] = useState<string | null>(
    null,
  );
  const autoStageId = useMemo(
    () => defaultStageId(jobStatus, stages),
    [jobStatus, stages],
  );
  const selectedStageId = userSelectedStageId ?? autoStageId;

  const { nodes, edges } = useMemo(
    () => buildPipelineGraph(stages),
    [stages],
  );

  useEffect(() => {
    fitView({ padding: 0.2, duration: 200 });
  }, [fitView, nodes]);

  const onNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node<PipelineNodeData>) => {
      setUserSelectedStageId(node.id);
    },
    [],
  );

  const selectedSnapshot = selectedStageId
    ? (stages[selectedStageId] ?? null)
    : null;

  return (
    <div className="flex flex-col gap-4">
      <div className="h-56 w-full rounded-lg border border-border bg-muted/20 [&_.react-flow\_\_panel]:hidden">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodeClick={onNodeClick}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable
          panOnDrag={false}
          zoomOnScroll={false}
          zoomOnPinch={false}
          zoomOnDoubleClick={false}
          preventScrolling={false}
          proOptions={{ hideAttribution: true }}
          fitView
        >
          <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
        </ReactFlow>
      </div>
      <StageDetailPanel
        stageId={selectedStageId}
        snapshot={selectedSnapshot}
      />
    </div>
  );
}

/** Live React Flow pipeline graph driven by SSE stage snapshots. */
export function PipelineGraph(props: PipelineGraphProps) {
  return (
    <ReactFlowProvider>
      <PipelineGraphCanvas {...props} />
    </ReactFlowProvider>
  );
}
