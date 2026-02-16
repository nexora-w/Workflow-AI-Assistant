'use client';

import { useState, useEffect } from 'react';
import { chatApi, Chat } from '@/lib/api';
import styles from './ChatList.module.css';

interface ChatListProps {
  onSelectChat: (chatId: number | null) => void;
  selectedChatId: number | null;
}

export default function ChatList({ onSelectChat, selectedChatId }: ChatListProps) {
  const [chats, setChats] = useState<Chat[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadChats();
  }, []);

  const loadChats = async () => {
    try {
      const data = await chatApi.getChats();
      setChats(data);
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
      
      // If deleting the currently selected chat, deselect it
      if (selectedChatId === chatId) {
        onSelectChat(null); // Changed from chats[0]?.id || 0 to null
      }
    } catch (error) {
      console.error('Failed to delete chat:', error);
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
        ) : chats.length === 0 ? (
          <div className={styles.empty}>No conversations yet</div>
        ) : (
          chats.map(chat => (
            <div
              key={chat.id}
              className={`${styles.chatItem} ${selectedChatId === chat.id ? styles.active : ''}`}
              onClick={() => onSelectChat(chat.id)}
            >
              <div className={styles.chatTitle}>{chat.title}</div>
              <button
                onClick={(e) => handleDeleteChat(chat.id, e)}
                className={styles.deleteButton}
              >
                ×
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
