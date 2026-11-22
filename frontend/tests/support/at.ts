/** The i-th element of a list, failing the test with a clear message when it is missing. */
export function at<T>(list: readonly T[], i: number): T {
  const value = list[i];
  if (value === undefined) throw new Error(`expected an element at index ${i}, got a list of ${list.length}`);
  return value;
}
