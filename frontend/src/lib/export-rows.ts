export type ExportRow = {
  segment_id: string;
  content: string;
  labels: Record<string, string>;
  provenance: Record<string, unknown>;
};

export type LabelFieldSummary =
  | { kind: "counts"; field: string; counts: Record<string, number> }
  | { kind: "unique"; field: string; uniqueCount: number };

const FREE_TEXT_MAX_LENGTH = 80;

export function parseExportJsonl(content: string): ExportRow[] {
  return content
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line) as ExportRow);
}

function isFreeTextField(values: string[]): boolean {
  if (values.length === 0) {
    return false;
  }
  const unique = new Set(values);
  if (unique.size === values.length && values.some((value) => value.length > FREE_TEXT_MAX_LENGTH)) {
    return true;
  }
  return values.some((value) => value.length > FREE_TEXT_MAX_LENGTH);
}

/** Aggregate categorical label values; free-text fields show unique count only. */
export function summarizeLabelFields(rows: ExportRow[]): LabelFieldSummary[] {
  const fieldValues = new Map<string, string[]>();

  for (const row of rows) {
    for (const [field, value] of Object.entries(row.labels ?? {})) {
      if (typeof value !== "string" || !value.trim()) {
        continue;
      }
      const bucket = fieldValues.get(field) ?? [];
      bucket.push(value.trim());
      fieldValues.set(field, bucket);
    }
  }

  const summaries: LabelFieldSummary[] = [];
  for (const [field, values] of fieldValues) {
    if (isFreeTextField(values)) {
      summaries.push({
        kind: "unique",
        field,
        uniqueCount: new Set(values).size,
      });
      continue;
    }

    const counts: Record<string, number> = {};
    for (const value of values) {
      counts[value] = (counts[value] ?? 0) + 1;
    }
    summaries.push({ kind: "counts", field, counts });
  }

  return summaries.sort((left, right) => left.field.localeCompare(right.field));
}
