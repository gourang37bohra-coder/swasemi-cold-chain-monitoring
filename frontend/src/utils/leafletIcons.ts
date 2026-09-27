import L from 'leaflet';

/**
 * Creates custom SVG HTML pin icons for Leaflet.
 * Avoids any image asset bundler resolution issues with Vite.
 */
export function createTrackerMarkerIcon(status: 'ONLINE' | 'OFFLINE' = 'ONLINE', isBreach: boolean = false) {
  const color = isBreach ? '#ef4444' : status === 'ONLINE' ? '#10b981' : '#f59e0b';
  const pulseHtml = status === 'ONLINE'
    ? `<span style="position: absolute; width: 100%; height: 100%; border-radius: 50%; background-color: ${color}; opacity: 0.6; animation: markerPulse 1.8s ease-out infinite;"></span>`
    : '';

  return L.divIcon({
    className: 'custom-leaflet-marker',
    html: `
      <div style="position: relative; width: 28px; height: 28px; display: flex; align-items: center; justify-content: center;">
        ${pulseHtml}
        <div style="width: 18px; height: 18px; border-radius: 50%; background-color: ${color}; border: 3px solid #ffffff; box-shadow: 0 2px 8px rgba(0,0,0,0.5); z-index: 2;"></div>
      </div>
      <style>
        @keyframes markerPulse {
          0% { transform: scale(0.8); opacity: 0.8; }
          100% { transform: scale(2.2); opacity: 0; }
        }
      </style>
    `,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
}

export function createRoutePinIcon(type: 'start' | 'end') {
  const color = type === 'start' ? '#10b981' : '#ef4444';
  const label = type === 'start' ? 'A' : 'B';

  return L.divIcon({
    className: 'route-pin-marker',
    html: `
      <div style="width: 24px; height: 24px; border-radius: 50%; background-color: ${color}; color: white; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 11px; border: 2px solid white; box-shadow: 0 2px 6px rgba(0,0,0,0.4);">
        ${label}
      </div>
    `,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  });
}
