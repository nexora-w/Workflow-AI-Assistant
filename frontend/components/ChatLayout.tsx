'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/lib/store';
import ChatList from '@/components/ChatList';
import ChatWindow from '@/components/ChatWindow';
import WorkflowVisualization from '@/components/WorkflowVisualization';
import type { StreamingData, StreamEvent } from '@/types';
import styles from '@/app/page.module.css';

interface ChatLayoutProps {
  selectedChatId: number | null;
  isOwnerOfSelected: boolean;
  workflowData: string | null;
  streamingData: StreamingData | null;
  currentMessageId: number | null;
  onWorkflowUpdate: (data: string | null, messageId?: number) => void;
  onStreamEvent: (event: StreamEvent) => void;
  onPositionChange: (updatedWorkflow: string) => void | Promise<void>;
  onLogout: () => void;
}

export default function ChatLayout({
  selectedChatId,
  isOwnerOfSelected,
  workflowData,
  streamingData,
  currentMessageId,
  onWorkflowUpdate,
  onStreamEvent,
  onPositionChange,
  onLogout,
}: ChatLayoutProps) {
  const router = useRouter();
  const { user } = useAuthStore();

  const handleSelectChat = (chatId: number | null) => {
    if (chatId === null) {
      router.push('/');
    } else {
      router.push(`/chat/${chatId}`);
    }
  };

  const handleSelectSharedChat = (_chatId: number) => {
    router.push(`/chat/${_chatId}`);
  };

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <h1>
          <Link href="/" className={styles.titleLink}>
            Workflow AI Assistant
          </Link>
        </h1>
        <div className={styles.userInfo}>
          <span>Welcome, {user?.username ?? 'User'}</span>
          <button type="button" onClick={onLogout} className={styles.logoutButton}>
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
            onWorkflowUpdate={onWorkflowUpdate}
            onStreamEvent={onStreamEvent}
            isOwner={isOwnerOfSelected}
          />
        </div>

        <div className={styles.workflowSection}>
          <WorkflowVisualization
            workflowData={workflowData}
            streamingData={streamingData}
            chatId={selectedChatId}
            onPositionChange={onPositionChange}
          />
        </div>
      </div>
    </div>
  );
}
