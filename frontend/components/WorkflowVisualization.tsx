'use client';

import { useCallback, useMemo, useEffect, useRef } from 'react';
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
} from 'reactflow';
import 'reactflow/dist/style.css';
import styles from './WorkflowVisualization.module.css';

interface WorkflowVisualizationProps {
  workflowData: string | null;
  chatId: number | null;
  onPositionChange?: (workflowData: string) => void;
}

export default function WorkflowVisualization({ 
  workflowData, 
  chatId,
  onPositionChange 
}: WorkflowVisualizationProps) {
  const saveTimerRef = useRef<NodeJS.Timeout | null>(null);
  const lastSavedDataRef = useRef<string | null>(null);
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
        style: {
          background: node.type === 'start' ? '#FC005C' :
                     node.type === 'end' ? '#667eea' :
                     node.type === 'decision' ? '#f6ad55' :
                     '#48bb78',
          color: 'white',
          padding: '10px 20px',
          borderRadius: node.type === 'decision' ? '8px' : '50px',
          fontSize: '14px',
          fontWeight: '500',
          border: 'none',
          minWidth: '150px',
          textAlign: 'center',
        },
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

  const { nodes: initialNodes, edges: initialEdges } = useMemo(
    () => parseWorkflow(workflowData),
    [workflowData, parseWorkflow]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Update nodes and edges when workflow data changes
  useEffect(() => {
    const { nodes: newNodes, edges: newEdges } = parseWorkflow(workflowData);
    setNodes(newNodes);
    setEdges(newEdges);
  }, [workflowData, parseWorkflow, setNodes, setEdges]);

  // Cleanup debounce timer when unmounted
  useEffect(() => {
    return () => {
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current);
      }
    };
  }, []);

  // Debounced save function (implemented after discussion)
  const debouncedSave = useCallback((updatedWorkflow: string) => {
    // Clear existing timer
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
    }

    // Set new timer, waiting 500 ms after last change
    saveTimerRef.current = setTimeout(() => {
      // Only save if data actually changed
      if (updatedWorkflow !== lastSavedDataRef.current && onPositionChange) {
        console.log('Saving workflow positions...');
        onPositionChange(updatedWorkflow);
        lastSavedDataRef.current = updatedWorkflow;
      }
    }, 500); // Value in miliseconds for debounce delay
  }, [onPositionChange]);

  // Handle node changes with debounced save
  const handleNodesChange = useCallback((changes: NodeChange[]) => {
    onNodesChange(changes);
    
    // Check if any node was dragged
    const hasDragStop = changes.some(change => 
      change.type === 'position' && change.dragging === false
    );
    
    if (hasDragStop && workflowData) {
      // Get current node positions after the change
      setTimeout(() => {
        setNodes((currentNodes) => {
          try {
            const workflow = JSON.parse(workflowData);
            
            // Update positions in workflow data
            const updatedNodes = workflow.nodes.map((node: any) => {
              const reactFlowNode = currentNodes.find((n: Node) => n.id === node.id);
              return {
                ...node,
                position: reactFlowNode?.position || node.position
              };
            });
            
            const updatedWorkflow = {
              ...workflow,
              nodes: updatedNodes
            };
            
            // Use debounced save instead of immediate save
            debouncedSave(JSON.stringify(updatedWorkflow));
          } catch (error) {
            console.error('Failed to save positions:', error);
          }
          
          return currentNodes;
        });
      }, 0);
    }
  }, [onNodesChange, workflowData, setNodes, debouncedSave]);

  if (!workflowData) {
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
          <p>Ask the AI Chabot to create a workflow and it will be visualized over here</p>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.flowContainer}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={handleNodesChange}
          onEdgesChange={onEdgesChange}
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
