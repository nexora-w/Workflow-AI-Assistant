/** Shared domain types for API and UI. */

export interface User {
  id: number;
  username: string;
  email: string;
  created_at: string;
}

export interface Chat {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: number;
  chat_id: number;
  role: 'user' | 'assistant';
  content: string;
  workflow_data?: string;
  created_at: string;
}

export interface ChatWithMessages extends Chat {
  messages: Message[];
}

export interface Collaborator {
  id: number;
  user_id: number;
  username: string;
  email: string;
  role: string;
  invited_by: number;
  inviter_username: string;
  created_at: string;
}

export interface SharedChat {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  owner_id: number;
  owner_username: string;
  my_role: string;
}

export interface UserSearchResult {
  id: number;
  username: string;
  email: string;
}

export interface OnlineUser {
  user_id: number;
  username: string;
}

export interface WSMessage {
  type: string;
  chat_id: number;
  [key: string]: unknown;
}

export interface WorkflowOp {
  op_type: 'move_node' | 'add_node' | 'delete_node' | 'update_node' | 'add_edge' | 'delete_edge';
  payload: Record<string, unknown>;
}

export interface WorkflowOpResult {
  status: 'applied' | 'merged' | 'conflict';
  version: number;
  data: string;
  conflicts: string[];
}

export interface WorkflowStateData {
  chat_id: number;
  version: number;
  max_version: number;
  data: string;
  updated_at: string | null;
  updated_by: number | null;
}

export interface VersionEntry {
  version: number;
  description: string | null;
  created_by: number | null;
  created_by_username: string | null;
  created_at: string;
  is_current: boolean;
}

export interface VersionTimeline {
  chat_id: number;
  current_version: number;
  versions: VersionEntry[];
}

export interface RevertResult {
  version: number;
  data: string;
  message: string;
}

export interface StreamingNode {
  id: string;
  label: string;
  type: string;
}

export interface StreamingEdge {
  from: string;
  to: string;
}

export interface StreamCallbacks {
  onStreamStart?: (data: { user_message_id: number }) => void;
  onTextChunk?: (data: { content: string }) => void;
  onNodeAdd?: (data: { node: StreamingNode }) => void;
  onEdgeAdd?: (data: { edge: StreamingEdge }) => void;
  onWorkflowComplete?: (data: { workflow_data: string | null; display_content: string }) => void;
  onStreamEnd?: (data: { message_id: number; workflow_version: number | null }) => void;
  onError?: (error: string) => void;
}
