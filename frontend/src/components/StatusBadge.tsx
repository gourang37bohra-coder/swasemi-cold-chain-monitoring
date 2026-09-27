import React from 'react';
import type { ShipmentStatus, TrackerStatus } from '../types';

interface StatusBadgeProps {
  status: TrackerStatus | ShipmentStatus | 'BREACH' | 'NORMAL' | string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => {
  let badgeClass = 'badge-completed';
  let label = status;

  if (status === 'ONLINE' || status === 'ACTIVE') {
    badgeClass = status === 'ONLINE' ? 'badge-online' : 'badge-active';
  } else if (status === 'OFFLINE' || status === 'NOT_STARTED') {
    badgeClass = status === 'OFFLINE' ? 'badge-offline' : 'badge-not-started';
  } else if (status === 'COMPLETED') {
    badgeClass = 'badge-completed';
  } else if (status === 'BREACH') {
    badgeClass = 'badge-breach';
    label = 'BREACH';
  }

  return (
    <span className={`badge ${badgeClass}`}>
      <span className="badge-dot" />
      {label}
    </span>
  );
};
