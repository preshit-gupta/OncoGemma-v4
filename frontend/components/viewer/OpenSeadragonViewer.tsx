"use client";

import React, { useEffect, useRef, useState } from "react";
import OpenSeadragon from "openseadragon";
import { ZoomIn, ZoomOut, Maximize, RefreshCw } from "lucide-react";

interface OpenSeadragonViewerProps {
  caseId: string;
  mppX?: number;
  mppY?: number;
  imageWidthPx?: number;
  imageHeightPx?: number;
  layer?: "orig" | "norm";
}

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
  const [zoomLevelText, setZoomLevelText] = useState<string>("1.0x");

  useEffect(() => {
    if (!containerRef.current) return;

    // Destroy existing instance if re-initializing
    if (viewerRef.current) {
      viewerRef.current.destroy();
      viewerRef.current = null;
    }

    const tileSource: OpenSeadragon.TileSourceOptions = {
      width: imageWidthPx,
      height: imageHeightPx,
      tileSize: 256,
      tileOverlap: 0,
      minLevel: 8,
      maxLevel: 18,
      getTileUrl: (level: number, x: number, y: number) => {
        return `/api/v1/cases/${caseId}/tiles/${layer}/${level}/${x}_${y}.jpg`;
      }
    };

    const viewer = OpenSeadragon({
      element: containerRef.current,
      prefixUrl: "https://openseadragon.github.io/openseadragon/images/",
      tileSources: tileSource,
      showNavigationControl: false,
      animationTime: 0.3,
      bllendTime: 0.1,
      maxZoomPixelRatio: 2.0,
      visibilityRatio: 0.8,
      constrainDuringPan: true
    });

    viewerRef.current = viewer;

    // Scalebar dynamic update listener
    const updateScalebar = () => {
      if (!viewer.viewport) return;
      const zoom = viewer.viewport.getZoom(true);
      const imageZoom = viewer.viewport.viewportToImageZoom(zoom);
      
      // Calculate scale length in micrometers
      const umPerPx = mppX / imageZoom;
      const targetUm = 200 * umPerPx; // 200px visual scalebar target width
      
      // Round scalebar to nice human numbers (10, 20, 50, 100, 250, 500, 1000 um)
      const niceScales = [10, 25, 50, 100, 250, 500, 1000, 2500, 5000];
      const chosenScale = niceScales.reduce((prev, curr) => 
        Math.abs(curr - targetUm) < Math.abs(prev - targetUm) ? curr : prev
      );

      setScaleLengthUm(chosenScale);
      setZoomLevelText(`${(imageZoom * (40.0 * 0.25 / mppX)).toFixed(1)}x`);
    };

    viewer.addHandler("zoom", updateScalebar);
    viewer.addHandler("open", updateScalebar);

    return () => {
      if (viewerRef.current) {
        viewerRef.current.destroy();
        viewerRef.current = null;
      }
    };
  }, [caseId, layer, imageWidthPx, imageHeightPx, mppX]);

  const handleZoomIn = () => {
    if (viewerRef.current && viewerRef.current.viewport) {
      viewerRef.current.viewport.zoomBy(1.2);
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

  return (
    <div className="relative w-full h-full bg-slate-900 overflow-hidden flex flex-col">
      {/* OSD Container */}
      <div ref={containerRef} className="w-full h-full cursor-crosshair" />

      {/* Floating Toolbar */}
      <div className="absolute top-4 right-4 bg-slate-900/80 backdrop-blur border border-slate-700 text-white rounded-lg p-1.5 flex items-center space-x-1 shadow-lg z-10">
        <button
          onClick={handleZoomIn}
          className="p-1.5 hover:bg-slate-700 rounded transition"
          title="Zoom In"
        >
          <ZoomIn className="w-4 h-4" />
        </button>
        <button
          onClick={handleZoomOut}
          className="p-1.5 hover:bg-slate-700 rounded transition"
          title="Zoom Out"
        >
          <ZoomOut className="w-4 h-4" />
        </button>
        <button
          onClick={handleResetZoom}
          className="p-1.5 hover:bg-slate-700 rounded transition"
          title="Reset View"
        >
          <Maximize className="w-4 h-4" />
        </button>
        <div className="h-4 w-[1px] bg-slate-700 mx-1" />
        <span className="text-xs font-mono text-slate-300 px-2">{zoomLevelText}</span>
      </div>

      {/* Calibrated Dynamic Scalebar */}
      <div className="absolute bottom-4 left-4 bg-slate-900/80 backdrop-blur border border-slate-700 px-3 py-1.5 rounded-lg shadow-lg z-10 text-white flex flex-col items-center">
        <div
          className="h-1 bg-sky-400 border-x border-white mb-1 transition-all"
          style={{ width: "120px" }}
        />
        <span className="text-[11px] font-mono text-slate-200">{scaleLengthUm} µm</span>
      </div>
    </div>
  );
}
