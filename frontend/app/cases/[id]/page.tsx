"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, RefreshCcw } from "lucide-react";
import { fetchCaseDetail, CaseDetail } from "@/lib/api";
import { StageRail } from "@/components/viewer/StageRail";
import { OpenSeadragonViewer } from "@/components/viewer/OpenSeadragonViewer";

export default function CaseWorkspacePage({ params }: { params: { id: string } }) {
  const caseId = params.id;

  const [caseDetail, setCaseDetail] = useState<CaseDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeStage, setActiveStage] = useState<string>("ingest");

  const loadData = async () => {
    try {
      const data = await fetchCaseDetail(caseId);
      setCaseDetail(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    // Poll every 3 seconds for stage execution status updates
    const interval = setInterval(loadData, 3000);
    return () => clearInterval(interval);
  }, [caseId]);

  const slide = caseDetail?.slides?.[0];

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-slate-900">
      {/* Top Workspace Bar */}
      <div className="bg-slate-900 border-b border-slate-800 text-white px-4 py-2 flex items-center justify-between z-20">
        <div className="flex items-center space-x-3">
          <Link
            href="/cases"
            className="p-1.5 hover:bg-slate-800 rounded-lg text-slate-400 hover:text-white transition"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div className="h-4 w-[1px] bg-slate-700" />
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-sm font-semibold tracking-tight">
                Case #{caseId.substring(0, 8)}
              </h1>
              <span className="text-[10px] bg-slate-800 text-slate-300 px-2 py-0.5 rounded font-mono">
                {slide?.format?.toUpperCase() || "WSI"}
              </span>
            </div>
            <div className="text-[11px] text-slate-400 flex items-center space-x-3">
              <span>MPP: {slide?.mpp_x || 0.25} µm/px</span>
              <span>Mag: {slide?.base_mag || 40}x</span>
              <span>Dimensions: {slide?.width_px || "N/A"} x {slide?.height_px || "N/A"}</span>
            </div>
          </div>
        </div>

        <button
          onClick={loadData}
          className="p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg transition text-xs flex items-center space-x-1"
        >
          <RefreshCcw className="w-3.5 h-3.5" />
          <span>Refresh</span>
        </button>
      </div>

      {/* Main Workspace Body */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* Left Stage Rail */}
        <StageRail
          stages={caseDetail?.stages || []}
          activeStage={activeStage}
          onSelectStage={setActiveStage}
        />

        {/* Center Digital Slide Viewer */}
        <div className="flex-1 relative overflow-hidden bg-slate-950">
          {loading ? (
            <div className="flex items-center justify-center h-full text-slate-400 text-sm">
              Loading slide workspace...
            </div>
          ) : (
            <OpenSeadragonViewer
              caseId={caseId}
              mppX={slide?.mpp_x || 0.25}
              imageWidthPx={slide?.width_px || 100000}
              imageHeightPx={slide?.height_px || 80000}
            />
          )}
        </div>
      </div>
    </div>
  );
}
