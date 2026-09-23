"use client";

// Global selected JLPT level (N3/N4/N2/"all") — ARCHITECTURE.md V4 §V4.5: AppHeader's
// LevelSelector and every page that reads the level (Dashboard, Review setup, Stats) share
// one persisted value "for the session" unless a page has its own local override (e.g. the
// Grammar list page's own filter chips, which stay page-local per §V4.5's table).
//
// Persistence follows useFuriganaMode.ts's exact hydration-safe pattern (every render starts
// from the default so server/client markup match, then swaps to the stored value post-mount)
// — wrapped in a Context, not a bare hook, because AppHeader lives outside the page tree
// (RootLayout) and needs live updates to reach page components without a full navigation.

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import type { LevelFilter } from "./types";

const STORAGE_KEY = "jp-grammar:selected-level";
const DEFAULT_LEVEL: LevelFilter = "all";

export function isLevelFilter(value: string | null): value is LevelFilter {
  return value === "all" || value === "N3" || value === "N4" || value === "N2";
}

function readStoredLevel(): LevelFilter {
  if (typeof window === "undefined") return DEFAULT_LEVEL;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return isLevelFilter(raw) ? raw : DEFAULT_LEVEL;
  } catch {
    // localStorage unavailable (private browsing, blocked storage) — fall back silently.
    return DEFAULT_LEVEL;
  }
}

interface LevelContextValue {
  level: LevelFilter;
  setLevel: (level: LevelFilter) => void;
}

const LevelContext = createContext<LevelContextValue | undefined>(undefined);

export function LevelProvider({ children }: { children: ReactNode }) {
  const [level, setLevelState] = useState<LevelFilter>(DEFAULT_LEVEL);

  useEffect(() => {
    setLevelState(readStoredLevel());
  }, []);

  const setLevel = useCallback((next: LevelFilter) => {
    setLevelState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Setting just won't persist across reloads — non-fatal.
    }
  }, []);

  return <LevelContext.Provider value={{ level, setLevel }}>{children}</LevelContext.Provider>;
}

export function useLevel(): [LevelFilter, (level: LevelFilter) => void] {
  const ctx = useContext(LevelContext);
  if (!ctx) {
    throw new Error("useLevel must be used within a LevelProvider");
  }
  return [ctx.level, ctx.setLevel];
}
