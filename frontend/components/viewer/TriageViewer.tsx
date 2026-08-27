"use client";

import React, { useEffect, useState } from "react";
import { 
  Flame, 
  CheckCircle2, 
  XCircle, 
  Plus, 
  Sliders, 
  ShieldAlert, 
  ArrowRight, 
  Info,
  Loader2,
  Trash2
} from "lucide-react";
import { API_BASE } from "@/lib/api";
import { OpenSeadragonViewer } from "./OpenSeadragonViewer";

interface HotspotItem {
  id: string;
  polygon_um: number[][];
  area_mm2: number;
  prob_mean: number;
  prob_max: number;
  source: string;
  excluded: boolean;
  exclude_reason?: string | null;
}

interface TriageData {
  case_id: string;
  stage_execution_id: string;
  status: string;
  heatmap_png_uri: string | null;
  prob_grid_uri: string | null;
  grid: {
    origin_um: number[];
    stride_um: number;
    nx: number;
    ny: number;
  };
  machine_hotspots: HotspotItem[];
  effective_hotspots: HotspotItem[];
  review_edits: any[];
}

export function TriageViewer({ caseId }: { caseId: string }) {
  const [data, setData] = useState<TriageData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const [heatmapOpacity, setHeatmapOpacity] = useState<number>(0.6);
  const [showHeatmap, setShowHeatmap] = useState<boolean>(true);
  const [hotspotsList, setHotspotsList] = useState<HotspotItem[]>([]);
  const [noInvasiveTumor, setNoInvasiveTumor] = useState<boolean>(false);
  const [excludeReasonInput, setExcludeReasonInput] = useState<{ [id: string]: string }>({});

  const fetchTriageData = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/api/v1/stages/triage/${caseId}`);
      if (!res.ok) {
        throw new Error(`Failed to fetch triage data (Status: ${res.status})`);
      }
      const json = await res.json();
      setData(json);
      setHotspotsList(json.effective_hotspots || []);
    } catch (err: any) {
      setError(err.message || "Failed to load triage data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTriageData();
  }, [caseId]);

  const handleExcludeHotspot = (id: string) => {
    const reason = excludeReasonInput[id] || "Pathologist excluded";
    setHotspotsList((prev) =>
      prev.map((h) => (h.id === id ? { ...h, excluded: true, exclude_reason: reason } : h))
    );
  };

  const handleRestoreHotspot = (id: string) => {
    setHotspotsList((prev) =>
      prev.map((h) => (h.id === id ? { ...h, excluded: false, exclude_reason: null } : h))
    );
  };

  const handleDeleteHotspot = (id: string) => {
    setHotspotsList((prev) => prev.filter((h) => h.id !== id));
  };

  const handleAddUserHotspot = () => {
    const newId = `user_${Date.now().toString().slice(-4)}`;
    const newHs: HotspotItem = {
      id: newId,
      polygon_um: [[1000, 1000], [2000, 1000], [2000, 2000], [1000, 2000]],
      area_mm2: 1.0,
      prob_mean: 1.0,
      prob_max: 1.0,
      source: "pathologist_added",
      excluded: false
    };
    setHotspotsList((prev) => [...prev, newHs]);
  };

  const handleSaveDraftEdits = async () => {
    try {
      setSubmitting(true);
      const edits = hotspotsList.map((h) => {
        if (h.excluded) {
          return { op: "exclude", id: h.id, reason: h.exclude_reason };
        } else if (h.source === "pathologist_added") {
          return { op: "add", id: h.id, polygon_um: h.polygon_um, area_mm2: h.area_mm2 };
        }
        return { op: "modify", id: h.id, polygon_um: h.polygon_um };
      });

      const res = await fetch(`${API_BASE}/api/v1/stages/triage/edits`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case_id: caseId, edits })
      });

      if (!res.ok) {
        throw new Error("Failed to save draft edits");
      }
    } catch (err: any) {
      alert(`Error saving edits: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const handleConfirmStage = async () => {
    try {
      setSubmitting(true);
      await handleSaveDraftEdits();

      const res = await fetch(`${API_BASE}/api/v1/stages/triage/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          case_id: caseId,
          no_invasive_tumor: noInvasiveTumor,
          reviewed_by: "pathologist_01"
        })
      });

      if (!res.ok) {
        throw new Error("Failed to confirm stage execution");
      }

      const json = await res.json();
      alert(`Hotspot Triage Confirmed! Queued next stage: ${json.next_stage_queued}`);
      window.location.reload();
    } catch (err: any) {
      alert(`Error confirming triage: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const activeHotspotsCount = hotspotsList.filter((h) => !h.excluded).length;
  const totalAreaMm2 = hotspotsList
    .filter((h) => !h.excluded)
    .reduce((sum, h) => sum + (h.area_mm2 || 0), 0);

  if (loading) {
    return (
      <div className="w-full h-full bg-slate-950 flex flex-col items-center justify-center text-slate-400">
        <Loader2 className="w-8 h-8 animate-spin text-sky-500 mb-2" />
        <p className="text-sm font-medium">Extracting 10× Path Foundation Tumor Hotspots...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="w-full h-full bg-slate-950 flex flex-col items-center justify-center text-rose-400">
        <ShieldAlert className="w-10 h-10 mb-2" />
        <p className="text-sm font-semibold">{error}</p>
      </div>
    );
  }

  return (
    <div className="w-full h-full flex bg-slate-950 overflow-hidden">
      {/* Left Main Viewport */}
      <div className="flex-1 relative">
        <OpenSeadragonViewer caseId={caseId} />

        {/* Heatmap Overlay Opacity Control floating toolbar */}
        <div className="absolute top-4 left-4 z-20 bg-slate-900/90 backdrop-blur border border-slate-800 rounded-lg p-3 shadow-xl flex items-center space-x-3">
          <div className="flex items-center space-x-2 text-xs font-semibold text-slate-200">
            <Flame className="w-4 h-4 text-amber-400" />
            <span>Tumor Probability Heatmap</span>
          </div>

          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              checked={showHeatmap}
              onChange={(e) => setShowHeatmap(e.target.checked)}
              className="sr-only peer"
            />
            <div className="w-9 h-5 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-sky-600"></div>
          </label>

          {showHeatmap && (
            <div className="flex items-center space-x-2 border-l border-slate-800 pl-3">
              <Sliders className="w-3.5 h-3.5 text-slate-400" />
              <input
                type="range"
                min="0.1"
                max="1.0"
                step="0.05"
                value={heatmapOpacity}
                onChange={(e) => setHeatmapOpacity(parseFloat(e.target.value))}
                className="w-20 accent-sky-500 cursor-pointer"
              />
              <span className="text-[11px] font-mono text-slate-400">
                {Math.round(heatmapOpacity * 100)}%
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Right Pathologist Review Sidebar Rail */}
      <div className="w-96 border-l border-slate-800 bg-slate-900 flex flex-col h-full shadow-2xl z-20">
        {/* Header */}
        <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/50">
          <div>
            <h2 className="text-sm font-bold text-slate-100 flex items-center space-x-2">
              <Flame className="w-4 h-4 text-amber-500" />
              <span>Stage 3: Hotspot Triage</span>
            </h2>
            <p className="text-[11px] text-slate-400 mt-0.5">Path Foundation 10× Tumor Front Screening</p>
          </div>
          <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
            data?.status === "confirmed" ? "bg-emerald-950 text-emerald-400 border border-emerald-800" : "bg-amber-950 text-amber-400 border border-amber-800"
          }`}>
            {data?.status}
          </span>
        </div>

        {/* Stats Summary Panel */}
        <div className="p-4 bg-slate-950/60 border-b border-slate-800 grid grid-cols-2 gap-3">
          <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
            <div className="text-[10px] font-semibold uppercase text-slate-400">Active Hotspots</div>
            <div className="text-lg font-bold font-mono text-sky-400">{activeHotspotsCount}</div>
          </div>
          <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
            <div className="text-[10px] font-semibold uppercase text-slate-400">Total Tumor Area</div>
            <div className="text-lg font-bold font-mono text-amber-400">{totalAreaMm2.toFixed(2)} mm²</div>
          </div>
        </div>

        {/* Hotspots List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-300 uppercase tracking-wider">Proposed Tumor ROIs</span>
            <button
              onClick={handleAddUserHotspot}
              className="px-2 py-1 bg-sky-600/20 hover:bg-sky-600/40 text-sky-400 border border-sky-600/40 rounded text-xs font-semibold flex items-center space-x-1 transition"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Add ROI</span>
            </button>
          </div>

          {hotspotsList.length === 0 ? (
            <div className="p-4 border border-dashed border-slate-800 rounded-lg text-center text-xs text-slate-500">
              No tumor hotspots extracted.
            </div>
          ) : (
            hotspotsList.map((hs) => (
              <div
                key={hs.id}
                className={`p-3 rounded-lg border transition ${
                  hs.excluded
                    ? "bg-slate-950/40 border-slate-800/60 opacity-60"
                    : "bg-slate-900/90 border-slate-800 hover:border-slate-700"
                }`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center space-x-2">
                    <span className="font-mono text-xs font-bold text-sky-400">{hs.id}</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 font-mono">
                      {hs.source}
                    </span>
                  </div>

                  {hs.excluded ? (
                    <button
                      onClick={() => handleRestoreHotspot(hs.id)}
                      className="text-xs text-emerald-400 hover:underline font-semibold"
                    >
                      Restore
                    </button>
                  ) : (
                    <div className="flex items-center space-x-1">
                      <button
                        onClick={() => handleDeleteHotspot(hs.id)}
                        className="p-1 hover:bg-slate-800 text-slate-500 hover:text-rose-400 rounded"
                        title="Delete Hotspot"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}
                </div>

                <div className="grid grid-cols-3 gap-1 text-[11px] font-mono text-slate-400 mb-2">
                  <div>Area: <span className="text-slate-200">{hs.area_mm2} mm²</span></div>
                  <div>Mean: <span className="text-slate-200">{hs.prob_mean}</span></div>
                  <div>Max: <span className="text-slate-200">{hs.prob_max}</span></div>
                </div>

                {!hs.excluded && (
                  <div className="flex items-center space-x-2 pt-2 border-t border-slate-800/80">
                    <input
                      type="text"
                      placeholder="Reason for exclusion..."
                      value={excludeReasonInput[hs.id] || ""}
                      onChange={(e) => setExcludeReasonInput({ ...excludeReasonInput, [hs.id]: e.target.value })}
                      className="flex-1 bg-slate-950 border border-slate-800 text-xs px-2 py-1 rounded text-slate-300 placeholder-slate-600 focus:outline-none focus:border-slate-700"
                    />
                    <button
                      onClick={() => handleExcludeHotspot(hs.id)}
                      className="px-2 py-1 bg-rose-950/60 hover:bg-rose-900 text-rose-300 border border-rose-800/60 rounded text-xs font-semibold transition"
                    >
                      Exclude
                    </button>
                  </div>
                )}

                {hs.excluded && hs.exclude_reason && (
                  <div className="text-[11px] text-amber-400 italic mt-1">
                    Excluded: {hs.exclude_reason}
                  </div>
                )}
              </div>
            ))
          )}
        </div>

        {/* Footer Confirmation Gate */}
        <div className="p-4 border-t border-slate-800 bg-slate-950/80 space-y-3">
          <label className="flex items-start space-x-2 cursor-pointer">
            <input
              type="checkbox"
              checked={noInvasiveTumor}
              onChange={(e) => setNoInvasiveTumor(e.target.checked)}
              className="mt-0.5 accent-rose-500 rounded cursor-pointer"
            />
            <span className="text-xs text-slate-300">
              No invasive tumor identified (route directly to benign report queue)
            </span>
          </label>

          <button
            onClick={handleConfirmStage}
            disabled={submitting || (activeHotspotsCount === 0 && !noInvasiveTumor)}
            className={`w-full py-2.5 rounded-lg text-xs font-bold flex items-center justify-center space-x-2 shadow-lg transition ${
              activeHotspotsCount > 0 || noInvasiveTumor
                ? "bg-sky-600 hover:bg-sky-500 text-white shadow-sky-600/20"
                : "bg-slate-800 text-slate-500 cursor-not-allowed"
            }`}
          >
            {submitting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <>
                <span>Confirm Hotspots & Continue</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
