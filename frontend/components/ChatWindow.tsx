'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { chatApi, Message, chatWS, OnlineUser, WSMessage, streamApi } from '@/lib/api';
import ShareDialog from './ShareDialog';
import OnlineIndicator from './OnlineIndicator';
import styles from './ChatWindow.module.css';
import type { StreamEvent } from '@/app/page';

/** Delay between revealing each character (ms) for ChatGPT-like typing. */
const CHAR_REVEAL_INTERVAL_MS = 20;

interface ChatWindowProps {
  chatId: number | null;
  onWorkflowUpdate: (workflowData: string | null, messageId?: number) => void;
  onStreamEvent?: (event: StreamEvent) => void;
  isOwner?: boolean;
}

export default function ChatWindow({ chatId, onWorkflowUpdate, onStreamEvent, isOwner = true }: ChatWindowProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  /** Full text received from stream (buffered). */
  const [streamingBuffer, setStreamingBuffer] = useState('');
  /** Number of characters to show — animates up for letter-by-letter effect. */
  const [streamingVisibleLength, setStreamingVisibleLength] = useState(0);
  const [showShareDialog, setShowShareDialog] = useState(false);
  const [onlineUsers, setOnlineUsers] = useState<OnlineUser[]>([]);
  const [typingUsers, setTypingUsers] = useState<string[]>([]);
  const [processingInfo, setProcessingInfo] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const typingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const streamControllerRef = useRef<AbortController | null>(null);
  const bufferRef = useRef('');
  const visibleLengthRef = useRef(0);
  const revealIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  visibleLengthRef.current = streamingVisibleLength;

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
      setOnlineUsers((data.users as OnlineUser[]) || []);
    });

    const unsubNewMessage = chatWS.on('new_message', (data: WSMessage) => {
      if (data.chat_id === chatId) {
        loadMessages();
      }
    });

    const unsubWorkflow = chatWS.on('workflow_update', (data: WSMessage) => {
      if (data.chat_id === chatId && data.workflow_data) {
        onWorkflowUpdate(data.workflow_data as string, data.message_id as number);
      }
    });

    const unsubUndo = chatWS.on('undo', (data: WSMessage) => {
      if (data.chat_id === chatId) {
        loadMessages();
        onWorkflowUpdate((data.workflow_data as string) || null);
      }
    });

    const unsubTyping = chatWS.on('typing', (data: WSMessage) => {
      const username = data.username as string;
      if (data.is_typing) {
        setTypingUsers(prev => {
          if (!prev.includes(username)) return [...prev, username];
          return prev;
        });
        setTimeout(() => {
          setTypingUsers(prev => prev.filter(u => u !== username));
        }, 3000);
      } else {
        setTypingUsers(prev => prev.filter(u => u !== username));
      }
    });

    const unsubProcessing = chatWS.on('processing', (data: WSMessage) => {
      if (data.chat_id !== chatId) return;
      if (data.status === 'started') {
        setProcessingInfo(`Processing ${data.processed_by_username as string}'s message...`);
      } else if (data.status === 'queued') {
        setProcessingInfo((data.message as string) || 'Waiting for another request to finish...');
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

  // Keep ref in sync for the reveal interval
  bufferRef.current = streamingBuffer;

  // Character-by-character reveal (ChatGPT-like): tick visible length until it catches up to buffer
  useEffect(() => {
    if (!isStreaming) {
      if (revealIntervalRef.current) {
        clearInterval(revealIntervalRef.current);
        revealIntervalRef.current = null;
      }
      return;
    }

    const targetLen = bufferRef.current.length;
    if (visibleLengthRef.current >= targetLen) return;
    if (revealIntervalRef.current) return; // already ticking

    revealIntervalRef.current = setInterval(() => {
      const target = bufferRef.current.length;
      setStreamingVisibleLength((prev) => {
        const next = Math.min(prev + 1, target);
        if (next >= target && revealIntervalRef.current) {
          clearInterval(revealIntervalRef.current);
          revealIntervalRef.current = null;
        }
        return next;
      });
    }, CHAR_REVEAL_INTERVAL_MS);

    return () => {
      if (revealIntervalRef.current) {
        clearInterval(revealIntervalRef.current);
        revealIntervalRef.current = null;
      }
    };
  }, [isStreaming, streamingBuffer]);

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

  /**
   * Helper: display only the text *before* the JSON code block
   * so the chat bubble never shows raw JSON during streaming.
   */
  const cleanStreamingText = (text: string): string => {
    const codeBlockStart = text.indexOf('```');
    if (codeBlockStart > -1) {
      return text.substring(0, codeBlockStart).trim();
    }
    return text;
  };

  const handleSend = async () => {
    if (!input.trim() || !chatId || loading || isStreaming) return;

    const userMessage = input;
    setInput('');
    setLoading(true);
    setIsStreaming(true);
    setStreamingBuffer('');
    setStreamingVisibleLength(0);
    chatWS.sendTyping(false);

    const tempUserMessage: Message = {
      id: Date.now(),
      chat_id: chatId,
      role: 'user',
      content: userMessage,
      created_at: new Date().toISOString(),
    };
    setMessages(prev => [...prev, tempUserMessage]);

    streamControllerRef.current = streamApi.streamMessage(chatId, userMessage, {
      onStreamStart: () => {
        onStreamEvent?.({ type: 'start' });
      },
      onTextChunk: (data) => {
        setStreamingBuffer((prev) => prev + data.content);
      },
      onNodeAdd: (data) => {
        onStreamEvent?.({ type: 'node_add', node: data.node });
      },
      onEdgeAdd: (data) => {
        onStreamEvent?.({ type: 'edge_add', edge: data.edge });
      },
      onWorkflowComplete: (data) => {
        onStreamEvent?.({
          type: 'workflow_complete',
          workflow_data: data.workflow_data,
          display_content: data.display_content,
        });
      },
      onStreamEnd: (data) => {
        setIsStreaming(false);
        setStreamingBuffer('');
        setStreamingVisibleLength(0);
        setLoading(false);
        onStreamEvent?.({
          type: 'end',
          message_id: data.message_id,
          workflow_version: data.workflow_version,
        });
        loadMessages();
      },
      onError: (error) => {
        console.error('Stream error:', error);
        setIsStreaming(false);
        setStreamingBuffer('');
        setStreamingVisibleLength(0);
        setLoading(false);
        onStreamEvent?.({ type: 'error', error });
        // Remove the optimistic user message on error
        setMessages(prev => prev.filter(msg => msg.id !== tempUserMessage.id));
      },
    });
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
        {isStreaming && (streamingBuffer.length > 0 || streamingVisibleLength > 0) && (
          <div className={`${styles.message} ${styles.assistantMessage} ${styles.streamingMessage}`}>
            <div className={styles.messageContent}>
              {cleanStreamingText(streamingBuffer.slice(0, streamingVisibleLength))}
              <span className={styles.streamCursor}>|</span>
            </div>
          </div>
        )}
        {loading && streamingBuffer.length === 0 && (
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
          disabled={loading || isStreaming}
        />
        <button
          onClick={handleSend}
          className={styles.sendButton}
          disabled={loading || isStreaming || !input.trim()}
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
