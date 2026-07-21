import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ArtistTypeAhead from '../../../components/filters/ArtistTypeAhead.vue'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('../../../utils/api.js', () => ({
  default: { get: apiGet },
}))

const artists = [
  { id: 1, name: 'Kaskade', has_artwork: true },
  { id: 2, name: 'Kasablanca', has_artwork: false },
]

describe('ArtistTypeAhead', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    apiGet.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('debounces the server search by 250ms then queries with q + limit', async () => {
    apiGet.mockResolvedValue({ data: { items: artists } })
    const wrapper = mount(ArtistTypeAhead)
    await wrapper.find('input').setValue('ka')

    await vi.advanceTimersByTimeAsync(249)
    expect(apiGet).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(1)
    expect(apiGet).toHaveBeenCalledWith('/api/artists/', { params: { q: 'ka', limit: 6 } })
  })

  it('opens the dropdown with avatar-or-initial items', async () => {
    apiGet.mockResolvedValue({ data: { items: artists } })
    const wrapper = mount(ArtistTypeAhead)
    await wrapper.find('input').setValue('ka')
    await vi.advanceTimersByTimeAsync(250)

    const items = wrapper.findAll('.ata-item')
    expect(items).toHaveLength(2)
    // has_artwork → avatar from the artist-artworks bucket.
    expect(items[0].find('img').attributes('src')).toBe('/storage/artist-artworks/1.jpg')
    // no artwork → uppercase initial.
    expect(items[1].find('img').exists()).toBe(false)
    expect(items[1].find('.ata-ini').text()).toBe('K')
  })

  it('click-selects an artist: chip added, input cleared, dropdown closed', async () => {
    apiGet.mockResolvedValue({ data: { items: artists } })
    const wrapper = mount(ArtistTypeAhead)
    await wrapper.find('input').setValue('ka')
    await vi.advanceTimersByTimeAsync(250)

    await wrapper.findAll('.ata-item')[0].trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([[[artists[0]]]])
    expect(wrapper.find('input').element.value).toBe('')
    expect(wrapper.find('.ata-drop').exists()).toBe(false)
  })

  it('navigates with arrows and selects with Enter', async () => {
    apiGet.mockResolvedValue({ data: { items: artists } })
    const wrapper = mount(ArtistTypeAhead)
    const input = wrapper.find('input')
    await input.setValue('ka')
    await vi.advanceTimersByTimeAsync(250)

    await input.trigger('keydown', { key: 'ArrowDown' })
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('update:modelValue')).toEqual([[[artists[1]]]])
  })

  it('closes the dropdown on Escape', async () => {
    apiGet.mockResolvedValue({ data: { items: artists } })
    const wrapper = mount(ArtistTypeAhead)
    const input = wrapper.find('input')
    await input.setValue('ka')
    await vi.advanceTimersByTimeAsync(250)
    expect(wrapper.find('.ata-drop').exists()).toBe(true)

    await input.trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('.ata-drop').exists()).toBe(false)
  })

  it('shows « Aucun artiste » when the search returns nothing', async () => {
    apiGet.mockResolvedValue({ data: { items: [] } })
    const wrapper = mount(ArtistTypeAhead)
    await wrapper.find('input').setValue('zzz')
    await vi.advanceTimersByTimeAsync(250)

    expect(wrapper.find('.ata-none').text()).toBe('Aucun artiste')
  })

  it('excludes already-selected artists from the results', async () => {
    apiGet.mockResolvedValue({ data: { items: artists } })
    const wrapper = mount(ArtistTypeAhead, { props: { modelValue: [artists[0]] } })
    await wrapper.find('input').setValue('ka')
    await vi.advanceTimersByTimeAsync(250)

    const names = wrapper.findAll('.ata-item .ata-name').map((n) => n.text())
    expect(names).toEqual(['Kasablanca'])
  })

  it('renders selected chips and removes one via its ×', async () => {
    const wrapper = mount(ArtistTypeAhead, { props: { modelValue: artists } })
    const chips = wrapper.findAll('.ata-chip')
    expect(chips.map((c) => c.text())).toEqual(['Kaskade', 'Kasablanca'])

    await chips[0].find('.ata-x').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([[[artists[1]]]])
  })

  it('hides the placeholder once at least one artist is selected', () => {
    const empty = mount(ArtistTypeAhead)
    expect(empty.find('input').attributes('placeholder')).toBe('Rechercher un artiste…')
    const filled = mount(ArtistTypeAhead, { props: { modelValue: [artists[0]] } })
    expect(filled.find('input').attributes('placeholder')).toBe('')
  })

  it('does not query for an empty input', async () => {
    const wrapper = mount(ArtistTypeAhead)
    const input = wrapper.find('input')
    await input.setValue('k')
    await input.setValue('')
    await vi.advanceTimersByTimeAsync(300)
    expect(apiGet).not.toHaveBeenCalled()
  })
})
