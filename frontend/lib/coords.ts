/**
 * Coordinate conversion helper for OpenSeadragon viewport & micrometer coordinates
 */
export function umToViewport(
  xUm: number,
  yUm: number,
  mppX: number,
  mppY: number,
  imageWidthPx: number,
  imageHeightPx: number
): { x: number; y: number } {
  const xPx = xUm / mppX;
  const yPx = yUm / mppY;

  // OpenSeadragon viewport coordinates (0..1 across image width)
  return {
    x: xPx / imageWidthPx,
    y: yPx / imageWidthPx // OSD maintains aspect ratio relative to width
  };
}

export function viewportToUm(
  vpX: number,
  vpY: number,
  mppX: number,
  mppY: number,
  imageWidthPx: number
): { xUm: number; yUm: number } {
  const xPx = vpX * imageWidthPx;
  const yPx = vpY * imageWidthPx;

  return {
    xUm: xPx * mppX,
    yUm: yPx * mppY
  };
}
