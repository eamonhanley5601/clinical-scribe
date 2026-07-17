export type DiffToken = { text: string; type: "same" | "add" | "remove" };

/** Word-level LCS diff -- small inputs (note text), so O(n*m) DP is plenty fast. */
export function wordDiff(oldText: string, newText: string): DiffToken[] {
  const a = oldText.split(/(\s+)/);
  const b = newText.split(/(\s+)/);
  const n = a.length;
  const m = b.length;

  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }

  const tokens: DiffToken[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      tokens.push({ text: a[i], type: "same" });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      tokens.push({ text: a[i], type: "remove" });
      i++;
    } else {
      tokens.push({ text: b[j], type: "add" });
      j++;
    }
  }
  while (i < n) tokens.push({ text: a[i++], type: "remove" });
  while (j < m) tokens.push({ text: b[j++], type: "add" });

  return tokens;
}
