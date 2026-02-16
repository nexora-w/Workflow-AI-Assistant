import { api } from './client';
import type {
  WorkflowOp,
  WorkflowOpResult,
  WorkflowStateData,
  VersionTimeline,
  RevertResult,
} from '@/types';

export const workflowApi = {
  getState: async (chatId: number) => {
    const response = await api.get<WorkflowStateData>(`/chats/${chatId}/workflow/state`);
    return response.data;
  },
  applyOperations: async (chatId: number, baseVersion: number, operations: WorkflowOp[]) => {
    const response = await api.post<WorkflowOpResult>(
      `/chats/${chatId}/workflow/operations`,
      { base_version: baseVersion, operations }
    );
    return response.data;
  },
  getVersionTimeline: async (chatId: number) => {
    const response = await api.get<VersionTimeline>(`/chats/${chatId}/workflow/versions`);
    return response.data;
  },
  revertToVersion: async (chatId: number, targetVersion: number) => {
    const response = await api.post<RevertResult>(`/chats/${chatId}/workflow/revert`, {
      target_version: targetVersion,
    });
    return response.data;
  },
  getVersionSnapshot: async (chatId: number, version: number) => {
    const response = await api.get(`/chats/${chatId}/workflow/versions/${version}`);
    return response.data;
  },
};
