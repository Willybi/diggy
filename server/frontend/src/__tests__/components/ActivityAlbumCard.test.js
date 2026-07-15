import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ActivityAlbumCard from '../../components/ActivityAlbumCard.vue'

function makeAlbum(tracks) {
  return {
    album_id: '900',
    album_title: 'Test EP',
    artist_name: 'Someone',
    release_date: '2026-07-12',
    cover_id: tracks.find((t) => t.catalog_id && t.has_artwork)?.catalog_id ?? null,
    tracks,
  }
}

// The list is collapsed by default → expand before inspecting the track titles.
async function mountExpanded(tracks) {
  const wrapper = mount(ActivityAlbumCard, { props: { album: makeAlbum(tracks) } })
  await wrapper.find('.ac-toggle').trigger('click')
  return wrapper
}

describe('ActivityAlbumCard track title rendering', () => {
  it('renders a crawled track title as a clickable button that emits open', async () => {
    const wrapper = await mountExpanded([
      { id: 1, title: 'Crawled', catalog_id: 77, has_artwork: true, has_preview: false },
    ])
    const title = wrapper.find('.ac-ititle')
    expect(title.element.tagName).toBe('BUTTON')
    await title.trigger('click')
    expect(wrapper.emitted('open')).toBeTruthy()
  })

  it('renders a non-crawled track with an external_url as a link', async () => {
    const wrapper = await mountExpanded([
      { id: 2, title: 'External', catalog_id: null, external_url: 'https://deezer.com/track/1' },
    ])
    const title = wrapper.find('.ac-ititle')
    expect(title.element.tagName).toBe('A')
    expect(title.attributes('href')).toBe('https://deezer.com/track/1')
  })

  it('renders a track with no catalog_id and no external_url as an inert span (no navigation)', async () => {
    const wrapper = await mountExpanded([
      { id: 3, title: 'Orphan', catalog_id: null, external_url: null },
    ])
    const title = wrapper.find('.ac-ititle')
    expect(title.element.tagName).toBe('SPAN')
    expect(title.classes()).toContain('ac-ititle--inert')
    // No interactive element for this title → no /catalog/null navigation.
    expect(wrapper.find('a.ac-ititle').exists()).toBe(false)
    expect(wrapper.find('button.ac-ititle').exists()).toBe(false)
    expect(wrapper.emitted('open')).toBeFalsy()
  })
})
