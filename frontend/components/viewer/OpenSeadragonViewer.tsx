"use client";

import React, { useEffect, useRef, useState } from "react";
import OpenSeadragon from "openseadragon";
import { ZoomIn, ZoomOut, Maximize, ChevronDown, Check, Layers, Image as ImageIcon, Info } from "lucide-react";
import { API_BASE } from "@/lib/api";

interface OpenSeadragonViewerProps {
  caseId: string;
  mppX?: number;
  mppY?: number;
  imageWidthPx?: number;
  imageHeightPx?: number;
  layer?: "orig" | "norm";
}

const ZOOM_PRESETS = [2.5, 5, 10, 20, 40];

export function OpenSeadragonViewer({
  caseId,
  mppX = 0.25,
  imageWidthPx = 2048,
  imageHeightPx = 2048,
  layer = "orig"
}: OpenSeadragonViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<OpenSeadragon.Viewer | null>(null);
  const [scaleLengthUm, setScaleLengthUm] = useState<number>(100);
  const [scalebarWidthPx, setScalebarWidthPx] = useState<number>(120);
  const [currentMag, setCurrentMag] = useState<number>(1.0);
  const [isEditingZoom, setIsEditingZoom] = useState<boolean>(false);
  const [customZoomInput, setCustomZoomInput] = useState<string>("1.0");
  const [showDropdown, setShowDropdown] = useState<boolean>(false);
  const [activeLayer, setActiveLayer] = useState<"orig" | "norm">(layer);

  const isNormFallbackToOrig = activeLayer === "norm" && currentMag > 10.0;

  useEffect(() => {
    if (!containerRef.current) return;

    if (viewerRef.current) {
      viewerRef.current.destroy();
      viewerRef.current = null;
    }

    const maxDim = Math.max(imageWidthPx, imageHeightPx);
    const maxLevel = Math.ceil(Math.log2(maxDim)) || 11;

    const tileSource: OpenSeadragon.TileSourceOptions = {
      width: imageWidthPx,
      height: imageHeightPx,
      tileSize: 256,
      tileOverlap: 0,
      minLevel: 0,
      maxLevel: maxLevel,
      getTileUrl: (level: number, x: number, y: number) => {
        // Beyond 10x level (level > maxLevel - 2), normalized pyramid falls back to original colors
        const effectiveLayer = (activeLayer === "norm" && level > maxLevel - 2) ? "orig" : activeLayer;
        return `${API_BASE}/api/v1/cases/${caseId}/tiles/${effectiveLayer}/${level}/${x}_${y}.png`;
      }
    };

    const viewer = OpenSeadragon({
      element: containerRef.current,
      prefixUrl: "https://openseadragon.github.io/openseadragon/images/",
      tileSources: tileSource,
      showNavigationControl: false,
      animationTime: 0.3,
      blendTime: 0.1,
      maxZoomPixelRatio: 4.0,
      visibilityRatio: 0.9,
      constrainDuringPan: true,
      homeFillsViewer: false
    });

    viewerRef.current = viewer;

    const updateScalebar = () => {
      if (!viewer.viewport) return;
      const zoom = viewer.viewport.getZoom(true);
      const imageZoom = viewer.viewport.viewportToImageZoom(zoom);
      
      const umPerPx = mppX / (imageZoom || 1.0);
      const targetUm = 120 * umPerPx;
      
      const niceScales = [5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000];
      const chosenScaleUm = niceScales.reduce((prev, curr) => 
        Math.abs(curr - targetUm) < Math.abs(prev - targetUm) ? curr : prev
      );

      const actualWidthPx = Math.max(30, Math.min(220, Math.round(chosenScaleUm / umPerPx)));
      
      setScaleLengthUm(chosenScaleUm);
      setScalebarWidthPx(actualWidthPx);

      const calculatedMag = imageZoom * (40.0 * 0.25 / mppX);
      setCurrentMag(calculatedMag);
      if (!isEditingZoom) {
        setCustomZoomInput(calculatedMag.toFixed(1));
      }
    };

    viewer.addHandler("open", () => {
      updateScalebar();
      if (viewer.viewport) {
        viewer.viewport.goHome(true);
      }
    });

    return () => {
      if (viewerRef.current) {
        viewerRef.current.destroy();
        viewerRef.current = null;
      }
    };
  }, [caseId, activeLayer, imageWidthPx, imageHeightPx, mppX]);

  const handleZoomIn = () => {
    if (viewerRef.current?.viewport) {
      viewerRef.current.viewport.zoomBy(1.3);
      viewerRef.current.viewport.applyConstraints();
    }
  };

  const handleZoomOut = () => {
    if (viewerRef.current?.viewport) {
      viewerRef.current.viewport.zoomBy(1 / 1.3);
      viewerRef.current.viewport.applyConstraints();
    }
  };

  const handleResetZoom = () => {
    if (viewerRef.current?.viewport) {
      viewerRef.current.viewport.goHome();
    }
  };

  const applyPower = (power: number) => {
    if (!viewerRef.current?.viewport) return;
    const targetImageZoom = power * (mppX / (40.0 * 0.25));
    const targetViewportZoom = viewerRef.current.viewport.imageToViewportZoom(targetImageZoom);
    viewerRef.current.viewport.zoomTo(targetViewportZoom);
    viewerRef.current.viewport.applyConstraints();
    setShowDropdown(false);
  };

  const handleCustomZoomSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const val = parseFloat(customZoomInput);
    if (!isNaN(val) && val > 0) {
      applyPower(val);
    }
    setIsEditingZoom(false);
  };

  return (
    <div className="relative w-full h-full bg-slate-950 flex flex-col">
      {/* Top Floating Controls Bar */}
      <div className="absolute top-4 left-4 right-4 z-10 flex items-center justify-between pointer-events-none">
        {/* Layer Selector Bar */}
        <div className="pointer-events-auto bg-slate-900/90 backdrop-blur border border-slate-800 rounded-lg shadow-lg p-1 flex items-center space-x-1">
          <button
            onClick={() => setActiveLayer("orig")}
            className={`px-3 py-1.5 rounded-md text-xs font-semibold flex items-center space-x-1.5 transition ${
              activeLayer === "orig"
                ? "bg-sky-600 text-white shadow-sm"
                : "text-slate-400 hover:text-white hover:bg-slate-800"
            }`}
          >
            <ImageIcon className="w-3.5 h-3.5" />
            <span>Original Colors</span>
          </button>
          <button
            onClick={() => setActiveLayer("norm")}
            className={`px-3 py-1.5 rounded-md text-xs font-semibold flex items-center space-x-1.5 transition ${
              activeLayer === "norm"
                ? "bg-sky-600 text-white shadow-sm"
                : "text-slate-400 hover:text-white hover:bg-slate-800"
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>Normalized 10×</span>
          </button>
        </div>

        {/* Fallback Badge when zoomed beyond 10x in normalized view */}
        {isNormFallbackToOrig && (
          <div className="pointer-events-auto bg-amber-950/80 border border-amber-800/80 text-amber-300 px-2.5 py-1 rounded-full text-xs font-medium flex items-center space-x-1 shadow-md">
            <Info className="w-3.5 h-3.5 text-amber-400" />
            <span>Original Colors (&gt;10× zoom)</span>
          </div>
        )}

        {/* Zoom & Power Controls */}
        <div className="pointer-events-auto bg-slate-900/90 backdrop-blur border border-slate-800 rounded-lg shadow-lg p-1 flex items-center space-x-1">
          <button
            onClick={handleZoomOut}
            className="p-2 hover:bg-slate-800 text-slate-300 hover:text-white rounded transition"
            title="Zoom Out"
          >
            <ZoomOut className="w-4 h-4" />
          </button>

          <button
            onClick={handleZoomIn}
            className="p-2 hover:bg-slate-800 text-slate-300 hover:text-white rounded transition"
            title="Zoom In"
          >
            <ZoomIn className="w-4 h-4" />
          </button>

          <button
            onClick={handleResetZoom}
            className="p-2 hover:bg-slate-800 text-slate-300 hover:text-white rounded transition"
            title="Reset View"
          >
            <Maximize className="w-4 h-4" />
          </button>

          <div className="h-4 w-[1px] bg-slate-800 mx-1" />

          {/* Editable Custom Zoom Input & Presets Menu */}
          <div className="relative">
            <div className="flex items-center space-x-1 bg-slate-800/80 border border-slate-700 rounded px-2 py-1">
              {isEditingZoom ? (
                <form onSubmit={handleCustomZoomSubmit} className="flex items-center">
                  <input
                    type="number"
                    step="0.1"
                    min="0.1"
                    max="100"
                    value={customZoomInput}
                    onChange={(e) => setCustomZoomInput(e.target.value)}
                    onBlur={() => setIsEditingZoom(false)}
                    autoFocus
                    className="w-12 bg-slate-900 text-white text-xs font-mono px-1 py-0.5 rounded outline-none border border-sky-500"
                  />
                  <span className="text-xs font-mono text-slate-400 ml-0.5">x</span>
                </form>
              ) : (
                <button
                  onClick={() => setIsEditingZoom(true)}
                  className="text-xs font-mono font-semibold text-sky-400 hover:text-sky-300 transition"
                  title="Click to enter custom zoom magnification"
                >
                  {currentMag.toFixed(1)}x
                </button>
              )}

              <button
                onClick={() => setShowDropdown(!showDropdown)}
                className="p-0.5 text-slate-400 hover:text-white transition"
              >
                <ChevronDown className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Presets Dropdown */}
            {showDropdown && (
              <div className="absolute right-0 mt-2 w-32 bg-slate-900 border border-slate-800 rounded-lg shadow-xl py-1 z-20">
                <div className="px-3 py-1 text-[10px] uppercase font-bold text-slate-500 tracking-wider">
                  Presets
                </div>
                {ZOOM_PRESETS.map((power) => (
                  <button
                    key={power}
                    onClick={() => applyPower(power)}
                    className="w-full px-3 py-1.5 text-left text-xs text-slate-300 hover:bg-sky-600 hover:text-white flex items-center justify-between transition font-mono"
                  >
                    <span>{power}x</span>
                    {Math.abs(currentMag - power) < 0.2 && (
                      <Check className="w-3 h-3 text-sky-400" />
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Main OSD Container */}
      <div ref={containerRef} className="flex-1 w-full h-full cursor-grab active:cursor-grabbing" />

      {/* Continuous Calibrated Dynamic Scalebar */}
      <div className="absolute bottom-4 left-4 z-10 pointer-events-none">
        <div className="bg-slate-900/90 backdrop-blur border border-slate-800 rounded-lg p-2 shadow-lg flex flex-col items-center">
          <div
            className="h-1.5 bg-sky-400 rounded-full mb-1 transition-all duration-150 shadow-sm"
            style={{ width: `${scalebarWidthPx}px` }}
          />
          <div className="text-[10px] font-mono font-semibold text-slate-300 tracking-wider">
            {scaleLengthUm >= 1000 ? `${scaleLengthUm / 1000} mm` : `${scaleLengthUm} µm`}
          </div>
        </div>
      </div>
    </div>
  );
}
