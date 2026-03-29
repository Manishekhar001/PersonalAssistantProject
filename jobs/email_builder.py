"""
email_builder.py — Builds the HTML email for a single sector briefing.

Public function:
  build_html_email(sector_data: dict, date_str: str) -> str

The string literal {GMAIL_ADDRESS} is left in the footer as a placeholder.
news_emailer.py replaces it with the real address before sending.
"""

# ── Accent colors per sector ──────────────────────────────────────────────────

SECTOR_COLORS = {
    "AI & Machine Learning": "#7C3AED",
    "Dev Tools & Open Source": "#0EA5E9",
    "Startups & Venture Capital": "#F59E0B",
    "Big Tech": "#6B7280",
    "Cybersecurity": "#EF4444",
    "India Tech": "#10B981",
}

DEFAULT_COLOR = "#4F46E5"


def _hex_to_rgba(hex_color: str, alpha: float = 0.10) -> str:
    """Convert a hex color string to an rgba() string with the given alpha."""
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _render_story(story: dict, accent: str) -> str:
    """Render a single story block as an HTML div."""
    rgba_bg = _hex_to_rgba(accent, 0.06)

    # Summary — split on double newlines for multi-paragraph support
    summary_html = "".join(
        f'<p style="margin:0 0 12px 0;">{para.strip()}</p>'
        for para in story.get("summary", "").split("\n\n")
        if para.strip()
    ) or f'<p style="margin:0 0 12px 0;">{story.get("summary", "")}</p>'

    # Key points
    key_points = story.get("key_points", [])
    key_points_html = ""
    if key_points:
        items = "".join(
            f'<li style="margin-bottom:6px;">'
            f'<span style="color:{accent};margin-right:6px;">&#9632;</span>{pt}</li>'
            for pt in key_points
        )
        key_points_html = f"""
        <div style="margin:16px 0;">
          <p style="margin:0 0 8px 0;font-size:11px;font-weight:600;letter-spacing:.08em;
                     text-transform:uppercase;color:{accent};">Key Points</p>
          <ul style="margin:0;padding-left:4px;list-style:none;">
            {items}
          </ul>
        </div>"""

    # Why it matters
    why = story.get("why_it_matters", "")
    why_html = ""
    if why:
        why_html = f"""
        <div style="margin:16px 0;">
          <p style="margin:0 0 6px 0;font-size:11px;font-weight:600;letter-spacing:.08em;
                     text-transform:uppercase;color:{accent};">Why it matters for you</p>
          <p style="margin:0;color:#6B7280;font-style:italic;line-height:1.7;">{why}</p>
        </div>"""

    # Citation pills
    citations = story.get("citations", [])
    citations_html = ""
    if citations:
        pills = "".join(
            f'<a href="{c.get("url", "#")}" target="_blank" rel="noopener" '
            f'style="display:inline-block;margin:4px 6px 4px 0;padding:4px 12px;'
            f'background:{_hex_to_rgba(accent, 0.10)};color:{accent};'
            f'border:1px solid {accent};border-radius:999px;'
            f'font-size:12px;text-decoration:none;white-space:nowrap;">'
            f'{c.get("source") or c.get("title", "Source")} &#8599;</a>'
            for c in citations
        )
        citations_html = f"""
        <div style="margin-top:16px;">
          <p style="margin:0 0 6px 0;font-size:11px;font-weight:600;letter-spacing:.08em;
                     text-transform:uppercase;color:#9CA3AF;">Sources</p>
          <div>{pills}</div>
        </div>"""

    return f"""
    <div style="margin:0 0 32px 0;padding:20px 20px 20px 24px;
                border-left:3px solid {accent};background:{rgba_bg};border-radius:0 8px 8px 0;">
      <h2 style="margin:0 0 14px 0;font-size:20px;font-weight:700;color:#111827;line-height:1.3;">
        {story.get("headline", "Untitled")}
      </h2>
      <div style="font-size:15px;line-height:1.8;color:#374151;">
        {summary_html}
      </div>
      {key_points_html}
      {why_html}
      {citations_html}
    </div>"""


def build_html_email(sector_data: dict, date_str: str) -> str:
    """Build and return a complete self-contained HTML email string for one sector."""
    sector_name = sector_data.get("sector_name", "Tech")
    icon = sector_data.get("icon", "📰")
    stories = sector_data.get("stories", [])
    tldr = sector_data.get("tldr", "")
    accent = SECTOR_COLORS.get(sector_name, DEFAULT_COLOR)

    stories_html = "".join(_render_story(s, accent) for s in stories)

    if not stories_html:
        stories_html = (
            '<p style="color:#6B7280;">No stories available for this sector today.</p>'
        )

    # NOTE: {{...}} in this f-string produces literal {…} in the output (f-string escape).
    # {GMAIL_ADDRESS} is intentionally left as a placeholder replaced by news_emailer.py.
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{icon} {sector_name} — {date_str}</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    body {{
      margin: 0;
      padding: 0;
      background: #F3F4F6;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      -webkit-font-smoothing: antialiased;
    }}
    a {{ color: inherit; }}
  </style>
</head>
<body>
  <div style="max-width:680px;margin:32px auto;background:#ffffff;border-radius:12px;
               overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">

    <!-- HEADER -->
    <div style="background:{accent};padding:28px 32px;">
      <p style="margin:0;font-size:26px;font-weight:700;color:#ffffff;line-height:1.2;">
        {icon} {sector_name}
      </p>
      <p style="margin:6px 0 0 0;font-size:14px;color:rgba(255,255,255,0.80);font-weight:400;">
        {date_str}
      </p>
    </div>

    <!-- BODY -->
    <div style="padding:32px;">

      <!-- TLDR BOX -->
      <div style="background:#F9FAFB;border:1px solid #E5E7EB;border-radius:8px;
                  padding:18px 20px;margin-bottom:32px;">
        <p style="margin:0 0 6px 0;font-size:12px;font-weight:700;letter-spacing:.08em;
                   text-transform:uppercase;color:{accent};">TL;DR</p>
        <p style="margin:0;color:#374151;line-height:1.7;font-size:15px;">
          {tldr or "No summary available."}
        </p>
      </div>

      <!-- STORIES -->
      {stories_html}

    </div>

    <!-- FOOTER -->
    <div style="border-top:1px solid #E5E7EB;padding:20px 32px;text-align:center;">
      <p style="margin:0;font-size:12px;color:#9CA3AF;">
        Sent by your Personal Assistant &middot; {date_str}<br/>
        <a href="mailto:{{GMAIL_ADDRESS}}" style="color:#9CA3AF;text-decoration:underline;">
          Unsubscribe
        </a>
      </p>
    </div>

  </div>
</body>
</html>"""
