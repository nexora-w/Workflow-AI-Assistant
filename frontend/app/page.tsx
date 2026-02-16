'use client';

import { useEffect, useState } from 'react';
import { useAuthStore } from '@/lib/store';
import AuthForm from '@/components/AuthForm';
import ChatList from '@/components/ChatList';
import ChatWindow from '@/components/ChatWindow';
import WorkflowVisualization from '@/components/WorkflowVisualization';
import '../styles/globals.css';
import styles from './page.module.css';
import { chatApi } from '@/lib/api';

export default function Home() {
  const { user, isLoading, logout, checkAuth } = useAuthStore();
  const [selectedChatId, setSelectedChatId] = useState<number | null>(null);
  const [workflowData, setWorkflowData] = useState<string | null>(null);
  const [currentMessageId, setCurrentMessageId] = useState<number | null>(null);

  const handleWorkflowUpdate = (data: string | null, messageId?: number) => {
    setWorkflowData(data);
    if (messageId) setCurrentMessageId(messageId);
  };

  const handlePositionChange = async (updatedWorkflow: string) => {
  if (currentMessageId) {
      try {
        await chatApi.updateWorkflowPositions(currentMessageId, updatedWorkflow);
      } catch (error) {
        console.error('Failed to save positions:', error);
      }
  }
  };


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
            onSelectChat={setSelectedChatId}
            selectedChatId={selectedChatId}
          />
        </div>

        <div className={styles.chatWindowSection}>
          <ChatWindow
            chatId={selectedChatId}
            onWorkflowUpdate={handleWorkflowUpdate}
          />
        </div>

        <div className={styles.workflowSection}>
          <WorkflowVisualization 
            workflowData={workflowData} 
            chatId={selectedChatId}
            onPositionChange={handlePositionChange}
          />
        </div>
      </div>
    </div>
  );
}
