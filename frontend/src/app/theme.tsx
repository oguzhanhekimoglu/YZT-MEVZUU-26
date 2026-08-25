import { createContext, useContext, useEffect, useState, type PropsWithChildren } from "react";

export type Theme = "dark" | "light";

const STORAGE_KEY = "mevzuu-theme";

function readStoredTheme(): Theme {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

function persistTheme(theme: Theme) {
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // localStorage erişilemiyor (gizli sekme/engellenmiş depolama) — sessizce yut,
    // tema seçimi sadece bu oturumda hatırlanmaz.
  }
}

interface ThemeContextValue {
  theme: Theme;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: PropsWithChildren) {
  const [theme, setTheme] = useState<Theme>(readStoredTheme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    persistTheme(theme);
    document.getElementById("theme-color-meta")?.setAttribute("content", theme === "light" ? "#f6f8fa" : "#0b0f14");
  }, [theme]);

  function toggleTheme() {
    setTheme((current) => (current === "dark" ? "light" : "dark"));
  }

  return <ThemeContext.Provider value={{ theme, toggleTheme }}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext);

  if (!value) {
    throw new Error("ThemeProvider sağlayıcısı bulunamadı.");
  }

  return value;
}
