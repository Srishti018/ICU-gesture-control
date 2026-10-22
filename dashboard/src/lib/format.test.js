import { describe, expect, it } from "vitest";
import { bedName, formatAgo, formatDuration, formatSeconds, formatSigned, formatWhen, parseLocalIso } from "./format.js";

describe("alert age formatting", () => {
  it("formats mm:ss under an hour and h:mm:ss above", () => {
    expect(formatDuration(0)).toBe("00:00");
    expect(formatDuration(42)).toBe("00:42");
    expect(formatDuration(42.9)).toBe("00:42");
    expect(formatDuration(725)).toBe("12:05");
    expect(formatDuration(3599)).toBe("59:59");
    expect(formatDuration(3723)).toBe("1:02:03");
    expect(formatDuration(-5)).toBe("00:00");
  });
  it("formats ages", () => {
    expect(formatAgo(2)).toBe("2 s ago");
    expect(formatAgo(125)).toBe("2 min ago");
    expect(formatAgo(7300)).toBe("2 h ago");
  });
});

describe("other formatting", () => {
  it("names beds", () => {
    expect(bedName("bed1")).toBe("Bed 1");
    expect(bedName("bed12")).toBe("Bed 12");
    expect(bedName("icu-x")).toBe("icu-x");
  });
  it("parses contract timestamps as local time", () => {
    expect(parseLocalIso("2026-10-25T10:02:11")).toBe(new Date(2026, 9, 25, 10, 2, 11).getTime());
    expect(parseLocalIso("nope")).toBeNull();
    expect(parseLocalIso(null)).toBeNull();
  });
  it("shows the date only for other days", () => {
    const now = new Date(2026, 9, 25, 12, 0, 0).getTime();
    expect(formatWhen("2026-10-25T10:02:11", now)).toBe("10:02:11");
    expect(formatWhen("2026-10-24T10:02:11", now)).toBe("24 Oct 10:02:11");
    expect(formatWhen(null, now)).toBe("—");
  });
  it("formats numbers", () => {
    expect(formatSeconds(8.24)).toBe("8.2 s");
    expect(formatSeconds(null)).toBe("—");
    expect(formatSigned(24)).toBe("+24");
    expect(formatSigned(-3)).toBe("−3");
    expect(formatSigned(0)).toBe("0");
  });
});
