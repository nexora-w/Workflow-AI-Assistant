'use client';

import { useState, useEffect, useCallback } from 'react';
import { collaborationApi, Collaborator, UserSearchResult } from '@/lib/api';
import styles from './ShareDialog.module.css';

interface ShareDialogProps {
  chatId: number;
  isOwner: boolean;
  onClose: () => void;
}

export default function ShareDialog({ chatId, isOwner, onClose }: ShareDialogProps) {
  const [collaborators, setCollaborators] = useState<Collaborator[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<UserSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedRole, setSelectedRole] = useState<string>('editor');

  useEffect(() => {
    loadCollaborators();
  }, [chatId]);

  const loadCollaborators = async () => {
    try {
      const data = await collaborationApi.getCollaborators(chatId);
      setCollaborators(data);
    } catch (err) {
      console.error('Failed to load collaborators:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = useCallback(async (query: string) => {
    setSearchQuery(query);
    if (query.length < 1) {
      setSearchResults([]);
      return;
    }
    setSearching(true);
    try {
      const results = await collaborationApi.searchUsers(query);
      const collabUserIds = new Set(collaborators.map(c => c.user_id));
      setSearchResults(results.filter(u => !collabUserIds.has(u.id)));
    } catch (err) {
      console.error('Search failed:', err);
    } finally {
      setSearching(false);
    }
  }, [collaborators]);

  const handleAddCollaborator = async (username: string) => {
    setError(null);
    try {
      await collaborationApi.addCollaborator(chatId, username, selectedRole);
      await loadCollaborators();
      setSearchQuery('');
      setSearchResults([]);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to add collaborator');
    }
  };

  const handleRemoveCollaborator = async (userId: number) => {
    try {
      await collaborationApi.removeCollaborator(chatId, userId);
      setCollaborators(prev => prev.filter(c => c.user_id !== userId));
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to remove collaborator');
    }
  };

  const handleRoleChange = async (userId: number, newRole: string) => {
    try {
      await collaborationApi.updateCollaboratorRole(chatId, userId, newRole);
      setCollaborators(prev =>
        prev.map(c => c.user_id === userId ? { ...c, role: newRole } : c)
      );
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update role');
    }
  };

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.dialog} onClick={e => e.stopPropagation()}>
        <div className={styles.dialogHeader}>
          <h3>Share Chat</h3>
          <button onClick={onClose} className={styles.closeButton}>&times;</button>
        </div>

        {error && <div className={styles.error}>{error}</div>}

        {isOwner && (
          <div className={styles.addSection}>
            <div className={styles.searchRow}>
              <input
                type="text"
                placeholder="Search users by username or email..."
                value={searchQuery}
                onChange={e => handleSearch(e.target.value)}
                className={styles.searchInput}
              />
              <select
                value={selectedRole}
                onChange={e => setSelectedRole(e.target.value)}
                className={styles.roleSelect}
              >
                <option value="editor">Editor</option>
                <option value="viewer">Viewer</option>
              </select>
            </div>

            {searching && <div className={styles.searchStatus}>Searching...</div>}

            {searchResults.length > 0 && (
              <div className={styles.searchResults}>
                {searchResults.map(user => (
                  <div key={user.id} className={styles.searchResultItem}>
                    <div className={styles.userInfo}>
                      <span className={styles.avatar}>
                        {user.username[0].toUpperCase()}
                      </span>
                      <div>
                        <div className={styles.username}>{user.username}</div>
                        <div className={styles.email}>{user.email}</div>
                      </div>
                    </div>
                    <button
                      onClick={() => handleAddCollaborator(user.username)}
                      className={styles.addButton}
                    >
                      + Add
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className={styles.collaboratorsList}>
          <h4>Collaborators ({collaborators.length})</h4>
          {loading ? (
            <div className={styles.loadingText}>Loading...</div>
          ) : collaborators.length === 0 ? (
            <div className={styles.emptyText}>
              No collaborators yet. Search for users above to share this chat.
            </div>
          ) : (
            collaborators.map(collab => (
              <div key={collab.id} className={styles.collaboratorItem}>
                <div className={styles.userInfo}>
                  <span className={styles.avatar}>
                    {collab.username[0].toUpperCase()}
                  </span>
                  <div>
                    <div className={styles.username}>{collab.username}</div>
                    <div className={styles.email}>{collab.email}</div>
                  </div>
                </div>
                <div className={styles.collaboratorActions}>
                  {isOwner ? (
                    <>
                      <select
                        value={collab.role}
                        onChange={e => handleRoleChange(collab.user_id, e.target.value)}
                        className={styles.roleSelectSmall}
                      >
                        <option value="editor">Editor</option>
                        <option value="viewer">Viewer</option>
                      </select>
                      <button
                        onClick={() => handleRemoveCollaborator(collab.user_id)}
                        className={styles.removeButton}
                        title="Remove collaborator"
                      >
                        &times;
                      </button>
                    </>
                  ) : (
                    <span className={styles.roleTag}>{collab.role}</span>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
