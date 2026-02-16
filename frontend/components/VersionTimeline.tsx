'use client';

import { useState, useEffect, useCallback } from 'react';
import { workflowApi, VersionEntry, chatWS, WSMessage } from '@/lib/api';
import styles from './VersionTimeline.module.css';

interface VersionTimelineProps {
  chatId: number | null;
  onRevert: (data: string, version: number) => void;
  onPreview: (data: string | null) => void;
}

export default function VersionTimeline({ chatId, onRevert, onPreview }: VersionTimelineProps) {
  const [versions, setVersions] = useState<VersionEntry[]>([]);
  const [currentVersion, setCurrentVersion] = useState(0);
  const [loading, setLoading] = useState(false);
  const [reverting, setReverting] = useState(false);
  const [previewingVersion, setPreviewingVersion] = useState<number | null>(null);
  const [expanded, setExpanded] = useState(false);

  const loadTimeline = useCallback(async () => {
    if (!chatId) return;
    try {
      const timeline = await workflowApi.getVersionTimeline(chatId);
      setVersions(timeline.versions);
      setCurrentVersion(timeline.current_version);
    } catch {
      // No versions yet
      setVersions([]);
    }
  }, [chatId]);

  useEffect(() => {
    loadTimeline();
  }, [loadTimeline]);

  useEffect(() => {
    // Real edits (ops, AI messages) create new snapshots → reload full timeline
    const unsub1 = chatWS.on('workflow_op', () => loadTimeline());
    const unsub2 = chatWS.on('new_message', () => loadTimeline());
    // Undo/redo only moves the pointer — no new snapshots, just update pointer
    const unsub3 = chatWS.on('version_revert', (data: WSMessage) => {
      if (data.current_version) {
        setCurrentVersion(data.current_version);
      }
      if (data.data) {
        onRevert(data.data, data.current_version ?? data.version);
      }
    });
    return () => { unsub1(); unsub2(); unsub3(); };
  }, [loadTimeline, onRevert]);

  const handleUndo = async () => {
    if (versions.length < 2 || reverting) return;
    const currentIdx = versions.findIndex(v => v.version === currentVersion);
    if (currentIdx <= 0) return;
    const prevVersion = versions[currentIdx - 1].version;
    await handleRevert(prevVersion);
  };

  const handleRedo = async () => {
    if (reverting) return;
    const currentIdx = versions.findIndex(v => v.version === currentVersion);
    if (currentIdx < 0 || currentIdx >= versions.length - 1) return;
    const nextVersion = versions[currentIdx + 1].version;
    await handleRevert(nextVersion);
  };

  const handleRevert = async (targetVersion: number) => {
    if (!chatId || reverting) return;
    setReverting(true);
    try {
      const result = await workflowApi.revertToVersion(chatId, targetVersion);
      // Backend now returns the pointer position, not a new version number
      setCurrentVersion(result.version);
      onRevert(result.data, result.version);
      setPreviewingVersion(null);
      // No need to reload timeline — the snapshot list hasn't changed,
      // only the pointer moved.
    } catch (error) {
      console.error('Failed to revert:', error);
    } finally {
      setReverting(false);
    }
  };

  const handlePreview = async (version: number) => {
    if (!chatId) return;
    if (previewingVersion === version) {
      setPreviewingVersion(null);
      onPreview(null);
      return;
    }
    try {
      const snap = await workflowApi.getVersionSnapshot(chatId, version);
      setPreviewingVersion(version);
      onPreview(snap.data);
    } catch {
      console.error('Failed to preview version');
    }
  };

  const cancelPreview = () => {
    setPreviewingVersion(null);
    onPreview(null);
  };

  if (!chatId || versions.length === 0) return null;

  const currentIdx = versions.findIndex(v => v.version === currentVersion);
  const canUndo = currentIdx > 0;
  const canRedo = currentIdx >= 0 && currentIdx < versions.length - 1;

  return (
    <div className={styles.container}>
      <div className={styles.toolbar}>
        <button
          onClick={handleUndo}
          disabled={!canUndo || reverting}
          className={styles.toolButton}
          title="Undo (go to previous version)"
        >
          &#x21B6;
        </button>
        <button
          onClick={handleRedo}
          disabled={!canRedo || reverting}
          className={styles.toolButton}
          title="Redo (go to next version)"
        >
          &#x21B7;
        </button>
        <span className={styles.versionLabel}>
          v{currentVersion}
        </span>
        <button
          onClick={() => setExpanded(!expanded)}
          className={`${styles.toolButton} ${expanded ? styles.active : ''}`}
          title="Version history"
        >
          &#x1F553;
        </button>
      </div>

      {expanded && (
        <div className={styles.timeline}>
          <div className={styles.timelineHeader}>
            <span>Version History</span>
            {previewingVersion !== null && (
              <button onClick={cancelPreview} className={styles.cancelPreview}>
                Exit preview
              </button>
            )}
          </div>
          <div className={styles.versionList}>
            {[...versions].reverse().map(entry => (
              <div
                key={entry.version}
                className={`${styles.versionItem} ${
                  entry.version === currentVersion ? styles.currentItem : ''
                } ${previewingVersion === entry.version ? styles.previewingItem : ''}`}
              >
                <div className={styles.versionDot} />
                <div className={styles.versionInfo}>
                  <div className={styles.versionNumber}>
                    v{entry.version}
                    {entry.version === currentVersion && (
                      <span className={styles.currentBadge}>current</span>
                    )}
                  </div>
                  <div className={styles.versionDesc}>
                    {entry.description || 'Workflow change'}
                  </div>
                  <div className={styles.versionMeta}>
                    {entry.created_by_username && `${entry.created_by_username} · `}
                    {new Date(entry.created_at).toLocaleTimeString()}
                  </div>
                </div>
                <div className={styles.versionActions}>
                  <button
                    onClick={() => handlePreview(entry.version)}
                    className={styles.previewButton}
                    title="Preview this version"
                  >
                    {previewingVersion === entry.version ? 'Hide' : 'View'}
                  </button>
                  {entry.version !== currentVersion && (
                    <button
                      onClick={() => handleRevert(entry.version)}
                      className={styles.acceptButton}
                      disabled={reverting}
                      title="Revert to this version"
                    >
                      Accept
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
