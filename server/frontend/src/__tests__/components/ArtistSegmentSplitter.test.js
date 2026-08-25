import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import ArtistSegmentSplitter from '../../components/admin/ArtistSegmentSplitter.vue'
import api from '../../utils/api.js'

// The live Deezer signal calls the admin search endpoint through the shared api
// client — mocked here (no network, no router/pinia pulled in).
vi.mock('../../utils/api.js', () => ({ default: { get: vi.fn() } }))

// Fake timers everywhere: the component debounces its Deezer lookups (400 ms),
// so interaction-only tests never fire a request unless timers are advanced.
beforeEach(() => {
  vi.useFakeTimers()
  api.get.mockReset()
  api.get.mockResolvedValue({ data: [] })
})

afterEach(() => {
  vi.useRealTimers()
})

const chipTexts = (wrapper) =>
  wrapper.findAll('.seg-chip').map((c) => c.find('.seg-chip-text').text())

const searchedQueries = () => api.get.mock.calls.map(([, opts]) => opts.params.q)

describe('ArtistSegmentSplitter — segmentation', () => {
  it('renders default chips with the "&" separators dropped (struck through)', () => {
    const wrapper = mount(ArtistSegmentSplitter, {
      props: { raw: 'Adam Beyer & Ida Engberg & Foo' },
    })
    expect(chipTexts(wrapper)).toEqual(['Adam Beyer', '&', 'Ida Engberg', '&', 'Foo'])
    const chips = wrapper.findAll('.seg-chip')
    expect(chips[1].classes()).toContain('deleted')
    expect(chips[3].classes()).toContain('deleted')
    expect(chips[0].classes()).not.toContain('deleted')
  })

  it('emits only the kept tokens, without the dropped separators', async () => {
    const wrapper = mount(ArtistSegmentSplitter, {
      props: { raw: 'Adam Beyer & Ida Engberg & Foo' },
    })
    await wrapper.find('.btn-seg-confirm').trigger('click')
    expect(wrapper.emitted('confirm')[0][0]).toEqual(['Adam Beyer', 'Ida Engberg', 'Foo'])
  })

  it('drops parentheses by default, leaving clean tokens', async () => {
    const wrapper = mount(ArtistSegmentSplitter, {
      props: { raw: 'Artist (feat Other)' },
    })
    // Each of "(", "feat", ")" is a struck-through droppable chip.
    expect(chipTexts(wrapper)).toEqual(['Artist', '(', 'feat', 'Other', ')'])
    await wrapper.find('.btn-seg-confirm').trigger('click')
    expect(wrapper.emitted('confirm')[0][0]).toEqual(['Artist', 'Other'])
  })

  it('splits a glued "/" by default, re-glued by restoring "/" + merging (AC/DC)', async () => {
    const wrapper = mount(ArtistSegmentSplitter, {
      props: { raw: 'AC/DC' },
    })
    expect(chipTexts(wrapper)).toEqual(['AC', '/', 'DC'])

    // Restore the dropped "/" chip, then merge both boundaries → glued name back.
    await wrapper.findAll('.seg-trash')[1].trigger('click')
    const cuts = wrapper.findAll('.seg-cut')
    await cuts[0].trigger('click')
    await cuts[1].trigger('click')
    expect(chipTexts(wrapper)).toEqual(['AC/DC'])

    await wrapper.find('.btn-seg-confirm').trigger('click')
    expect(wrapper.emitted('confirm')[0][0]).toEqual(['AC/DC'])
  })

  it('merging across a dropped "&" joins the words with a single space', async () => {
    const wrapper = mount(ArtistSegmentSplitter, {
      props: { raw: 'A & B' },
    })
    const cutButtons = wrapper.findAll('.seg-cut')
    await cutButtons[0].trigger('click')
    await cutButtons[1].trigger('click')
    expect(chipTexts(wrapper)).toEqual(['A B'])

    await wrapper.find('.btn-seg-confirm').trigger('click')
    expect(wrapper.emitted('confirm')[0][0]).toEqual(['A B'])
  })

  it('excludes a deleted segment from the emitted tokens', async () => {
    const wrapper = mount(ArtistSegmentSplitter, {
      props: { raw: 'A & B & C' },
    })
    // Chips: A, &, B, &, C — delete the last kept one (C).
    await wrapper.findAll('.seg-trash')[4].trigger('click')

    await wrapper.find('.btn-seg-confirm').trigger('click')
    expect(wrapper.emitted('confirm')).toBeTruthy()
    expect(wrapper.emitted('confirm')[0][0]).toEqual(['A', 'B'])
  })

  it('disables confirm and blocks the emit when nothing is kept', async () => {
    const wrapper = mount(ArtistSegmentSplitter, {
      props: { raw: 'A & B' },
    })
    const trashButtons = wrapper.findAll('.seg-trash')
    await trashButtons[0].trigger('click')
    await trashButtons[2].trigger('click')

    const confirmBtn = wrapper.find('.btn-seg-confirm')
    expect(confirmBtn.attributes('disabled')).toBeDefined()
    await confirmBtn.trigger('click')
    expect(wrapper.emitted('confirm')).toBeFalsy()
  })

  it('emits cancel on the Annuler button', async () => {
    const wrapper = mount(ArtistSegmentSplitter, { props: { raw: 'A & B' } })
    await wrapper.find('.btn-seg-ghost').trigger('click')
    expect(wrapper.emitted('cancel')).toBeTruthy()
  })
})

