/**
 * Resumable multipart upload straight from the browser to object storage.
 *
 * The API creates the upload session and signs each part; bytes go to the
 * presigned URLs directly. Parts upload 4 at a time with retries. A session
 * is remembered per browser (video id + file fingerprint), so after a dropped
 * connection or a reload the same file continues from the parts the server
 * already has.
 */
import { env } from "@/lib/env";

export type UploadMeta = {
  title: string;
  procedure_code: string;
  operation_date: string | null;
  request_analysis: boolean;
  workspace_id?: string | null;
};

export type UploadSession = {
  video_id: string;
  upload_id: string;
  key: string;
  part_size_bytes: number;
  part_count: number;
};

export type UploadProgress = {
  uploadedBytes: number;
  totalBytes: number;
  partsDone: number;
  partCount: number;
  phase: "starting" | "uploading" | "completing" | "done" | "error" | "aborted";
  message?: string;
};

type Listener = (progress: UploadProgress) => void;

const PARALLEL = 4;
const MAX_RETRIES = 6;
const STORE_KEY = "cornelius.uploads";

export function fileFingerprint(file: File): string {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

type StoredSession = { fingerprint: string; session: UploadSession; startedAt: number };

function readStore(): StoredSession[] {
  try {
    const raw = window.localStorage.getItem(STORE_KEY);
    const list = raw ? (JSON.parse(raw) as StoredSession[]) : [];
    const cutoff = Date.now() - 24 * 3600 * 1000;
    return list.filter((s) => s.startedAt > cutoff);
  } catch {
    return [];
  }
}

function writeStore(list: StoredSession[]) {
  try {
    window.localStorage.setItem(STORE_KEY, JSON.stringify(list));
  } catch {
    // storage unavailable; resume across reloads simply does not apply
  }
}

export function findResumable(file: File): UploadSession | null {
  const fp = fileFingerprint(file);
  return readStore().find((s) => s.fingerprint === fp)?.session ?? null;
}

function remember(file: File, session: UploadSession) {
  const fp = fileFingerprint(file);
  writeStore([...readStore().filter((s) => s.fingerprint !== fp), { fingerprint: fp, session, startedAt: Date.now() }]);
}

function forget(file: File) {
  const fp = fileFingerprint(file);
  writeStore(readStore().filter((s) => s.fingerprint !== fp));
}

async function apiJson<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${env.apiBaseUrl}${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = (await response.json()) as { detail?: unknown };
      if (typeof data.detail === "string") detail = data.detail;
    } catch {
      // keep statusText
    }
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function putPart(url: string, blob: Blob, signal: AbortSignal, onBytes: (sent: number) => void): Promise<string> {
  // XMLHttpRequest for upload progress events; fetch has none for the request body.
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.upload.onprogress = (e) => onBytes(e.loaded);
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        const etag = xhr.getResponseHeader("ETag");
        if (!etag) reject(new Error("Storage did not return an ETag (check the bucket CORS rules)"));
        else resolve(etag);
      } else {
        reject(new Error(`Part upload failed with status ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new Error("Network error during part upload"));
    xhr.onabort = () => reject(new DOMException("aborted", "AbortError"));
    signal.addEventListener("abort", () => xhr.abort(), { once: true });
    xhr.send(blob);
  });
}

export class MultipartUploader {
  private controller = new AbortController();
  private listeners: Listener[] = [];
  private progress: UploadProgress;
  private partBytes = new Map<number, number>();

  constructor(
    private file: File,
    private meta: UploadMeta,
    private getToken: () => Promise<string>,
  ) {
    this.progress = { uploadedBytes: 0, totalBytes: file.size, partsDone: 0, partCount: 0, phase: "starting" };
  }

  onProgress(listener: Listener) {
    this.listeners.push(listener);
    return () => {
      this.listeners = this.listeners.filter((l) => l !== listener);
    };
  }

  private emit(patch: Partial<UploadProgress>) {
    this.progress = { ...this.progress, ...patch };
    this.listeners.forEach((l) => l(this.progress));
  }

  private recomputeBytes(doneParts: Set<number>, partSize: number) {
    let total = 0;
    for (const n of doneParts) total += Math.min(partSize, this.file.size - (n - 1) * partSize);
    for (const [n, sent] of this.partBytes) if (!doneParts.has(n)) total += sent;
    this.emit({ uploadedBytes: Math.min(total, this.file.size), partsDone: doneParts.size });
  }

  abort() {
    this.controller.abort();
  }

  async run(): Promise<{ video_id: string }> {
    const token = await this.getToken();
    const signal = this.controller.signal;

    let session = findResumable(this.file);
    if (session) {
      // Make sure the server still knows this upload; otherwise start fresh.
      try {
        await apiJson(`/videos/${session.video_id}/upload/parts`, token);
      } catch {
        forget(this.file);
        session = null;
      }
    }
    if (!session) {
      session = await apiJson<UploadSession>("/videos", token, {
        method: "POST",
        body: JSON.stringify({
          ...this.meta,
          filename: this.file.name,
          size_bytes: this.file.size,
          consent_confirmed: true,
        }),
      });
      remember(this.file, session);
    }

    const partSize = session.part_size_bytes;
    const partCount = Math.max(1, Math.ceil(this.file.size / partSize));
    const existing = await apiJson<{ part_number: number; etag: string }[]>(
      `/videos/${session.video_id}/upload/parts`,
      token,
    );
    const etags = new Map<number, string>(existing.map((p) => [p.part_number, p.etag]));
    const done = new Set(etags.keys());
    this.emit({ phase: "uploading", partCount });
    this.recomputeBytes(done, partSize);

    const queue: number[] = [];
    for (let n = 1; n <= partCount; n += 1) if (!done.has(n)) queue.push(n);

    const worker = async () => {
      while (queue.length > 0) {
        if (signal.aborted) throw new DOMException("aborted", "AbortError");
        const n = queue.shift()!;
        const start = (n - 1) * partSize;
        const blob = this.file.slice(start, Math.min(start + partSize, this.file.size));
        let attempt = 0;
        for (;;) {
          try {
            const freshToken = await this.getToken();
            const { url } = await apiJson<{ url: string }>(
              `/videos/${session!.video_id}/upload/part/${n}`,
              freshToken,
            );
            const etag = await putPart(url, blob, signal, (sent) => {
              this.partBytes.set(n, sent);
              this.recomputeBytes(done, partSize);
            });
            etags.set(n, etag);
            done.add(n);
            this.partBytes.delete(n);
            this.recomputeBytes(done, partSize);
            break;
          } catch (error) {
            if (signal.aborted || (error instanceof DOMException && error.name === "AbortError")) throw error;
            attempt += 1;
            if (attempt > MAX_RETRIES) throw error;
            this.emit({ message: `Part ${n} failed, retrying (${attempt}/${MAX_RETRIES})` });
            await sleep(Math.min(30000, 1000 * 2 ** attempt));
          }
        }
      }
    };

    try {
      await Promise.all(Array.from({ length: Math.min(PARALLEL, queue.length || 1) }, worker));
    } catch (error) {
      if (signal.aborted) {
        this.emit({ phase: "aborted" });
        throw error;
      }
      this.emit({ phase: "error", message: error instanceof Error ? error.message : String(error) });
      throw error;
    }

    this.emit({ phase: "completing", message: undefined });
    const parts = Array.from(etags.entries())
      .sort((a, b) => a[0] - b[0])
      .map(([part_number, etag]) => ({ part_number, etag }));
    await apiJson(`/videos/${session.video_id}/upload/complete`, await this.getToken(), {
      method: "POST",
      body: JSON.stringify({ parts }),
    });
    forget(this.file);
    this.emit({ phase: "done", uploadedBytes: this.file.size, partsDone: partCount });
    return { video_id: session.video_id };
  }

  /** Abort on the server too (removes the pending row and the stored parts). */
  async cancel(): Promise<void> {
    this.abort();
    const session = findResumable(this.file);
    if (!session) return;
    try {
      await apiJson(`/videos/${session.video_id}/upload`, await this.getToken(), { method: "DELETE" });
    } finally {
      forget(this.file);
    }
  }
}
