import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#0D0C0A",
        surface: "#141310",
        elevated: "#1F1D18",
        paper: "#F3EFE6",
        subtle: "#26231D",
        accent: {
          orange: "#E8612C",
          "orange-hover": "#F2703E",
        },
        primary: "#F5F2EB",
        muted: "#8E897F",
      },
      fontFamily: {
        serif: ['"Instrument Serif"', "Georgia", "serif"],
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      borderColor: {
        subtle: "#26231D",
      },
    },
  },
  plugins: [],
} satisfies Config;