describe('ArtistSegmentSplitter — live Deezer signal', () => {
  it('debounces: no request before 400 ms, then searches every kept segment', async () => {
    mount(ArtistSegmentSplitter, {
      props: { raw: 'Adam Beyer & Ida Engberg' },
    })
    expect(api.get).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(399)
    expect(api.get).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    expect(searchedQueries().sort()).toEqual(['Adam Beyer', 'Ida Engberg'])
  })

  it('never searches a dropped separator or a deleted segment', async () => {
    const wrapper = mount(ArtistSegmentSplitter, {
      props: { raw: 'Adam Beyer & Ida Engberg' },
    })
    // Delete "Ida Engberg" (chip index 2) BEFORE the debounce fires: only the
    // remaining kept segment is searched.
    await wrapper.findAll('.seg-trash')[2].trigger('click')
    await vi.advanceTimersByTimeAsync(400)
    expect(searchedQueries()).toEqual(['Adam Beyer'])
  })

  it('shows a spinner while searching, then ✓ with name/fans or ✗', async () => {
    api.get.mockImplementation((url, { params }) => {
      if (params.q === 'Adam Beyer') {
        return Promise.resolve({
          data: [{ deezer_id: 7, name: 'Adam Beyer', picture: '', nb_fan: 120345 }],
        })
      }
      // Fuzzy non-exact hits only → no match.
      return Promise.resolve({ data: [{ deezer_id: 8, name: 'Ida Engberg Tribute', nb_fan: 3 }] })
    })
    const wrapper = mount(ArtistSegmentSplitter, {
      props: { raw: 'Adam Beyer & Ida Engberg' },
    })
    // Debounce window: both kept chips spin, the dropped "&" shows no signal.
    expect(wrapper.findAll('.seg-dz-spin')).toHaveLength(2)
    expect(wrapper.findAll('.seg-chip')[1].find('.seg-deezer').exists()).toBe(false)

    await vi.advanceTimersByTimeAsync(400)
    await nextTick()
    const chips = wrapper.findAll('.seg-chip')
    expect(wrapper.findAll('.seg-dz-spin')).toHaveLength(0)
    expect(chips[0].find('.seg-dz-found').exists()).toBe(true)
    expect(chips[0].find('.seg-dz-found').text()).toContain('Adam Beyer')
    expect(chips[0].find('.seg-dz-found').text()).toContain('fans')
    expect(chips[2].find('.seg-dz-missing').exists()).toBe(true)
  })

  it('matches case- and accent-insensitively (Nick Leon ↔ Nick León)', async () => {
    api.get.mockResolvedValue({
      data: [{ deezer_id: 9, name: 'Nick León', picture: '', nb_fan: 42 }],
    })
    const wrapper = mount(ArtistSegmentSplitter, {
      props: { raw: 'Nick Leon' },
    })
    await vi.advanceTimersByTimeAsync(400)
    await nextTick()
    const found = wrapper.find('.seg-dz-found')
    expect(found.exists()).toBe(true)
    expect(found.text()).toContain('Nick León')
  })

  it('re-searches when a cut changes the segment texts (cached texts excluded)', async () => {
    const wrapper = mount(ArtistSegmentSplitter, {
      props: { raw: 'Felix Nina' },
    })
    await vi.advanceTimersByTimeAsync(400)
    expect(searchedQueries()).toEqual(['Felix Nina'])

    await wrapper.find('.seg-cut').trigger('click')
    await vi.advanceTimersByTimeAsync(400)
    expect(searchedQueries().sort()).toEqual(['Felix', 'Felix Nina', 'Nina'])
  })
})
