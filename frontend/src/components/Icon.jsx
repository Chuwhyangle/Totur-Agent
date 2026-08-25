function Icon({ name, size = 20, strokeWidth = 1.7, className = '' }) {
  const paths = {
    plus: <><path d="M12 5v14M5 12h14" /></>,
    refresh: <><path d="M20 11a8.1 8.1 0 0 0-15.5-3M4 4v4h4" /><path d="M4 13a8.1 8.1 0 0 0 15.5 3M20 20v-4h-4" /></>,
    sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41" /></>,
    moon: <path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8Z" />,
    send: <><path d="m22 2-7 20-4-9-9-4Z" /><path d="M22 2 11 13" /></>,
    sparkles: <><path d="m12 3-1.3 3.7L7 8l3.7 1.3L12 13l1.3-3.7L17 8l-3.7-1.3Z" /><path d="m5 14-.8 2.2L2 17l2.2.8L5 20l.8-2.2L8 17l-2.2-.8Z" /><path d="m19 14-.8 2.2-2.2.8 2.2.8L19 20l.8-2.2L22 17l-2.2-.8Z" /></>,
    message: <><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4Z" /></>,
    target: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="4" /><path d="M12 3v3M21 12h-3M12 21v-3M3 12h3" /></>,
    chevron: <path d="m9 18 6-6-6-6" />,
    'chevron-left': <path d="m15 18-6-6 6-6" />,
    'chevron-down': <path d="m6 9 6 6 6-6" />,
    menu: <path d="M4 6h16M4 12h16M4 18h16" />,
    check: <path d="m5 12 4 4L19 6" />,
    user: <><path d="M20 21a8 8 0 0 0-16 0" /><circle cx="12" cy="7" r="4" /></>,
    panel: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16" /></>,
    globe: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18" /></>,
    paperclip: <path d="m21.4 11.6-8.9 8.9a6 6 0 0 1-8.5-8.5l9.4-9.4a4 4 0 1 1 5.7 5.7l-9.4 9.4a2 2 0 1 1-2.8-2.8l8.8-8.8" />,
    file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6" /></>,
    'file-text': <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6M8 13h8M8 17h6" /></>,
    'file-code': <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6M10 13l-2 2 2 2M14 13l2 2-2 2" /></>,
    'file-sheet': <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6M8 12h8M8 16h8M12 12v6" /></>,
    'file-slides': <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6M8 17v-4h8v4M10 20h4" /></>,
    trash: <><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" /><path d="M10 11v5M14 11v5" /></>,
    upload: <><path d="M12 16V4" /><path d="m7 9 5-5 5 5" /><path d="M5 20h14" /></>,
    download: <><path d="M12 4v12" /><path d="m7 11 5 5 5-5" /><path d="M5 20h14" /></>,
    copy: <><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" /></>,
    archive: <><path d="M4 7h16v13H4z" /><path d="M3 4h18v3H3zM9 12h6" /></>,
    close: <><path d="m6 6 12 12M18 6 6 18" /></>,
  }

  return (
    <svg
      className={`icon ${className}`.trim()}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  )
}

export default Icon
