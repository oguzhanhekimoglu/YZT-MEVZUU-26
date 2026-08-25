import { normalizeRisk } from "./risk-normalization";

describe("normalizeRisk", () => {
  it.each([
    ["LOW", "low"],
    ["low", "low"],
    ["düşük", "low"],
    ["dusuk", "low"],
    ["MEDIUM", "medium"],
    ["orta", "medium"],
    ["HIGH", "high"],
    ["yüksek", "high"],
    ["yuksek", "high"],
    ["CRITICAL", "critical"],
    ["kritik", "critical"],
  ] as const)("%s değerini %s olarak eşler", (input, expected) => {
    expect(normalizeRisk(input)).toBe(expected);
  });

  it.each([undefined, null, "", "tanımsız"])("%s değerini unknown yapar", (input) => {
    expect(normalizeRisk(input)).toBe("unknown");
  });
});
