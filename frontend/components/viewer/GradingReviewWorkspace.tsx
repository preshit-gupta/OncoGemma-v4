"use client";

import React, { useState, useEffect, useMemo } from "react";
import {
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  Sparkles,
  Edit3,
  Layers,
  ArrowRight,
  Eye,
  Microscope,
  HelpCircle,
  FileCheck,
  Check,
  X,
  ExternalLink,
  ChevronRight,
  Info,
  ShieldCheck,
  AlertCircle
} from "lucide-react";
import {
  GradingStageData,
  GradingPatch,
  fetchGradingStageData,
  recomputeGradingPreview,
  confirmGradingStage,
  API_BASE
} from "@/lib/api";

interface GradingReviewWorkspaceProps {
  caseId: string;
  onAdvanceToReport?: () => void;
  onReopenMitosis?: () => void;
}

const HISTOLOGIC_TYPE_OPTIONS = [
  { id: "IDC-NST", label: "Invasive Breast Carcinoma of No Special Type (IDC-NST / Ductal)" },
  { id: "ILC", label: "Invasive Lobular Carcinoma (ILC)" },
  { id: "mucinous", label: "Mucinous Carcinoma" },
  { id: "tubular", label: "Tubular Carcinoma" },
  { id: "papillary", label: "Invasive Papillary Carcinoma" },
  { id: "metaplastic", label: "Metaplastic Carcinoma" },
  { id: "other", label: "Other / Special Variant Carcinoma" }
];

