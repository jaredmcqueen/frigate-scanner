"""Report module — render HTML dashboard and write JSONL/HTML output."""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Frigate Open Instances</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #e2e8f0; padding: 2rem; }
  h1 { font-size: 1.5rem; font-weight: 700; color: #38bdf8; margin-bottom: 0.25rem; }
  .subtitle { color: #64748b; font-size: 0.875rem; margin-bottom: 2rem; }
  .stats-bar { display: flex; gap: 2rem; margin-bottom: 2rem; padding: 1rem 1.5rem; background: #1e293b; border-radius: 0.75rem; }
  .stat { display: flex; flex-direction: column; }
  .stat-value { font-size: 1.75rem; font-weight: 700; color: #38bdf8; }
  .stat-label { font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }
  .filters { display: flex; gap: 0.75rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
  .filter-btn { padding: 0.375rem 0.875rem; border-radius: 999px; border: 1px solid #334155; background: transparent; color: #94a3b8; cursor: pointer; font-size: 0.8125rem; transition: all 0.15s; }
  .filter-btn:hover, .filter-btn.active { background: #38bdf8; border-color: #38bdf8; color: #0f172a; font-weight: 600; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 1rem; }
  .card { background: #1e293b; border-radius: 0.75rem; padding: 1.25rem; border: 1px solid #334155; transition: border-color 0.15s; }
  .card:hover { border-color: #38bdf8; }
  .card-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.875rem; }
  .card-url { font-size: 0.9375rem; font-weight: 600; color: #38bdf8; word-break: break-all; text-decoration: none; }
  .card-url:hover { text-decoration: underline; }
  .badge { font-size: 0.6875rem; padding: 0.2rem 0.5rem; border-radius: 999px; font-weight: 600; white-space: nowrap; }
  .badge-country { background: #1e3a5f; color: #7dd3fc; }
  .badge-new { background: #166534; color: #86efac; }
  .card.is-new { border-color: #22c55e; }
  .cam-chip.is-new { background: #14532d; border-color: #22c55e; color: #86efac; }
  .changes { background: #1e293b; border-radius: 0.75rem; padding: 1.25rem 1.5rem; margin-bottom: 2rem; border: 1px solid #334155; }
  .changes h2 { font-size: 1rem; color: #e2e8f0; margin-bottom: 0.875rem; }
  .change-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; }
  .change-col h3 { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem; }
  .change-col.added h3 { color: #22c55e; }
  .change-col.dropped h3 { color: #f87171; }
  .change-col ul { list-style: none; font-size: 0.8125rem; color: #94a3b8; max-height: 200px; overflow-y: auto; }
  .change-col li { padding: 0.15rem 0; word-break: break-all; }
  .change-col .empty { color: #475569; font-style: italic; }
  .meta { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.875rem; }
  .meta-item { font-size: 0.75rem; color: #64748b; display: flex; align-items: center; gap: 0.3rem; }
  .meta-item strong { color: #94a3b8; }
  .cameras-label { font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.4rem; }
  .cameras { display: flex; flex-wrap: wrap; gap: 0.375rem; }
  .cam-chip { font-size: 0.75rem; padding: 0.2rem 0.6rem; background: #0f172a; border: 1px solid #334155; border-radius: 999px; color: #94a3b8; }
  .org { font-size: 0.8125rem; color: #64748b; margin-bottom: 0.75rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .hidden { display: none; }
  .search-wrap { flex: 1; min-width: 200px; }
  input[type=search] { width: 100%; padding: 0.375rem 0.875rem; border-radius: 999px; border: 1px solid #334155; background: #1e293b; color: #e2e8f0; font-size: 0.8125rem; outline: none; }
  input[type=search]:focus { border-color: #38bdf8; }
  .count-display { color: #64748b; font-size: 0.8125rem; margin-left: auto; align-self: center; }
  #no-results { display: none; color: #64748b; text-align: center; padding: 3rem; font-size: 0.9375rem; }
</style>
</head>
<body>
<h1>Frigate Open Instances</h1>
<p class="subtitle">Scanned {{ scanned_at }} &mdash; {{ total }} open instances found</p>
<div class="stats-bar">
  <div class="stat"><span class="stat-value">{{ total }}</span><span class="stat-label">Open</span></div>
  <div class="stat"><span class="stat-value">{{ total_cameras }}</span><span class="stat-label">Cameras</span></div>
  <div class="stat"><span class="stat-value">{{ country_count }}</span><span class="stat-label">Countries</span></div>
</div>
{% if diff and diff.has_changes %}
<div class="changes">
  <h2>Changes since last scan</h2>
  <div class="change-grid">
    <div class="change-col added">
      <h3>+ New instances ({{ diff.new_instances|length }})</h3>
      <ul>
        {% for url in diff.new_instances %}<li>{{ url }}</li>{% else %}<li class="empty">none</li>{% endfor %}
      </ul>
    </div>
    <div class="change-col added">
      <h3>↻ Returned ({{ diff.returned_instances|length }})</h3>
      <ul>
        {% for url in diff.returned_instances %}<li>{{ url }}</li>{% else %}<li class="empty">none</li>{% endfor %}
      </ul>
    </div>
    <div class="change-col dropped">
      <h3>− Dropped off ({{ diff.dropped_instances|length }})</h3>
      <ul>
        {% for d in diff.dropped_instances %}<li>{{ d.url }} <span style="color:#475569">[{{ d.country_code or '??' }}]</span></li>{% else %}<li class="empty">none</li>{% endfor %}
      </ul>
    </div>
    <div class="change-col added">
      <h3>+ New cameras ({{ diff.new_cameras|length }})</h3>
      <ul>
        {% for url, name in diff.new_cameras %}<li>{{ name }} <span style="color:#475569">@ {{ url }}</span></li>{% else %}<li class="empty">none</li>{% endfor %}
      </ul>
    </div>
  </div>
</div>
{% endif %}
<div class="filters">
  <div class="search-wrap"><input type="search" id="search" placeholder="Search URL, org, camera…"></div>
  <button class="filter-btn active" data-country="all">All countries</button>
  {% for country in countries %}
  <button class="filter-btn" data-country="{{ country }}">{{ country }}</button>
  {% endfor %}
  <span class="count-display" id="count-display"></span>
</div>
<div class="grid" id="grid">
{% for r in instances %}
  <div class="card{{ ' is-new' if r.is_new else '' }}" data-country="{{ r.country_code or 'XX' }}" data-search="{{ (r.url + ' ' + (r.org or '') + ' ' + ' '.join(r.probe_cameras))|lower }}">
    <div class="card-header">
      <a class="card-url" href="{{ r.url }}" target="_blank" rel="noopener">{{ r.url }}</a>
      <div style="display:flex;gap:0.35rem;flex-wrap:wrap;justify-content:flex-end">
        {% if r.is_new %}<span class="badge badge-new">NEW</span>{% endif %}
        {% if r.country_code %}<span class="badge badge-country">{{ r.country_code }}</span>{% endif %}
      </div>
    </div>
    {% if r.org %}<div class="org">{{ r.org }}</div>{% endif %}
    <div class="meta">
      {% if r.frigate_version %}<span class="meta-item"><strong>v</strong>{{ r.frigate_version }}</span>{% endif %}
      <span class="meta-item"><strong>{{ r.probe_camera_count }}</strong>&nbsp;cam{{ 's' if r.probe_camera_count != 1 else '' }}</span>
      {% if r.frigate_uptime_days is not none %}<span class="meta-item">up {{ r.frigate_uptime_days }}d</span>{% endif %}
      {% if r.port %}<span class="meta-item">:{{ r.port }}</span>{% endif %}
    </div>
    {% if r.probe_cameras %}
    <div class="cameras-label">Cameras</div>
    <div class="cameras">
      {% for cam in r.probe_cameras %}<span class="cam-chip{{ ' is-new' if cam in r.new_cameras else '' }}">{{ cam }}</span>{% endfor %}
    </div>
    {% endif %}
  </div>
{% endfor %}
</div>
<p id="no-results">No instances match your filter.</p>
<script>
const cards = Array.from(document.querySelectorAll('.card'));
const countEl = document.getElementById('count-display');
let activeCountry = 'all';
let searchTerm = '';

function update() {
  let visible = 0;
  cards.forEach(c => {
    const countryOk = activeCountry === 'all' || c.dataset.country === activeCountry;
    const searchOk = !searchTerm || c.dataset.search.includes(searchTerm);
    const show = countryOk && searchOk;
    c.classList.toggle('hidden', !show);
    if (show) visible++;
  });
  countEl.textContent = visible + ' shown';
  document.getElementById('no-results').style.display = visible === 0 ? 'block' : 'none';
}

document.querySelectorAll('.filter-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeCountry = btn.dataset.country;
    update();
  });
});

document.getElementById('search').addEventListener('input', e => {
  searchTerm = e.target.value.toLowerCase().trim();
  update();
});

update();
</script>
</body>
</html>
"""


def render_html(
    instances: list[dict],
    scanned_at: str,
    diff: object | None = None,
) -> str:
    """Render the card dashboard HTML from a list of instance dicts."""
    env = Environment(autoescape=True)
    tmpl = env.from_string(HTML_TEMPLATE)

    countries = sorted({r.get("country_code") or "XX" for r in instances} - {"XX"})
    total_cameras = sum(r.get("probe_camera_count", 0) for r in instances)

    return tmpl.render(
        instances=instances,
        total=len(instances),
        total_cameras=total_cameras,
        country_count=len(countries),
        countries=countries,
        scanned_at=scanned_at,
        diff=diff,
    )


def write_jsonl(instances: list[dict], path: Path) -> None:
    """Write open instances as newline-delimited JSON."""
    with path.open("w") as f:
        for record in instances:
            f.write(json.dumps(record, default=list) + "\n")


def write_html(
    instances: list[dict],
    scanned_at: str,
    diff: object | None,
    path: Path,
) -> None:
    """Render the HTML dashboard and write it to path."""
    path.write_text(render_html(instances, scanned_at, diff))
