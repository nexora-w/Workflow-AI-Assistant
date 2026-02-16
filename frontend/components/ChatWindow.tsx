'use client';

import { useState, useEffect, useRef } from 'react';
import { chatApi, Message } from '@/lib/api';
import styles from './ChatWindow.module.css';

interface ChatWindowProps {
  chatId: number | null;
  onWorkflowUpdate: (workflowData: string | null, messageId?: number) => void;
}

export default function ChatWindow({ chatId, onWorkflowUpdate }: ChatWindowProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (chatId) {
      loadMessages();
    } else {
      setMessages([]);
      onWorkflowUpdate(null);
    }
  }, [chatId]);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const loadMessages = async () => {
    if (!chatId) return;
    
    try {
      const chat = await chatApi.getChat(chatId);
      setMessages(chat.messages);
      
      // Update workflow with latest assistant message that has workflow data
      const lastWorkflow = [...chat.messages]
        .reverse()
        .find(msg => msg.role === 'assistant' && msg.workflow_data);
      onWorkflowUpdate(lastWorkflow?.workflow_data || null, lastWorkflow?.id);
    } catch (error) {
      console.error('Failed to load messages:', error);
    }
  };

  const handleSend = async () => {
    if (!input.trim() || !chatId || loading) return;

    const userMessage = input;
    setInput('');
    setLoading(true);

    const tempUserMessage: Message = {
      id: Date.now(), // Temporary ID
      chat_id: chatId,
      role: 'user',
      content: userMessage,
      created_at: new Date().toISOString(),
    };
    setMessages(prev => [...prev, tempUserMessage]);

    try {
      const response = await chatApi.sendMessage(chatId, userMessage);
      await loadMessages(); // This will reload with real data from server
      
      // Update workflow if present
      if (response.workflow_data) {
        onWorkflowUpdate(response.workflow_data, response.id);
      }
    } catch (error) {
      console.error('Failed to send message:', error);
      // Remove the optimistic message on error
      setMessages(prev => prev.filter(msg => msg.id !== tempUserMessage.id));
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleUndo = async () => {
    if (!chatId || loading) return;

    setLoading(true);
    try {
      const result = await chatApi.undoWorkflow(chatId);
      await loadMessages(); // Reload messages after undo
      
      // Update workflow to previous version or null
      if (result.workflow_data) {
        onWorkflowUpdate(result.workflow_data);
      } else {
        onWorkflowUpdate(null);
      }
    } catch (error) {
      console.error('Failed to undo:', error);
      alert('Could not undo. There may be no previous messages.');
    } finally {
      setLoading(false);
    }
  };

  if (!chatId) {
    return (
      <div className={styles.container}>
        <div className={styles.emptyState}>
          <h3>Welcome to Workflow AI Assistant</h3>
          <p>Select a conversation or create a new one to get started</p>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.messages}>
        {messages.map((message) => (
          <div
            key={message.id}
            className={`${styles.message} ${
              message.role === 'user' ? styles.userMessage : styles.assistantMessage
            }`}
          >
            <div className={styles.messageContent}>
              {message.content}
            </div>
            <div className={styles.messageTime}>
              {new Date(message.created_at).toLocaleTimeString()}
            </div>
          </div>
        ))}
        {loading && (
          <div className={`${styles.message} ${styles.assistantMessage}`}>
            <div className={styles.messageContent}>
              <div className={styles.typing}>
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className={styles.inputArea}>
        <button
          onClick={handleUndo}
          className={styles.undoButton}
          disabled={loading || messages.length < 2}
          title="Undo last change"
        >
          ↶ Undo
        </button>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="Describe the workflow you need..."
          className={styles.input}
          rows={3}
          disabled={loading}
        />
        <button
          onClick={handleSend}
          className={styles.sendButton}
          disabled={loading || !input.trim()}
        >
          Send
        </button>
      </div>
    </div>
  );
}
