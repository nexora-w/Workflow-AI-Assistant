'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useAuthStore } from '@/lib/store';
import AuthForm from '@/components/AuthForm';
import ChatLayout from '@/components/ChatLayout';
import { chatApi } from '@/lib/api';
import type { StreamingData, StreamEvent } from '@/types';

export default function ChatPage() {
  const params = useParams();
  const router = useRouter();
  const { user, isLoading, logout, checkAuth } = useAuthStore();
  const chatIdParam = params.chatId as string;

  const [chatId, setChatId] = useState<number | null>(null);
  const [isOwnerOfSelected, setIsOwnerOfSelected] = useState(true);
  const [workflowData, setWorkflowData] = useState<string | null>(null);
  const [currentMessageId, setCurrentMessageId] = useState<number | null>(null);
  const [streamingData, setStreamingData] = useState<StreamingData | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);

  const handleWorkflowUpdate = useCallback((data: string | null, messageId?: number) => {
    setWorkflowData(data);
    if (messageId) setCurrentMessageId(messageId);
  }, []);

  const handleStreamEvent = useCallback((event: StreamEvent) => {
    switch (event.type) {
      case 'start':
        setStreamingData({ nodes: [], edges: [], isStreaming: true });
        break;
      case 'node_add':
        setStreamingData(prev =>
          prev ? { ...prev, nodes: [...prev.nodes, event.node] } : null
        );
        break;
      case 'edge_add':
        setStreamingData(prev =>
          prev ? { ...prev, edges: [...prev.edges, event.edge] } : null
        );
        break;
      case 'workflow_complete':
        if (event.workflow_data) setWorkflowData(event.workflow_data);
        setStreamingData(prev => (prev ? { ...prev, isStreaming: false } : null));
        break;
      case 'end':
        setStreamingData(null);
        if (event.message_id) setCurrentMessageId(event.message_id);
        break;
      case 'error':
        setStreamingData(null);
        break;
    }
  }, []);

  const handlePositionChange = useCallback(async (updatedWorkflow: string) => {
    if (currentMessageId) {
      try {
        await chatApi.updateWorkflowPositions(currentMessageId, updatedWorkflow);
      } catch (error) {
        console.error('Failed to save positions:', error);
      }
    }
  }, [currentMessageId]);

  // Resolve chatId from URL: "new" → create and redirect; otherwise numeric id
  useEffect(() => {
    if (!user || !chatIdParam) return;

    if (chatIdParam === 'new') {
      chatApi
        .createChat('New Conversation')
        .then((newChat) => {
          router.replace(`/chat/${newChat.id}`);
        })
        .catch((err) => {
          console.error('Failed to create chat:', err);
          setPageError('Could not create conversation');
        });
      return;
    }

    const id = parseInt(chatIdParam, 10);
    if (Number.isNaN(id) || id <= 0) {
      router.replace('/');
      return;
    }

    setPageError(null);
    setChatId(id);

    // Determine ownership: in my chats = owner, in shared = not owner
    Promise.all([chatApi.getChats(), chatApi.getSharedChats()])
      .then(([myChats, sharedChats]) => {
        if (myChats.some((c) => c.id === id)) {
          setIsOwnerOfSelected(true);
        } else if (sharedChats.some((c) => c.id === id)) {
          setIsOwnerOfSelected(false);
        } else {
          // Chat not found or no access
          router.replace('/');
        }
      })
      .catch(() => router.replace('/'));
  }, [user, chatIdParam, router]);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-4">
        <div className="w-10 h-10 border-4 border-gray-200 border-t-indigo-500 rounded-full animate-spin" />
        <p className="text-gray-600">Loading...</p>
      </div>
    );
  }

  if (!user) {
    return <AuthForm />;
  }

  if (pageError) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-4">
        <p className="text-red-600">{pageError}</p>
        <button
          type="button"
          onClick={() => router.push('/')}
          className="px-4 py-2 bg-indigo-600 text-white rounded-lg"
        >
          Back to home
        </button>
      </div>
    );
  }

  // While resolving "new", show creating state
  if (chatIdParam === 'new') {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-4">
        <div className="w-10 h-10 border-4 border-gray-200 border-t-indigo-500 rounded-full animate-spin" />
        <p className="text-gray-600">Creating conversation...</p>
      </div>
    );
  }

  // Invalid or not yet resolved numeric id
  if (chatId === null) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-4">
        <div className="w-10 h-10 border-4 border-gray-200 border-t-indigo-500 rounded-full animate-spin" />
        <p className="text-gray-600">Loading...</p>
      </div>
    );
  }

  return (
    <ChatLayout
      selectedChatId={chatId}
      isOwnerOfSelected={isOwnerOfSelected}
      workflowData={workflowData}
      streamingData={streamingData}
      currentMessageId={currentMessageId}
      onWorkflowUpdate={handleWorkflowUpdate}
      onStreamEvent={handleStreamEvent}
      onPositionChange={handlePositionChange}
      onLogout={() => {
        setChatId(null);
        setWorkflowData(null);
        logout();
      }}
    />
  );
}
