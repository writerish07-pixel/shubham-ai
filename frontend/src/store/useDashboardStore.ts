import { create } from 'zustand';
import { DashboardApi } from '@/services/api';
import { ActiveCallsPayload, IntelligenceSummary, Lead, LearningStatus, Stats, TranscriptTurn } from '@/types';

interface DashboardState {
  stats: Stats | null;
  leads: Lead[];
  activeCalls: ActiveCallsPayload;
  intelligence: IntelligenceSummary | null;
  learningStatus: LearningStatus | null;
  transcript: TranscriptTurn[];
  agentState: 'listening' | 'user-speaking' | 'ai-speaking';
  loading: boolean;
  error?: string;
  refresh: () => Promise<void>;
  pushTranscript: (turn: TranscriptTurn) => void;
  setAgentState: (state: DashboardState['agentState']) => void;
}

export const useDashboardStore = create<DashboardState>((set) => ({
  stats: null,
  leads: [],
  activeCalls: { active_calls: 0, call_sids: [] },
  intelligence: null,
  learningStatus: null,
  transcript: [],
  agentState: 'listening',
  loading: false,
  async refresh() {
    set({ loading: true, error: undefined });
    try {
      const [stats, leads, activeCalls, intelligence, learningStatus] = await Promise.all([
        DashboardApi.getStats(),
        DashboardApi.getLeads(),
        DashboardApi.getActiveCalls(),
        DashboardApi.getIntelligence(),
        DashboardApi.getLearningStatus()
      ]);
      set({ stats, leads, activeCalls, intelligence, learningStatus, loading: false });
    } catch (error) {
      set({ loading: false, error: String(error) });
    }
  },
  pushTranscript(turn) {
    set((state) => ({ transcript: [turn, ...state.transcript].slice(0, 100) }));
  },
  setAgentState(agentState) {
    set({ agentState });
  }
}));
