import { TranscriptTurn } from '@/types';

export const createTranscriptSocket = (
  onTurn: (turn: TranscriptTurn) => void,
  onState: (status: 'connected' | 'connecting' | 'disconnected') => void
) => {
  onState('connecting');
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${protocol}//${window.location.host}/call/stream`);

  ws.onopen = () => onState('connected');
  ws.onclose = () => onState('disconnected');
  ws.onerror = () => onState('disconnected');

  ws.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      if (payload?.type === 'transcript' || payload?.event === 'response') {
        onTurn({
          speaker: payload.role === 'user' ? 'user' : 'ai',
          text: payload.text || payload.response || '…',
          timestamp: Date.now()
        });
      }
    } catch {
      // ignore malformed events
    }
  };

  return ws;
};
