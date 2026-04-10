import { useEffect } from 'react';
import { createTranscriptSocket } from '@/services/realtime';
import { useDashboardStore } from '@/store/useDashboardStore';

export const useRealtimeCallStream = () => {
  const pushTranscript = useDashboardStore((s) => s.pushTranscript);
  const setAgentState = useDashboardStore((s) => s.setAgentState);

  useEffect(() => {
    const socket = createTranscriptSocket(
      (turn) => {
        pushTranscript(turn);
        setAgentState(turn.speaker === 'user' ? 'user-speaking' : 'ai-speaking');
        setTimeout(() => setAgentState('listening'), 1200);
      },
      (status) => {
        if (status !== 'connected') {
          setAgentState('listening');
        }
      }
    );

    return () => socket.close();
  }, [pushTranscript, setAgentState]);
};
