# -*- coding: utf-8 -*-
"""
Cards Grid Preview Add-on for Anki 2.1.50+

Opens a dialog that previews cards from the currently selected deck in a
responsive grid. Hover flips a card to show the back via CSS 3D transform.
A toolbar lets you change columns, card size, page size, and flip all.

Author: You
License: MIT
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from aqt import mw
from aqt.qt import (
    QAction,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QCheckBox,
    QPushButton,
    QSizePolicy,
    QSlider,
  QTimer,
  QApplication,
  QPalette,
  Qt,
)

try:
    # Anki 2.1.50+: use AnkiWebView (Qt5/6 under the hood)
    from aqt.webview import AnkiWebView
except Exception:
    # Fallback
    from aqt.qt import QWebEngineView as AnkiWebView  # type: ignore

from anki.cards import Card
from anki.collection import Collection

ADDON_NAME = "Cards Grid Preview"


def current_deck_id() -> Optional[int]:
    col: Optional[Collection] = mw.col
    if not col:
        return None
    did = mw.col.decks.get_current_id() if hasattr(mw.col.decks, "get_current_id") else mw.col.decks.current().get("id")  # type: ignore[attr-defined]
    return did


def get_deck_cards(col: Collection, did: int, lim: Optional[int] = None) -> List[Card]:
  """Return Card objects for the given deck id.

  Prefer deck cids() if available; fallback to a search by deck name.
  """
  ids: List[int]
  try:
    # Newer Anki API; include child decks if supported
    try:
      ids = list(col.decks.cids(did, True))  # type: ignore[arg-type]
    except Exception:
      ids = list(col.decks.cids(did))  # type: ignore[arg-type]
  except Exception:
    # Fallback: search by deck name
    try:
      deck_name = col.decks.name(did)  # type: ignore[attr-defined]
    except Exception:
      deck = col.decks.get(did)  # type: ignore[attr-defined]
      deck_name = deck.get("name", str(did))
    query = f'deck:"{deck_name}"'
    try:
      ids = col.find_cards(query)  # type: ignore[attr-defined]
    except Exception:
      ids = col.findCards(query)  # type: ignore[attr-defined]

  if lim:
    ids = ids[:lim]
  return [col.get_card(cid) if hasattr(col, 'get_card') else col.getCard(cid) for cid in ids]  # type: ignore[attr-defined]


def render_card_front_back(card: Card) -> Tuple[str, str]:
  """Return rendered HTML for front/back of a card with fallbacks across versions."""
  # Try stable API first
  try:
    q = card.question()
    a = card.answer()
    if q and a:
      return q, a
  except Exception:
    pass
  # Try modern internal API
  try:
    q_a = card.col._renderQA(card, preview=True)  # type: ignore[attr-defined]
    return q_a.get("q", ""), q_a.get("a", "")
  except Exception:
    pass
  # Fallback to fields
  try:
    n = card.note()
    fields = list(n.items())
    front = fields[0][1] if fields else ""
    back = fields[1][1] if len(fields) > 1 else front
    return front, back
  except Exception:
    return "", ""


class CardsGridDialog(QDialog):
  def __init__(self, parent=None) -> None:
    super().__init__(parent)
    self.setWindowTitle(ADDON_NAME)
    # Make window maximizable and resizable
    try:
      self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
    except AttributeError:
      self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)
    self.resize(1200, 850)

    self.web = AnkiWebView()
    try:
      exp = QSizePolicy.Expanding  # Qt5 style
    except AttributeError:
      exp = QSizePolicy.Policy.Expanding  # Qt6 style
    self.web.setSizePolicy(exp, exp)

    # Native toolbar (Qt widgets at the top)
    toolbar = QHBoxLayout()
    try:
      toolbar.setAlignment(Qt.AlignVCenter)
    except AttributeError:
      toolbar.setAlignment(Qt.AlignmentFlag.AlignVCenter)

    # Helper function to create label-input pairs
    def create_labeled_control(label_text: str, control):
      container = QHBoxLayout()
      container.setSpacing(4)  # Small gap between label and control
      label = QLabel(label_text)
      # Set both horizontal and vertical alignment for the label
      try:
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
      except AttributeError:
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
      container.addWidget(label)
      container.addWidget(control)
      return container

    # Columns control
    self.spin_cols = QSpinBox()
    self.spin_cols.setRange(1, 10)
    self.spin_cols.setValue(4)
    self.spin_cols.setMaximumWidth(60)
    toolbar.addLayout(create_labeled_control("Columns:", self.spin_cols))

    # Rows control
    self.spin_rows = QSpinBox()
    self.spin_rows.setRange(1, 20)
    self.spin_rows.setValue(2)
    self.spin_rows.setMaximumWidth(60)
    toolbar.addLayout(create_labeled_control("Rows:", self.spin_rows))

    # Card size control
    self.spin_size = QSpinBox()
    self.spin_size.setRange(120, 600)
    self.spin_size.setValue(270)
    self.spin_size.setMaximumWidth(80)
    toolbar.addLayout(create_labeled_control("Card size (px):", self.spin_size))

    # Font size control
    self.spin_font = QSpinBox()
    self.spin_font.setRange(10, 28)
    self.spin_font.setValue(14)
    self.spin_font.setMaximumWidth(60)
    toolbar.addLayout(create_labeled_control("Font px:", self.spin_font))

    # Add some spacing before aspect ratio slider
    toolbar.addSpacing(15)

    # Aspect ratio slider control
    aspect_container = QHBoxLayout()
    aspect_container.setSpacing(4)
    aspect_label = QLabel("Aspect:")
    try:
      aspect_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    except AttributeError:
      aspect_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    
    self.slider_aspect = QSlider()
    try:
      self.slider_aspect.setOrientation(Qt.Horizontal)
    except AttributeError:
      self.slider_aspect.setOrientation(Qt.Orientation.Horizontal)
    
    # Range from 0.5 (tall) to 2.0 (wide), with 0.75 (3/4) as default
    # Using 50-200 internally, divide by 100 to get actual ratio
    self.slider_aspect.setRange(50, 200)
    self.slider_aspect.setValue(75)  # 3/4 aspect ratio
    self.slider_aspect.setMaximumWidth(100)
    
    # Aspect ratio display label
    self.lbl_aspect = QLabel("3:4")
    self.lbl_aspect.setMinimumWidth(30)
    self.lbl_aspect.setStyleSheet("font-size: 11px; color: #666;")
    
    aspect_container.addWidget(aspect_label)
    aspect_container.addWidget(self.slider_aspect)
    aspect_container.addWidget(self.lbl_aspect)
    toolbar.addLayout(aspect_container)

    # Add some spacing before flip all checkbox
    toolbar.addSpacing(20)

    # Flip all checkbox
    self.chk_flip_all = QCheckBox("Flip all")
    toolbar.addWidget(self.chk_flip_all)

    # Add spacing before pagination controls
    toolbar.addSpacing(20)

    # Pagination controls grouped together
    pagination_layout = QHBoxLayout()
    pagination_layout.setSpacing(4)  # Tight spacing between pagination elements
    
    self.btn_prev = QPushButton("<")
    pagination_layout.addWidget(self.btn_prev)
    
    # Editable page input
    self.spin_page = QSpinBox()
    self.spin_page.setRange(1, 999)
    self.spin_page.setValue(1)
    self.spin_page.setMaximumWidth(50)
    pagination_layout.addWidget(self.spin_page)
    
    self.lbl_page_divider = QLabel(" / ")
    pagination_layout.addWidget(self.lbl_page_divider)
    
    self.lbl_total_pages = QLabel("1")
    self.lbl_total_pages.setMinimumWidth(30)
    pagination_layout.addWidget(self.lbl_total_pages)
    
    self.btn_next = QPushButton(">")
    pagination_layout.addWidget(self.btn_next)
    
    toolbar.addLayout(pagination_layout)

    # Add spacing before refresh button
    toolbar.addSpacing(20)

    # Refresh button
    btn_refresh = QPushButton("Refresh")
    btn_refresh.clicked.connect(self.refresh)
    toolbar.addWidget(btn_refresh)

    layout = QVBoxLayout(self)
    layout.addLayout(toolbar)
    layout.addWidget(self.web)

    # live layout updates (typing or arrows)
    self.spin_cols.valueChanged.connect(lambda _: self._apply_layout())
    self.spin_rows.valueChanged.connect(lambda _: self._apply_layout())
    self.spin_size.valueChanged.connect(lambda _: self._apply_layout())
    self.spin_font.valueChanged.connect(lambda _: self._apply_layout())
    self.slider_aspect.valueChanged.connect(lambda _: self._apply_layout())
    self.spin_cols.editingFinished.connect(self._apply_layout)
    self.spin_rows.editingFinished.connect(self._apply_layout)
    self.spin_size.editingFinished.connect(self._apply_layout)
    self.spin_font.editingFinished.connect(self._apply_layout)
    self.chk_flip_all.stateChanged.connect(self._toggle_flip_all)
    self.btn_prev.clicked.connect(lambda: self._page_delta(-1))
    self.btn_next.clicked.connect(lambda: self._page_delta(1))
    self.spin_page.valueChanged.connect(self._page_changed)

    # load
    self.refresh()

  def _apply_layout(self) -> None:
    try:
      # Calculate aspect ratio from slider (50-200 range, divide by 100)
      aspect_ratio = self.slider_aspect.value() / 100.0
      
      # Update aspect ratio display label
      if aspect_ratio < 0.7:
        self.lbl_aspect.setText("tall")
      elif aspect_ratio < 0.9:
        self.lbl_aspect.setText("~3:4")
      elif aspect_ratio < 1.1:
        self.lbl_aspect.setText("~1:1")
      elif aspect_ratio < 1.4:
        self.lbl_aspect.setText("~4:3")
      else:
        self.lbl_aspect.setText("wide")
      
      js = (
        f"document.documentElement.style.setProperty('--cols', {self.spin_cols.value()});"
        f"document.documentElement.style.setProperty('--rows', {self.spin_rows.value()});"
        f"document.documentElement.style.setProperty('--card-size', '{self.spin_size.value()}px');"
        f"document.documentElement.style.setProperty('--card-font-size', '{self.spin_font.value()}px');"
        f"document.documentElement.style.setProperty('--card-aspect', '{aspect_ratio}');"
        f"document.getElementById('grid').style.gridTemplateColumns = 'repeat({self.spin_cols.value()}, {self.spin_size.value()}px)';"
        f"if (window.__gridRelayout) window.__gridRelayout();"
      )
      self.web.eval(js)
      # Update page info after layout change
      QTimer.singleShot(100, self._refresh_page_info)  # type: ignore[attr-defined]
    except Exception:
      pass

  def _page_delta(self, delta: int) -> None:
    try:
      self.web.eval(f"if(window.__gridPg) window.__gridPg({delta});")
      # Update page info after navigation
      QTimer.singleShot(100, self._refresh_page_info)  # type: ignore[attr-defined]
    except Exception:
      pass

  def _page_changed(self) -> None:
    """Handle manual page input change"""
    try:
      target_page = self.spin_page.value()
      self.web.eval(f"if(window.__gridGoToPage) window.__gridGoToPage({target_page});")
      # Update page info after navigation
      QTimer.singleShot(100, self._refresh_page_info)  # type: ignore[attr-defined]
    except Exception:
      pass

  def _refresh_page_info(self) -> None:
    """Get current page info from JavaScript and update the controls"""
    try:
      def callback(result):
        if result and isinstance(result, dict):
          current = result.get('page', 1)
          total = result.get('pages', 1)
          self.spin_page.blockSignals(True)
          self.spin_page.setValue(current)
          self.spin_page.setRange(1, max(1, total))
          self.spin_page.blockSignals(False)
          self.lbl_total_pages.setText(str(total))
      
      self.web.evalWithCallback("({page: state.page, pages: state.pages})", callback)
    except Exception:
      pass

  def _update_page_info(self, current: int, total: int) -> None:
    """Update the page info label"""
    try:
      self.lbl_page_info.setText(f"{current} / {total}")
    except Exception:
      pass

  def _toggle_flip_all(self) -> None:
    try:
      state = "true" if self.chk_flip_all.isChecked() else "false"
      self.web.eval(f"document.body.classList.toggle('flip-all', {state});")
    except Exception:
      pass

  def _build_html(self, cards: List[Card]) -> Tuple[str, str]:
    col = mw.col

    # Render cards
    items: List[dict] = []
    for c in cards:
      q, a = render_card_front_back(c)
      # keep only the back side (drop front + hr + back)
      import re as _re
      parts = _re.split(r"(?is)<hr[^>]*>", a, maxsplit=1)
      a_only = parts[-1] if len(parts) > 1 else a
      items.append({"q": q, "a": a, "aOnly": a_only})

    import json as _json
    items_json = _json.dumps(items)

    cols = str(self.spin_cols.value())
    rows = str(self.spin_rows.value())
    card_size = str(self.spin_size.value())
    font_size = str(self.spin_font.value())
    aspect_ratio = str(self.slider_aspect.value() / 100.0)
    flip_all = "true" if self.chk_flip_all.isChecked() else "false"

    # HTML without inline script and without duplicate controls
    html = """
