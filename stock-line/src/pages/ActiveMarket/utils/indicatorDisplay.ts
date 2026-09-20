interface PricePoint {
  close: number;
  open?: number | null;
  high?: number | null;
  low?: number | null;
}

// Inspect the data itself so close-only series also work with older API responses.
export function isCloseOnlySeries(data: readonly PricePoint[]): boolean {
  return data.some(item => Number.isFinite(item.close)) &&
    !data.some(item => [item.open, item.high, item.low, item.close].every(Number.isFinite));
}
