'use client';

import { useEffect, useState, useCallback } from 'react';
import { useAuthStore } from '@/lib/store';
import AuthForm from '@/components/AuthForm';
import ChatList from '@/components/ChatList';
import ChatWindow from '@/components/ChatWindow';
import WorkflowVisualization from '@/components/WorkflowVisualization';
import '../styles/globals.css';
import styles from './page.module.css';
import { chatApi } from '@/lib/api';
import type { StreamingNode, StreamingEdge } from '@/types';

export interface StreamingData {
  nodes: StreamingNode[];
  edges: StreamingEdge[];
  isStreaming: boolean;
}

export type StreamEvent =
  | { type: 'start' }
  | { type: 'node_add'; node: StreamingNode }
  | { type: 'edge_add'; edge: StreamingEdge }
  | { type: 'workflow_complete'; workflow_data: string | null; display_content: string }
  | { type: 'end'; message_id: number; workflow_version: number | null }
  | { type: 'error'; error: string };

export default function Home() {
  const { user, isLoading, logout, checkAuth } = useAuthStore();
  const [selectedChatId, setSelectedChatId] = useState<number | null>(null);
  const [workflowData, setWorkflowData] = useState<string | null>(null);
  const [currentMessageId, setCurrentMessageId] = useState<number | null>(null);
  const [isOwnerOfSelected, setIsOwnerOfSelected] = useState(true);
  const [streamingData, setStreamingData] = useState<StreamingData | null>(null);

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
        if (event.workflow_data) {
          setWorkflowData(event.workflow_data);
        }
        setStreamingData(prev =>
          prev ? { ...prev, isStreaming: false } : null
        );
        break;
      case 'end':
        setStreamingData(null);
        if (event.message_id) {
          setCurrentMessageId(event.message_id);
        }
        break;
      case 'error':
        setStreamingData(null);
        break;
    }
  }, []);

  const handlePositionChange = async (updatedWorkflow: string) => {
    if (currentMessageId) {
      try {
        await chatApi.updateWorkflowPositions(currentMessageId, updatedWorkflow);
      } catch (error) {
        console.error('Failed to save positions:', error);
      }
    }
  };

  const handleSelectChat = useCallback((chatId: number | null) => {
    setSelectedChatId(chatId);
    setIsOwnerOfSelected(true);
    setStreamingData(null);
  }, []);

  const handleSelectSharedChat = useCallback((chatId: number, ownerUsername: string) => {
    setSelectedChatId(chatId);
    setIsOwnerOfSelected(false);
    setStreamingData(null);
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  if (isLoading) {
    return (
      <div className={styles.loading}>
        <div className={styles.spinner}></div>
        <p>Loading...</p>
      </div>
    );
  }

  if (!user) {
    return <AuthForm />;
  }

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <h1>Workflow AI Assistant</h1>
        <div className={styles.userInfo}>
          <span>Welcome, {user.username}</span>
          <button onClick={() => {
            setSelectedChatId(null);
            setWorkflowData(null);
            logout();
          }} className={styles.logoutButton}>
            Logout
          </button>
        </div>
      </header>

      <div className={styles.mainContent}>
        <div className={styles.chatListSection}>
          <ChatList
            onSelectChat={handleSelectChat}
            selectedChatId={selectedChatId}
            onSelectSharedChat={handleSelectSharedChat}
          />
        </div>

        <div className={styles.chatWindowSection}>
          <ChatWindow
            chatId={selectedChatId}
            onWorkflowUpdate={handleWorkflowUpdate}
            onStreamEvent={handleStreamEvent}
            isOwner={isOwnerOfSelected}
          />
        </div>

        <div className={styles.workflowSection}>
          <WorkflowVisualization 
            workflowData={workflowData} 
            streamingData={streamingData}
            chatId={selectedChatId}
            onPositionChange={handlePositionChange}
          />
        </div>
      </div>
    </div>
  );
}
