"use client";

import { useCallback, useEffect, useState } from "react";
import type { FuriganaMode } from "./types";

const STORAGE_KEY = "jp-grammar:furigana-mode";
const DEFAULT_MODE: FuriganaMode = "by_level";

function isFuriganaMode(value: string | null): value is FuriganaMode {
  return (
    value === "always" || value === "never" || value === "by_level" || value === "adaptive"
  );
}

function readStoredMode(): FuriganaMode {
  if (typeof window === "undefined") return DEFAULT_MODE;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return isFuriganaMode(raw) ? raw : DEFAULT_MODE;
  } catch {
    // localStorage unavailable (private browsing, blocked storage) — fall back silently.
    return DEFAULT_MODE;
  }
}

/**
 * Furigana display mode (Always/Never/By-level/Adaptive), persisted per-browser in
 * localStorage — a local UI convenience, not shared/synced app state. ARCHITECTURE.md §5 /
 * Phase 4 task 4.6, adaptive mode added in V3 §V3.4.
 *
 * Hydration-safe: every render starts from DEFAULT_MODE (matches the server-rendered
 * markup), then swaps to the stored value in an effect after mount, so there's no
 * SSR/client markup mismatch — at the cost of a one-frame flash to the default mode on
 * first load, which is an acceptable trade for a single-user local setting.
 */
export function useFuriganaMode(): [FuriganaMode, (mode: FuriganaMode) => void] {
  const [mode, setModeState] = useState<FuriganaMode>(DEFAULT_MODE);

  useEffect(() => {
    setModeState(readStoredMode());
  }, []);

  const setMode = useCallback((next: FuriganaMode) => {
    setModeState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Setting just won't persist across reloads — non-fatal.
    }
  }, []);

  return [mode, setMode];
}
