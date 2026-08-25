export const API_BASE = typeof window !== "undefined"
  ? (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000")
  : "http://localhost:8000";

export interface Case {
  id: string;
  created_by: string;
  status: string;
  created_at: string;
}

export interface CaseDetail extends Case {
  slides: Array<{
    id: string;
    gcs_uri_original: string;
    gcs_uri_pyramid?: string;
    format?: string;
    scanner?: string;
    mpp_x?: number;
    mpp_y?: number;
    base_mag?: number;
    width_px?: number;
    height_px?: number;
    checksum_sha256?: string;
    label_stripped_at?: string;
  }>;
  stages: Array<{
    id: string;
    stage: string;
    attempt: number;
    status: string;
    output_ref?: string;
    error?: string;
    started_at?: string;
    completed_at?: string;
  }>;
}

export async function fetchCases(): Promise<Case[]> {
  const res = await fetch(`${API_BASE}/api/v1/cases`, {
    headers: { "X-User-Role": "pathologist" }
  });
  if (!res.ok) throw new Error("Failed to fetch cases");
  return res.json();
}

export async function createCase(): Promise<Case> {
  const res = await fetch(`${API_BASE}/api/v1/cases`, {
    method: "POST",
    headers: { "X-User-Role": "pathologist" }
  });
  if (!res.ok) throw new Error("Failed to create case");
  return res.json();
}

export async function uploadSlideFile(
  caseId: string,
  file: File,
  onProgress?: (percent: number) => void
): Promise<any> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append("file", file);

    if (xhr.upload && onProgress) {
      xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable) {
          const percent = Math.round((e.loaded / e.total) * 100);
          onProgress(percent);
        }
      });
    }

    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch (_) {
          resolve({});
        }
      } else {
        let errorMsg = `HTTP Upload Error (${xhr.status})`;
        try {
          const body = JSON.parse(xhr.responseText);
          if (body.detail) errorMsg = body.detail;
        } catch (_) {}
        reject(new Error(errorMsg));
      }
    });

    xhr.addEventListener("error", () => reject(new Error("Network connection error during file upload")));
    xhr.addEventListener("abort", () => reject(new Error("Slide upload aborted")));

    xhr.open("POST", `${API_BASE}/api/v1/cases/${caseId}/slide/upload`);
    xhr.setRequestHeader("X-User-Role", "pathologist");
    xhr.send(formData);
  });
}

export async function retryStage(caseId: string, stageName: string) {
  const res = await fetch(`${API_BASE}/api/v1/cases/${caseId}/stages/${stageName}/retry`, {
    method: "POST",
    headers: { "X-User-Role": "pathologist" }
  });
  if (!res.ok) throw new Error("Failed to retry stage execution");
  return res.json();
}

export async function deleteCase(caseId: string) {
  const res = await fetch(`${API_BASE}/api/v1/cases/${caseId}`, {
    method: "DELETE",
    headers: { "X-User-Role": "pathologist" }
  });
  if (!res.ok) throw new Error("Failed to delete case");
}

export async function clearAllCases() {
  const res = await fetch(`${API_BASE}/api/v1/cases`, {
    method: "DELETE",
    headers: { "X-User-Role": "pathologist" }
  });
  if (!res.ok) throw new Error("Failed to clear cases");
  return res.json();
}

export async function fetchCaseDetail(caseId: string): Promise<CaseDetail> {
  const res = await fetch(`${API_BASE}/api/v1/cases/${caseId}`, {
    headers: { "X-User-Role": "pathologist" }
  });
  if (!res.ok) throw new Error("Failed to fetch case detail");
  return res.json();
}
