export type IconName = "upload" | "play" | "pause" | "stop" | "restart" | "chevron-down" | "chevron-up" | "image" | "warning" | "target" | "clock" | "close" | "sun" | "moon" | "check";

const paths: Record<IconName, React.ReactNode> = {
  upload: <><path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5"/><path d="M5 14v5h14v-5"/></>,
  check: <path d="M5 12.5 10 17 19 7"/>,
  close: <path d="M18 6 6 18M6 6l12 12"/>,
  play: <path d="m8 5 11 7-11 7V5Z"/>,
  pause: <><path d="M8 5v14M16 5v14"/></>,
  stop: <rect x="6" y="6" width="12" height="12" rx="1"/>,
  restart: <><path d="M5 8V4m0 0h4M5 4l3 3a7 7 0 1 1-2 8"/></>,
  "chevron-down": <path d="m7 9 5 5 5-5"/>,
  "chevron-up": <path d="m7 15 5-5 5 5"/>,
  image: <><rect x="3" y="4" width="18" height="16" rx="2"/><path d="m3 16 5-5 4 4 3-3 6 6"/><circle cx="16" cy="9" r="1.5"/></>,
  warning: <><path d="M12 3 2.5 20h19L12 3Z"/><path d="M12 9v5m0 3v.1"/></>,
  target: <><circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3"/></>,
  clock: <><circle cx="12" cy="13" r="8"/><path d="M12 9v4l2.5 1.5M9 3h6"/></>,
  sun: <><circle cx="12" cy="12" r="4"/><path d="M12 2v2.5M12 19.5V22M4.2 4.2l1.8 1.8M18 18l1.8 1.8M2 12h2.5M19.5 12H22M4.2 19.8 6 18M18 6l1.8-1.8"/></>,
  moon: <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4 7 7 0 0 0 20 14.5Z"/>,
};

export function Icon({ name, size = 16, className }: { name: IconName; size?: number; className?: string }) {
  return <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}