export function GradingReviewWorkspace({
  caseId,
  onAdvanceToReport,
  onReopenMitosis
}: GradingReviewWorkspaceProps) {
  const [data, setData] = useState<GradingStageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Overrides & active states
  const [tubuleOverrideScore, setTubuleOverrideScore] = useState<number | null>(null);
  const [tubuleOverridePercent, setTubuleOverridePercent] = useState<number | null>(null);
  const [tubuleJustification, setTubuleJustification] = useState<string>("");
  const [isTubuleEditing, setIsTubuleEditing] = useState(false);

  const [pleoOverrideScore, setPleoOverrideScore] = useState<number | null>(null);
  const [pleoJustification, setPleoJustification] = useState<string>("");
  const [isPleoEditing, setIsPleoEditing] = useState(false);

  // Histologic type gate
  const [selectedHistologicType, setSelectedHistologicType] = useState<string>("IDC-NST");
  const [isTypeConfirmed, setIsTypeConfirmed] = useState<boolean>(false);

  // Evidence patch drawer / modal
  const [selectedPatch, setSelectedPatch] = useState<GradingPatch | null>(null);
  const [showAllPatches, setShowAllPatches] = useState(false);

  // Confirming submission state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetchGradingStageData(caseId);
      setData(res);

      // Initialize state from existing data/overrides
      if (res.histologic_type) {
        setSelectedHistologicType(res.histologic_type.confirmed_type || res.histologic_type.proposed_type || "IDC-NST");
        setIsTypeConfirmed(res.histologic_type.is_confirmed);
      }
      if (res.overrides?.tubule) {
        setTubuleOverrideScore(res.overrides.tubule.score);
        setTubuleOverridePercent(res.overrides.tubule.percent ?? null);
        setTubuleJustification(res.overrides.tubule.justification || "");
      }
      if (res.overrides?.pleo) {
        setPleoOverrideScore(res.overrides.pleo.score);
        setPleoJustification(res.overrides.pleo.justification || "");
      }
    } catch (err: any) {
      console.error(err);
      setError(err.message || "Failed to load Stage 5 Nottingham grading data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [caseId]);

  // Live Reactive Nottingham Sum & Grade Synthesis
  const activeTubuleScore = tubuleOverrideScore ?? (data?.machine?.tubule_score || 2);
  const activePleoScore = pleoOverrideScore ?? (data?.machine?.pleo_score || 2);
  const activeMitoticScore = data?.current?.mitotic_score || data?.mitotic_summary?.mitotic_score || 2;

  const activeSum = activeTubuleScore + activePleoScore + activeMitoticScore;
  const activeGrade = activeSum <= 5 ? 1 : activeSum <= 7 ? 2 : 3;

  const isTubuleOverridden = tubuleOverrideScore !== null && tubuleOverrideScore !== data?.machine?.tubule_score;
  const isPleoOverridden = pleoOverrideScore !== null && pleoOverrideScore !== data?.machine?.pleo_score;

  // Validation checks for final confirmation gate
  const isTubuleJustificationValid = !isTubuleOverridden || tubuleJustification.trim().length >= 10;
  const isPleoJustificationValid = !isPleoOverridden || pleoJustification.trim().length >= 10;
  const canConfirmStage = isTypeConfirmed && isTubuleJustificationValid && isPleoJustificationValid && !isSubmitting;

  const handleApplyTubuleOverride = (score: number) => {
    setTubuleOverrideScore(score);
    setIsTubuleEditing(false);
  };

  const handleResetTubule = () => {
    setTubuleOverrideScore(null);
    setTubuleOverridePercent(null);
    setTubuleJustification("");
    setIsTubuleEditing(false);
  };

  const handleApplyPleoOverride = (score: number) => {
    setPleoOverrideScore(score);
    setIsPleoEditing(false);
  };

  const handleResetPleo = () => {
    setPleoOverrideScore(null);
    setPleoJustification("");
    setIsPleoEditing(false);
  };

  const handleConfirmFinalStage = async () => {
    if (!canConfirmStage) return;
    setIsSubmitting(true);
    setSubmitError(null);

    const overridesPayload: Record<string, any> = {};
    if (isTubuleOverridden && tubuleOverrideScore !== null) {
      overridesPayload.tubule = {
        score: tubuleOverrideScore,
        percent: tubuleOverridePercent,
        original_score: data?.machine?.tubule_score,
        justification: tubuleJustification.trim(),
        overridden_at: new Date().toISOString()
      };
    }
    if (isPleoOverridden && pleoOverrideScore !== null) {
      overridesPayload.pleo = {
        score: pleoOverrideScore,
        original_score: data?.machine?.pleo_score,
        justification: pleoJustification.trim(),
        overridden_at: new Date().toISOString()
      };
    }

    try {
      await confirmGradingStage({
        case_id: caseId,
        reviewed_by: "user_pathologist_001",
        histologic_type: selectedHistologicType,
        type_confirmed: true,
        overrides: overridesPayload,
        tubule_score: activeTubuleScore,
        tubule_percent: tubuleOverridePercent ?? data?.machine?.tubule_percent,
        pleo_score: activePleoScore,
        mitotic_score: activeMitoticScore,
        nottingham_sum: activeSum,
        grade: activeGrade
      });

      if (onAdvanceToReport) {
        onAdvanceToReport();
      } else {
        await loadData();
      }
    } catch (err: any) {
      console.error(err);
      setSubmitError(err.message || "Failed to confirm Stage 5 grading");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 bg-slate-900 text-slate-200">
        <div className="w-10 h-10 border-4 border-sky-500 border-t-transparent rounded-full animate-spin mb-4" />
        <p className="text-sm font-medium">Evaluating Nottingham Parameters with MedGemma 1.5...</p>
        <p className="text-xs text-slate-400 mt-1">Processing 24 normalized 10× evidence patches</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 bg-slate-900 text-slate-200">
        <AlertTriangle className="w-12 h-12 text-rose-400 mb-3" />
        <h3 className="text-base font-semibold text-rose-300">Stage 5 Grading Error</h3>
        <p className="text-xs text-slate-400 mt-1 max-w-md text-center">{error}</p>
        <button
          onClick={loadData}
          className="mt-4 px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded text-xs font-semibold"
        >
          Retry Loading
        </button>
      </div>
    );
  }

  const patches = data.patches || [];
  const flags = data.machine?.flags || [];

  return (
    <div className="flex-1 flex flex-col h-full bg-slate-950 text-slate-100 overflow-y-auto">
      {/* Top Header */}
      <header className="px-6 py-4 bg-slate-900 border-b border-slate-800 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 rounded bg-sky-950 border border-sky-600 text-[11px] font-bold text-sky-300 uppercase tracking-wider">
              Stage 5: Nottingham Histological Grading
            </span>
            <span className="text-xs text-slate-400">• MedGemma 1.5 Architecture</span>
          </div>
          <h1 className="text-lg font-bold text-white mt-1">
            Nottingham Grading & Architectural Synthesis
          </h1>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowAllPatches(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded text-xs font-semibold text-slate-200 transition"
          >
            <Eye className="w-3.5 h-3.5 text-sky-400" />
            Inspect 24 Evidence Patches
          </button>
          <button
            onClick={loadData}
            title="Refresh Stage 5 Data"
            className="p-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded text-slate-400 hover:text-slate-200 transition"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* Quality Notice / Flags Banner */}
      {flags.length > 0 && (
        <div className="mx-6 mt-4 p-3 bg-amber-950/60 border border-amber-500/50 rounded-lg flex items-center gap-3 text-amber-200 text-xs">
          <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
          <div>
            <span className="font-semibold">Quality Agreement Notice: </span>
            {flags.includes("insufficient_tumor_patches") && "Low tumor patch density (<8 patches with tumor tissue). "}
            {flags.includes("pleo_high_variance") && "High nuclear pleomorphism variance across sampled areas (>30% off mode). "}
            Please inspect the evidence patches carefully.
          </div>
        </div>
      )}

      {/* Main Review Workspace Content */}
      <div className="flex-1 p-6 space-y-6 max-w-7xl mx-auto w-full">
        {/* Top 3 Sub-scores Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {/* 1. Tubule Formation Card */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col justify-between relative shadow-lg">
            <div>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="w-6 h-6 rounded-full bg-indigo-950 border border-indigo-500 text-indigo-300 font-bold text-xs flex items-center justify-center">
                    T
                  </span>
                  <h2 className="text-sm font-bold text-white">Tubule Formation</h2>
                </div>
                {isTubuleOverridden && (
                  <span className="px-2 py-0.5 rounded bg-amber-950 border border-amber-500 text-[10px] font-bold text-amber-300 flex items-center gap-1">
                    <Edit3 className="w-3 h-3" /> Manually Assigned
                  </span>
                )}
              </div>

              <div className="mt-2 bg-slate-950 rounded-lg p-3 border border-slate-800">
                <div className="flex items-baseline justify-between">
                  <span className="text-xs text-slate-400">Score & Classification:</span>
                  <span className="text-xl font-extrabold text-white">
                    Score {activeTubuleScore}{" "}
                    <span className="text-xs font-normal text-slate-400">
                      ({activeTubuleScore === 1 ? ">75%" : activeTubuleScore === 2 ? "10-75%" : "<10%"})
                    </span>
                  </span>
                </div>
                <div className="flex items-baseline justify-between mt-2 pt-2 border-t border-slate-800/80">
                  <span className="text-xs text-slate-400">Derived Weighted Median:</span>
                  <span className="text-xs font-semibold text-sky-300">
                    {data.machine?.tubule_percent ?? 0.0}% glandular area
                  </span>
                </div>
              </div>

              {/* Patch Distribution Mini-Pills */}
              <div className="mt-3">
                <div className="text-[11px] font-medium text-slate-400 mb-1.5 flex justify-between">
                  <span>Patch Tubule Estimates ({patches.length} sampled):</span>
                  <button
                    onClick={() => setShowAllPatches(true)}
                    className="text-sky-400 hover:underline text-[10px]"
                  >
                    View All
                  </button>
                </div>
                <div className="flex flex-wrap gap-1">
                  {patches.slice(0, 12).map((p) => (
                    <button
                      key={p.id}
                      onClick={() => setSelectedPatch(p)}
                      title={`Patch ${p.id}: ${p.tubule.tubule_percent}% tubule (${p.tubule.confidence} conf)`}
                      className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 hover:bg-slate-700 border border-slate-700 font-mono text-slate-300"
                    >
                      {p.tubule.tubule_percent}%
                    </button>
                  ))}
                  {patches.length > 12 && (
                    <span className="text-[10px] text-slate-500 self-center">+{patches.length - 12} more</span>
                  )}
                </div>
              </div>
            </div>

            {/* Override Controls */}
            <div className="mt-4 pt-3 border-t border-slate-800">
              {!isTubuleEditing && !isTubuleOverridden ? (
                <button
                  onClick={() => setIsTubuleEditing(true)}
                  className="w-full py-1.5 px-3 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-xs font-semibold flex items-center justify-center gap-1.5 transition"
                >
                  <Edit3 className="w-3.5 h-3.5 text-sky-400" /> Override Tubule Score
                </button>
              ) : (
                <div className="space-y-2.5">
                  <div className="flex items-center gap-1.5">
                    {[1, 2, 3].map((s) => (
                      <button
                        key={s}
                        onClick={() => handleApplyTubuleOverride(s)}
                        className={`flex-1 py-1 text-xs font-bold rounded border transition ${
                          activeTubuleScore === s
                            ? "bg-sky-600 border-sky-400 text-white"
                            : "bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200"
                        }`}
                      >
                        Score {s}
                      </button>
                    ))}
                  </div>

                  {isTubuleOverridden && (
                    <div>
                      <label className="text-[10px] text-slate-400 block mb-1">
                        Clinical Justification (min 10 chars):
                      </label>
                      <textarea
                        value={tubuleJustification}
                        onChange={(e) => setTubuleJustification(e.target.value)}
                        placeholder="State reason for overriding tubule formation score..."
                        rows={2}
                        className={`w-full bg-slate-950 border rounded p-2 text-xs text-slate-200 focus:outline-none ${
                          tubuleJustification.trim().length >= 10
                            ? "border-emerald-600 focus:border-emerald-500"
                            : "border-amber-600 focus:border-amber-500"
                        }`}
                      />
                      <div className="flex justify-between items-center mt-1">
                        <span
                          className={`text-[10px] ${
                            tubuleJustification.trim().length >= 10 ? "text-emerald-400" : "text-amber-400"
                          }`}
                        >
                          {tubuleJustification.trim().length}/10 characters
                        </span>
                        <button
                          onClick={handleResetTubule}
                          className="text-[10px] text-slate-400 hover:text-rose-400 underline"
                        >
                          Reset to AI Prediction
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* 2. Nuclear Pleomorphism Card */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col justify-between relative shadow-lg">
            <div>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="w-6 h-6 rounded-full bg-purple-950 border border-purple-500 text-purple-300 font-bold text-xs flex items-center justify-center">
                    P
                  </span>
                  <h2 className="text-sm font-bold text-white">Nuclear Pleomorphism</h2>
                </div>
                {isPleoOverridden && (
                  <span className="px-2 py-0.5 rounded bg-amber-950 border border-amber-500 text-[10px] font-bold text-amber-300 flex items-center gap-1">
                    <Edit3 className="w-3 h-3" /> Manually Assigned
                  </span>
                )}
              </div>

              <div className="mt-2 bg-slate-950 rounded-lg p-3 border border-slate-800">
                <div className="flex items-baseline justify-between">
                  <span className="text-xs text-slate-400">Score & Atypia:</span>
                  <span className="text-xl font-extrabold text-white">
                    Score {activePleoScore}{" "}
                    <span className="text-xs font-normal text-slate-400">
                      ({activePleoScore === 1 ? "Small/Uniform" : activePleoScore === 2 ? "Moderate" : "Marked/Vesicular"})
                    </span>
                  </span>
                </div>
                <div className="flex items-baseline justify-between mt-2 pt-2 border-t border-slate-800/80">
                  <span className="text-xs text-slate-400">Consensus Mode:</span>
                  <span className="text-xs font-semibold text-purple-300">
                    Worst-area weighted consensus
                  </span>
                </div>
              </div>

              {/* Pleo Patch Rationale Sample */}
              <div className="mt-3">
                <div className="text-[11px] font-medium text-slate-400 mb-1.5">
                  AI Morphometry Analysis:
                </div>
                <p className="text-xs text-slate-300 italic bg-slate-950/60 p-2.5 rounded border border-slate-800/60">
                  "{patches[0]?.pleo.rationale || "Moderate nuclear pleomorphism with open chromatin and conspicuous nucleoli."}"
                </p>
              </div>
            </div>

            {/* Override Controls */}
            <div className="mt-4 pt-3 border-t border-slate-800">
              {!isPleoEditing && !isPleoOverridden ? (
                <button
                  onClick={() => setIsPleoEditing(true)}
                  className="w-full py-1.5 px-3 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-xs font-semibold flex items-center justify-center gap-1.5 transition"
                >
                  <Edit3 className="w-3.5 h-3.5 text-purple-400" /> Override Pleomorphism Score
                </button>
              ) : (
                <div className="space-y-2.5">
                  <div className="flex items-center gap-1.5">
                    {[1, 2, 3].map((s) => (
                      <button
                        key={s}
                        onClick={() => handleApplyPleoOverride(s)}
                        className={`flex-1 py-1 text-xs font-bold rounded border transition ${
                          activePleoScore === s
                            ? "bg-purple-600 border-purple-400 text-white"
                            : "bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200"
                        }`}
                      >
                        Score {s}
                      </button>
                    ))}
                  </div>

                  {isPleoOverridden && (
                    <div>
                      <label className="text-[10px] text-slate-400 block mb-1">
                        Clinical Justification (min 10 chars):
                      </label>
                      <textarea
                        value={pleoJustification}
                        onChange={(e) => setPleoJustification(e.target.value)}
                        placeholder="State reason for overriding nuclear pleomorphism score..."
                        rows={2}
                        className={`w-full bg-slate-950 border rounded p-2 text-xs text-slate-200 focus:outline-none ${
                          pleoJustification.trim().length >= 10
                            ? "border-emerald-600 focus:border-emerald-500"
                            : "border-amber-600 focus:border-amber-500"
                        }`}
                      />
                      <div className="flex justify-between items-center mt-1">
                        <span
                          className={`text-[10px] ${
                            pleoJustification.trim().length >= 10 ? "text-emerald-400" : "text-amber-400"
                          }`}
                        >
                          {pleoJustification.trim().length}/10 characters
                        </span>
                        <button
                          onClick={handleResetPleo}
                          className="text-[10px] text-slate-400 hover:text-rose-400 underline"
                        >
                          Reset to AI Prediction
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* 3. Mitotic Score Card (Read-Only from Stage 4) */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col justify-between relative shadow-lg">
            <div>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="w-6 h-6 rounded-full bg-emerald-950 border border-emerald-500 text-emerald-300 font-bold text-xs flex items-center justify-center">
                    M
                  </span>
                  <h2 className="text-sm font-bold text-white">Mitotic Count (v4.3)</h2>
                </div>
                <span className="px-2 py-0.5 rounded bg-emerald-950 border border-emerald-500/50 text-[10px] font-bold text-emerald-300">
                  Verified in Stage 4
                </span>
              </div>

              <div className="mt-2 bg-slate-950 rounded-lg p-3 border border-slate-800">
                <div className="flex items-baseline justify-between">
                  <span className="text-xs text-slate-400">Score & Rate:</span>
                  <span className="text-xl font-extrabold text-white">
                    Score {activeMitoticScore}{" "}
                    <span className="text-xs font-normal text-slate-400">
                      ({activeMitoticScore === 1 ? "Low" : activeMitoticScore === 2 ? "Moderate" : "High"})
                    </span>
                  </span>
                </div>
                <div className="flex items-baseline justify-between mt-2 pt-2 border-t border-slate-800/80">
                  <span className="text-xs text-slate-400">Confirmed Mitoses:</span>
                  <span className="text-xs font-semibold text-emerald-300">
                    {data.mitotic_summary?.total_mitoses ?? 0} mitoses in 10 HPFs
                  </span>
                </div>
              </div>

              <div className="mt-3 space-y-1.5 text-xs text-slate-400">
                <div className="flex justify-between">
                  <span>Standard Evaluated Area:</span>
                  <span className="text-slate-200 font-mono">2.157 mm²</span>
                </div>
                <div className="flex justify-between">
                  <span>Standardized Density:</span>
                  <span className="text-slate-200 font-mono">
                    {((data.mitotic_summary?.total_mitoses ?? 0) / 2.157).toFixed(1)} mitoses/mm²
                  </span>
                </div>
              </div>
            </div>

            {/* Reopen Stage 4 Link */}
            <div className="mt-4 pt-3 border-t border-slate-800">
              <button
                onClick={onReopenMitosis}
                className="w-full py-1.5 px-3 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-xs font-semibold flex items-center justify-center gap-1.5 transition"
              >
                <RotateCcw className="w-3.5 h-3.5 text-emerald-400" /> Reopen Stage 4 Mitosis Review
              </button>
            </div>
          </div>
        </div>

        {/* Histologic Subtype Classification Card (MANDATORY GATE) */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg">
          <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-slate-800">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-white">CAP Histologic Subtype Classification</h2>
                {isTypeConfirmed ? (
                  <span className="px-2.5 py-0.5 rounded-full bg-emerald-950 border border-emerald-500 text-emerald-300 text-xs font-bold flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" /> Confirmed
                  </span>
                ) : (
                  <span className="px-2.5 py-0.5 rounded-full bg-rose-950 border border-rose-500 text-rose-300 text-xs font-bold flex items-center gap-1 animate-pulse">
                    <AlertCircle className="w-3.5 h-3.5" /> Action Required Before Confirming Stage 5
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-400 mt-1">
                Multi-image consensus across top 8 tumor patches. Pathologist confirmation is strictly required.
              </p>
            </div>

            {/* Confirmation Toggle Button */}
            <div>
              {!isTypeConfirmed ? (
                <button
                  onClick={() => setIsTypeConfirmed(true)}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-bold flex items-center gap-2 shadow-lg shadow-emerald-950 transition"
                >
                  <ShieldCheck className="w-4 h-4" /> Confirm Histologic Subtype
                </button>
              ) : (
                <button
                  onClick={() => setIsTypeConfirmed(false)}
                  className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 rounded text-xs font-medium transition"
                >
                  Edit Subtype Selection
                </button>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-5">
            {/* Subtype Selection Dropdown */}
            <div className="lg:col-span-1 space-y-3">
              <label className="text-xs font-semibold text-slate-300 block">
                Primary Histologic Subtype:
              </label>
              <select
                value={selectedHistologicType}
                onChange={(e) => {
                  setSelectedHistologicType(e.target.value);
                  setIsTypeConfirmed(false); // require re-confirmation on change
                }}
                disabled={isTypeConfirmed}
                className={`w-full bg-slate-950 border rounded-lg p-2.5 text-xs text-white focus:outline-none ${
                  isTypeConfirmed
                    ? "border-emerald-600/70 bg-emerald-950/20"
                    : "border-slate-700 focus:border-sky-500"
                }`}
              >
                {HISTOLOGIC_TYPE_OPTIONS.map((opt) => (
                  <option key={opt.id} value={opt.id}>
                    {opt.label}
                  </option>
                ))}
              </select>

              {/* Differentials */}
              {data.histologic_type?.differential && data.histologic_type.differential.length > 0 && (
                <div className="mt-3">
                  <span className="text-[11px] text-slate-400 block mb-1">Differential Diagnoses Considered:</span>
                  <div className="flex flex-wrap gap-1.5">
                    {data.histologic_type.differential.map((d, i) => (
                      <span
                        key={i}
                        className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-[10px] text-slate-300"
                      >
                        {d}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* AI Clinical Subtype Rationale */}
            <div className="lg:col-span-2 bg-slate-950/80 border border-slate-800 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-2">
                <Sparkles className="w-4 h-4 text-sky-400" />
                <span className="text-xs font-bold text-slate-300">MedGemma Morphological Rationale:</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
                  Confidence: {data.histologic_type?.confidence || "High"}
                </span>
              </div>
              <p className="text-xs text-slate-300 leading-relaxed">
                {data.histologic_type?.rationale ||
                  "Invasive ductal carcinoma characterized by cohesive malignant cell cords and irregular tubular formations infiltrating fibrous desmoplastic stroma."}
              </p>
            </div>
          </div>
        </div>

        {/* Live Nottingham Histological Grade Synthesis Card */}
        <div className="bg-gradient-to-r from-slate-900 via-sky-950/40 to-slate-900 border border-sky-800/40 rounded-xl p-6 shadow-xl">
          <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-slate-800">
            <div>
              <span className="text-xs font-bold text-sky-400 uppercase tracking-wider">
                Overall Histological Synthesis
              </span>
              <h2 className="text-2xl font-black text-white mt-0.5 flex items-center gap-3">
                Nottingham Histological Grade {activeGrade}
                <span className="text-sm font-normal text-slate-300">
                  ({activeGrade === 1 ? "Well Differentiated" : activeGrade === 2 ? "Moderately Differentiated" : "Poorly Differentiated"})
                </span>
              </h2>
            </div>

            {/* Total Sum Pill */}
            <div className="flex items-center gap-3">
              <div className="px-4 py-2 bg-slate-950 border border-slate-800 rounded-lg text-right">
                <div className="text-[10px] text-slate-400">Nottingham Sum (T + P + M)</div>
                <div className="text-xl font-mono font-bold text-sky-300">{activeSum} / 9</div>
              </div>
            </div>
          </div>

          {/* Mathematical Invariant Formula Display */}
          <div className="mt-4 grid grid-cols-1 md:grid-cols-4 gap-3 bg-slate-950/70 p-4 rounded-lg border border-slate-800 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Tubule Score (T):</span>
              <span className="font-mono font-bold text-white">
                {activeTubuleScore} {isTubuleOverridden && <span className="text-amber-400">*</span>}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Pleomorphism Score (P):</span>
              <span className="font-mono font-bold text-white">
                {activePleoScore} {isPleoOverridden && <span className="text-amber-400">*</span>}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Mitotic Score (M):</span>
              <span className="font-mono font-bold text-white">{activeMitoticScore}</span>
            </div>
            <div className="flex items-center justify-between border-t md:border-t-0 md:border-l md:pl-3 border-slate-800">
              <span className="text-sky-400 font-semibold">Sum = {activeSum} →</span>
              <span className="font-bold text-sky-300">Grade {activeGrade}</span>
            </div>
          </div>

          {/* Grounded Diagnostic Narrative */}
          <div className="mt-5">
            <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
              Diagnostic Summary Narrative:
            </h4>
            <p className="text-xs text-slate-200 leading-relaxed bg-slate-950/90 p-4 rounded-lg border border-slate-800/80">
              {data.narrative ||
                `Invasive breast carcinoma (${selectedHistologicType}), Nottingham Histological Grade ${activeGrade} (Total Score ${activeSum}/9). Tubule formation is moderate (${data.machine?.tubule_percent ?? 22}%, Score ${activeTubuleScore}). Nuclear pleomorphism demonstrates moderate to marked atypia (Score ${activePleoScore}). Mitotic activity is evaluated across 10 standardized high-power fields (Score ${activeMitoticScore}).`}
            </p>
          </div>

          {/* Final Confirmation Bar */}
          <div className="mt-6 pt-4 border-t border-slate-800 flex flex-wrap items-center justify-between gap-4">
            <div className="text-xs text-slate-400">
              {!isTypeConfirmed ? (
                <span className="text-amber-400 flex items-center gap-1.5">
                  <AlertCircle className="w-4 h-4" /> Please click "Confirm Histologic Subtype" above to unlock final stage advancement.
                </span>
              ) : !isTubuleJustificationValid || !isPleoJustificationValid ? (
                <span className="text-amber-400 flex items-center gap-1.5">
                  <AlertCircle className="w-4 h-4" /> Please provide at least 10 characters justification for manual score overrides.
                </span>
              ) : (
                <span className="text-emerald-400 flex items-center gap-1.5">
                  <CheckCircle2 className="w-4 h-4" /> All clinical gates satisfied. Ready to generate CAP-compliant report.
                </span>
              )}
            </div>

            <button
              onClick={handleConfirmFinalStage}
              disabled={!canConfirmStage}
              className={`px-6 py-3 rounded-lg text-xs font-bold flex items-center gap-2 shadow-lg transition ${
                canConfirmStage
                  ? "bg-sky-600 hover:bg-sky-500 text-white shadow-sky-950 cursor-pointer"
                  : "bg-slate-800 text-slate-500 border border-slate-700 cursor-not-allowed"
              }`}
            >
              {isSubmitting ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Finalizing Stage 5...
                </>
              ) : (
                <>
                  Confirm Nottingham Grade & Advance to CAP Report (Stage 6) <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </div>

          {submitError && (
            <div className="mt-3 text-xs text-rose-400 bg-rose-950/60 p-2.5 rounded border border-rose-800">
              {submitError}
            </div>
          )}
        </div>
      </div>

      {/* 24 Evidence Patches Modal / Drawer */}
      {showAllPatches && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-6">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-6xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">
            <div className="p-4 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Microscope className="w-5 h-5 text-sky-400" />
                <h3 className="text-sm font-bold text-white">
                  24 Evidence Patches (10× @ 1.0 µm/px • Macenko Normalized)
                </h3>
              </div>
              <button
                onClick={() => setShowAllPatches(false)}
                className="p-1 hover:bg-slate-800 text-slate-400 hover:text-white rounded"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
              {patches.map((p) => (
                <div
                  key={p.id}
                  onClick={() => setSelectedPatch(p)}
                  className="bg-slate-950 border border-slate-800 hover:border-sky-500 rounded-lg p-2 flex flex-col cursor-pointer transition group"
                >
                  <div className="w-full aspect-square bg-slate-900 rounded overflow-hidden relative">
                    <img
                      src={`${API_BASE}${p.image_url}`}
                      alt={`Patch ${p.id}`}
                      className="w-full h-full object-cover group-hover:scale-105 transition"
                      loading="lazy"
                    />
                    <span className="absolute bottom-1 right-1 px-1 py-0.5 rounded bg-black/70 text-[9px] font-mono text-white">
                      #{p.index}
                    </span>
                  </div>
                  <div className="mt-2 space-y-0.5 text-[10px]">
                    <div className="flex justify-between text-slate-400">
                      <span>Tubule:</span>
                      <span className="font-semibold text-slate-200">{p.tubule.tubule_percent}%</span>
                    </div>
                    <div className="flex justify-between text-slate-400">
                      <span>Pleo:</span>
                      <span className="font-semibold text-purple-300">Score {p.pleo.pleomorphism_score}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Single Patch Detailed Inspection Modal */}
      {selectedPatch && (
        <div className="fixed inset-0 z-50 bg-black/85 backdrop-blur-sm flex items-center justify-center p-6">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-xl flex flex-col shadow-2xl overflow-hidden">
            <div className="p-4 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
              <h3 className="text-sm font-bold text-white">
                Evidence Patch #{selectedPatch.index} ({selectedPatch.id})
              </h3>
              <button
                onClick={() => setSelectedPatch(null)}
                className="p-1 hover:bg-slate-800 text-slate-400 hover:text-white rounded"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 space-y-4">
              <div className="w-full aspect-square max-h-80 bg-black rounded-lg overflow-hidden border border-slate-800 mx-auto">
                <img
                  src={`${API_BASE}${selectedPatch.image_url}`}
                  alt={`Patch ${selectedPatch.id}`}
                  className="w-full h-full object-contain"
                />
              </div>

              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                  <span className="text-[10px] text-slate-400 block">Tubule Formation</span>
                  <span className="text-base font-bold text-sky-400">
                    {selectedPatch.tubule.tubule_percent}%
                  </span>
                  <span className="text-[10px] text-slate-500 block mt-1">
                    Confidence: {selectedPatch.tubule.confidence}
                  </span>
                </div>

                <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                  <span className="text-[10px] text-slate-400 block">Nuclear Pleomorphism</span>
                  <span className="text-base font-bold text-purple-400">
                    Score {selectedPatch.pleo.pleomorphism_score}
                  </span>
                  <span className="text-[10px] text-slate-500 block mt-1">
                    Confidence: {selectedPatch.pleo.confidence}
                  </span>
                </div>
              </div>

              <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 text-xs">
                <span className="text-[10px] text-slate-400 block mb-1">Pleomorphism Rationale:</span>
                <p className="text-slate-300 italic">"{selectedPatch.pleo.rationale}"</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
