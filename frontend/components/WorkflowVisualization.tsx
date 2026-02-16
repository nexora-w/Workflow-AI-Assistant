'use client';

import { useCallback, useMemo, useEffect, useRef, useState } from 'react';
import ReactFlow, {
  Node,
  Edge,
  Controls,
  Background,
  MiniMap,
  useNodesState,
  useEdgesState,
  BackgroundVariant,
  NodeChange,
  MarkerType,
  ReactFlowInstance,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { workflowApi, chatWS, WSMessage, WorkflowOp, StreamingNode, StreamingEdge } from '@/lib/api';
import type { StreamingData } from '@/app/page';
import VersionTimeline from './VersionTimeline';
import styles from './WorkflowVisualization.module.css';

/** Delay (ms) between each node "dropping in" during streaming. */
const NODE_REVEAL_DELAY = 400;

interface WorkflowVisualizationProps {
  workflowData: string | null;
  streamingData?: StreamingData | null;
  chatId: number | null;
  onPositionChange?: (workflowData: string) => void;
}

// Node style helper
function getNodeStyle(type: string): React.CSSProperties {
  return {
    background: type === 'start' ? '#FC005C' :
               type === 'end' ? '#667eea' :
               type === 'decision' ? '#f6ad55' :
               '#48bb78',
    color: 'white',
    padding: '10px 20px',
    borderRadius: type === 'decision' ? '8px' : '50px',
    fontSize: '14px',
    fontWeight: '500',
    border: 'none',
    minWidth: '150px',
    textAlign: 'center' as const,
  };
}

export default function WorkflowVisualization({ 
  workflowData,
  streamingData,
  chatId,
  onPositionChange 
}: WorkflowVisualizationProps) {
  const saveTimerRef = useRef<NodeJS.Timeout | null>(null);
  const lastSavedDataRef = useRef<string | null>(null);
  const workflowVersionRef = useRef<number>(0);
  const [conflictMessage, setConflictMessage] = useState<string | null>(null);
  const [previewData, setPreviewData] = useState<string | null>(null);

  // ----- Staggered node reveal state -----
  const [revealedCount, setRevealedCount] = useState(0);
  const revealTimerRef = useRef<NodeJS.Timeout | null>(null);
  const reactFlowRef = useRef<ReactFlowInstance | null>(null);

  const handleVersionRevert = useCallback((data: string, version: number) => {
    workflowVersionRef.current = version;
    setPreviewData(null);
    if (onPositionChange) {
      onPositionChange(data);
    }
  }, [onPositionChange]);

  const handleVersionPreview = useCallback((data: string | null) => {
    setPreviewData(data);
  }, []);

  // Fetch initial workflow version when chat or workflow changes
  useEffect(() => {
    if (chatId && workflowData) {
      workflowApi.getState(chatId).then(state => {
        workflowVersionRef.current = state.version;
      }).catch(() => {
        workflowVersionRef.current = 0;
      });
    }
  }, [chatId, workflowData]);

  // Listen for remote workflow operations to update our version
  useEffect(() => {
    const unsubOp = chatWS.on('workflow_op', (data: WSMessage) => {
      if (data.chat_id === chatId && data.version) {
        workflowVersionRef.current = data.version;
      }
    });
    const unsubMsg = chatWS.on('new_message', (data: WSMessage) => {
      if (data.chat_id === chatId && data.workflow_version) {
        workflowVersionRef.current = data.workflow_version;
      }
    });
    return () => { unsubOp(); unsubMsg(); };
  }, [chatId]);

  // ----- Staggered node reveal: reveal one node at a time like chat messages -----

  // Reset when streaming stops
  useEffect(() => {
    if (!streamingData) {
      setRevealedCount(0);
      if (revealTimerRef.current) {
        clearTimeout(revealTimerRef.current);
        revealTimerRef.current = null;
      }
    }
  }, [streamingData]);

  // Drive the stagger: whenever there are un-revealed nodes, schedule the next one
  useEffect(() => {
    if (!streamingData) return;

    const target = streamingData.nodes.length;

    if (revealedCount < target) {
      revealTimerRef.current = setTimeout(() => {
        setRevealedCount(prev => prev + 1);
      }, NODE_REVEAL_DELAY);
    }

    return () => {
      if (revealTimerRef.current) {
        clearTimeout(revealTimerRef.current);
        revealTimerRef.current = null;
      }
    };
  }, [streamingData, streamingData?.nodes.length, revealedCount]);

  // Auto-fit the view each time a new node is revealed (camera follows the graph)
  useEffect(() => {
    if (revealedCount > 0 && reactFlowRef.current) {
      reactFlowRef.current.fitView({ padding: 0.35, duration: 300 });
    }
  }, [revealedCount]);

  const parseWorkflow = useCallback((data: string | null) => {
  if (!data) {
    return { nodes: [], edges: [] };
  }

  try {
    const workflow = JSON.parse(data);
    
    // Build adjacency map for the graph that will be displayed.
    const adjacencyMap = new Map<string, string[]>();
    workflow.edges.forEach((edge: any) => {
      if (!adjacencyMap.has(edge.from)) {
        adjacencyMap.set(edge.from, []);
      }
      adjacencyMap.get(edge.from)!.push(edge.to);
    });

    // Find nodes where branches merge from decision nodes merge.
    const incomingEdges = new Map<string, string[]>();
    workflow.edges.forEach((edge: any) => {
      if (!incomingEdges.has(edge.to)) {
        incomingEdges.set(edge.to, []);
      }
      incomingEdges.get(edge.to)!.push(edge.from);
    });

    const mergeNodes = new Set<string>();
    incomingEdges.forEach((sources, target) => {
      if (sources.length > 1) {
        mergeNodes.add(target);
      }
    });

    // Calculate positions with the branching logic
    const positions = new Map<string, { x: number; y: number }>();
    const visited = new Set<string>();
    let currentY = 100;
    const verticalSpacing = 180; // Increased spacing between nodes for better routing
    const horizontalSpacing = 350; // Increased spacing for branches of decision nodes
    const centerX = 400; // Center of the workflow

    const calculatePositions = (
      nodeId: string, 
      x: number, 
      y: number, 
      isBranch: boolean = false,
      branchIndex: number = 0,
      totalBranches: number = 1
    ) => {
      if (visited.has(nodeId)) return;
      visited.add(nodeId);

      const node = workflow.nodes.find((n: any) => n.id === nodeId);
      if (!node) return;

      // Calculate each node position
      let nodeX = x;
      let nodeY = y;

      // Use saved position if available, otherwise calculate. This way, calculations can be reduced.
      if (node.position) {
        positions.set(nodeId, node.position);
        nodeX = node.position.x;
        nodeY = node.position.y;
      } else {
        if (isBranch && totalBranches > 1) {
          // Spread branches horizontally
          const offset = (branchIndex - (totalBranches - 1) / 2) * horizontalSpacing;
          nodeX = centerX + offset;
        }

        positions.set(nodeId, { x: nodeX, y: nodeY });
      }

      const children = adjacencyMap.get(nodeId) || [];
      const isDecision = node.type === 'decision';
      const nextY = y + verticalSpacing;

      if (isDecision && children.length > 1) {
        // Decision node with multiple children, so they are laid out horizontally
        children.forEach((childId, index) => {
          calculatePositions(
            childId,
            centerX,
            nextY,
            true,
            index,
            children.length
          );
        });
      } else if (children.length === 1) {
        // If it only has a single child, check if it's a merge point for the decision branches
        const childId = children[0];
        const isMerge = mergeNodes.has(childId);
        
        if (isMerge) {
          // This is where branches merge, so we go back to center position
          calculatePositions(childId, centerX, nextY, false, 0, 1);
        } else {
          // Continue in same branch, since it is not a merge point
          calculatePositions(childId, nodeX, nextY, isBranch, branchIndex, totalBranches);
        }
      } else if (children.length > 1 && !isDecision) {
        // Regular node with multiple children, in case the API returns a regular node with more than one branch as a failsafe
        children.forEach((childId, index) => {
          calculatePositions(
            childId,
            centerX,
            nextY,
            true,
            index,
            children.length
          );
        });
      }
    };

    // Find the starting node
    const startNode = workflow.nodes.find((n: any) => n.type === 'start');
    if (startNode) {
      calculatePositions(startNode.id, centerX, currentY);
    } else if (workflow.nodes.length > 0) {
      // If no start node, then use first node
      calculatePositions(workflow.nodes[0].id, centerX, currentY);
    }

    // Filter out disconnected/orphaned nodes (nodes not visited from start)
    const connectedNodes = workflow.nodes.filter((node: any) => visited.has(node.id));

    const nodes: Node[] = connectedNodes.map((node: any) => {
      const position = positions.get(node.id) || { x: centerX, y: 100 };
      
      return {
        id: node.id,
        type: 'default',
        data: { label: node.label },
        position,
        style: getNodeStyle(node.type),
      };
    });

    const edges: Edge[] = workflow.edges.map((edge: any) => ({
      id: `e${edge.from}-${edge.to}`,
      source: edge.from,
      target: edge.to,
      animated: true,
      style: { stroke: '#667eea', strokeWidth: 2 },
      type: 'smoothstep',
      pathOptions: { 
        offset: 35,        
        borderRadius: 25, 
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: 20,
        height: 20,
        color: '#667eea',
      },
      // Use bottom/top handles for vertical flows
      sourceHandle: undefined,  // Auto-select best handle
    }));

    return { nodes, edges };
  } catch (error) {
    console.error('Failed to parse workflow:', error);
    return { nodes: [], edges: [] };
  }
}, []);

  // Build streaming visualization: only show the first `revealedCount` nodes.
  // Each node gets an entrance animation; the newest gets a glow.
  const buildStreamingGraph = useCallback(
    (sData: StreamingData, revealed: number): { nodes: Node[]; edges: Edge[] } => {
      const centerX = 400;
      const verticalSpacing = 180;

      // Only show nodes up to the revealed count
      const visibleNodes = sData.nodes.slice(0, revealed);
      const visibleIds = new Set(visibleNodes.map(n => n.id));

      const nodes: Node[] = visibleNodes.map((node, index) => ({
        id: node.id,
        type: 'default',
        data: { label: node.label },
        position: { x: centerX, y: 100 + index * verticalSpacing },
        style: {
          ...getNodeStyle(node.type),
          animation: 'workflowNodeAppear 0.5s cubic-bezier(0.22, 1, 0.36, 1) forwards',
          // The newest revealed node gets a pulsing glow
          ...(index === revealed - 1 && sData.isStreaming
            ? {
                boxShadow:
                  '0 0 0 4px rgba(252, 0, 92, 0.3), 0 0 20px rgba(252, 0, 92, 0.15)',
              }
            : {}),
        },
      }));

      // Only show edges where BOTH source and target are already revealed
      const edges: Edge[] = sData.edges
        .filter(e => visibleIds.has(e.from) && visibleIds.has(e.to))
        .map(edge => ({
          id: `e${edge.from}-${edge.to}`,
          source: edge.from,
          target: edge.to,
          animated: true,
          style: {
            stroke: '#667eea',
            strokeWidth: 2,
            animation: 'workflowEdgeAppear 0.4s ease-out forwards',
          },
          type: 'smoothstep',
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 20,
            height: 20,
            color: '#667eea',
          },
        }));

      return { nodes, edges };
    },
    []
  );

  const { nodes: initialNodes, edges: initialEdges } = useMemo(
    () => parseWorkflow(workflowData),
    [workflowData, parseWorkflow]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Update nodes and edges when workflow data, preview, or streaming changes
  const displayData = previewData || workflowData;

  useEffect(() => {
    // If actively streaming AND we have nodes to show, use the staggered reveal
    if (streamingData && revealedCount > 0) {
      const { nodes: sNodes, edges: sEdges } = buildStreamingGraph(
        streamingData,
        revealedCount
      );
      setNodes(sNodes);
      setEdges(sEdges);
      return;
    }

    // Otherwise render the final (non-streaming) workflow
    if (!streamingData) {
      const { nodes: newNodes, edges: newEdges } = parseWorkflow(displayData);
      setNodes(newNodes);
      setEdges(newEdges);
    }
  }, [displayData, streamingData, revealedCount, parseWorkflow, buildStreamingGraph, setNodes, setEdges]);

  // Cleanup debounce timer when unmounted
  useEffect(() => {
    return () => {
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current);
      }
    };
  }, []);

  // Collect pending move operations and send them as a batch
  const pendingOpsRef = useRef<Map<string, { x: number; y: number }>>(new Map());

  const flushOperations = useCallback(async () => {
    if (!chatId || pendingOpsRef.current.size === 0) return;

    const ops: WorkflowOp[] = [];
    pendingOpsRef.current.forEach((position, nodeId) => {
      ops.push({
        op_type: 'move_node',
        payload: { node_id: nodeId, position }
      });
    });
    pendingOpsRef.current.clear();

    const baseVersion = workflowVersionRef.current;

    try {
      const result = await workflowApi.applyOperations(chatId, baseVersion, ops);

      if (result.status === 'conflict') {
        setConflictMessage(
          result.conflicts[0] || 'Your edit conflicted with another user\'s change. Refreshing...'
        );
        setTimeout(() => setConflictMessage(null), 4000);

        // Rebase: apply the server's latest state
        if (onPositionChange) {
          onPositionChange(result.data);
        }
        workflowVersionRef.current = result.version;
      } else {
        workflowVersionRef.current = result.version;
        if (result.status === 'merged') {
          // Server merged our changes with concurrent ones — update local state
          if (onPositionChange) {
            onPositionChange(result.data);
          }
        } else {
          // Applied cleanly — also update the legacy message store
          if (onPositionChange) {
            onPositionChange(result.data);
          }
        }
        lastSavedDataRef.current = result.data;
      }
    } catch (error) {
      console.error('Failed to apply workflow operations:', error);
      // Fallback to legacy full-state save
      if (onPositionChange && workflowData) {
        onPositionChange(workflowData);
      }
    }
  }, [chatId, onPositionChange, workflowData]);

  // Debounced flush
  const debouncedFlush = useCallback(() => {
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
    }
    saveTimerRef.current = setTimeout(() => {
      flushOperations();
    }, 500);
  }, [flushOperations]);

  // Handle node changes with operation-based saving
  const handleNodesChange = useCallback((changes: NodeChange[]) => {
    onNodesChange(changes);
    
    const hasDragStop = changes.some(change => 
      change.type === 'position' && change.dragging === false
    );
    
    if (hasDragStop && workflowData) {
      setTimeout(() => {
        setNodes((currentNodes) => {
          try {
            const workflow = JSON.parse(workflowData);
            
            for (const change of changes) {
              if (change.type === 'position' && change.dragging === false && change.position) {
                pendingOpsRef.current.set(change.id, change.position);
              }
            }
            
            // Also build the full updated workflow for local state
            const updatedNodes = workflow.nodes.map((node: any) => {
              const reactFlowNode = currentNodes.find((n: Node) => n.id === node.id);
              return {
                ...node,
                position: reactFlowNode?.position || node.position
              };
            });
            
            const updatedWorkflow = { ...workflow, nodes: updatedNodes };
            lastSavedDataRef.current = JSON.stringify(updatedWorkflow);
            
            debouncedFlush();
          } catch (error) {
            console.error('Failed to process position change:', error);
          }
          
          return currentNodes;
        });
      }, 0);
    }
  }, [onNodesChange, workflowData, setNodes, debouncedFlush]);

  const isStreamActive = streamingData && streamingData.isStreaming;
  const hasVisibleStreamingNodes = streamingData && revealedCount > 0;

  if (!workflowData && !hasVisibleStreamingNodes) {
    return (
      <div className={styles.container}>
        <div className={styles.emptyState}>
          <svg
            className={styles.icon}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <rect x="3" y="3" width="7" height="7" rx="1" />
            <rect x="14" y="3" width="7" height="7" rx="1" />
            <rect x="14" y="14" width="7" height="7" rx="1" />
            <rect x="3" y="14" width="7" height="7" rx="1" />
            <path d="M10 6.5h4M10 17.5h4M6.5 10v4M17.5 10v4" />
          </svg>
          <h3>Workflow Visualization</h3>
          <p>Ask the AI Chatbot to create a workflow and it will be visualized over here</p>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      {isStreamActive && (
        <div className={styles.streamingBanner}>
          <div className={styles.streamingDot} />
          <span>Building workflow&hellip;</span>
          <span className={styles.streamingCount}>
            {revealedCount} / {streamingData!.nodes.length} node{streamingData!.nodes.length !== 1 ? 's' : ''}
          </span>
        </div>
      )}
      {conflictMessage && (
        <div className={styles.conflictBanner}>
          <span className={styles.conflictIcon}>!</span>
          {conflictMessage}
        </div>
      )}
      {previewData && (
        <div className={styles.previewBanner}>
          Previewing an older version. Click &ldquo;Accept&rdquo; to revert or &ldquo;Exit preview&rdquo; to return.
        </div>
      )}
      <VersionTimeline
        chatId={chatId}
        onRevert={handleVersionRevert}
        onPreview={handleVersionPreview}
      />
      <div className={styles.flowContainer}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={handleNodesChange}
          onEdgesChange={onEdgesChange}
          onInit={(instance) => { reactFlowRef.current = instance; }}
          fitView
          attributionPosition="bottom-left"
          defaultEdgeOptions={{
            type: 'smoothstep',
            animated: true,
            style: { strokeWidth: 2 },
          }}
          connectionLineStyle={{ strokeWidth: 2, stroke: '#667eea' }}
          snapToGrid={true}
          snapGrid={[15, 15]}
          elevateEdgesOnSelect={true}
          minZoom={0.2}
          maxZoom={4}
          nodesDraggable={true}
          nodesConnectable={false}
          elementsSelectable={true}
          fitViewOptions={{ padding: 0.3 }}
        >
          <Controls />
          <MiniMap
            style={{
              background: '#f5f5f5',
            }}
            nodeColor={(node) => {
              const bgColor = node.style?.background as string;
              return bgColor || '#667eea';
            }}
          />
          <Background variant={BackgroundVariant.Dots} gap={12} size={1} />
        </ReactFlow>
      </div>
    </div>
  );
}
