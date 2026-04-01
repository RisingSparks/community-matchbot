"""Shared lightweight branding assets for public HTML pages."""

from __future__ import annotations

from html import escape
from pathlib import Path
from urllib.parse import urljoin

FAVICON_PATH = "/favicon.ico"
WEBMANIFEST_PATH = "/site.webmanifest"
BRAND_LOGO_PATH = "/media/rising-sparks-logo.png"
BRAND_FONT_STYLESHEET = (
    "https://fonts.googleapis.com/css2?family=Anton&family=Merriweather:"
    "ital,wght@0,300;0,400;0,700;1,300;1,400&display=swap"
)
GOOGLE_ANALYTICS_MEASUREMENT_ID = "G-4QW073D00W"
BRAND_LOGO_FILE = Path(__file__).resolve().parent / "assets" / "rising-sparks-logo.png"

FAVICON_LINK_TAGS = (
    f'<link rel="icon" href="{FAVICON_PATH}" sizes="any">\n'
    f'<link rel="shortcut icon" href="{FAVICON_PATH}">\n'
    f'<link rel="manifest" href="{WEBMANIFEST_PATH}">'
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
        f'<meta name="twitter:card" content="summary_large_image">',
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
                    f'<meta property="og:image:alt" content="{escaped_title}">',
                    f'<meta name="twitter:image" content="{escape(image_url)}">',
                ]
            )

    return "\n  ".join(tags)


def build_google_analytics_tags() -> str:
    """Build the GA4 tag snippet for public HTML pages."""
    safe_id = GOOGLE_ANALYTICS_MEASUREMENT_ID
    return (
        f'<script async src="https://www.googletagmanager.com/gtag/js?id={safe_id}"></script>\n'
        "<script>\n"
        "  window.dataLayer = window.dataLayer || [];\n"
        "  function gtag(){dataLayer.push(arguments);}\n"
        "  gtag('js', new Date());\n"
        f"  gtag('config', '{safe_id}');\n"
        "</script>"
    )
