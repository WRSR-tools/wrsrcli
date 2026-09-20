"""`wrsrcli output-table` — build rows and render the standalone HTML.

SPEC.md 4.2. The rendered file embeds its data as JSON and does its own
search/filter/sort in vanilla JS: it must keep working standalone,
indefinitely, with no network access, so nothing is loaded from a CDN.
"""

import datetime
import json

from . import config, updates, workshopconfig
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


def build_rows(entries, workshop_path):
    """Combine manifest entries with each item's workshopconfig.ini.

    Everything Steam knows was written into the manifest by `scan`, so this
    renders with Steam closed and with no network (decision D-024). The
    config files are still read here for the display name and tags, which
    SPEC 4.2 sources from 2.2 data.
    """
    installed = {e.get("item_id") for e in entries if e.get("item_id")}

    rows = []
    for entry in entries:
        item_id = entry.get("item_id", "")
        name = ""
        tags = []

        config_file = workshop_path / item_id / "workshopconfig.ini"
        if config_file.exists():
            record = workshopconfig.load(config_file)
            name = workshopconfig.first(record, ITEM_NAME, "") or ""
            tags = record.get(TAGS, [])
        # Steam's title covers an item whose workshopconfig.ini was deleted
        # locally — the case D-005 could previously only leave blank.
        if not name:
            name = entry.get("title") or NO_CONFIG

        item_type = entry.get("item_type") or ""
        owner_id = entry.get("owner_id")
        updated = entry.get("date_updated")
        posted = entry.get("date_published")

        row = {
            "item_id": item_id,
            "name": name,
            "item_type": item_type.replace(TYPE_PREFIX, "") or "—",
            "item_type_raw": item_type,
            "tags": ", ".join(tags),
            "owner_id": owner_id or "—",
            "author": entry.get("author") or owner_id or "—",
            "updated": _format_date(updated),
            "updated_sort": int(updated) if updated else 0,
            "posted": _format_date(posted),
            "posted_sort": int(posted) if posted else 0,
            "size": _format_size(entry.get("size_on_disk")),
            "size_sort": int(entry.get("size_on_disk") or 0),
        }

        if entry.get("dependencies"):
            row["dependencies"] = [
                {
                    "item_id": dep.get("item_id", ""),
                    "name": dep.get("name") or "(name unavailable)",
                    "creator": dep.get("creator")
                    or dep.get("creator_id")
                    or "unknown",
                    "creator_id": dep.get("creator_id") or "",
                    # Derived here rather than stored, so it cannot disagree
                    # with the manifest it was read from (decision D-020).
                    "installed": dep.get("item_id") in installed,
                }
                for dep in entry["dependencies"]
            ]

        rows.append(row)
    return rows


