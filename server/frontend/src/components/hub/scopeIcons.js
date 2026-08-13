// Shared scope/type icon set + labels for the Hub. Used by the search bar's scope
// dropdown (HubView) and the search-results type badges (HubSearchResults) — kept
// in one module so the two never drift out of sync.
export const scopes = [
  { value: 'all', label: 'Tout' },
  { value: 'track', label: 'Tracks' },
  { value: 'artist', label: 'Artistes' },
  { value: 'set', label: 'Sets' },
  { value: 'playlist', label: 'Playlists' },
  { value: 'genre', label: 'Genres' },
]

export const scopeIcons = {
  all: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="9"/><path d="M12 3v18M3 12h18" stroke-linecap="round"/></svg>`,
  track: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="16" r="4"/><path d="M16 16V4l-8 2" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  artist: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="8" r="4"/><path d="M5 20a7 7 0 0 1 14 0" stroke-linecap="round"/></svg>`,
  set: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="1" fill="currentColor"/></svg>`,
  playlist: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M3 6h18M3 12h12M3 18h8"/></svg>`,
  genre: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M3 12V5a2 2 0 0 1 2-2h7l9 9-7 7-9-9z"/><circle cx="7.5" cy="7.5" r="1.2" fill="currentColor"/></svg>`,
}
