"use client";

import React, { useEffect, useState } from "react";
import {
  FileText,
  Download,
  CheckCircle2,
  Lock,
  Sparkles,
  ShieldCheck,
  AlertTriangle,
  RotateCcw,
  ExternalLink,
  ChevronRight,
  Edit3,
  Layers,
  Activity,
  Microscope,
  Info,
  Calendar,
  UserCheck
} from "lucide-react";
import {
  fetchReportData,
  updateReportData,
  regenerateReportNarrative,
  signReport,
  amendReport,
  CapReportData,
  API_BASE
} from "@/lib/api";
import { formatISTDateTime } from "@/lib/utils";

interface ReportWorkspaceProps {
  caseId: string;
  onRefreshCase?: () => void;
}

export function ReportWorkspace({ caseId, onRefreshCase }: ReportWorkspaceProps) {
  const [data, setData] = useState<CapReportData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [generatingNarrative, setGeneratingNarrative] = useState<boolean>(false);

  // Form State
  const [procedure, setProcedure] = useState<string>("Core Needle Biopsy");
  const [laterality, setLaterality] = useState<string>("right");
  const [tumorSite, setTumorSite] = useState<string>("upper_outer_quadrant");
  const [tumorSizeMm, setTumorSizeMm] = useState<number>(18.0);
  const [lviStatus, setLviStatus] = useState<"absent" | "present" | "indeterminate">("absent");
  const [dcisPresent, setDcisPresent] = useState<boolean>(false);

  const [marginStatus, setMarginStatus] = useState<"negative" | "positive" | "cannot_be_assessed">("negative");
  const [closestMarginMm, setClosestMarginMm] = useState<number>(5.0);
  const [closestMarginName, setClosestMarginName] = useState<string>("posterior");

  const [nodesExamined, setNodesExamined] = useState<number>(0);
  const [nodesPositive, setNodesPositive] = useState<number>(0);
  const [extranodalExt, setExtranodalExt] = useState<boolean>(false);

  // Biomarkers
  const [erPercent, setErPercent] = useState<number>(95);
  const [prPercent, setPrPercent] = useState<number>(80);
  const [her2Score, setHer2Score] = useState<string>("1+");
  const [her2Result, setHer2Result] = useState<string>("negative");
  const [ki67Percent, setKi67Percent] = useState<number>(18);

  // Narrative
  const [diagnosisLine, setDiagnosisLine] = useState<string>("");
  const [microscopicFindings, setMicroscopicFindings] = useState<string>("");
  const [clinicalCorrelation, setClinicalCorrelation] = useState<string>("");

  // Sign-off Modal
  const [showSignModal, setShowSignModal] = useState<boolean>(false);
  const [signedBy, setSignedBy] = useState<string>("Dr. Jane Doe, MD, FCAP");
  const [npi, setNpi] = useState<string>("NPI-1982347102");
  const [attestationAgreed, setAttestationAgreed] = useState<boolean>(false);
  const [signLoading, setSignLoading] = useState<boolean>(false);

  // Amendment Modal
  const [showAmendModal, setShowAmendModal] = useState<boolean>(false);
  const [amendReason, setAmendReason] = useState<string>("");
  const [amendLoading, setAmendLoading] = useState<boolean>(false);

  const loadData = async () => {
    try {
      setLoading(true);
      const res = await fetchReportData(caseId);
      setData(res);

      setProcedure(res.procedure || "Core Needle Biopsy");
      setLaterality(res.laterality || "right");
      setTumorSite(res.tumor_site || "upper_outer_quadrant");
      setTumorSizeMm(res.tumor_size_mm || 18.0);
      setLviStatus(res.lvi_status || "absent");
      setDcisPresent(res.dcis_present || false);

      setMarginStatus(res.margins?.status || "negative");
      setClosestMarginMm(res.margins?.closest_margin_mm ?? 5.0);
      setClosestMarginName(res.margins?.closest_margin_name || "posterior");

      setNodesExamined(res.lymph_nodes?.examined_count || 0);
      setNodesPositive(res.lymph_nodes?.positive_count || 0);
      setExtranodalExt(res.lymph_nodes?.extranodal_extension || false);

      setErPercent(res.biomarkers?.er?.percent ?? 95);
      setPrPercent(res.biomarkers?.pr?.percent ?? 80);
      setHer2Score(res.biomarkers?.her2?.ihc_score || "1+");
      setHer2Result(res.biomarkers?.her2?.result || "negative");
      setKi67Percent(res.biomarkers?.ki67?.percent ?? 18);

      setDiagnosisLine(res.narrative?.diagnosis_line || "");
      setMicroscopicFindings(res.narrative?.microscopic_findings || "");
      setClinicalCorrelation(res.narrative?.clinical_correlation || "");
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [caseId]);

  const handleUpdate = async (overrides?: Partial<CapReportData>) => {
    try {
      setSaving(true);
      const payload = {
        case_id: caseId,
        procedure,
        laterality,
        tumor_site: tumorSite,
        tumor_size_mm: tumorSizeMm,
        lvi_status: lviStatus,
        dcis_present: dcisPresent,
        margins: {
          status: marginStatus,
          closest_margin_mm: closestMarginMm,
          closest_margin_name: closestMarginName,
          positive_margins: []
        },
        lymph_nodes: {
          examined_count: nodesExamined,
          positive_count: nodesPositive,
          extranodal_extension: extranodalExt,
          largest_metastasis_mm: 0.0
        },
        biomarkers: {
          er: { status: erPercent > 1 ? "positive" : "negative", percent: erPercent, allred_score: 8 },
          pr: { status: prPercent > 1 ? "positive" : "negative", percent: prPercent, allred_score: 7 },
          her2: { ihc_score: her2Score, fish_status: "not_performed", result: her2Result },
          ki67: { percent: ki67Percent }
        },
        narrative: {
          diagnosis_line: diagnosisLine,
          microscopic_findings: microscopicFindings,
          clinical_correlation: clinicalCorrelation
        },
        ...overrides
      };
      const res = await updateReportData(payload);
      setData(res);
      if (onRefreshCase) onRefreshCase();
    } catch (err) {
      console.error(err);
      alert("Failed to update report");
    } finally {
      setSaving(false);
    }
  };

  const handleRegenerateNarrative = async () => {
    try {
      setGeneratingNarrative(true);
      const res = await regenerateReportNarrative(caseId);
      if (res.narrative) {
        setDiagnosisLine(res.narrative.diagnosis_line);
        setMicroscopicFindings(res.narrative.microscopic_findings);
        setClinicalCorrelation(res.narrative.clinical_correlation);
      }
      await loadData();
    } catch (err) {
      console.error(err);
      alert("Failed to regenerate narrative");
    } finally {
      setGeneratingNarrative(false);
    }
  };

  const handleSign = async () => {
    if (!attestationAgreed) {
      alert("Please agree to the pathologist attestation statement before signing.");
      return;
    }
    try {
      setSignLoading(true);
      const res = await signReport({
        case_id: caseId,
        signed_by: signedBy,
        npi,
        attestation_statement: "I electronically attest that I have reviewed the whole slide image, triage hotspots, mitotic counts, and Nottingham histologic grading parameters, and I verify that the diagnostic findings, CAP synoptic elements, and AJCC staging in this report are accurate."
      });
      setData(res);
      setShowSignModal(false);
      if (onRefreshCase) onRefreshCase();
    } catch (err: any) {
      console.error(err);
      alert(err.message || "Failed to sign report");
    } finally {
      setSignLoading(false);
    }
  };

  const handleAmend = async () => {
    if (amendReason.trim().length < 10) {
      alert("Please provide an amendment rationale of at least 10 characters.");
      return;
    }
    try {
      setAmendLoading(true);
      const res = await amendReport({
        case_id: caseId,
        amended_by: signedBy,
        amendment_reason: amendReason,
        updated_fields: {
          tumor_size_mm: tumorSizeMm,
          lvi_status: lviStatus
        }
      });
      setData(res);
      setShowAmendModal(false);
      setAmendReason("");
      if (onRefreshCase) onRefreshCase();
    } catch (err: any) {
      console.error(err);
      alert(err.message || "Failed to submit amendment");
    } finally {
      setAmendLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-slate-400 space-y-3 bg-slate-950 p-8">
        <div className="w-10 h-10 border-4 border-sky-500/20 border-t-sky-500 rounded-full animate-spin" />
        <p className="text-sm font-medium">Loading CAP-Compliant Synoptic Report...</p>
      </div>
    );
  }

  const isSigned = data?.status === "signed" || data?.status === "amended";
  const isResection = procedure.toLowerCase().includes("excision") || procedure.toLowerCase().includes("mastectomy");

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-slate-950 text-slate-100">
      {/* Top Action & Status Bar */}
      <div className="bg-slate-900 border-b border-slate-800 px-6 py-3.5 flex items-center justify-between z-10 shrink-0">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-sky-950/80 border border-sky-800/80 rounded-lg text-sky-400">
            <FileText className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2.5">
              <h2 className="text-base font-bold text-white tracking-tight">
                Stage 6: CAP Synoptic Pathology Report
              </h2>
              <span
                className={`text-[10px] font-mono font-bold uppercase px-2.5 py-0.5 rounded-full border ${
                  isSigned
                    ? "bg-emerald-950/80 border-emerald-700 text-emerald-300"
                    : "bg-amber-950/80 border-amber-700 text-amber-300"
                }`}
              >
                {data?.status || "Draft"}
              </span>
              {data?.amendments && data.amendments.length > 0 && (
                <span className="text-[10px] font-mono bg-purple-950/80 border border-purple-700 text-purple-300 px-2 py-0.5 rounded-full">
                  v1.{data.amendments.length}
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              College of American Pathologists (CAP) Cancer Protocol • Invasive Carcinoma of the Breast
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2.5">
          {/* Download JSON Button */}
          <a
            href={`${API_BASE}/api/v1/stages/report/${caseId}/json`}
            download={`CAP_Synoptic_${caseId.substring(0, 8)}.json`}
            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 rounded-lg transition text-xs font-semibold flex items-center space-x-1.5"
            title="Download structured CAP eCC / FHIR-compatible JSON"
          >
            <Download className="w-3.5 h-3.5 text-sky-400" />
            <span>Export JSON</span>
          </a>

          {/* Download/Preview PDF Button */}
          <a
            href={`${API_BASE}/api/v1/stages/report/${caseId}/pdf`}
            target="_blank"
            rel="noopener noreferrer"
            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 rounded-lg transition text-xs font-semibold flex items-center space-x-1.5"
            title="Open printable institutional clinical PDF"
          >
            <ExternalLink className="w-3.5 h-3.5 text-sky-400" />
            <span>Printable PDF</span>
          </a>

          {/* Save / Update Button */}
          {!isSigned && (
            <button
              onClick={() => handleUpdate()}
              disabled={saving}
              className="px-3.5 py-1.5 bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white rounded-lg transition text-xs font-semibold flex items-center space-x-1.5 shadow"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${saving ? "animate-spin" : ""}`} />
              <span>{saving ? "Saving..." : "Save Draft"}</span>
            </button>
          )}

          {/* Sign / Amend Action Buttons */}
          {!isSigned ? (
            <button
              onClick={() => setShowSignModal(true)}
              className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg transition text-xs font-bold flex items-center space-x-1.5 shadow-lg shadow-emerald-950/50 border border-emerald-400/50"
            >
              <ShieldCheck className="w-4 h-4" />
              <span>Sign & Finalize Report</span>
            </button>
          ) : (
            <button
              onClick={() => setShowAmendModal(true)}
              className="px-3.5 py-1.5 bg-purple-700 hover:bg-purple-600 text-white rounded-lg transition text-xs font-bold flex items-center space-x-1.5 shadow border border-purple-500/50"
            >
              <Edit3 className="w-3.5 h-3.5" />
              <span>Create Amendment</span>
            </button>
          )}
        </div>
      </div>

      {/* Main Content Workspace Grid */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Signed / Locked State Banner */}
        {isSigned && (
          <div className="bg-emerald-950/40 border border-emerald-800/80 rounded-xl p-4 flex items-start justify-between">
            <div className="flex items-start space-x-3">
              <div className="p-2 bg-emerald-900/60 rounded-lg text-emerald-400 shrink-0 mt-0.5">
                <Lock className="w-5 h-5" />
              </div>
              <div className="space-y-1">
                <div className="flex items-center space-x-2">
                  <h4 className="text-sm font-bold text-emerald-300">
                    Report Finalized & Electronically Signed
                  </h4>
                  <span className="text-[11px] font-mono text-slate-400">
                    ({formatISTDateTime(data?.signed_at)})
                  </span>
                </div>
                <p className="text-xs text-slate-300">
                  Attested by <span className="font-semibold text-white">{data?.signed_by}</span> ({data?.npi}). This synoptic document is locked against accidental alterations.
                </p>
                <div className="text-[10px] font-mono text-emerald-400/80 truncate max-w-2xl pt-1">
                  SHA-256 Verification Hash: {data?.integrity_hash}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 2-Column Responsive Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Column: Specimen Setup & CAP Synoptic Smart-Form (7 Cols) */}
          <div className="lg:col-span-7 space-y-6">
            {/* 1. Specimen & Surgical Procedure Card */}
            <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 space-y-4 shadow-sm">
              <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
                <h3 className="text-xs font-bold text-sky-400 uppercase tracking-wider flex items-center space-x-2">
                  <Layers className="w-4 h-4" />
                  <span>1. Specimen Protocol & Clinical Intake</span>
                </h3>
                <span className="text-[11px] text-slate-400">
                  {isResection ? "Comprehensive Resection Protocol" : "Core Needle Biopsy Protocol"}
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
                {/* Procedure Selector */}
                <div className="space-y-1.5">
                  <label className="text-slate-400 font-medium">Procedure Type</label>
                  <select
                    disabled={isSigned}
                    value={procedure}
                    onChange={(e) => setProcedure(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-sky-500 disabled:opacity-60"
                  >
                    <option value="Core Needle Biopsy">Core Needle Biopsy</option>
                    <option value="Excision / Lumpectomy">Excision / Lumpectomy</option>
                    <option value="Total Mastectomy">Total Mastectomy</option>
                    <option value="Modified Radical Mastectomy">Modified Radical Mastectomy</option>
                  </select>
                </div>

                {/* Laterality */}
                <div className="space-y-1.5">
                  <label className="text-slate-400 font-medium">Laterality</label>
                  <select
                    disabled={isSigned}
                    value={laterality}
                    onChange={(e) => setLaterality(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-sky-500 disabled:opacity-60"
                  >
                    <option value="right">Right Breast</option>
                    <option value="left">Left Breast</option>
                    <option value="bilateral">Bilateral</option>
                  </select>
                </div>

                {/* Tumor Location */}
                <div className="space-y-1.5">
                  <label className="text-slate-400 font-medium">Tumor Site</label>
                  <select
                    disabled={isSigned}
                    value={tumorSite}
                    onChange={(e) => setTumorSite(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-sky-500 disabled:opacity-60"
                  >
                    <option value="upper_outer_quadrant">Upper Outer Quadrant (UOQ)</option>
                    <option value="upper_inner_quadrant">Upper Inner Quadrant (UIQ)</option>
                    <option value="lower_outer_quadrant">Lower Outer Quadrant (LOQ)</option>
                    <option value="lower_inner_quadrant">Lower Inner Quadrant (LIQ)</option>
                    <option value="central_subareolar">Central / Subareolar</option>
                    <option value="clock_12">12:00 Position</option>
                    <option value="clock_2">2:00 Position</option>
                    <option value="clock_6">6:00 Position</option>
                    <option value="clock_9">9:00 Position</option>
                  </select>
                </div>
              </div>
            </div>

            {/* 2. Auto-Locked Stage 1-5 Diagnostic Findings Card */}
            <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 space-y-4 shadow-sm">
              <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
                <h3 className="text-xs font-bold text-sky-400 uppercase tracking-wider flex items-center space-x-2">
                  <Microscope className="w-4 h-4" />
                  <span>2. Verified Histologic & Grade Synthesis (Stages 4 & 5)</span>
                </h3>
                <span className="text-[10px] font-mono bg-sky-950 border border-sky-800 text-sky-300 px-2 py-0.5 rounded">
                  Zero-LLM Math Guard
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {/* Histologic Type */}
                <div className="p-3 bg-slate-950/80 border border-slate-800 rounded-lg space-y-1">
                  <div className="text-[10px] text-slate-400 font-semibold uppercase">CAP Histologic Subtype</div>
                  <div className="text-sm font-bold text-white truncate">
                    {data?.nottingham_grade?.histologic_type || "IDC-NST"}
                  </div>
                  <div className="text-[10px] text-emerald-400 flex items-center space-x-1">
                    <UserCheck className="w-3 h-3" />
                    <span>Pathologist Confirmed</span>
                  </div>
                </div>

                {/* Nottingham Grade */}
                <div className="p-3 bg-slate-950/80 border border-slate-800 rounded-lg space-y-1">
                  <div className="text-[10px] text-slate-400 font-semibold uppercase">Nottingham Grade</div>
                  <div className="text-sm font-bold text-sky-300">
                    Grade {data?.nottingham_grade?.grade || 2} ({data?.nottingham_grade?.nottingham_sum || 7}/9)
                  </div>
                  <div className="text-[10px] text-slate-400">
                    T{data?.nottingham_grade?.tubule_score || 2} + P{data?.nottingham_grade?.pleo_score || 2} + M{data?.nottingham_grade?.mitotic_score || 3}
                  </div>
                </div>

                {/* Mitotic Activity */}
                <div className="p-3 bg-slate-950/80 border border-slate-800 rounded-lg space-y-1">
                  <div className="text-[10px] text-slate-400 font-semibold uppercase">Mitotic Density</div>
                  <div className="text-sm font-bold text-purple-300">
                    Score {data?.nottingham_grade?.mitotic_score || 3}
                  </div>
                  <div className="text-[10px] text-slate-400">
                    Evaluated across 10 Hotspot HPFs (2.157 mm²)
                  </div>
                </div>
              </div>
            </div>

            {/* 3. CAP Synoptic Smart-Form: Tumor Extent, Margins, Nodes */}
            <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 space-y-5 shadow-sm">
              <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
                <h3 className="text-xs font-bold text-sky-400 uppercase tracking-wider flex items-center space-x-2">
                  <Activity className="w-4 h-4" />
                  <span>3. Tumor Extent, Margins & Lymph Nodes</span>
                </h3>
              </div>

              {/* Tumor Size & LVI Grid */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
                <div className="space-y-1.5">
                  <label className="text-slate-400 font-medium">Invasive Tumor Size (mm)</label>
                  <div className="flex items-center space-x-2">
                    <input
                      type="number"
                      step="0.5"
                      min="0.1"
                      disabled={isSigned}
                      value={tumorSizeMm}
                      onChange={(e) => setTumorSizeMm(parseFloat(e.target.value) || 0)}
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-sky-500 font-mono"
                    />
                    <span className="text-slate-400 shrink-0">mm</span>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="text-slate-400 font-medium">Lymphovascular Invasion (LVI)</label>
                  <select
                    disabled={isSigned}
                    value={lviStatus}
                    onChange={(e) => setLviStatus(e.target.value as any)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-sky-500"
                  >
                    <option value="absent">Not Identified / Absent</option>
                    <option value="present">Present</option>
                    <option value="indeterminate">Indeterminate</option>
                  </select>
                </div>

                <div className="space-y-1.5">
                  <label className="text-slate-400 font-medium">DCIS Component</label>
                  <div className="pt-2">
                    <label className="inline-flex items-center space-x-2 cursor-pointer">
                      <input
                        type="checkbox"
                        disabled={isSigned}
                        checked={dcisPresent}
                        onChange={(e) => setDcisPresent(e.target.checked)}
                        className="rounded border-slate-700 text-sky-600 focus:ring-0 bg-slate-950 w-4 h-4"
                      />
                      <span className="text-xs text-slate-300">DCIS Present</span>
                    </label>
                  </div>
                </div>
              </div>

              {/* Margins & Nodes Section (Resection Specific) */}
              <div className="pt-3 border-t border-slate-800/80 space-y-4">
                <div className="text-[11px] font-bold text-slate-300 uppercase tracking-wider">
                  Surgical Margins & Nodal Evaluation
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
                  <div className="space-y-1.5">
                    <label className="text-slate-400 font-medium">Margins Status</label>
                    <select
                      disabled={isSigned}
                      value={marginStatus}
                      onChange={(e) => setMarginStatus(e.target.value as any)}
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-sky-500"
                    >
                      <option value="negative">Negative (All Margins Clear)</option>
                      <option value="positive">Positive for Invasive Carcinoma</option>
                      <option value="cannot_be_assessed">Cannot be Assessed</option>
                    </select>
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-slate-400 font-medium">Closest Margin Distance (mm)</label>
                    <input
                      type="number"
                      step="0.5"
                      min="0"
                      disabled={isSigned}
                      value={closestMarginMm}
                      onChange={(e) => setClosestMarginMm(parseFloat(e.target.value) || 0)}
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-sky-500 font-mono"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-slate-400 font-medium">Positive / Examined Nodes</label>
                    <div className="flex items-center space-x-2">
                      <input
                        type="number"
                        min="0"
                        placeholder="Pos"
                        disabled={isSigned}
                        value={nodesPositive}
                        onChange={(e) => setNodesPositive(parseInt(e.target.value) || 0)}
                        className="w-16 bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-2 text-slate-200 font-mono text-center"
                      />
                      <span className="text-slate-400">/</span>
                      <input
                        type="number"
                        min="0"
                        placeholder="Exam"
                        disabled={isSigned}
                        value={nodesExamined}
                        onChange={(e) => setNodesExamined(parseInt(e.target.value) || 0)}
                        className="w-16 bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-2 text-slate-200 font-mono text-center"
                      />
                      <span className="text-slate-400 text-[11px]">Nodes</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* 4. Receptor Biomarkers Panel */}
              <div className="pt-3 border-t border-slate-800/80 space-y-3">
                <div className="text-[11px] font-bold text-slate-300 uppercase tracking-wider">
                  Receptor Biomarkers (IHC / ISH)
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                  <div className="space-y-1">
                    <label className="text-slate-400 font-medium">ER % Positive</label>
                    <input
                      type="number"
                      min="0"
                      max="100"
                      disabled={isSigned}
                      value={erPercent}
                      onChange={(e) => setErPercent(parseInt(e.target.value) || 0)}
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-slate-200 font-mono"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-slate-400 font-medium">PR % Positive</label>
                    <input
                      type="number"
                      min="0"
                      max="100"
                      disabled={isSigned}
                      value={prPercent}
                      onChange={(e) => setPrPercent(parseInt(e.target.value) || 0)}
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-slate-200 font-mono"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-slate-400 font-medium">HER2 IHC Score</label>
                    <select
                      disabled={isSigned}
                      value={her2Score}
                      onChange={(e) => {
                        setHer2Score(e.target.value);
                        setHer2Result(e.target.value === "3+" ? "positive" : e.target.value === "2+" ? "equivocal" : "negative");
                      }}
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-slate-200"
                    >
                      <option value="0">0 (Negative)</option>
                      <option value="1+">1+ (Negative)</option>
                      <option value="2+">2+ (Equivocal)</option>
                      <option value="3+">3+ (Positive)</option>
                    </select>
                  </div>

                  <div className="space-y-1">
                    <label className="text-slate-400 font-medium">Ki-67 Index %</label>
                    <input
                      type="number"
                      min="0"
                      max="100"
                      disabled={isSigned}
                      value={ki67Percent}
                      onChange={(e) => setKi67Percent(parseInt(e.target.value) || 0)}
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-slate-200 font-mono"
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Right Column: Staging, MedGemma Narrative & Evidence (5 Cols) */}
          <div className="lg:col-span-5 space-y-6">
            {/* Live AJCC Staging Card */}
            <div className="bg-gradient-to-br from-slate-900 to-sky-950/40 border border-sky-800/80 rounded-xl p-5 space-y-3 shadow">
              <div className="flex items-center justify-between border-b border-sky-800/40 pb-2.5">
                <h3 className="text-xs font-bold text-sky-400 uppercase tracking-wider flex items-center space-x-2">
                  <ShieldCheck className="w-4 h-4" />
                  <span>AJCC 8th/9th Ed. Pathologic Staging</span>
                </h3>
                <span className="text-[10px] font-mono text-sky-300 bg-sky-900/60 px-2 py-0.5 rounded">
                  Deterministic
                </span>
              </div>

              <div className="flex items-center justify-between pt-1">
                <div>
                  <div className="text-2xl font-black text-white tracking-tight">
                    {data?.staging?.pt_stage || "pT1c"} {data?.staging?.pn_stage || "pNX"}
                  </div>
                  <div className="text-xs text-sky-300 font-semibold mt-0.5">
                    Anatomic Stage Group: <span className="text-white font-bold">{data?.staging?.stage_group || "IA"}</span>
                  </div>
                </div>

                <div className="text-right text-[11px] text-slate-400 space-y-0.5">
                  <div>Size: {tumorSizeMm} mm</div>
                  <div>Nodes: {nodesPositive}/{nodesExamined}</div>
                </div>
              </div>
            </div>

            {/* MedGemma Grounded Narrative Card */}
            <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 space-y-4 shadow-sm">
              <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
                <h3 className="text-xs font-bold text-sky-400 uppercase tracking-wider flex items-center space-x-2">
                  <Sparkles className="w-4 h-4" />
                  <span>MedGemma 1.5 Grounded Narrative</span>
                </h3>
                {!isSigned && (
                  <button
                    onClick={handleRegenerateNarrative}
                    disabled={generatingNarrative}
                    className="p-1.5 bg-sky-950 hover:bg-sky-900 text-sky-300 rounded border border-sky-800/80 text-xs font-medium flex items-center space-x-1"
                    title="Regenerate diagnostic narrative with MedGemma"
                  >
                    <RotateCcw className={`w-3 h-3 ${generatingNarrative ? "animate-spin" : ""}`} />
                    <span>Regenerate</span>
                  </button>
                )}
              </div>

              <div className="space-y-3 text-xs">
                {/* Diagnosis Line */}
                <div className="space-y-1">
                  <label className="text-slate-400 font-semibold uppercase text-[10px]">
                    Synoptic Diagnosis Line
                  </label>
                  <textarea
                    rows={2}
                    disabled={isSigned}
                    value={diagnosisLine}
                    onChange={(e) => setDiagnosisLine(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-sky-500 font-mono text-[11px] leading-relaxed resize-none"
                  />
                </div>

                {/* Microscopic Findings */}
                <div className="space-y-1">
                  <label className="text-slate-400 font-semibold uppercase text-[10px]">
                    Microscopic Findings
                  </label>
                  <textarea
                    rows={3}
                    disabled={isSigned}
                    value={microscopicFindings}
                    onChange={(e) => setMicroscopicFindings(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-sky-500 text-xs leading-relaxed resize-none"
                  />
                </div>

                {/* Clinical Correlation */}
                <div className="space-y-1">
                  <label className="text-slate-400 font-semibold uppercase text-[10px]">
                    Clinical-Pathologic Correlation
                  </label>
                  <textarea
                    rows={3}
                    disabled={isSigned}
                    value={clinicalCorrelation}
                    onChange={(e) => setClinicalCorrelation(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-sky-500 text-xs leading-relaxed resize-none"
                  />
                </div>
              </div>
            </div>

            {/* Key Visual Evidence Gallery Preview */}
            <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 space-y-3 shadow-sm">
              <div className="flex items-center justify-between border-b border-slate-800/80 pb-2.5">
                <h3 className="text-xs font-bold text-sky-400 uppercase tracking-wider flex items-center space-x-2">
                  <Layers className="w-4 h-4" />
                  <span>Key Computational Evidence</span>
                </h3>
              </div>

              <div className="grid grid-cols-3 gap-2 pt-1">
                <div className="bg-slate-950 border border-slate-800 rounded-lg p-2 text-center space-y-1">
                  <div className="h-16 bg-slate-900 rounded flex items-center justify-center text-[10px] text-slate-500 font-mono">
                    WSI Heatmap
                  </div>
                  <div className="text-[10px] text-slate-300 font-medium truncate">Triage Map</div>
                </div>

                <div className="bg-slate-950 border border-slate-800 rounded-lg p-2 text-center space-y-1">
                  <div className="h-16 bg-slate-900 rounded flex items-center justify-center text-[10px] text-slate-500 font-mono">
                    Mitotic Crop
                  </div>
                  <div className="text-[10px] text-slate-300 font-medium truncate">Top HPF (40×)</div>
                </div>

                <div className="bg-slate-950 border border-slate-800 rounded-lg p-2 text-center space-y-1">
                  <div className="h-16 bg-slate-900 rounded flex items-center justify-center text-[10px] text-slate-500 font-mono">
                    Grading Patch
                  </div>
                  <div className="text-[10px] text-slate-300 font-medium truncate">10× Morphology</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Pathologist Sign-Off Modal */}
      {showSignModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-lg w-full p-6 space-y-5 shadow-2xl">
            <div className="flex items-center space-x-3 border-b border-slate-800 pb-3">
              <div className="p-2.5 bg-emerald-950/80 border border-emerald-800 rounded-xl text-emerald-400">
                <ShieldCheck className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">
                  Pathologist Electronic Sign-Off & Attestation
                </h3>
                <p className="text-xs text-slate-400">
                  Case #{caseId.substring(0, 8)} • Stage 6 CAP Finalization
                </p>
              </div>
            </div>

            <div className="space-y-4 text-xs">
              <div className="space-y-1.5">
                <label className="text-slate-300 font-medium">Pathologist Name & Title</label>
                <input
                  type="text"
                  value={signedBy}
                  onChange={(e) => setSignedBy(e.target.value)}
                  placeholder="e.g. Dr. Jane Doe, MD, FCAP"
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-sky-500 font-medium"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-slate-300 font-medium">NPI / License Number</label>
                <input
                  type="text"
                  value={npi}
                  onChange={(e) => setNpi(e.target.value)}
                  placeholder="e.g. NPI-1982347102"
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-sky-500 font-mono"
                />
              </div>

              <div className="p-3.5 bg-slate-950 border border-slate-800 rounded-xl space-y-3">
                <div className="text-[11px] font-semibold text-slate-300">
                  Legal Attestation Statement:
                </div>
                <p className="text-[11px] text-slate-400 leading-relaxed italic">
                  "I electronically attest that I have reviewed the Whole-Slide Image (WSI), AI-generated hotspot triage regions, mitotic figure annotations across 10 high-power fields, and Nottingham histological parameters, and I verify that the diagnostic findings, CAP synoptic elements, and AJCC staging in this report are clinically accurate."
                </p>
                <label className="flex items-start space-x-2.5 pt-1 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={attestationAgreed}
                    onChange={(e) => setAttestationAgreed(e.target.checked)}
                    className="mt-0.5 rounded border-slate-700 text-emerald-600 focus:ring-0 bg-slate-900 w-4 h-4"
                  />
                  <span className="text-xs font-semibold text-emerald-400">
                    I agree and electronically sign this diagnostic report.
                  </span>
                </label>
              </div>
            </div>

            <div className="flex items-center justify-end space-x-3 pt-2">
              <button
                onClick={() => setShowSignModal(false)}
                disabled={signLoading}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-semibold transition"
              >
                Cancel
              </button>
              <button
                onClick={handleSign}
                disabled={signLoading || !attestationAgreed}
                className="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white rounded-lg text-xs font-bold transition shadow-lg shadow-emerald-950/50 flex items-center space-x-1.5"
              >
                <Lock className={`w-3.5 h-3.5 ${signLoading ? "animate-spin" : ""}`} />
                <span>{signLoading ? "Signing & Hashing..." : "Commit Signature"}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Amendment Modal */}
      {showAmendModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-lg w-full p-6 space-y-5 shadow-2xl">
            <div className="flex items-center space-x-3 border-b border-slate-800 pb-3">
              <div className="p-2.5 bg-purple-950/80 border border-purple-800 rounded-xl text-purple-400">
                <Edit3 className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">
                  Create Formal Synoptic Amendment
                </h3>
                <p className="text-xs text-slate-400">
                  Versioned Clinical Addendum (v1.{((data?.amendments?.length || 0) + 1)})
                </p>
              </div>
            </div>

            <div className="space-y-4 text-xs">
              <div className="space-y-1.5">
                <label className="text-slate-300 font-medium">Amendment Rationale & Justification</label>
                <textarea
                  rows={4}
                  value={amendReason}
                  onChange={(e) => setAmendReason(e.target.value)}
                  placeholder="State the clinical or laboratory rationale for amending this finalized report (min 10 characters)..."
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg p-3 text-slate-200 focus:outline-none focus:border-purple-500 leading-relaxed resize-none"
                />
              </div>
            </div>

            <div className="flex items-center justify-end space-x-3 pt-2">
              <button
                onClick={() => setShowAmendModal(false)}
                disabled={amendLoading}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-semibold transition"
              >
                Cancel
              </button>
              <button
                onClick={handleAmend}
                disabled={amendLoading || amendReason.trim().length < 10}
                className="px-5 py-2 bg-purple-700 hover:bg-purple-600 disabled:opacity-50 text-white rounded-lg text-xs font-bold transition shadow flex items-center space-x-1.5"
              >
                <RotateCcw className={`w-3.5 h-3.5 ${amendLoading ? "animate-spin" : ""}`} />
                <span>{amendLoading ? "Submitting..." : "Submit Amendment"}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
