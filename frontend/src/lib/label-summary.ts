import { parseExportJsonl, type ExportRow } from "@/lib/export-rows";

export type LabelValueCount = {
  value: string;
  count: number;
  percentage: number;
};

export type LabelFieldSummary = {
  field: string;
  total: number;
  unique: number;
  highCardinality: boolean;
  displayLimit: number;
  items: LabelValueCount[];
};

export type SummarizeLabelsOptions = {
  topN?: number;
  highCardinalityTopN?: number;
  highCardinalityUniqueThreshold?: number;
  highCardinalityRatio?: number;
};

const DEFAULT_TOP_N = 5;
const DEFAULT_HIGH_CARDINALITY_TOP_N = 3;
const DEFAULT_UNIQUE_THRESHOLD = 8;
const DEFAULT_UNIQUE_RATIO = 0.4;

function normalizeLabelValue(value: unknown): string | null {
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : null;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  return null;
}

function isHighCardinality(
  unique: number,
  total: number,
  options: SummarizeLabelsOptions,
): boolean {
  const threshold =
    options.highCardinalityUniqueThreshold ?? DEFAULT_UNIQUE_THRESHOLD;
  const ratio = options.highCardinalityRatio ?? DEFAULT_UNIQUE_RATIO;
  return unique > threshold || unique > total * ratio;
}

/** Aggregate label value distributions with top-N and high-cardinality rules. */
export function summarizeLabels(
  rows: ExportRow[],
  options: SummarizeLabelsOptions = {},
): LabelFieldSummary[] {
  const topN = options.topN ?? DEFAULT_TOP_N;
  const highCardinalityTopN =
    options.highCardinalityTopN ?? DEFAULT_HIGH_CARDINALITY_TOP_N;
  const fieldValues = new Map<string, string[]>();

  for (const row of rows) {
    for (const [field, raw] of Object.entries(row.labels ?? {})) {
      const value = normalizeLabelValue(raw);
      if (value === null) {
        continue;
      }
      const bucket = fieldValues.get(field) ?? [];
      bucket.push(value);
      fieldValues.set(field, bucket);
    }
  }

  const summaries: LabelFieldSummary[] = [];

  for (const [field, values] of fieldValues) {
    const counts = new Map<string, number>();
    for (const value of values) {
      counts.set(value, (counts.get(value) ?? 0) + 1);
    }

    const total = values.length;
    const unique = counts.size;
    const highCardinality = isHighCardinality(unique, total, options);
    const displayLimit = highCardinality ? highCardinalityTopN : topN;

    const items = Array.from(counts.entries())
      .sort((left, right) => {
        if (right[1] !== left[1]) {
          return right[1] - left[1];
        }
        return left[0].localeCompare(right[0]);
      })
      .map(([value, count]) => ({
        value,
        count,
        percentage: total > 0 ? (count / total) * 100 : 0,
      }));

    summaries.push({
      field,
      total,
      unique,
      highCardinality,
      displayLimit,
      items,
    });
  }

  return summaries.sort((left, right) => left.field.localeCompare(right.field));
}

/** Parse export JSONL and return label field summaries. */
export function summarizeLabelsFromExport(
  content: string,
  options?: SummarizeLabelsOptions,
): LabelFieldSummary[] {
  return summarizeLabels(parseExportJsonl(content), options);
}

export function formatLabelFieldTitle(summary: LabelFieldSummary): string {
  if (summary.highCardinality) {
    return `${summary.field} · ${summary.unique} unique`;
  }
  return summary.field;
}

export function formatLabelCount(count: number, percentage: number): string {
  return `${count} (${Math.round(percentage)}%)`;
}

export function getHiddenLabelCount(summary: LabelFieldSummary): number {
  return Math.max(0, summary.items.length - summary.displayLimit);
}

export function getVisibleLabelItems(
  summary: LabelFieldSummary,
  expanded: boolean,
): LabelValueCount[] {
  if (expanded) {
    return summary.items;
  }
  return summary.items.slice(0, summary.displayLimit);
}
