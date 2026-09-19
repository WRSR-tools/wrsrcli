"""`wrsrcli output-table` — build rows and render the standalone HTML.

SPEC.md 4.2. The rendered file embeds its data as JSON and does its own
search/filter/sort in vanilla JS: it must keep working standalone,
indefinitely, with no network access, so nothing is loaded from a CDN.
"""

import datetime
import json

from . import config, workshopconfig
from .errors import WrsrcliError

ITEM_NAME = "$ITEM_NAME"
TAGS = "$TAGS"

NO_CONFIG = "(no workshopconfig.ini)"
TYPE_PREFIX = "WORKSHOP_ITEMTYPE_"


def load_manifest():
    path = config.manifest_path()
    if not path.exists():
        raise WrsrcliError(
            f"{path} not found — run `wrsrcli scan` first to build the manifest."
        )
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise WrsrcliError(f"could not read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise WrsrcliError(
            f"{path} is not valid JSON ({exc}) — re-run `wrsrcli scan`."
        ) from exc

    if not isinstance(data, list):
        raise WrsrcliError(f"{path} should contain a JSON array of entries.")
    return data


def _format_date(raw):
    """Unix timestamp string -> YYYY-MM-DD, or '' if unusable."""
    if not raw:
        return ""
    try:
        moment = datetime.datetime.fromtimestamp(int(raw))
    except (TypeError, ValueError, OSError, OverflowError):
        return ""
    return moment.strftime("%Y-%m-%d")


def _format_size(raw):
    """Byte count -> a compact human-readable size, or '' if unusable."""
    if raw in (None, ""):
        return ""
    try:
        size = float(raw)
    except (TypeError, ValueError):
        return ""

    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return ""


def build_rows(entries, workshop_path, details=None, authors=None):
    """Combine manifest entries with each item's workshopconfig.ini.

    SPEC.md 4.2 sources the display name and tags from 2.2 data, which the
    manifest schema (4.1) does not carry, so the config files are read here
    at render time. The manifest itself is not rebuilt.

    `details` and `authors` carry Steam Web API enrichment when a key is
    set; both are None in the no-API path.
    """
    details = details or {}
    authors = authors or {}

    rows = []
    for entry in entries:
        item_id = entry.get("item_id", "")
        name = NO_CONFIG
        tags = []

        config_file = workshop_path / item_id / "workshopconfig.ini"
        if config_file.exists():
            record = workshopconfig.load(config_file)
            name = workshopconfig.first(record, ITEM_NAME, "") or ""
            tags = record.get(TAGS, [])

        item_type = entry.get("item_type") or ""
        owner_id = entry.get("owner_id")
        enriched = details.get(item_id, {})

        # The API's time_updated is authoritative where present; the .acf's
        # value is what the no-API path has to work with.
        updated = enriched.get("time_updated") or entry.get("date_updated")
        posted = enriched.get("time_created")
        size = enriched.get("file_size")

        row = {
            "item_id": item_id,
            "name": name,
            "item_type": item_type.replace(TYPE_PREFIX, "") or "—",
            "item_type_raw": item_type,
            "tags": ", ".join(tags),
            "owner_id": owner_id or "—",
            "updated": _format_date(updated),
            "updated_sort": int(updated) if updated else 0,
        }

        if details or authors:
            row["author"] = authors.get(owner_id) or (owner_id or "—")
            row["posted"] = _format_date(posted)
            row["posted_sort"] = int(posted) if posted else 0
            row["size"] = _format_size(size)
            row["size_sort"] = int(size) if size else 0

        rows.append(row)
    return rows


