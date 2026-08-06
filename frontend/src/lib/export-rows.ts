export type ExportRow = {
  segment_id: string;
  content: string;
  labels: Record<string, string>;
  provenance: Record<string, unknown>;
  audio_uri?: string;
  start_ms?: number;
  end_ms?: number;
};

export function parseExportJsonl(content: string): ExportRow[] {
  return content
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line) as ExportRow);
}
