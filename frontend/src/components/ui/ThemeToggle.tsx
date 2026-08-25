import { useTheme } from "../../app/theme";
import { Icon } from "./Icon";
import styles from "./ThemeToggle.module.css";

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";

  return (
    <button
      type="button"
      className={styles.toggle}
      aria-label={isDark ? "Aydınlık temaya geç" : "Karanlık temaya geç"}
      onClick={toggleTheme}
    >
      <Icon name={isDark ? "moon" : "sun"} size={15} />
      <span>Tema</span>
    </button>
  );
}
