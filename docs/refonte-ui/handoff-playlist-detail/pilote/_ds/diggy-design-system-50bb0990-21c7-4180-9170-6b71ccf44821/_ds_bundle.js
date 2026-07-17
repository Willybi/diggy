/* @ds-bundle: {"format":4,"namespace":"DiggyDesignSystem_50bb09","components":[{"name":"Badge","sourcePath":"components/badges/Badge.jsx"},{"name":"Button","sourcePath":"components/buttons/Button.jsx"},{"name":"PageHead","sourcePath":"components/page/PageHead.jsx"},{"name":"TrackTable","sourcePath":"components/table/TrackTable.jsx"},{"name":"StyleTag","sourcePath":"components/tags/StyleTag.jsx"}],"sourceHashes":{"components/badges/Badge.jsx":"9aa5fbe9a7a2","components/buttons/Button.jsx":"0fd30f6fe515","components/page/PageHead.jsx":"54f1be46526c","components/table/TrackTable.jsx":"7c94727d7f70","components/tags/StyleTag.jsx":"972422fa178f","ui_kits/diggy/CatalogScreen.jsx":"a20448379d45","ui_kits/diggy/Sidebar.jsx":"2dce4e1e175b"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.DiggyDesignSystem_50bb09 = window.DiggyDesignSystem_50bb09 || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/badges/Badge.jsx
try { (() => {
const nanoMono = {
  font: '600 var(--fs-nano) var(--font-mono)',
  letterSpacing: '0.08em',
  textTransform: 'uppercase'
};

/**
 * Diggy badge — library status, platform keys (uppercase mono nano), rating.
 * Visuals sourced from the /design-system reference page (§6 Badges).
 */
function Badge({
  variant = 'neutral',
  children
}) {
  const base = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 'var(--space-1)',
    borderRadius: 'var(--r-pill)',
    whiteSpace: 'nowrap'
  };
  if (variant === 'in-lib') {
    return /*#__PURE__*/React.createElement("span", {
      style: {
        ...base,
        padding: '3px var(--space-25)',
        background: 'var(--pos-soft)',
        color: 'var(--pos-ink)',
        font: '600 var(--fs-xs) var(--font-ui)'
      }
    }, "\u2713 ", children ?? 'In lib');
  }
  if (variant === 'not-in-lib') {
    return /*#__PURE__*/React.createElement("span", {
      style: {
        ...base,
        padding: '3px var(--space-25)',
        background: 'var(--surface-2)',
        color: 'var(--ink-3)',
        font: '500 var(--fs-xs) var(--font-ui)'
      }
    }, children ?? 'Not in lib');
  }
  if (variant === 'platform') {
    return /*#__PURE__*/React.createElement("span", {
      style: {
        ...base,
        padding: '3px var(--space-2)',
        borderRadius: 'var(--r-xs)',
        background: 'var(--surface-2)',
        border: '1px solid var(--line)',
        color: 'var(--ink-2)',
        ...nanoMono
      }
    }, children);
  }
  if (variant === 'rating') {
    return /*#__PURE__*/React.createElement("span", {
      style: {
        ...base,
        gap: 'var(--space-15)',
        padding: '3px var(--space-25)',
        background: 'var(--accent-soft)',
        color: 'var(--accent-ink)',
        font: '600 var(--fs-xs) var(--font-mono)'
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        width: 26,
        height: 5,
        borderRadius: 'var(--r-pill)',
        background: 'var(--accent)'
      }
    }), children);
  }
  return /*#__PURE__*/React.createElement("span", {
    style: {
      ...base,
      padding: '3px var(--space-25)',
      background: 'var(--surface-2)',
      color: 'var(--ink-2)',
      font: '500 var(--fs-xs) var(--font-ui)'
    }
  }, children);
}
Object.assign(__ds_scope, { Badge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/badges/Badge.jsx", error: String((e && e.message) || e) }); }

// components/buttons/Button.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Diggy button — wraps the shared .btn classes from styles/buttons.css.
 * Variants map 1:1 to the codebase classes.
 */
function Button({
  variant = 'ghost',
  size,
  disabled = false,
  icon,
  children,
  onClick,
  ...rest
}) {
  const cls = ['btn', variant === 'accent' && 'btn--accent', variant === 'ghost-accent' && 'btn--ghost-accent', variant === 'danger' && 'btn--danger', size === 'sm' && 'btn--sm'].filter(Boolean).join(' ');
  return /*#__PURE__*/React.createElement("button", _extends({
    type: "button",
    className: cls,
    disabled: disabled,
    onClick: onClick,
    style: disabled ? {
      opacity: 0.45,
      cursor: 'default'
    } : undefined
  }, rest), icon, children);
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/buttons/Button.jsx", error: String((e && e.message) || e) }); }

// components/page/PageHead.jsx
try { (() => {
/**
 * Diggy PageHead — shared header row for listing views (.page-head, page.css).
 * View title at --fs-lg + factual count subtitle; actions right-aligned.
 */
function PageHead({
  title,
  count,
  actions
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "page-head"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("h1", {
    style: {
      margin: 0,
      font: '700 var(--fs-lg) var(--font-ui)',
      color: 'var(--ink)'
    }
  }, title), count != null && /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 'var(--space-05)',
      font: '500 var(--fs-xs) var(--font-mono)',
      color: 'var(--ink-3)'
    }
  }, count)), actions && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 'var(--space-2)',
      alignItems: 'center'
    }
  }, actions));
}
Object.assign(__ds_scope, { PageHead });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/page/PageHead.jsx", error: String((e && e.message) || e) }); }

