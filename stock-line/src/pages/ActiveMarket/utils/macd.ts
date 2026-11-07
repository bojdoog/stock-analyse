// EMA starts from the first valid close; missing sessions do not advance it.
export function calculateMACD(closes: number[]) {
  let fast: number | undefined;
  let slow: number | undefined;
  let dea = 0;
  return closes.map(close => {
    if (!Number.isFinite(close)) return { dif: null, dea: null, histogram: null };
    fast = fast === undefined ? close : fast + (close - fast) * 2 / 13;
    slow = slow === undefined ? close : slow + (close - slow) * 2 / 27;
    const dif = fast - slow;
    dea += (dif - dea) * 2 / 10;
    return { dif, dea, histogram: 2 * (dif - dea) };
  });
}
