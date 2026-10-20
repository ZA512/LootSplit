import { describe, expect, it } from "vitest";
import { cents } from "./money";

describe("conversion exacte des montants saisis", () => {
  it.each([
    ["115,01", 11501],
    ["1\u202f720,00", 172000],
    ["-800.01", -80001],
    ["0,29", 29],
    ["0", 0],
  ])("convertit %s", (input, expected) => {
    expect(cents(String(input))).toBe(expected);
  });
  it.each(["NaN", "1e3", "1.001", "1,2.3", "", "1000000000000000"])(
    "refuse %s",
    (input) => {
      expect(() => cents(input)).toThrow();
    },
  );
});
