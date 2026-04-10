export type LeadStatus = 'hot' | 'warm' | 'cold' | 'dead' | 'converted' | 'new' | 'active';

export interface Lead {
  id: string;
  name?: string;
  mobile: string;
  interested_model?: string;
  status?: LeadStatus;
  intent?: string;
  objections?: string[];
  lost_reason?: string;
  updated_at?: string;
}

export interface Stats {
  total: number;
  hot: number;
  warm: number;
  cold: number;
  dead: number;
  converted: number;
  new: number;
  conversion_rate?: number;
}

export interface ActiveCallsPayload {
  active_calls: number;
  call_sids: string[];
}

export interface IntelligenceSummary {
  success: boolean;
  top_reasons?: Array<{ reason: string; count: number }>;
  competitor_losses?: Array<{ competitor: string; count: number }>;
  intents?: Array<{ intent: string; count: number }>;
  error?: string;
}

export interface LearningStatus {
  learning_enabled: boolean;
  vector_db_entries: number;
  total_learnings: number;
  vector_db_status: string;
}

export interface TranscriptTurn {
  speaker: 'user' | 'ai' | 'system';
  text: string;
  timestamp: number;
}
