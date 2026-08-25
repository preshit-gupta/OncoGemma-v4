"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, RefreshCcw, Info, X, Microscope, AlertTriangle } from "lucide-react";
import { fetchCaseDetail, CaseDetail, retryStage } from "@/lib/api";
import { formatISTDateTime } from "@/lib/utils";
import { StageRail } from "@/components/viewer/StageRail";
import { OpenSeadragonViewer } from "@/components/viewer/OpenSeadragonViewer";

export default function CaseWorkspacePage({ params }: { params: { id: string } }) {
  const caseId = params.id;

  const [caseDetail, setCaseDetail] = useState<CaseDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeStage, setActiveStage] = useState<string>("ingest");
  const [showSlideDetails, setShowSlideDetails] = useState<boolean>(false);

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
    const interval = setInterval(loadData, 2500);
    return () => clearInterval(interval);
  }, [caseId]);

  const slide = caseDetail?.slides?.[0];
  const ingestStage = caseDetail?.stages?.find((s) => s.stage === "ingest");
  const isIngestDone = ingestStage?.status === "completed" || ingestStage?.status === "done";
  const isIngestRunning = ingestStage?.status === "running" || ingestStage?.status === "queued" || !ingestStage;
  const isIngestFailed = ingestStage?.status === "failed";

  const handleRetryIngest = async () => {
    try {
      await retryStage(caseId, "ingest");
      await loadData();
    } catch (err) {
      console.error(err);
      alert("Failed to retry ingest stage");
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-slate-900">
      {/* Top Workspace Bar */}
      <div className="bg-slate-900 border-b border-slate-800 text-white px-4 py-2 flex items-center justify-between z-20">
        <div className="flex items-center space-x-3">
          <Link
            href="/cases"
            className="p-1.5 hover:bg-slate-800 rounded-lg text-slate-400 hover:text-white transition"
            title="Back to Cases"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div className="h-4 w-[1px] bg-slate-700" />
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-sm font-semibold tracking-tight">
                Case #{caseId.substring(0, 8)}
              </h1>
              <span className="text-[10px] bg-sky-900/60 border border-sky-700 text-sky-300 px-2 py-0.5 rounded font-mono font-medium">
                Nottingham Grading
              </span>
            </div>
            <div className="text-[11px] text-slate-400 flex items-center space-x-3 mt-0.5">
              <span>MPP: {slide?.mpp_x || 0.25} µm/px</span>
              <span>•</span>
              <span>Base Mag: {slide?.base_mag || 40}x</span>
              <span>•</span>
              <span>Created: {formatISTDateTime(caseDetail?.created_at)}</span>
            </div>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={() => setShowSlideDetails(!showSlideDetails)}
            className="p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg transition text-xs flex items-center space-x-1.5 border border-slate-700"
          >
            <Info className="w-3.5 h-3.5 text-sky-400" />
            <span>Slide Details</span>
          </button>

          <button
            onClick={loadData}
            className="p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg transition text-xs flex items-center space-x-1 border border-slate-700"
            title="Refresh Status"
          >
            <RefreshCcw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Main Workspace Body */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* Left Stage Rail */}
        <StageRail
          caseId={caseId}
          stages={caseDetail?.stages || []}
          activeStage={activeStage}
          onSelectStage={setActiveStage}
          onRefresh={loadData}
        />

        {/* Center Digital Slide Viewer */}
        <div className="flex-1 relative overflow-hidden bg-slate-950">
          {loading ? (
            <div className="flex items-center justify-center h-full text-slate-400 text-sm">
              Loading slide workspace...
            </div>
          ) : isIngestRunning ? (
            <div className="flex flex-col items-center justify-center h-full text-slate-300 space-y-4 bg-slate-950 p-8">
              <div className="relative w-16 h-16 flex items-center justify-center">
                <div className="absolute inset-0 rounded-full border-4 border-sky-500/20 border-t-sky-500 animate-spin" />
                <Microscope className="w-8 h-8 text-sky-400" />
              </div>
              <div className="text-center max-w-md">
                <h3 className="text-base font-bold text-white tracking-tight">Processing Whole-Slide Image</h3>
                <p className="text-xs text-slate-400 mt-1.5 leading-relaxed">
                  Extracting WSI metadata, streaming raw slide to Cloud Storage (<span className="font-mono text-sky-400">gs://oncogemma-dev-raw</span>), and generating multi-resolution pyramid tiles...
                </p>
                <div className="mt-4 inline-flex items-center space-x-2 text-[11px] font-mono text-sky-400 bg-sky-950/60 border border-sky-800/80 px-3 py-1.5 rounded-full">
                  <span className="w-2 h-2 rounded-full bg-sky-400 animate-ping" />
                  <span>Pipeline Worker Active</span>
                </div>
              </div>
            </div>
          ) : isIngestFailed ? (
            <div className="flex flex-col items-center justify-center h-full text-slate-300 space-y-4 bg-slate-950 p-8">
              <AlertTriangle className="w-12 h-12 text-rose-500" />
              <div className="text-center max-w-md">
                <h3 className="text-base font-bold text-white">Slide Ingest Failed</h3>
                <p className="text-xs text-slate-400 mt-1">
                  {ingestStage?.error || "Failed to process slide file during pyramid tile generation."}
                </p>
                <button
                  onClick={handleRetryIngest}
                  className="mt-4 bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold px-4 py-2 rounded-lg transition shadow"
                >
                  Retry Ingest Stage
                </button>
              </div>
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

        {/* Slide Technical Details Popover/Modal */}
        {showSlideDetails && (
          <div className="absolute top-4 left-72 bg-slate-900/95 backdrop-blur border border-slate-700 text-white rounded-xl shadow-2xl p-4 w-96 z-30 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <h3 className="text-xs font-bold text-sky-400 uppercase tracking-wider flex items-center space-x-1.5">
                <Info className="w-4 h-4" />
                <span>Technical Slide Details</span>
              </h3>
              <button
                onClick={() => setShowSlideDetails(false)}
                className="p-1 hover:bg-slate-800 text-slate-400 hover:text-white rounded transition"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-2 text-xs">
              <div className="flex justify-between border-b border-slate-800/50 py-1">
                <span className="text-slate-400">Slide ID:</span>
                <span className="font-mono text-slate-200">{slide?.id || "N/A"}</span>
              </div>
              <div className="flex justify-between border-b border-slate-800/50 py-1">
                <span className="text-slate-400">Original Format:</span>
                <span className="font-mono text-slate-200 uppercase">{slide?.format || "SVS"}</span>
              </div>
              <div className="flex justify-between border-b border-slate-800/50 py-1">
                <span className="text-slate-400">Dimensions:</span>
                <span className="font-mono text-slate-200">{slide?.width_px || "N/A"} x {slide?.height_px || "N/A"} px</span>
              </div>
              <div className="flex justify-between border-b border-slate-800/50 py-1">
                <span className="text-slate-400">Scanner Vendor:</span>
                <span className="font-mono text-slate-200 capitalize">{slide?.scanner || "Generic"}</span>
              </div>
              <div className="flex justify-between border-b border-slate-800/50 py-1">
                <span className="text-slate-400">SHA256 Checksum:</span>
                <span className="font-mono text-[10px] text-slate-300 truncate max-w-[180px]" title={slide?.checksum_sha256}>
                  {slide?.checksum_sha256 || "N/A"}
                </span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-slate-400">Label Stripped At:</span>
                <span className="font-mono text-slate-200">{formatISTDateTime(slide?.label_stripped_at)}</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
