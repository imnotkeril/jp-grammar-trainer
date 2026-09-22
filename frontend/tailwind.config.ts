import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        ink: "var(--ink)",
        "ink-muted": "var(--ink-muted)",
        accent: "var(--accent)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "Hiragino Sans", "Yu Gothic", "sans-serif"],
        display: ["var(--font-display)", "Hiragino Mincho ProN", "serif"],
      },
    },
  },
  plugins: [],
};

export default config;
