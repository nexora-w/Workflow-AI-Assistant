'use client';

import { useState, useEffect } from 'react';
import { chatApi, Chat, SharedChat } from '@/lib/api';
import styles from './ChatList.module.css';

interface ChatListProps {
  onSelectChat: (chatId: number | null) => void;
  selectedChatId: number | null;
  onSelectSharedChat?: (chatId: number, ownerUsername: string) => void;
}

export default function ChatList({ onSelectChat, selectedChatId, onSelectSharedChat }: ChatListProps) {
  const [chats, setChats] = useState<Chat[]>([]);
  const [sharedChats, setSharedChats] = useState<SharedChat[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadChats();
  }, []);

  const loadChats = async () => {
    try {
      const [ownChats, shared] = await Promise.all([
        chatApi.getChats(),
        chatApi.getSharedChats()
      ]);
      setChats(ownChats);
      setSharedChats(shared);
    } catch (error) {
      console.error('Failed to load chats:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleNewChat = async () => {
    try {
      const newChat = await chatApi.createChat('New Conversation');
      setChats([newChat, ...chats]);
      onSelectChat(newChat.id);
    } catch (error) {
      console.error('Failed to create chat:', error);
    }
  };

  const handleDeleteChat = async (chatId: number, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Delete this chat?')) return;

    try {
      await chatApi.deleteChat(chatId);
      const updatedChats = chats.filter(chat => chat.id !== chatId);
      setChats(updatedChats);
      
      if (selectedChatId === chatId) {
        onSelectChat(null);
      }
    } catch (error) {
      console.error('Failed to delete chat:', error);
    }
  };

  const handleSelectShared = (chat: SharedChat) => {
    onSelectChat(chat.id);
    if (onSelectSharedChat) {
      onSelectSharedChat(chat.id, chat.owner_username);
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>Conversations</h2>
        <button onClick={handleNewChat} className={styles.newChatButton}>
          + New
        </button>
      </div>

      <div className={styles.chatList}>
        {loading ? (
          <div className={styles.loading}>Loading...</div>
        ) : (
          <>
            {chats.length === 0 && sharedChats.length === 0 && (
              <div className={styles.empty}>No conversations yet</div>
            )}

            {chats.map(chat => (
              <div
                key={`own-${chat.id}`}
                className={`${styles.chatItem} ${selectedChatId === chat.id ? styles.active : ''}`}
                onClick={() => onSelectChat(chat.id)}
              >
                <div className={styles.chatTitle}>{chat.title}</div>
                <button
                  onClick={(e) => handleDeleteChat(chat.id, e)}
                  className={styles.deleteButton}
                >
                  &times;
                </button>
              </div>
            ))}

            {sharedChats.length > 0 && (
              <>
                <div className={styles.sectionDivider}>
                  <span>Shared with me</span>
                </div>
                {sharedChats.map(chat => (
                  <div
                    key={`shared-${chat.id}`}
                    className={`${styles.chatItem} ${styles.sharedItem} ${selectedChatId === chat.id ? styles.active : ''}`}
                    onClick={() => handleSelectShared(chat)}
                  >
                    <div className={styles.chatTitleGroup}>
                      <div className={styles.chatTitle}>{chat.title}</div>
                      <div className={styles.sharedBy}>
                        by {chat.owner_username} &middot; {chat.my_role}
                      </div>
                    </div>
                  </div>
                ))}
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
