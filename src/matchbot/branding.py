"""Shared lightweight branding assets for public HTML pages."""

from __future__ import annotations

FAVICON_PATH = "/favicon.svg"

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="bg" x1="0%" x2="100%" y1="0%" y2="100%">
      <stop offset="0%" stop-color="#fff4dc"/>
      <stop offset="100%" stop-color="#f1c98d"/>
    </linearGradient>
    <linearGradient id="spark" x1="50%" x2="50%" y1="0%" y2="100%">
      <stop offset="0%" stop-color="#ffcf67"/>
      <stop offset="100%" stop-color="#d96a1d"/>
    </linearGradient>
  </defs>
  <rect width="64" height="64" rx="16" fill="url(#bg)"/>
  <circle cx="32" cy="32" r="24" fill="#21483f"/>
  <path
    d="M34.5 10 23 34h8l-1.5 20L41 29h-8.5z"
    fill="url(#spark)"
    stroke="#fff6e8"
    stroke-linejoin="round"
    stroke-width="2"
  />
  <circle cx="20" cy="20" r="2.2" fill="#ffcf67" opacity="0.9"/>
  <circle cx="44" cy="19" r="1.8" fill="#ffcf67" opacity="0.8"/>
  <circle cx="47" cy="43" r="2.4" fill="#f6b24d" opacity="0.75"/>
</svg>
"""

FAVICON_LINK_TAGS = (
    f'<link rel="icon" href="{FAVICON_PATH}" type="image/svg+xml">\n'
    f'<link rel="shortcut icon" href="{FAVICON_PATH}" type="image/svg+xml">'
)
