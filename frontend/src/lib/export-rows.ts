export type ExportRow = {
  segment_id: string;
  content: string;
  labels: Record<string, string>;
  provenance: Record<string, unknown>;
};

export function parseExportJsonl(content: string): ExportRow[] {
  return content
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line) as ExportRow);
}
