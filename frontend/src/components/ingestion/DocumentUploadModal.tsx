import React, { useState } from 'react';
import { UploadCloud, FileText, X, Sparkles, AlertCircle } from 'lucide-react';
import { api } from '../../services/api';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onUploaded: (rfpId: string) => void;
}

export const DocumentUploadModal: React.FC<Props> = ({ isOpen, onClose, onUploaded }) => {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;

    try {
      setLoading(true);
      setUploadError(null);
      const res = await api.uploadRFP(file);
      onUploaded(res.rfp_id);
      onClose();
    } catch (err) {
      console.error('Upload failed:', err);
      setUploadError('Upload failed. Please ensure file is a valid PDF, DOCX, or TXT document.');
    } finally {
      setLoading(false);
    }
  };

  const handleUseSampleRFP = async () => {
    try {
      setLoading(true);
      // Create a mock File object with the sample text
      const sampleText = `REQUEST FOR PROPOSAL (RFP)
DOCUMENT REF: RFP-NTSCA-2026-CLOUD-088
ISSUED BY: National Transit & Supply Chain Authority (NTSCA)
TITLE: Enterprise Cloud Modernization & Distributed Logistics Platform
DUE DATE: November 15, 2026 at 5:00 PM EST

SECTION 1: EXECUTIVE SUMMARY & PROCUREMENT OBJECTIVE
The National Transit & Supply Chain Authority (NTSCA) invites proposals from qualified cloud software vendors to deliver a modern, secure, and highly available cloud platform.

SECTION 2: TECHNICAL & INFRASTRUCTURE REQUIREMENTS
2.1 High Availability & SLA: The proposed cloud platform SHALL maintain a monthly service uptime of no less than 99.95% excluding pre-scheduled maintenance windows.
2.2 Disaster Recovery: The vendor MUST provide automated cross-region database replication with a documented Recovery Time Objective (RTO) of less than 30 minutes and Recovery Point Objective (RPO) of less than 15 minutes.
2.3 Containerized Scalability: The system MUST support automated horizontal scaling to handle peak transit demand of up to 10,000 concurrent active users.
2.4 API Integration: The vendor SHALL provide documented RESTful APIs supporting JSON payload serialization for integration with legacy SAP and mainframe dispatch systems.

SECTION 3: INFORMATION SECURITY & COMPLIANCE REQUIREMENTS
3.1 Compliance Certifications: The vendor MUST hold an active SOC2 Type II certification and an ISO/IEC 27001:2022 certification covering all hosting environments.
3.2 Cryptographic Safeguards: All sensitive customer data SHALL be encrypted using AES-256 for data-at-rest and TLS 1.3 for all data-in-transit.
3.3 Authentication & SSO: The platform MUST integrate natively with Okta and SAML 2.0 Identity Providers, enforcing mandatory multi-factor authentication for administrative users.
3.4 Data Sovereignty: All transaction logs and telemetry data SHALL reside exclusively within sovereign Australian cloud infrastructure (Sydney/Melbourne regions).

SECTION 4: FUNCTIONAL & USER WORKFLOW REQUIREMENTS
4.1 Real-Time Dashboard: The system SHALL provide an interactive web dashboard displaying shipment status, transit delay alerts, and vehicle telemetry.
4.2 Role-Based Access Control: The platform MUST support role-based access control with granular permissions for Dispatchers, Station Managers, and Compliance Auditors.
4.3 Export & Reporting: The system MUST allow administrative users to export audit trails and operational reports in CSV and PDF formats.

SECTION 5: LEGAL, RISK & COMMERCIAL TERMS
5.1 Unlimited Liability: The contractor SHALL agree to unlimited liability for any data loss, service interruption, or operational delay caused by platform outages.
5.2 Service Level Penalty: Any single outage exceeding 15 minutes in duration SHALL result in an immediate 10% penalty deduction from the monthly service invoice.
5.3 Implementation Timeline: Complete platform migration and user acceptance testing MUST be concluded within 24 weeks of contract award.`;

      const blob = new Blob([sampleText], { type: 'text/plain' });
      const sampleFile = new File([blob], 'sample_rfp_enterprise_cloud.txt', { type: 'text/plain' });

      const res = await api.uploadRFP(sampleFile);
      onUploaded(res.rfp_id);
      onClose();
    } catch (err) {
      console.error('Failed to load sample RFP:', err);
      setUploadError('Failed to initialize sample RFP. Please check backend connectivity.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 max-w-lg w-full overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        <div className="p-5 flex items-center justify-between border-b border-slate-100 bg-slate-50">
          <div className="flex items-center gap-2">
            <UploadCloud className="w-5 h-5 text-sky-600" />
            <h3 className="font-bold text-base text-slate-900">Upload RFP / RFQ / Tender Document</h3>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-slate-200 text-slate-400">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-5">
          {uploadError && (
            <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-800 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
                <span>{uploadError}</span>
              </div>
              <button
                onClick={() => setUploadError(null)}
                className="text-rose-500 hover:text-rose-700 font-bold ml-2"
              >
                &times;
              </button>
            </div>
          )}

          {/* Preset Sample Option */}
          <button
            type="button"
            onClick={handleUseSampleRFP}
            disabled={loading}
            className="w-full p-4 rounded-xl border-2 border-dashed border-sky-300 bg-sky-50/50 hover:bg-sky-50 text-left transition flex items-center justify-between group"
          >
            <div>
              <span className="inline-flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded bg-sky-100 text-sky-800 mb-1">
                <Sparkles className="w-3 h-3" /> Quick Demo Test
              </span>
              <h4 className="text-xs font-bold text-slate-900 group-hover:text-sky-700">
                Load Sample Enterprise Cloud RFP
              </h4>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Pre-configured tender containing technical, security, SLA, and Australian sovereignty terms
              </p>
            </div>
            <span className="text-xs font-bold text-sky-600 group-hover:underline">Load &bull;</span>
          </button>

          <div className="relative flex py-1 items-center">
            <div className="flex-grow border-t border-slate-200"></div>
            <span className="flex-shrink mx-4 text-[11px] font-bold text-slate-400 uppercase">Or upload your own file</span>
            <div className="flex-grow border-t border-slate-200"></div>
          </div>

          {/* Form */}
          <form onSubmit={handleUpload} className="space-y-4">
            <div className="border-2 border-dashed border-slate-300 rounded-xl p-6 text-center hover:border-sky-500 transition cursor-pointer">
              <input
                type="file"
                id="file-upload"
                accept=".pdf,.docx,.txt"
                onChange={(e) => setFile(e.target.files ? e.target.files[0] : null)}
                className="hidden"
              />
              <label htmlFor="file-upload" className="cursor-pointer block">
                <FileText className="w-8 h-8 text-slate-400 mx-auto mb-2" />
                <span className="text-xs font-semibold text-slate-700 block">
                  {file ? file.name : 'Click to browse or drag and drop document'}
                </span>
                <span className="text-[10px] text-slate-400 mt-1 block">Supports PDF, DOCX, and TXT</span>
              </label>
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-xs font-semibold rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-100"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading || !file}
                className="px-5 py-2 text-xs font-bold rounded-lg bg-sky-600 hover:bg-sky-700 disabled:bg-slate-300 text-white shadow-sm transition"
              >
                {loading ? 'Uploading & Parsing...' : 'Upload & Proceed'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};
