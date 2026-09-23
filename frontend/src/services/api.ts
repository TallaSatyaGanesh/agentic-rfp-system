import axios from 'axios';
import {
  RFPDocumentSummary,
  RequirementItem,
  ComplianceItem,
  RiskItem,
  ClarificationQuestion,
  ProposalDraft,
  WorkflowStatus,
  CompanyDoc,
  WorkflowDecision,
  RAGQueryResult
} from '../types';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const client = axios.create({
  baseURL: API_BASE,
  timeout: 60000,
});

export const api = {
  // RFP Document Endpoints
  async listRFPs(includeArchived: boolean = false): Promise<RFPDocumentSummary[]> {
    const res = await client.get('/api/rfp', {
      params: { include_archived: includeArchived }
    });
    return res.data;
  },

  async archiveRFP(rfpId: string): Promise<{ id: string; message: string; archived_at: string }> {
    const res = await client.post(`/api/rfp/${rfpId}/archive`);
    return res.data;
  },

  async unarchiveRFP(rfpId: string): Promise<{ id: string; message: string; archived_at: string | null }> {
    const res = await client.post(`/api/rfp/${rfpId}/unarchive`);
    return res.data;
  },

  async getRFPDetails(rfpId: string): Promise<RFPDocumentSummary> {
    const res = await client.get(`/api/rfp/${rfpId}`);
    return res.data;
  },

  async uploadRFP(file: File): Promise<{ rfp_id: string; message: string }> {
    const formData = new FormData();
    formData.append('file', file);
    const res = await client.post('/api/rfp/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },

  async getRequirements(rfpId: string): Promise<RequirementItem[]> {
    const res = await client.get(`/api/rfp/${rfpId}/requirements`);
    return res.data;
  },

  async getComplianceMatrix(rfpId: string): Promise<ComplianceItem[]> {
    const res = await client.get(`/api/rfp/${rfpId}/compliance-matrix`);
    return res.data;
  },

  async getRisks(rfpId: string): Promise<{ risks: RiskItem[]; clarification_questions: ClarificationQuestion[] }> {
    const res = await client.get(`/api/rfp/${rfpId}/risks`);
    return res.data;
  },

  async getProposals(rfpId: string): Promise<ProposalDraft[]> {
    const res = await client.get(`/api/rfp/${rfpId}/proposals`);
    return res.data;
  },

  getExportUrl(rfpId: string, format: string = 'docx'): string {
    return `${API_BASE}/api/rfp/${rfpId}/export/${format}`;
  },

  // Workflow & HITL Endpoints
  async startWorkflow(rfpId: string): Promise<{ message: string; rfp_id: string }> {
    const res = await client.post(`/api/workflow/${rfpId}/start`);
    return res.data;
  },

  async getWorkflowStatus(rfpId: string): Promise<WorkflowStatus> {
    const res = await client.get(`/api/workflow/${rfpId}/status`);
    return res.data;
  },

  async resumeWorkflow(
    rfpId: string,
    payload: { decision: WorkflowDecision; notes?: string; feedback?: string }
  ): Promise<{ message: string }> {
    const res = await client.post(`/api/workflow/${rfpId}/resume`, payload);
    return res.data;
  },

  // Company Knowledge (RAG) Endpoints
  async listCompanyDocs(): Promise<CompanyDoc[]> {
    const res = await client.get('/api/company-knowledge');
    return res.data;
  },

  async uploadCompanyDoc(file: File, title: string, category: string): Promise<CompanyDoc> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('title', title);
    formData.append('category', category);
    const res = await client.post('/api/company-knowledge/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },

  async testQueryRAG(query: string, threshold?: number): Promise<RAGQueryResult> {
    const res = await client.post('/api/company-knowledge/query', { query, threshold });
    return res.data;
  }
};