def build_status(entries, rows):
    """The payload behind the two status accordions (D-021, D-024).

    Both read the manifest, so both work with Steam closed. `assets` is None
    when no entry carries `date_latest` — the accordion is absent rather
    than claiming everything is fine on the strength of knowing nothing.
    """
    named = {row["item_id"]: row for row in rows}

    def describe(item_id, fallback_name="", fallback_creator=""):
        row = named.get(item_id, {})
        return {
            "item_id": item_id,
            "name": row.get("name") or fallback_name or "(name unavailable)",
            "creator": row.get("author")
            or fallback_creator
            or row.get("owner_id")
            or "unknown",
            "creator_id": row.get("owner_id") or "",
        }

    status = {"dependencies": None, "assets": None}

    if any("dependencies" in entry for entry in entries):
        missing = updates.unmet(entries)
        status["dependencies"] = {
            "state": "missing" if missing else "ok",
            "items": [
                describe(dep["item_id"], dep["name"], dep["creator"])
                for dep in missing
            ],
        }

    if updates.can_check_staleness(entries):
        stale = updates.outdated(entries)
        status["assets"] = {
            "state": "stale" if stale else "ok",
            "items": [describe(item["item_id"]) for item in stale],
            "source": "acf",
        }

    return status


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
    /* Semantic pairs, contrast-checked against their own tint, not the page. */
    --good-ink: #1d6b3f; --good-bg: #eaf5ee; --good-line: #bcdcc8;
    --bad-ink: #9d2727; --bad-bg: #fbecea; --bad-line: #eec4be;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #17171a; --panel: #202024; --ink: #e9e9e4; --muted: #9a9a93;
      --line: #33333a; --accent: #d9793f; --hover: #26262c;
      --good-ink: #7fd3a0; --good-bg: #172420; --good-line: #2c4536;
      --bad-ink: #f3a49b; --bad-bg: #261a1a; --bad-line: #4a2d2b;
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
  td a, .deps a {{ color: var(--accent); text-decoration: none; }}
  td a:hover, td a:focus, .deps a:hover, .deps a:focus {{ text-decoration: underline; }}
  th.fold, td.fold {{ width: 1px; padding-right: 0; }}
  .toggle {{
    font: inherit; line-height: 1; cursor: pointer; padding: 2px 6px;
    border: 1px solid var(--line); border-radius: 6px;
    background: var(--panel); color: var(--muted);
  }}
  .toggle:hover {{ color: var(--accent); border-color: var(--accent); }}
  .toggle:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 1px; }}
  tr.deps > td {{ white-space: normal; padding: 4px 13px 13px 13px; }}
  tr.deps h2 {{
    font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em;
    color: var(--muted); margin: 0 0 6px;
  }}
  tr.deps ul {{ margin: 0; padding: 0; list-style: none; }}
  tr.deps li {{ padding: 2px 0; }}
  tr.deps .sid {{ font-family: Consolas, ui-monospace, monospace; font-size: 13px; }}
  .ok {{ color: var(--muted); }}
  .missing {{ color: var(--accent); font-weight: 600; }}
  .status {{ margin-bottom: 14px; }}
  .status details {{
    border: 1px solid var(--line); border-radius: 9px; margin-bottom: 8px;
    background: var(--panel); overflow: hidden;
  }}
  .status details.good {{ border-color: var(--good-line); background: var(--good-bg); }}
  .status details.bad {{ border-color: var(--bad-line); background: var(--bad-bg); }}
  .status summary {{
    cursor: pointer; padding: 10px 13px; font-weight: 600; font-size: 14px;
    list-style: none; user-select: none;
  }}
  .status summary::-webkit-details-marker {{ display: none; }}
  .status summary::before {{ content: '\\25b8 '; font-size: 11px; opacity: 0.7; }}
  .status details[open] > summary::before {{ content: '\\25be '; }}
  .status summary:focus-visible {{ outline: 2px solid var(--accent); outline-offset: -2px; }}
  .status details.good summary {{ color: var(--good-ink); }}
  .status details.bad summary {{ color: var(--bad-ink); }}
  .status .panel {{ padding: 0 13px 12px; font-size: 14px; }}
  .status ul {{ margin: 6px 0; padding: 0 0 0 18px; list-style: none; }}
  .status li {{ padding: 2px 0; }}
  .status .sid {{ font-family: Consolas, ui-monospace, monospace; font-size: 13px; }}
  .status .note {{ color: var(--muted); font-size: 13px; }}
  .status code {{
    font-family: Consolas, ui-monospace, monospace; font-size: 13px;
    background: var(--panel); border: 1px solid var(--line);
    border-radius: 5px; padding: 1px 5px;
  }}
  footer {{ margin-top: 16px; color: var(--muted); font-size: 12px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>WRSR Assets</h1>
  <div class="meta">{count} installed workshop item(s) &middot; generated {generated}{mode}</div>

  <div class="status" id="status"></div>

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
<script id="status-data" type="application/json">{status}</script>
<script>
(function () {{
  var rows = JSON.parse(document.getElementById('data').textContent);
  var status = JSON.parse(document.getElementById('status-data').textContent);
  var columns = {columns};

  var q = document.getElementById('q');
  var typeSelect = document.getElementById('type');
  var head = document.getElementById('head');
  var body = document.getElementById('body');
  var count = document.getElementById('count');
  var sortKey = null, sortDir = 1;

  var ITEM_URL = 'https://steamcommunity.com/sharedfiles/filedetails/?id=';
  var USER_URL = 'https://steamcommunity.com/profiles/';
  var DASH = '\\u2014';

  // Links are navigation, never a resource the page loads, so the file stays
  // standalone with no external references (decision D-020).
  function link(href, text, cls) {{
    var a = document.createElement('a');
    a.href = href;
    a.textContent = text;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    if (cls) a.className = cls;
    return a;
  }}

  // The two status accordions. Clean ones are collapsed: a green "nothing to
  // do" panel has nothing worth unfolding, a red one is why you are here.
  function accordion(title, good, goodLabel, badLabel, lead, items, footer) {{
    var box = document.createElement('details');
    box.className = good ? 'good' : 'bad';
    box.open = !good;

    var head = document.createElement('summary');
    head.textContent = title + ' (' + (good ? goodLabel : badLabel) + ')';
    box.appendChild(head);

    var panel = document.createElement('div');
    panel.className = 'panel';

    var first = document.createElement('div');
    first.textContent = lead;
    panel.appendChild(first);

    if (items && items.length) {{
      var list = document.createElement('ul');
      items.forEach(function (item) {{
        var li = document.createElement('li');
        li.appendChild(document.createTextNode('- '));
        li.appendChild(link(ITEM_URL + encodeURIComponent(item.item_id),
                            item.item_id, 'sid'));
        li.appendChild(document.createTextNode(' '));
        li.appendChild(link(ITEM_URL + encodeURIComponent(item.item_id), item.name));
        li.appendChild(document.createTextNode(' ('));
        if (item.creator_id) {{
          li.appendChild(link(USER_URL + encodeURIComponent(item.creator_id),
                              item.creator));
        }} else {{
          li.appendChild(document.createTextNode(item.creator));
        }}
        li.appendChild(document.createTextNode(')'));
        list.appendChild(li);
      }});
      panel.appendChild(list);
    }}

    if (footer) {{
      var tail = document.createElement('div');
      footer.forEach(function (part) {{
        if (part.code) {{
          var code = document.createElement('code');
          code.textContent = part.code;
          tail.appendChild(code);
        }} else if (part.muted) {{
          var note = document.createElement('span');
          note.className = 'note';
          note.textContent = part.text;
          tail.appendChild(note);
        }} else {{
          tail.appendChild(document.createTextNode(part.text));
        }}
      }});
      panel.appendChild(tail);
    }}

    box.appendChild(panel);
    document.getElementById('status').appendChild(box);
  }}

  if (status.dependencies) {{
    var depsOk = status.dependencies.state === 'ok';
    accordion('Dependencies', depsOk, 'OK', 'Dependencies missing',
      depsOk ? 'Dependencies OK. No further action needed.'
             : 'The following items have unmet dependencies:',
      depsOk ? null : status.dependencies.items,
      depsOk ? null : [{{text: 'Run '}}, {{code: 'wrsrcli update'}},
                       {{text: ' to download all dependencies.'}}]);
  }}

  if (status.assets) {{
    var assetsOk = status.assets.state === 'ok';
    var tail = assetsOk ? [] : [{{text: 'Run '}}, {{code: 'wrsrcli update'}},
                                {{text: ' to update.'}}];
    // Say which check produced this. Steam's cached view is worth trusting,
    // but not worth passing off as a live one.
    if (status.assets.source === 'acf') {{
      tail.push({{text: (assetsOk ? '' : ' ') +
        'Checked against Steam\\u2019s own record, as of its last sync. ' +
        'Run wrsrcli update for a live check.', muted: true}});
    }}
    accordion('Asset status', assetsOk, 'OK', 'Update needed',
      assetsOk ? 'All assets are up to date. No further action is needed.'
               : 'The following items need to be updated:',
      assetsOk ? null : status.assets.items,
      tail.length ? tail : null);
  }}

  columns.forEach(function (col) {{
    var th = document.createElement('th');
    th.textContent = col.label;
    if (col.key === '_fold') {{
      th.className = 'fold';
      col.th = th;
      head.appendChild(th);
      return;
    }}
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
      var deps = row.dependencies || [];
      var toggle = null;

      if (deps.length) {{
        toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'toggle';
        toggle.setAttribute('aria-expanded', 'false');
        toggle.setAttribute('aria-label',
          deps.length + ' dependency(ies) for ' + row.item_id);
        toggle.textContent = '\\u25b8';
      }}

      columns.forEach(function (col) {{
        var td = document.createElement('td');
        if (col.cls) td.className = col.cls;

        if (col.key === '_fold') {{
          if (toggle) td.appendChild(toggle);
          tr.appendChild(td);
          return;
        }}

        var value = row[col.key];
        var id = col.link === 'item' ? row.item_id
               : col.link === 'creator' ? row.owner_id : null;

        if (value === '' || value === null || value === undefined) {{
          td.className = (td.className + ' none').trim();
          td.textContent = DASH;
        }} else if (col.link && id && id !== DASH) {{
          td.appendChild(link(
            (col.link === 'item' ? ITEM_URL : USER_URL) + encodeURIComponent(id),
            String(value)));
        }} else {{
          td.textContent = value;
        }}
        tr.appendChild(td);
      }});
      body.appendChild(tr);

      if (!deps.length) return;

      var dtr = document.createElement('tr');
      dtr.className = 'deps';
      dtr.hidden = true;
      var dtd = document.createElement('td');
      dtd.colSpan = columns.length;

      var heading = document.createElement('h2');
      heading.textContent = deps.length === 1 ? 'DEPENDENCY' : 'DEPENDENCIES';
      dtd.appendChild(heading);

      var list = document.createElement('ul');
      deps.forEach(function (dep) {{
        var li = document.createElement('li');
        li.appendChild(document.createTextNode('- '));
        li.appendChild(link(ITEM_URL + encodeURIComponent(dep.item_id),
                            dep.item_id, 'sid'));
        li.appendChild(document.createTextNode(' ' + dep.name + ' ('));
        if (dep.creator_id) {{
          li.appendChild(link(USER_URL + encodeURIComponent(dep.creator_id),
                              dep.creator));
        }} else {{
          li.appendChild(document.createTextNode(dep.creator));
        }}
        li.appendChild(document.createTextNode(') '));
        var state = document.createElement('span');
        state.className = dep.installed ? 'ok' : 'missing';
        state.textContent = dep.installed ? '(OK)' : '(Not installed)';
        li.appendChild(state);
        list.appendChild(li);
      }});
      dtd.appendChild(list);
      dtr.appendChild(dtd);
      body.appendChild(dtr);

      toggle.addEventListener('click', function () {{
        var open = dtr.hidden;
        dtr.hidden = !open;
        toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        toggle.textContent = open ? '\\u25be' : '\\u25b8';
      }});
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
# `link` names the row field holding the id the href is built from, not the
# cell's own text: the Author column shows a name and links by owner_id.
# One set of columns: since D-024 every field has a local source, so there
# is no reduced no-key mode to fall back to.
COLUMNS = [
    {"key": "item_id", "label": "Item ID", "cls": "id", "link": "item"},
    {"key": "name", "label": "Name", "cls": "name"},
    {"key": "item_type", "label": "Type"},
    {"key": "tags", "label": "Tags"},
    {"key": "author", "label": "Author", "link": "creator"},
    {"key": "posted", "label": "Posted", "sort": "posted_sort"},
    {"key": "updated", "label": "Updated", "sort": "updated_sort"},
    {"key": "size", "label": "Size", "sort": "size_sort"},
]


# Prepended when anything has dependencies to show. Unlike author/posted/size,
# dependencies survive in the manifest once scanned, so they are local data at
# render time and the fold is not conditional on a key being set (D-020).
FOLD_COLUMN = {"key": "_fold", "label": "", "cls": "fold"}


def columns_for(rows):
    if any(row.get("dependencies") for row in rows):
        return [FOLD_COLUMN] + COLUMNS
    return COLUMNS


def render(rows, status=None):
    generated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    return _TEMPLATE.format(
        count=len(rows),
        generated=generated,
        mode="",
        data=_embed(rows),
        status=_embed(status or {"dependencies": None, "assets": None}),
        columns=_embed(columns_for(rows)),
    )
