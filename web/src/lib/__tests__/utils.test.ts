import { describe, expect, it } from "vitest";

import { t } from "@/lib/i18n";
import en from "@/messages/en.json";
import { formatBytes, formatTimestamp, initials } from "@/lib/utils";

describe("formatTimestamp", () => {
  it("formats mm:ss under one hour", () => {
    expect(formatTimestamp(0)).toBe("00:00");
    expect(formatTimestamp(65)).toBe("01:05");
    expect(formatTimestamp(1499.7)).toBe("24:59");
  });
  it("formats h:mm:ss above one hour", () => {
    expect(formatTimestamp(3600)).toBe("1:00:00");
    expect(formatTimestamp(3725)).toBe("1:02:05");
  });
});

describe("formatBytes", () => {
  it("uses base 1000 like storage billing", () => {
    expect(formatBytes(999)).toBe("999 B");
    expect(formatBytes(1500)).toBe("1.5 KB");
    expect(formatBytes(2_300_000_000)).toBe("2.3 GB");
  });
});

describe("initials", () => {
  it("takes up to two initials", () => {
    expect(initials("Stefanos Raptis")).toBe("SR");
    expect(initials("solo")).toBe("S");
    expect(initials("")).toBe("?");
  });
});

describe("t", () => {
  it("resolves nested keys and placeholders", () => {
    expect(t("auth.signIn")).toBe("Sign in");
    expect(t("library.storageUsed", { used: "1.2 GB", quota: "20 GB" })).toBe("1.2 GB of 20 GB used");
  });
  it("never uses em dashes in UI copy", () => {
    const json = JSON.stringify(en);
    expect(json.includes("—")).toBe(false);
  });
});

describe("legal versions", () => {
  it("are date-based and identical in both modules", async () => {
    const { TERMS_VERSION, PRIVACY_VERSION } = await import("@/lib/legal-versions");
    expect(TERMS_VERSION).toMatch(/^\d{4}-\d{2}-\d{2}\.\d+$/);
    expect(PRIVACY_VERSION).toMatch(/^\d{4}-\d{2}-\d{2}\.\d+$/);
  });
});
