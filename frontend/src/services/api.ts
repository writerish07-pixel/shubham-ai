import axios from 'axios';
import { ActiveCallsPayload, IntelligenceSummary, Lead, LearningStatus, Stats } from '@/types';

const api = axios.create({
  baseURL: '/',
  timeout: 12000
});

api.interceptors.response.use(
  (res) => res,
  (error) => Promise.reject(error?.response?.data?.detail ?? error?.message ?? 'API request failed')
);

export const DashboardApi = {
  getStats: async () => (await api.get<Stats>('/api/stats')).data,
  getLeads: async () => (await api.get<Lead[]>('/api/leads')).data,
  getActiveCalls: async () => (await api.get<ActiveCallsPayload>('/api/active-calls')).data,
  getIntelligence: async () => (await api.get<IntelligenceSummary>('/api/intelligence/summary')).data,
  getLearningStatus: async () => (await api.get<LearningStatus>('/api/learning/status')).data,
  uploadDocument: async (formData: FormData) => (await api.post('/api/documents/upload', formData)).data,
  uploadOffer: async (formData: FormData) => (await api.post('/api/offers/upload', formData)).data,
  triggerCall: async (payload: { lead_id?: string; mobile?: string }) => (await api.post('/api/call/make', payload)).data
};
