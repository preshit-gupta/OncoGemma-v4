"use client";

import React from "react";
import { CheckCircle2, Clock, AlertTriangle, XCircle, ArrowRight, Play } from "lucide-react";

export interface StageInfo {
  id: string;
  stage: string;
  status: string;
  started_at?: string;
  completed_at?: string;
}

interface StageRailProps {
  stages: StageInfo[];
  activeStage: string;
  onSelectStage: (stageName: string) => void;
}

const STAGE_ORDER = [
  { name: "ingest", label: "v4.0 WSI Ingest" },
  { name: "preprocess", label: "v4.1 Stain & QC Gate" },
  { name: "triage", label: "v4.2 Hotspot Triage" },
  { name: "mitosis", label: "v4.3 Mitosis Counting" },
  { name: "grading", label: "v4.4 Nottingham Grade" },
  { name: "report", label: "v4.5 CAP Report" },
];

export function StageRail({ stages, activeStage, onSelectStage }: StageRailProps) {
  const getStageStatus = (stageName: string) => {
    const found = stages.find((s) => s.stage === stageName);
    return found ? found.status : "pending";
  };

  const renderStatusBadge = (status: string) => {
    switch (status) {
      case "done":
      case "confirmed":
        return <CheckCircle2 className="w-4 h-4 text-emerald-500" />;
      case "running":
        return <Play className="w-4 h-4 text-blue-500 animate-pulse" />;
      case "awaiting_review":
        return <AlertTriangle className="w-4 h-4 text-amber-500" />;
      case "queued":
        return <Clock className="w-4 h-4 text-sky-500" />;
      case "failed":
        return <XCircle className="w-4 h-4 text-rose-500" />;
      default:
        return <div className="w-2 h-2 rounded-full bg-slate-300" />;
    }
  };

  return (
    <aside className="w-64 bg-white border-r border-slate-200 flex flex-col h-full select-none">
      <div className="p-4 border-b border-slate-100 bg-slate-50">
        <h2 className="text-sm font-semibold text-slate-800 uppercase tracking-wider">
          Workflow Pipeline
        </h2>
        <p className="text-xs text-slate-500 mt-0.5">Nottingham Grade Diagnostics</p>
      </div>

      <nav className="flex-1 overflow-y-auto p-3 space-y-1">
        {STAGE_ORDER.map((st, idx) => {
          const status = getStageStatus(st.name);
          const isActive = activeStage === st.name;

          return (
            <button
              key={st.name}
              onClick={() => onSelectStage(st.name)}
              className={`w-full text-left p-3 rounded-lg border transition-all flex items-center justify-between ${
                isActive
                  ? "bg-sky-50 border-sky-300 text-sky-900 shadow-sm"
                  : "bg-white border-slate-100 hover:bg-slate-50 text-slate-700"
              }`}
            >
              <div className="flex items-center space-x-3">
                <span className="text-xs font-medium text-slate-400 w-4">{idx + 1}.</span>
                <div>
                  <div className="text-xs font-semibold">{st.label}</div>
                  <div className="text-[10px] text-slate-400 capitalize">{status}</div>
                </div>
              </div>
              <div className="flex items-center">
                {renderStatusBadge(status)}
              </div>
            </button>
          );
        })}
      </nav>

      <div className="p-3 border-t border-slate-100 bg-slate-50 text-[11px] text-slate-400">
        OncoGemma v4.0 • Pathologist Verified
      </div>
    </aside>
  );
}
