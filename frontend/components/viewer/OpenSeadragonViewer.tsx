"use client";

import React, { useEffect, useRef, useState } from "react";
import OpenSeadragon from "openseadragon";
import { ZoomIn, ZoomOut, Maximize, ChevronDown, Check, Layers, Image as ImageIcon } from "lucide-react";

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
  imageWidthPx = 100000,
  imageHeightPx = 80000,
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
  const [activeLayer, setActiveLayer] = useState<"orig" | "norm">("orig");

  useEffect(() => {
    if (!containerRef.current) return;

    if (viewerRef.current) {
      viewerRef.current.destroy();
      viewerRef.current = null;
    }

    const tileSource: OpenSeadragon.TileSourceOptions = {
      width: imageWidthPx,
      height: imageHeightPx,
      tileSize: 256,
      tileOverlap: 0,
      minLevel: 0,
      maxLevel: 18,
      getTileUrl: (level: number, x: number, y: number) => {
        return `/api/v1/cases/${caseId}/tiles/${activeLayer}/${level}/${x}_${y}.jpg`;
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

    viewer.addHandler("zoom", updateScalebar);
    viewer.addHandler("open", updateScalebar);
    viewer.addHandler("animation-finish", updateScalebar);

    return () => {
      if (viewerRef.current) {
        viewerRef.current.destroy();
        viewerRef.current = null;
      }
    };
  }, [caseId, activeLayer, imageWidthPx, imageHeightPx, mppX]);

  const setTargetMagnification = (targetMag: number) => {
    if (!viewerRef.current || !viewerRef.current.viewport) return;
    const baseMagRatio = 40.0 * 0.25 / mppX;
    const targetImageZoom = targetMag / baseMagRatio;
    const targetViewportZoom = viewerRef.current.viewport.imageToViewportZoom(targetImageZoom);
    viewerRef.current.viewport.zoomTo(targetViewportZoom, undefined, false);
  };

  const handleZoomIn = () => {
    if (viewerRef.current && viewerRef.current.viewport) {
      viewerRef.current.viewport.zoomBy(1.25);
    }
  };

  const handleZoomOut = () => {
    if (viewerRef.current && viewerRef.current.viewport) {
      viewerRef.current.viewport.zoomBy(0.8);
    }
  };

  const handleResetZoom = () => {
    if (viewerRef.current && viewerRef.current.viewport) {
      viewerRef.current.viewport.goHome();
    }
  };

  const handleCustomZoomSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setIsEditingZoom(false);
    const parsed = parseFloat(customZoomInput);
    if (!isNaN(parsed) && parsed > 0 && parsed <= 100) {
      setTargetMagnification(parsed);
    } else {
      setCustomZoomInput(currentMag.toFixed(1));
    }
  };

  return (
    <div className="relative w-full h-full bg-slate-950 overflow-hidden flex flex-col">
      {/* View Mode Layer Selector Bar */}
      <div className="absolute top-4 left-4 bg-slate-900/90 backdrop-blur border border-slate-700 text-white rounded-lg p-1.5 flex items-center space-x-2 shadow-xl z-20 text-xs">
        <button
          onClick={() => setActiveLayer("orig")}
          className={`px-3 py-1.5 rounded-md font-medium flex items-center space-x-1.5 transition ${
            activeLayer === "orig"
              ? "bg-sky-600 text-white shadow-sm"
              : "text-slate-300 hover:bg-slate-800"
          }`}
        >
          <ImageIcon className="w-3.5 h-3.5" />
          <span>H&E Slide (Pyramid)</span>
        </button>

        <button
          onClick={() => setActiveLayer("norm")}
          className={`px-3 py-1.5 rounded-md font-medium flex items-center space-x-1.5 transition ${
            activeLayer === "norm"
              ? "bg-sky-600 text-white shadow-sm"
              : "text-slate-300 hover:bg-slate-800"
          }`}
        >
          <Layers className="w-3.5 h-3.5" />
          <span>Normalized / Mask</span>
        </button>
      </div>

      {/* OSD Canvas */}
      <div ref={containerRef} className="w-full h-full cursor-crosshair bg-slate-950" />

      {/* Floating Toolbar with Custom Zoom Input & Presets */}
      <div className="absolute top-4 right-4 bg-slate-900/90 backdrop-blur border border-slate-700 text-white rounded-lg p-1.5 flex items-center space-x-1.5 shadow-xl z-20">
        <button
          onClick={handleZoomIn}
          className="p-1.5 hover:bg-slate-700 rounded transition"
          title="Zoom In (+25%)"
        >
          <ZoomIn className="w-4 h-4 text-slate-200" />
        </button>
        <button
          onClick={handleZoomOut}
          className="p-1.5 hover:bg-slate-700 rounded transition"
          title="Zoom Out (-20%)"
        >
          <ZoomOut className="w-4 h-4 text-slate-200" />
        </button>
        <button
          onClick={handleResetZoom}
          className="p-1.5 hover:bg-slate-700 rounded transition"
          title="Reset View to Overview"
        >
          <Maximize className="w-4 h-4 text-slate-200" />
        </button>

        <div className="h-4 w-[1px] bg-slate-700 mx-1" />

        {/* Custom Zoom Input Box */}
        <div className="relative flex items-center">
          {isEditingZoom ? (
            <form onSubmit={handleCustomZoomSubmit} className="flex items-center">
              <input
                type="number"
                step="0.1"
                min="0.1"
                max="100"
                autoFocus
                value={customZoomInput}
                onChange={(e) => setCustomZoomInput(e.target.value)}
                onBlur={() => handleCustomZoomSubmit()}
                className="w-16 bg-slate-950 border border-sky-500 text-sky-400 font-mono text-xs px-1.5 py-0.5 rounded text-center focus:outline-none"
              />
              <span className="text-xs text-sky-400 font-mono ml-0.5">x</span>
            </form>
          ) : (
            <div className="flex items-center space-x-1">
              <button
                onClick={() => setIsEditingZoom(true)}
                className="font-mono text-xs text-sky-400 hover:text-sky-300 bg-slate-800/80 hover:bg-slate-800 px-2 py-1 rounded transition font-semibold"
                title="Click to enter custom magnification value"
              >
                {currentMag.toFixed(1)}x
              </button>

              {/* Presets Dropdown */}
              <div className="relative">
                <button
                  onClick={() => setShowDropdown(!showDropdown)}
                  className="p-1 hover:bg-slate-800 text-slate-400 hover:text-white rounded transition"
                  title="Select Objective Power Preset"
                >
                  <ChevronDown className="w-3.5 h-3.5" />
                </button>

                {showDropdown && (
                  <div className="absolute right-0 mt-2 w-28 bg-slate-900 border border-slate-700 rounded-lg shadow-2xl py-1 z-30">
                    <div className="px-2 py-1 text-[10px] uppercase tracking-wider text-slate-400 font-semibold border-b border-slate-800">
                      Presets
                    </div>
                    {ZOOM_PRESETS.map((preset) => (
                      <button
                        key={preset}
                        onClick={() => {
                          setTargetMagnification(preset);
                          setShowDropdown(false);
                        }}
                        className="w-full text-left px-3 py-1.5 text-xs text-slate-200 hover:bg-sky-600 hover:text-white flex items-center justify-between font-mono transition"
                      >
                        <span>{preset}x</span>
                        {Math.abs(currentMag - preset) < 0.2 && (
                          <Check className="w-3.5 h-3.5 text-sky-400" />
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Calibrated Continuous Dynamic Scalebar */}
      <div className="absolute bottom-4 left-4 bg-slate-900/90 backdrop-blur border border-slate-700 px-3 py-1.5 rounded-lg shadow-lg z-10 text-white flex flex-col items-center">
        <div
          className="h-1 bg-sky-400 border-x border-white mb-1 transition-all duration-150"
          style={{ width: `${scalebarWidthPx}px` }}
        />
        <span className="text-[11px] font-mono text-slate-200 font-medium">{scaleLengthUm} µm</span>
      </div>
    </div>
  );
}
