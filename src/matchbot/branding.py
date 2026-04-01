"""Shared lightweight branding assets for public HTML pages."""

from __future__ import annotations

from html import escape
from pathlib import Path
from urllib.parse import urljoin

FAVICON_PATH = "/favicon.svg"
BRAND_LOGO_PATH = "/media/rising-sparks-logo.png"
BRAND_FONT_STYLESHEET = (
    "https://fonts.googleapis.com/css2?family=Anton&family=Merriweather:"
    "ital,wght@0,300;0,400;0,700;1,300;1,400&display=swap"
)
BRAND_LOGO_FILE = Path(__file__).resolve().parent / "assets" / "rising-sparks-logo.png"

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


def build_brand_logo_link(
    href: str,
    *,
    link_class: str = "brand-logo",
    image_class: str = "brand-logo__image",
    text_class: str = "brand-logo__text",
    text: str = "Rising Sparks",
) -> str:
    """Build a linked logo lockup using the shared wordmark asset."""
    safe_href = escape(href, quote=True)
    safe_link_class = escape(link_class, quote=True)
    safe_image_class = escape(image_class, quote=True)
    safe_text_class = escape(text_class, quote=True)
    safe_text = escape(text)
    safe_alt = escape(text, quote=True)
    return (
        f'<a href="{safe_href}" class="{safe_link_class}">'
        f'<img src="{BRAND_LOGO_PATH}" alt="{safe_alt}" class="{safe_image_class}">'
        # f'<span class="{safe_text_class}">{safe_text}</span>'
        "</a>"
    )


def build_meta_tags(
    *,
    title: str,
    description: str,
    path: str,
    base_url: str | None = None,
    robots: str = "index,follow",
    og_type: str = "website",
    site_name: str = "Rising Sparks",
    image_path: str = BRAND_LOGO_PATH,
    theme_color: str = "#ff9200",
) -> str:
    """Build a compact set of SEO and sharing tags for public HTML pages."""
    escaped_title = escape(title)
    escaped_description = escape(description)
    escaped_robots = escape(robots)
    escaped_site_name = escape(site_name)
    escaped_theme_color = escape(theme_color)

    tags = [
        f"<title>{escaped_title}</title>",
        f'<meta name="description" content="{escaped_description}">',
        f'<meta name="robots" content="{escaped_robots}">',
        f'<meta name="theme-color" content="{escaped_theme_color}">',
        f'<meta property="og:site_name" content="{escaped_site_name}">',
        f'<meta property="og:type" content="{escape(og_type)}">',
        f'<meta property="og:title" content="{escaped_title}">',
        f'<meta property="og:description" content="{escaped_description}">',
        f'<meta name="twitter:card" content="summary">',
        f'<meta name="twitter:title" content="{escaped_title}">',
        f'<meta name="twitter:description" content="{escaped_description}">',
    ]

    if base_url:
        canonical_url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
        tags.extend(
            [
                f'<link rel="canonical" href="{escape(canonical_url)}">',
                f'<meta property="og:url" content="{escape(canonical_url)}">',
                f'<meta name="twitter:url" content="{escape(canonical_url)}">',
            ]
        )

        if image_path:
            image_url = urljoin(base_url.rstrip("/") + "/", image_path.lstrip("/"))
            tags.extend(
                [
                    f'<meta property="og:image" content="{escape(image_url)}">',
                    f'<meta name="twitter:image" content="{escape(image_url)}">',
                ]
            )

    return "\n  ".join(tags)
