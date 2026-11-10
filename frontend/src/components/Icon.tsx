// Small hand-drawn icon set (1.6px strokes on a 20px grid).

const PATHS: Record<string, string> = {
  chat: "M4 5.5h12a1.5 1.5 0 0 1 1.5 1.5v6a1.5 1.5 0 0 1-1.5 1.5H9l-3.5 3v-3H4A1.5 1.5 0 0 1 2.5 13V7A1.5 1.5 0 0 1 4 5.5Z",
  mail: "M3 5.5h14v9H3zM3.4 6l6.6 5 6.6-5",
  form: "M5 2.5h7l3.5 3.5v11.5H5zM12 2.5V6h3.5M7.5 10h5M7.5 13h5",
  whatsapp: "M4 16.5l1-3.2A6.5 6.5 0 1 1 7.6 16zM8 7.5c0 2.5 2 4.5 4.5 4.5l1-1.2-1.6-.9-.7.7c-.8-.3-1.5-1-1.8-1.8l.7-.7-.9-1.6z",
  slack: "M7.5 3v14M12.5 3v14M3 7.5h14M3 12.5h14",
  bell: "M10 3a4.5 4.5 0 0 0-4.5 4.5c0 4-1.5 5.5-1.5 5.5h12s-1.5-1.5-1.5-5.5A4.5 4.5 0 0 0 10 3ZM8.3 15.5a1.8 1.8 0 0 0 3.4 0",
  phone: "M6.5 3h-2A1.5 1.5 0 0 0 3 4.6 12.5 12.5 0 0 0 15.4 17a1.5 1.5 0 0 0 1.6-1.5v-2l-3.5-1.5-1.6 1.6A9 9 0 0 1 6.4 8.1L8 6.5z",
  search: "M8.5 3.5a5 5 0 1 1 0 10 5 5 0 0 1 0-10ZM12.2 12.2 16.5 16.5",
  back: "M12 4.5 6.5 10l5.5 5.5",
  check: "M4.5 10.5 8 14l7.5-8",
  x: "M5 5l10 10M15 5 5 15",
  calendar: "M3.5 5h13v11.5h-13zM3.5 8.5h13M7 3v3.5M13 3v3.5",
  pin: "M10 17.5s5.5-5 5.5-9.5a5.5 5.5 0 0 0-11 0c0 4.5 5.5 9.5 5.5 9.5ZM10 6a2 2 0 1 1 0 4 2 2 0 0 1 0-4Z",
  wrench: "M12.8 3.2a4 4 0 0 0-4.6 5.4L3.5 13.3a1.6 1.6 0 0 0 2.3 2.3l4.7-4.7a4 4 0 0 0 5.4-4.6l-2.4 2.4-2.1-.5-.5-2.1z",
  alert: "M10 3 17.5 16h-15zM10 8v3.5M10 13.6v.4",
  send: "M3 10 17 3.5 13 17l-3-5.5zM10 11.5l7-8",
  refresh: "M15.5 7A6 6 0 0 0 4.2 8.5M4.5 13A6 6 0 0 0 15.8 11.5M15.5 3v4h-4M4.5 17v-4h4",
  user: "M10 10a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4ZM3.5 17a6.5 6.5 0 0 1 13 0",
  clock: "M10 3.5a6.5 6.5 0 1 1 0 13 6.5 6.5 0 0 1 0-13ZM10 6.5V10l2.5 1.5",
  steps:"M4 5h4v4H4zM12 11h4v4h-4zM8 7h2.5a1.5 1.5 0 0 1 1.5 1.5V11",
  open: "M11 3.5h5.5V9M16.5 3.5 9 11M14 12.5v4H3.5V6h4",
};

export function Icon({ name, size = 18, className }: { name: keyof typeof PATHS | string; size?: number; className?: string }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={PATHS[name] ?? PATHS.chat} />
    </svg>
  );
}

/** The condenser-fan mark. `spin` turns it while the desk is working. */
export function FanMark({ size = 28, spin = false }: { size?: number; spin?: boolean }) {
  return (
    <svg width={size} height={size} viewBox="-16 -16 32 32" aria-hidden="true" className={spin ? "fan fan--spin" : "fan"}>
      <circle r="15" className="fan__ring" />
      <g className="fan__blades">
        {[0, 120, 240].map((r) => (
          <path key={r} transform={`rotate(${r})`} d="M0-2.2C-1.2-6.6 1.2-11.5 5.6-11.6 7.2-8 4.4-3.6 0-2.2Z" />
        ))}
      </g>
      <circle r="2.4" className="fan__hub" />
    </svg>
  );
}

export const channelIcon = (c: string) =>
  c === "web" ? "chat" : c === "form" ? "form" : c === "whatsapp" ? "whatsapp" : "mail";
