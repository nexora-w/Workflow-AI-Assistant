'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { chatApi, Message, chatWS, OnlineUser, WSMessage } from '@/lib/api';
import ShareDialog from './ShareDialog';
import OnlineIndicator from './OnlineIndicator';
import styles from './ChatWindow.module.css';

interface ChatWindowProps {
  chatId: number | null;
  onWorkflowUpdate: (workflowData: string | null, messageId?: number) => void;
  isOwner?: boolean;
}

export default function ChatWindow({ chatId, onWorkflowUpdate, isOwner = true }: ChatWindowProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [showShareDialog, setShowShareDialog] = useState(false);
  const [onlineUsers, setOnlineUsers] = useState<OnlineUser[]>([]);
  const [typingUsers, setTypingUsers] = useState<string[]>([]);
  const [processingInfo, setProcessingInfo] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const typingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (chatId) {
      loadMessages();
      chatWS.connect(chatId);
    } else {
      setMessages([]);
      onWorkflowUpdate(null);
      chatWS.disconnect();
      setOnlineUsers([]);
      setTypingUsers([]);
      setProcessingInfo(null);
    }

    return () => {
      chatWS.disconnect();
    };
  }, [chatId]);

  useEffect(() => {
    const unsubPresence = chatWS.on('presence', (data: WSMessage) => {
      setOnlineUsers(data.users || []);
    });

    const unsubNewMessage = chatWS.on('new_message', (data: WSMessage) => {
      if (data.chat_id === chatId) {
        loadMessages();
      }
    });

    const unsubWorkflow = chatWS.on('workflow_update', (data: WSMessage) => {
      if (data.chat_id === chatId && data.workflow_data) {
        onWorkflowUpdate(data.workflow_data, data.message_id);
      }
    });

    const unsubUndo = chatWS.on('undo', (data: WSMessage) => {
      if (data.chat_id === chatId) {
        loadMessages();
        onWorkflowUpdate(data.workflow_data || null);
      }
    });

    const unsubTyping = chatWS.on('typing', (data: WSMessage) => {
      if (data.is_typing) {
        setTypingUsers(prev => {
          if (!prev.includes(data.username)) return [...prev, data.username];
          return prev;
        });
        setTimeout(() => {
          setTypingUsers(prev => prev.filter(u => u !== data.username));
        }, 3000);
      } else {
        setTypingUsers(prev => prev.filter(u => u !== data.username));
      }
    });

    const unsubProcessing = chatWS.on('processing', (data: WSMessage) => {
      if (data.chat_id !== chatId) return;
      if (data.status === 'started') {
        setProcessingInfo(`Processing ${data.processed_by_username}'s message...`);
      } else if (data.status === 'queued') {
        setProcessingInfo(data.message || 'Waiting for another request to finish...');
      } else if (data.status === 'done') {
        setProcessingInfo(null);
      }
    });

    return () => {
      unsubPresence();
      unsubNewMessage();
      unsubWorkflow();
      unsubUndo();
      unsubTyping();
      unsubProcessing();
    };
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
      
      const lastWorkflow = [...chat.messages]
        .reverse()
        .find(msg => msg.role === 'assistant' && msg.workflow_data);
      onWorkflowUpdate(lastWorkflow?.workflow_data || null, lastWorkflow?.id);
    } catch (error) {
      console.error('Failed to load messages:', error);
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    chatWS.sendTyping(true);
    if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
    typingTimeoutRef.current = setTimeout(() => {
      chatWS.sendTyping(false);
    }, 2000);
  };

  const handleSend = async () => {
    if (!input.trim() || !chatId || loading) return;

    const userMessage = input;
    setInput('');
    setLoading(true);
    chatWS.sendTyping(false);

    const tempUserMessage: Message = {
      id: Date.now(),
      chat_id: chatId,
      role: 'user',
      content: userMessage,
      created_at: new Date().toISOString(),
    };
    setMessages(prev => [...prev, tempUserMessage]);

    try {
      const response = await chatApi.sendMessage(chatId, userMessage);
      await loadMessages();
      
      if (response.workflow_data) {
        onWorkflowUpdate(response.workflow_data, response.id);
      }
    } catch (error) {
      console.error('Failed to send message:', error);
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
      await loadMessages();
      
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
      <div className={styles.chatHeader}>
        <OnlineIndicator users={onlineUsers} typingUsers={typingUsers} />
        <button
          onClick={() => setShowShareDialog(true)}
          className={styles.shareButton}
          title="Share this chat"
        >
          Share
        </button>
      </div>

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
        {processingInfo && !loading && (
          <div className={styles.processingBanner}>
            <div className={styles.processingDot} />
            {processingInfo}
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
          &#x21B6; Undo
        </button>
        <textarea
          value={input}
          onChange={handleInputChange}
          onKeyDown={handleKeyPress}
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

      {showShareDialog && (
        <ShareDialog
          chatId={chatId}
          isOwner={isOwner}
          onClose={() => setShowShareDialog(false)}
        />
      )}
    </div>
  );
}