// components/table/TrackTable.jsx
try { (() => {
/**
 * Diggy TrackTable — dense, density-aware table. Row height = var(--row-h),
 * cell padding = var(--pad) (both driven by [data-density]); cell text uses the
 * table-reserved sizes --fs-table / --fs-table-sm; headers --fs-label uppercase.
 * Row states: isPlaying → --accent-wash tint; liked → --pos-wash.
 */
function TrackTable({
  columns,
  rows,
  onRowClick
}) {
  return /*#__PURE__*/React.createElement("table", {
    style: {
      width: '100%',
      borderCollapse: 'collapse',
      font: '400 var(--fs-table) var(--font-ui)',
      color: 'var(--ink)'
    }
  }, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, columns.map(c => /*#__PURE__*/React.createElement("th", {
    key: c.key,
    style: {
      textAlign: c.align || 'left',
      padding: 'var(--space-2) var(--pad)',
      font: '600 var(--fs-label) var(--font-mono)',
      letterSpacing: '0.08em',
      textTransform: 'uppercase',
      color: 'var(--ink-3)',
      borderBottom: '1px solid var(--line-2)'
    }
  }, c.label)))), /*#__PURE__*/React.createElement("tbody", null, rows.map((row, i) => /*#__PURE__*/React.createElement("tr", {
    key: row.id ?? i,
    onClick: onRowClick ? () => onRowClick(row) : undefined,
    style: {
      height: 'var(--row-h)',
      background: row.isPlaying ? 'var(--accent-wash)' : row.liked ? 'var(--pos-wash)' : 'transparent',
      cursor: onRowClick ? 'pointer' : 'default'
    }
  }, columns.map(c => /*#__PURE__*/React.createElement("td", {
    key: c.key,
    style: {
      textAlign: c.align || 'left',
      padding: '0 var(--pad)',
      borderBottom: '1px solid var(--line)',
      font: c.mono ? '500 var(--fs-table-sm) var(--font-mono)' : undefined,
      color: c.dim ? 'var(--ink-2)' : undefined,
      whiteSpace: 'nowrap'
    }
  }, row[c.key]))))));
}
Object.assign(__ds_scope, { TrackTable });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/table/TrackTable.jsx", error: String((e && e.message) || e) }); }

// components/tags/StyleTag.jsx
try { (() => {
const PILLARS = {
  house: {
    hue: 'var(--hue-house)',
    label: 'House'
  },
  techno: {
    hue: 'var(--hue-techno)',
    label: 'Techno'
  },
  trance: {
    hue: 'var(--hue-trance)',
    label: 'Trance'
  },
  dnb: {
    hue: 'var(--hue-dnb)',
    label: 'Drum & Bass'
  },
  hardcore: {
    hue: 'var(--hue-hardcore)',
    label: 'Hardcore'
  },
  harddance: {
    hue: 'var(--hue-harddance)',
    label: 'Hard Dance'
  },
  autres: {
    hue: '0',
    label: 'Autres'
  }
};

/**
 * Diggy StyleTag — genre-pillar chip. One hue per pillar; taxonomy DEPTH
 * lowers the chip's chroma without ever moving the hue (diggy-tokens.css
 * "GENRE PILLARS v2"):  bg chroma ×(1−0.17d), dot L+0.04d & chroma ×(1−0.19d).
 * "autres" renders grey (chroma 0).
 */
function StyleTag({
  pillar = 'autres',
  depth = 0,
  children
}) {
  const p = PILLARS[pillar] || PILLARS.autres;
  const grey = pillar === 'autres';
  const d = Math.max(0, depth);
  const bgC = grey ? '0' : `calc(var(--tag-bg-c) * ${1 - 0.17 * d})`;
  const fgC = grey ? '0' : 'var(--tag-fg-c)';
  const dotL = `calc(var(--tag-dot-l) + ${0.04 * d})`;
  const dotC = grey ? '0' : `calc(var(--tag-dot-c) * ${1 - 0.19 * d})`;
  return /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 'var(--space-15)',
      padding: '3px var(--space-25)',
      borderRadius: 'var(--r-pill)',
      background: `oklch(var(--tag-bg-l) ${bgC} ${p.hue})`,
      color: `oklch(var(--tag-fg-l) ${fgC} ${p.hue})`,
      font: '500 var(--fs-xs) var(--font-ui)',
      whiteSpace: 'nowrap'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 7,
      height: 7,
      borderRadius: 'var(--r-pill)',
      background: `oklch(${dotL} ${dotC} ${p.hue})`
    }
  }), children ?? p.label);
}
Object.assign(__ds_scope, { StyleTag });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/tags/StyleTag.jsx", error: String((e && e.message) || e) }); }