def _embed(data):
    """JSON safe to place inside a <script> element."""
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WRSR Assets</title>
<style>
  :root {{
    --bg: #f6f6f4; --panel: #ffffff; --ink: #1b1b1a; --muted: #6a6a66;
    --line: #dcdcd6; --accent: #b7410e; --hover: #f0efe9;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #17171a; --panel: #202024; --ink: #e9e9e4; --muted: #9a9a93;
      --line: #33333a; --accent: #d9793f; --hover: #26262c;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 24px 16px; background: var(--bg); color: var(--ink);
    font: 15px/1.5 "Segoe UI", system-ui, sans-serif;
  }}
  .wrap {{ max-width: 1180px; margin: 0 auto; }}
  h1 {{ font-size: 21px; margin: 0 0 4px; letter-spacing: -0.01em; }}
  .meta {{ color: var(--muted); font-size: 13px; margin-bottom: 18px; }}
  .controls {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; }}
  input, select {{
    font: inherit; padding: 8px 11px; border: 1px solid var(--line);
    border-radius: 7px; background: var(--panel); color: var(--ink);
  }}
  input {{ flex: 1 1 260px; min-width: 0; }}
  input:focus, select:focus {{ outline: 2px solid var(--accent); outline-offset: -1px; }}
  .count {{ color: var(--muted); font-size: 13px; margin-bottom: 10px; }}
  .scroll {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 9px; }}
  table {{ border-collapse: collapse; width: 100%; background: var(--panel); }}
  th, td {{
    text-align: left; padding: 9px 13px; border-bottom: 1px solid var(--line);
    vertical-align: top; white-space: nowrap;
  }}
  th {{
    position: sticky; top: 0; background: var(--panel); cursor: pointer;
    font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em;
    color: var(--muted); user-select: none;
  }}
  th:hover {{ color: var(--ink); }}
  th[aria-sort] {{ color: var(--accent); }}
  th .arrow {{ opacity: 0.55; font-size: 10px; }}
  td.name {{ white-space: normal; min-width: 260px; }}
  td.id, td.owner {{ font-family: Consolas, ui-monospace, monospace; font-size: 13px; }}
  tbody tr:hover {{ background: var(--hover); }}
  tbody tr:last-child td {{ border-bottom: 0; }}
  .none {{ color: var(--muted); font-style: italic; }}
  .empty {{ padding: 28px 13px; color: var(--muted); text-align: center; }}
  footer {{ margin-top: 16px; color: var(--muted); font-size: 12px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>WRSR Assets</h1>
  <div class="meta">{count} installed workshop item(s) &middot; generated {generated}{mode}</div>

  <div class="controls">
    <input id="q" type="search" placeholder="Search name, ID, type, tags, owner&hellip;"
           aria-label="Search">
    <select id="type" aria-label="Filter by item type"></select>
  </div>
  <div class="count" id="count"></div>

  <div class="scroll">
    <table>
      <thead><tr id="head"></tr></thead>
      <tbody id="body"></tbody>
    </table>
  </div>

  <footer>Item IDs are also the workshop folder names under
    <code>steamapps/workshop/content/784150/</code>.</footer>
</div>

<script id="data" type="application/json">{data}</script>
<script>
(function () {{
  var rows = JSON.parse(document.getElementById('data').textContent);
  var columns = {columns};

  var q = document.getElementById('q');
  var typeSelect = document.getElementById('type');
  var head = document.getElementById('head');
  var body = document.getElementById('body');
  var count = document.getElementById('count');
  var sortKey = null, sortDir = 1;

  columns.forEach(function (col) {{
    var th = document.createElement('th');
    th.textContent = col.label;
    th.addEventListener('click', function () {{
      if (sortKey === col.key) {{ sortDir = -sortDir; }}
      else {{ sortKey = col.key; sortDir = 1; }}
      render();
    }});
    col.th = th;
    head.appendChild(th);
  }});

  var types = rows.map(function (r) {{ return r.item_type; }})
                  .filter(function (v, i, a) {{ return v && a.indexOf(v) === i; }})
                  .sort();
  typeSelect.appendChild(new Option('All types', ''));
  types.forEach(function (t) {{ typeSelect.appendChild(new Option(t, t)); }});

  function matches(row, needle) {{
    if (!needle) return true;
    return columns.some(function (col) {{
      return String(row[col.key] || '').toLowerCase().indexOf(needle) !== -1;
    }});
  }}

  function compare(a, b) {{
    var col = columns.filter(function (c) {{ return c.key === sortKey; }})[0];
    var ka = col && col.sort ? a[col.sort] : a[sortKey];
    var kb = col && col.sort ? b[col.sort] : b[sortKey];
    if (typeof ka === 'number' && typeof kb === 'number') return (ka - kb) * sortDir;
    return String(ka).localeCompare(String(kb), undefined, {{numeric: true}}) * sortDir;
  }}

  function render() {{
    var needle = q.value.trim().toLowerCase();
    var wanted = typeSelect.value;
    var view = rows.filter(function (r) {{
      return (!wanted || r.item_type === wanted) && matches(r, needle);
    }});
    if (sortKey) view.sort(compare);

    columns.forEach(function (col) {{
      if (col.key === sortKey) {{
        col.th.setAttribute('aria-sort', sortDir > 0 ? 'ascending' : 'descending');
        col.th.innerHTML = col.label + ' <span class="arrow">' +
          (sortDir > 0 ? '\\u25b2' : '\\u25bc') + '</span>';
      }} else {{
        col.th.removeAttribute('aria-sort');
        col.th.textContent = col.label;
      }}
    }});

    body.textContent = '';
    view.forEach(function (row) {{
      var tr = document.createElement('tr');
      columns.forEach(function (col) {{
        var td = document.createElement('td');
        if (col.cls) td.className = col.cls;
        var value = row[col.key];
        if (value === '' || value === null || value === undefined) {{
          td.className = (td.className + ' none').trim();
          td.textContent = '\\u2014';
        }} else {{
          td.textContent = value;
        }}
        tr.appendChild(td);
      }});
      body.appendChild(tr);
    }});

    if (!view.length) {{
      var tr = document.createElement('tr');
      var td = document.createElement('td');
      td.className = 'empty';
      td.colSpan = columns.length;
      td.textContent = 'No items match.';
      tr.appendChild(td);
      body.appendChild(tr);
    }}

    count.textContent = view.length === rows.length
      ? rows.length + ' item(s)'
      : view.length + ' of ' + rows.length + ' item(s)';
  }}

  q.addEventListener('input', render);
  typeSelect.addEventListener('change', render);
  render();
}})();
</script>
</body>
</html>
"""

# SPEC.md 4.2. In no-API mode Author name, Posted date and File size are
# omitted rather than rendered empty — there is no local source for any of
# them.
COLUMNS = [
    {"key": "item_id", "label": "Item ID", "cls": "id"},
    {"key": "name", "label": "Name", "cls": "name"},
    {"key": "item_type", "label": "Type"},
    {"key": "tags", "label": "Tags"},
    {"key": "owner_id", "label": "Owner ID", "cls": "owner"},
    {"key": "updated", "label": "Updated", "sort": "updated_sort"},
]

COLUMNS_API = [
    {"key": "item_id", "label": "Item ID", "cls": "id"},
    {"key": "name", "label": "Name", "cls": "name"},
    {"key": "item_type", "label": "Type"},
    {"key": "tags", "label": "Tags"},
    {"key": "author", "label": "Author"},
    {"key": "posted", "label": "Posted", "sort": "posted_sort"},
    {"key": "updated", "label": "Updated", "sort": "updated_sort"},
    {"key": "size", "label": "Size", "sort": "size_sort"},
]


def render(rows, api_mode=False):
    generated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    mode = "" if api_mode else " &middot; local data only (no Steam Web API key set)"
    return _TEMPLATE.format(
        count=len(rows),
        generated=generated,
        mode=mode,
        data=_embed(rows),
        columns=_embed(COLUMNS_API if api_mode else COLUMNS),
    )
