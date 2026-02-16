import { API_URL } from './client';
import type { StreamCallbacks } from '@/types';

export const streamApi = {
  streamMessage: (
    chatId: number,
    content: string,
    callbacks: StreamCallbacks
  ): AbortController => {
    const token =
      typeof window !== 'undefined' ? localStorage.getItem('token') : null;
    const controller = new AbortController();

    (async () => {
      try {
        const response = await fetch(`${API_URL}/chats/${chatId}/messages/stream`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ content }),
          signal: controller.signal,
        });

        if (!response.ok) {
          let detail = 'Stream request failed';
          try {
            const err = await response.json();
            detail = (err as { detail?: string }).detail ?? detail;
          } catch {
            /* ignore */
          }
          callbacks.onError?.(detail);
          return;
        }

        const reader = response.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split('\n\n');
          buffer = parts.pop() ?? '';

          for (const part of parts) {
            if (!part.trim()) continue;
            let eventType = '';
            let eventData = '';
            for (const line of part.split('\n')) {
              if (line.startsWith('event: ')) eventType = line.slice(7);
              else if (line.startsWith('data: ')) eventData = line.slice(6);
            }
            if (!eventType || !eventData) continue;
            try {
              const data = JSON.parse(eventData) as Record<string, unknown>;
              switch (eventType) {
                case 'stream_start':
                  callbacks.onStreamStart?.(data as { user_message_id: number });
                  break;
                case 'text_chunk':
                  callbacks.onTextChunk?.(data as { content: string });
                  break;
                case 'node_add':
                  callbacks.onNodeAdd?.(data as { node: { id: string; label: string; type: string } });
                  break;
                case 'edge_add':
                  callbacks.onEdgeAdd?.(data as { edge: { from: string; to: string } });
                  break;
                case 'workflow_complete':
                  callbacks.onWorkflowComplete?.(data as {
                    workflow_data: string | null;
                    display_content: string;
                  });
                  break;
                case 'stream_end':
                  callbacks.onStreamEnd?.(data as {
                    message_id: number;
                    workflow_version: number | null;
                  });
                  break;
                case 'error':
                  callbacks.onError?.(String(data.error ?? 'Unknown stream error'));
                  break;
              }
            } catch {
              /* ignore malformed SSE */
            }
          }
        }
      } catch (err: unknown) {
        if (err instanceof Error && err.name !== 'AbortError') {
          callbacks.onError?.(err.message ?? 'Stream connection failed');
        }
      }
    })();

    return controller;
  },
};