// ui_kits/diggy/CatalogScreen.jsx
try { (() => {
function CatalogScreen() {
  const {
    PageHead,
    Button,
    Badge,
    StyleTag,
    TrackTable
  } = window.DiggyDesignSystem_50bb09;
  const [query, setQuery] = React.useState('');
  const [playing, setPlaying] = React.useState(1);
  const data = [{
    id: 1,
    title: 'Voodoo Ray',
    artist: 'A Guy Called Gerald',
    pillar: 'house',
    genre: 'Acid House',
    depth: 1,
    bpm: '122',
    key: '09A',
    dur: '03:51',
    inLib: true,
    liked: false,
    platform: 'DEEZER'
  }, {
    id: 2,
    title: 'Spastik',
    artist: 'Plastikman',
    pillar: 'techno',
    genre: 'Techno',
    depth: 0,
    bpm: '134',
    key: '05A',
    dur: '06:42',
    inLib: true,
    liked: true,
    platform: 'TIDAL'
  }, {
    id: 3,
    title: 'Age of Love',
    artist: 'Age of Love',
    pillar: 'trance',
    genre: 'Trance',
    depth: 0,
    bpm: '136',
    key: '11B',
    dur: '05:12',
    inLib: true,
    liked: false,
    platform: 'DEEZER'
  }, {
    id: 4,
    title: 'Valley of the Shadows',
    artist: 'Origin Unknown',
    pillar: 'dnb',
    genre: 'Jungle',
    depth: 1,
    bpm: '160',
    key: '02A',
    dur: '04:58',
    inLib: false,
    liked: false,
    platform: 'SPOTIFY'
  }, {
    id: 5,
    title: 'Thunderdome',
    artist: 'The Prophet',
    pillar: 'hardcore',
    genre: 'Gabber',
    depth: 1,
    bpm: '180',
    key: '07A',
    dur: '04:05',
    inLib: false,
    liked: false,
    platform: 'TIDAL'
  }, {
    id: 6,
    title: 'Wonderful Days',
    artist: 'Charly Lownoise',
    pillar: 'harddance',
    genre: 'Happy Hardcore',
    depth: 2,
    bpm: '168',
    key: '10B',
    dur: '03:44',
    inLib: true,
    liked: true,
    platform: 'DEEZER'
  }];
  const filtered = data.filter(t => !query || (t.title + ' ' + t.artist + ' ' + t.genre).toLowerCase().includes(query.toLowerCase()));
  const columns = [{
    key: 'titleCell',
    label: 'Titre'
  }, {
    key: 'artist',
    label: 'Artiste',
    dim: true
  }, {
    key: 'genreCell',
    label: 'Genre'
  }, {
    key: 'bpm',
    label: 'BPM',
    align: 'right',
    mono: true
  }, {
    key: 'key',
    label: 'Key',
    align: 'right',
    mono: true
  }, {
    key: 'dur',
    label: 'Durée',
    align: 'right',
    mono: true
  }, {
    key: 'platformCell',
    label: 'Source'
  }, {
    key: 'libCell',
    label: 'Lib',
    align: 'right'
  }];
  const rows = filtered.map(t => ({
    ...t,
    isPlaying: t.id === playing,
    titleCell: /*#__PURE__*/React.createElement("span", {
      style: {
        fontWeight: 500
      }
    }, t.title),
    genreCell: /*#__PURE__*/React.createElement(StyleTag, {
      pillar: t.pillar,
      depth: t.depth
    }, t.genre),
    platformCell: /*#__PURE__*/React.createElement(Badge, {
      variant: "platform"
    }, t.platform),
    libCell: t.inLib ? /*#__PURE__*/React.createElement(Badge, {
      variant: "in-lib"
    }) : /*#__PURE__*/React.createElement(Badge, {
      variant: "not-in-lib"
    })
  }));
  return /*#__PURE__*/React.createElement("main", {
    style: {
      flex: 1,
      minWidth: 0,
      maxWidth: 'var(--page-max-w)'
    }
  }, /*#__PURE__*/React.createElement(PageHead, {
    title: "Catalogue",
    count: `${filtered.length} éléments`,
    actions: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Button, {
      size: "sm"
    }, "Filtrer"), /*#__PURE__*/React.createElement(Button, {
      variant: "accent",
      size: "sm"
    }, "Ajouter un track"))
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 'var(--space-2)',
      padding: '0 var(--page-px) var(--space-4)',
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement("input", {
    value: query,
    onChange: e => setQuery(e.target.value),
    placeholder: "Rechercher un track\u2026",
    style: {
      flex: '0 1 320px',
      height: 38,
      padding: '0 var(--space-3)',
      borderRadius: 'var(--r-sm)',
      border: '1px solid var(--line-2)',
      background: 'var(--surface)',
      color: 'var(--ink)',
      font: '400 var(--fs-input) var(--font-ui)',
      outline: 'none',
      boxSizing: 'border-box'
    }
  }), /*#__PURE__*/React.createElement(Button, {
    variant: "ghost-accent",
    size: "sm"
  }, "House"), /*#__PURE__*/React.createElement(Button, {
    size: "sm"
  }, "Techno")), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '0 var(--page-px)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      background: 'var(--surface)',
      border: '1px solid var(--line)',
      borderRadius: 'var(--r-md)',
      overflow: 'hidden',
      boxShadow: 'var(--shadow-sm)'
    }
  }, /*#__PURE__*/React.createElement(TrackTable, {
    columns: columns,
    rows: rows,
    onRowClick: r => setPlaying(r.id)
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 'var(--space-3) var(--space-05)',
      font: '500 var(--fs-xs) var(--font-mono)',
      color: 'var(--ink-3)'
    }
  }, "Clic sur une ligne = lecture (tint --accent-wash) \xB7 lignes lik\xE9es en --pos-wash")));
}
window.DiggyCatalogScreen = CatalogScreen;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/diggy/CatalogScreen.jsx", error: String((e && e.message) || e) }); }