<!DOCTYPE html>
<html>
<head>
<meta charset='utf-8'/>
<meta http-equiv='Content-Security-Policy' content="default-src 'self' data: blob: filesystem: https:; style-src 'self' 'unsafe-inline' https:; script-src 'self' 'unsafe-inline' https:;">
<title>Cards Grid Preview</title>
<style>
:root { --card-size: %%CARD_SIZE%%px; --cols: %%COLS%%; --card-aspect: %%ASPECT_RATIO%%; --card-radius: 12px; --card-font-size: %%FONT_SIZE%%px; }
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }
.grid { padding: 16px; display: grid; gap: 16px; justify-content: center; }
.card { perspective: 1200px; width: var(--card-size); height: calc(var(--card-size) / var(--card-aspect)); /* dynamic height based on aspect ratio */ aspect-ratio: var(--card-aspect); justify-self: center; cursor: pointer; display: block;}
.inner { position: relative; width: 100%; height: 100%; transform-style: preserve-3d; transition: transform 0.6s cubic-bezier(.2,.7,.2,1); border-radius: var(--card-radius); will-change: transform; }
.card:hover .inner, .card.flip .inner, body.flip-all .inner { transform: rotateY(180deg); }
.face { position: absolute; inset: 0; backface-visibility: hidden; overflow: auto; border-radius: var(--card-radius); border: 1px solid #ccc; background: #fff; color: #111; padding: 10px; box-shadow: 0 2px 12px rgba(0,0,0,.15); font-size: var(--card-font-size); line-height: 1.3; }
.back { transform: rotateY(180deg); }
.card .face table { max-width: 100%; overflow: auto; display: block; }

/* spinner removed (was causing overlay issues) */
</style>
</head>
<body>
<div id=\"grid\" class=\"grid\"></div>

</body>
</html>
"""
    html = (html
        .replace("%%CARD_SIZE%%", card_size)
        .replace("%%COLS%%", cols)
        .replace("%%FONT_SIZE%%", font_size)
        .replace("%%ASPECT_RATIO%%", aspect_ratio)
        )

    # JavaScript to inject after load
    js = """
const all = { items: %%ITEMS%%, cols: %%COLS%%, rows: %%ROWS%%, cardSize: %%CARD_SIZE%%, fontSize: %%FONT_SIZE%%, aspectRatio: %%ASPECT_RATIO%%, flipAll: %%FLIP_ALL%% };
document.documentElement.style.setProperty('--cols', all.cols);
document.documentElement.style.setProperty('--rows', all.rows);
document.documentElement.style.setProperty('--card-size', all.cardSize + 'px');
document.documentElement.style.setProperty('--card-font-size', all.fontSize + 'px');
document.documentElement.style.setProperty('--card-aspect', all.aspectRatio);
document.body.classList.toggle('flip-all', all.flipAll);

const grid = document.getElementById('grid');
grid.style.gridTemplateColumns = `repeat(${all.cols}, ${all.cardSize}px)`;
let firstRender = true;

// Pagination state and helpers
const state = { page: 1, pages: 1 };
function pageSize() {
  return all.rows * all.cols;
}
function clampPage() {
  const ps = pageSize();
  state.pages = Math.max(1, Math.ceil(all.items.length / ps));
  if (state.page > state.pages) state.page = state.pages;
  if (state.page < 1) state.page = 1;
}
window.__gridPg = function(delta) { 
  state.page += delta; 
  clampPage(); 
  render(); 
};
window.__gridGoToPage = function(page) {
  state.page = page;
  clampPage();
  render();
};
window.__gridRelayout = function() {
  // Read back CSS variables to keep JS in sync
  const cs = getComputedStyle(document.documentElement);
  const cols = parseInt(cs.getPropertyValue('--cols')) || all.cols;
  const rows = parseInt(cs.getPropertyValue('--rows')) || all.rows;
  const size = parseInt(cs.getPropertyValue('--card-size')) || all.cardSize;
  const aspect = parseFloat(cs.getPropertyValue('--card-aspect')) || all.aspectRatio;
  all.cols = cols; all.rows = rows; all.cardSize = size; all.aspectRatio = aspect;
  grid.style.gridTemplateColumns = `repeat(${all.cols}, ${all.cardSize}px)`;
  clampPage();
  render();
};
window.addEventListener('resize', () => {
  clampPage();
  render();
});

// Load MathJax v3 if not present
if (!window.__MJX_LOADING && !(window.MathJax && MathJax.typesetPromise)) {
  window.__MJX_LOADING = true;
  window.MathJax = {
    tex: { 
      inlineMath: [['\\\\(', '\\\\)'], ['$', '$']], 
      displayMath: [['\\\\[', '\\\\]']],
      processEscapes: true,
      processEnvironments: false,
      processRefs: false,
      // Load packages to extend TeX support (mostly the ones in Anki's default header)
      packages: {'[+]': ['base', 'ams', 'newcommand', 'mathtools', 'physics', 'braket', 'cancel', 'color']}
    },
    loader: {
      load: ['[tex]/mathtools', '[tex]/color', '[tex]/physics', '[tex]/braket', '[tex]/cancel']
    },
    startup: { typeset: false },
    options: {
      skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code'],
      ignoreHtmlClass: 'tex2jax_ignore',
      processHtmlClass: 'tex2jax_process'
    }
  };
  const s = document.createElement('script');
  s.src = 'https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js';
  s.async = true;
  s.onload = () => { window.__MJX_READY = true; };
  document.head.appendChild(s);
}

function typeset() {
  if (window.MathJax && MathJax.typesetPromise) {
    MathJax.typesetPromise([grid]).catch(console.warn);
  }
  // No spinner to hide; just run MathJax if available
}

// Make typeset available globally for initial render
window.typeset = typeset;

function render() {
  const items = all.items;
  grid.innerHTML = '';
  // no spinner: we run typesetting but don't block UI
  clampPage();
  const ps = pageSize();
  const start = (state.page - 1) * ps;
  const end = Math.min(items.length, start + ps);
  for (let i=start; i<end; i++) {
  const it = items[i];
  const el = document.createElement('div');
  el.className = 'card';
  el.innerHTML = '<div class="inner">' +
    '<div class="face front">' + it.q + '</div>' +
    '<div class="face back">' + it.aOnly + '</div>' +
    '</div>';
    el.addEventListener('click', () => el.classList.toggle('flip'));
  grid.appendChild(el);
  }
  typeset();
  firstRender = false;
}

render();
"""
    js = (js
        .replace("%%ITEMS%%", items_json)
        .replace("%%COLS%%", cols)
        .replace("%%ROWS%%", rows)
        .replace("%%CARD_SIZE%%", card_size)
        .replace("%%FONT_SIZE%%", font_size)
        .replace("%%ASPECT_RATIO%%", aspect_ratio)
        .replace("%%FLIP_ALL%%", flip_all)
        )

    return html, js

  def refresh(self) -> None:
    col = mw.col
    did = current_deck_id()
    if not col or did is None:
      self.web.setHtml("<h3 style='margin:1rem'>No collection or no deck selected.</h3>")
      return

    cards = get_deck_cards(col, did)
    if not cards:
      self.web.setHtml("<h3 style='margin:1rem'>This deck has no cards to preview.</h3>")
      return

    html, js = self._build_html(cards)
    try:
      self.web.setHtml(html)
    except Exception:
      self.web.stdHtml(html, context=self)  # type: ignore
    try:
      QTimer.singleShot(0, lambda: self.web.eval(js))  # type: ignore[attr-defined]
      # Additional delay for MathJax initial render
      QTimer.singleShot(500, lambda: self.web.eval("if(window.typeset) window.typeset();"))  # type: ignore[attr-defined]
      # Initialize page info after everything loads
      QTimer.singleShot(600, self._refresh_page_info)  # type: ignore[attr-defined]
    except Exception:
      pass


def open_cards_grid() -> None:
    dlg = CardsGridDialog(mw)
    dlg.show()
    dlg.raise_()


def on_profile_loaded() -> None:
    act = QAction(ADDON_NAME, mw)
    act.setShortcut("Ctrl+Shift+G")
    act.triggered.connect(open_cards_grid)
    mw.form.menuTools.addAction(act)


# Hook when profile is loaded so menu is available
try:
  from aqt import gui_hooks
  # Anki 25.09.2 calls this hook without arguments
  gui_hooks.profile_did_open.append(on_profile_loaded)
except Exception:
  try:
    # Older hook API
    from anki.hooks import addHook  # type: ignore
    addHook('profileLoaded', on_profile_loaded)
  except Exception:
    # Last resort: run when addon is imported
    on_profile_loaded()
