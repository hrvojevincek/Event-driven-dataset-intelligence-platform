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

/** Pretty-print export rows for the dashboard preview panel. */
export function formatExportPreview(content: string, maxRows = 5): string {
  return parseExportJsonl(content)
    .slice(0, maxRows)
    .map((row) => JSON.stringify(row, null, 2))
    .join("\n\n");
}

export function formatAudioTiming(row: ExportRow): string | null {
  if (row.start_ms == null || row.end_ms == null) {
    return null;
  }
  return `${row.start_ms}ms – ${row.end_ms}ms`;
}