// ui_kits/diggy/Sidebar.jsx
try { (() => {
function Sidebar({
  current,
  onNav
}) {
  const items = ['Hub', 'Catalogue', 'Sets', 'Artistes', 'Genres', 'Watchlist', 'Collections'];
  return /*#__PURE__*/React.createElement("aside", {
    style: {
      width: 'var(--sidebar-w)',
      flex: '0 0 auto',
      borderRight: '1px solid var(--line)',
      background: 'var(--surface)',
      display: 'flex',
      flexDirection: 'column',
      padding: 'var(--space-4) var(--space-3)',
      gap: 'var(--space-05)',
      boxSizing: 'border-box'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      font: '700 var(--fs-md) var(--font-ui)',
      color: 'var(--ink)',
      padding: 'var(--space-2) var(--space-25) var(--space-4)'
    }
  }, "Diggy"), items.map(it => {
    const active = it === current;
    return /*#__PURE__*/React.createElement("a", {
      key: it,
      onClick: () => onNav(it),
      style: {
        display: 'flex',
        alignItems: 'center',
        padding: 'var(--space-2) var(--space-25)',
        borderRadius: 'var(--r-sm)',
        font: `${active ? 600 : 500} var(--fs-sm) var(--font-ui)`,
        color: active ? 'var(--accent-ink)' : 'var(--ink-2)',
        background: active ? 'var(--accent-soft)' : 'transparent',
        cursor: 'pointer'
      }
    }, it);
  }));
}
window.DiggySidebar = Sidebar;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/diggy/Sidebar.jsx", error: String((e && e.message) || e) }); }

__ds_ns.Badge = __ds_scope.Badge;

__ds_ns.Button = __ds_scope.Button;

__ds_ns.PageHead = __ds_scope.PageHead;

__ds_ns.TrackTable = __ds_scope.TrackTable;

__ds_ns.StyleTag = __ds_scope.StyleTag;

})();
