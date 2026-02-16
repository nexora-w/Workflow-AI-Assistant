'use client';

import { OnlineUser } from '@/lib/api';
import styles from './OnlineIndicator.module.css';

interface OnlineIndicatorProps {
  users: OnlineUser[];
  typingUsers: string[];
}

export default function OnlineIndicator({ users, typingUsers }: OnlineIndicatorProps) {
  if (users.length === 0) return null;

  return (
    <div className={styles.container}>
      <div className={styles.avatarStack}>
        {users.slice(0, 5).map(user => (
          <div
            key={user.user_id}
            className={styles.avatarBubble}
            title={user.username}
          >
            {user.username[0].toUpperCase()}
            <span className={styles.onlineDot} />
          </div>
        ))}
        {users.length > 5 && (
          <div className={styles.overflowBubble}>+{users.length - 5}</div>
        )}
      </div>
      {typingUsers.length > 0 && (
        <div className={styles.typingIndicator}>
          {typingUsers.join(', ')} {typingUsers.length === 1 ? 'is' : 'are'} typing...
        </div>
      )}
    </div>
  );
}
