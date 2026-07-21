import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import FilterBar from '../../../components/filters/FilterBar.vue'
import FilterChip from '../../../components/filters/FilterChip.vue'
import { compareCamelot } from '../../../components/filters/camelot.js'

const criteria = [
  { key: 'q', type: 'text', label: 'Recherche', chip: false },
  { key: 'bpm', type: 'range', label: 'BPM', min: 60, max: 200 },
  { key: 'keys', type: 'multi', label: 'Key', sort: compareCamelot },
  { key: 'styles', type: 'multi', label: 'Style', chipPerValue: true },
  {
    key: 'artists',
    type: 'multi',
    label: 'Artiste',
    chipPerValue: true,
    format: (a) => a.name,
  },
  {
    key: 'inlib',
    type: 'segment',
    label: 'Bibliothèque',
    options: [
      { value: null, label: 'Tous' },
      { value: 'in', label: 'Dans ma bib' },
    ],
  },
  { key: 'preview', type: 'toggle', label: 'Extrait', valueLabel: 'Écoutable' },
]

const inactiveFilters = {
  q: '',
  bpm: [60, 200],
  keys: [],
  styles: [],
  artists: [],
  inlib: null,
  preview: false,
}

function mountBar(filters = {}, props = {}) {
  return mount(FilterBar, {
    props: { criteria, filters: { ...inactiveFilters, ...filters }, ...props },
  })
}

function chipTuples(wrapper) {
  return wrapper.findAllComponents(FilterChip).map((c) => [c.props('label'), c.props('value')])
}

describe('FilterBar', () => {
  it('shows no chips row and no badge when everything is inactive', () => {
    const wrapper = mountBar()
    expect(wrapper.find('.fbar-chips').exists()).toBe(false)
    expect(wrapper.find('.fbar-badge').exists()).toBe(false)
  })

  it('maps a range to a single « BPM 120–133 » chip', () => {
    const wrapper = mountBar({ bpm: [120, 133] })
    expect(chipTuples(wrapper)).toEqual([['BPM', '120–133']])
  })

  it('maps multi keys to ONE chip, values sorted harmonically', () => {
    const wrapper = mountBar({ keys: ['6B', '7A', '5A', '6A'] })
    expect(chipTuples(wrapper)).toEqual([['Key', '5A 6A 7A 6B']])
  })

  it('maps styles and artists to one chip PER value', () => {
    const wrapper = mountBar({
      styles: ['Tech House', 'Techno'],
      artists: [{ id: 1, name: 'Kaskade' }],
    })
    expect(chipTuples(wrapper)).toEqual([
      ['Style', 'Tech House'],
      ['Style', 'Techno'],
      ['Artiste', 'Kaskade'],
    ])
  })

  it('maps a segment to its option label and a toggle to its valueLabel', () => {
    const wrapper = mountBar({ inlib: 'in', preview: true })
    expect(chipTuples(wrapper)).toEqual([
      ['Bibliothèque', 'Dans ma bib'],
      ['Extrait', 'Écoutable'],
    ])
  })

  it('tri-state « Tous » (null) and toggle off produce NO chip', () => {
    const wrapper = mountBar({ inlib: null, preview: false })
    expect(wrapper.find('.fbar-chips').exists()).toBe(false)
  })

  it('the bar search (chip: false) never produces a chip nor counts in the badge', () => {
    const wrapper = mountBar({ q: 'kaskade' })
    expect(wrapper.find('.fbar-chips').exists()).toBe(false)
    expect(wrapper.find('.fbar-badge').exists()).toBe(false)
  })

  it('badge: a multi counts its values, a range counts 1', () => {
    const wrapper = mountBar({
      bpm: [120, 133],
      keys: ['5A', '6A', '7A', '6B'],
      styles: ['Tech House', 'Techno'],
      inlib: 'in',
      preview: true,
    })
    // range 1 + keys 4 + styles 2 + segment 1 + toggle 1 = 9
    expect(wrapper.find('.fbar-badge').text()).toBe('9')
  })

  it('removing a per-value chip removes only THAT value', async () => {
    const wrapper = mountBar({ styles: ['Tech House', 'Techno'] })
    await wrapper.findAllComponents(FilterChip)[1].find('.fchip-x').trigger('click')
    const [payload] = wrapper.emitted('update:filters').at(-1)
    expect(payload.styles).toEqual(['Tech House'])
    expect(wrapper.emitted('remove').at(-1)).toEqual(['styles', 'Techno'])
  })

  it('removing a single-chip criterion resets it to its default', async () => {
    const wrapper = mountBar({ bpm: [120, 133], keys: ['5A', '6A'] })
    // First chip is BPM.
    await wrapper.findAllComponents(FilterChip)[0].find('.fchip-x').trigger('click')
    const [payload] = wrapper.emitted('update:filters').at(-1)
    expect(payload.bpm).toEqual([60, 200])
    expect(payload.keys).toEqual(['5A', '6A']) // untouched
  })

  it('« Tout effacer » resets every chip criterion but keeps the bar search', async () => {
    const wrapper = mountBar({
      q: 'kaskade',
      bpm: [120, 133],
      keys: ['5A'],
      styles: ['Techno'],
      inlib: 'in',
      preview: true,
    })
    await wrapper.find('.fbar-clear').trigger('click')
    const [payload] = wrapper.emitted('update:filters').at(-1)
    expect(payload).toEqual({ ...inactiveFilters, q: 'kaskade' })
    expect(wrapper.emitted('clear')).toHaveLength(1)
  })

  it('renders the live result counter in French, … while loading', async () => {
    const wrapper = mountBar({}, { resultCount: 42 })
    expect(wrapper.find('.fbar-count').text()).toBe('42 résultats')

    await wrapper.setProps({ resultCount: 1 })
    expect(wrapper.find('.fbar-count').text()).toBe('1 résultat')

    await wrapper.setProps({ loading: true })
    expect(wrapper.find('.fbar-count').text()).toBe('…')
  })

  it('toggles the inline panel by default and mirrors it on aria-expanded', async () => {
    const wrapper = mountBar({}, { panelOpen: false })
    const btn = wrapper.find('.fbar-toggle')
    expect(btn.attributes('aria-expanded')).toBe('false')

    await btn.trigger('click')
    expect(wrapper.emitted('update:panelOpen')).toEqual([[true]])
    expect(wrapper.emitted('update:drawerOpen')).toBeUndefined()
  })

  it('opens the drawer instead when the bar is narrower than 640px', async () => {
    const wrapper = mountBar()
    Object.defineProperty(wrapper.element, 'offsetWidth', { value: 375, configurable: true })
    await wrapper.find('.fbar-toggle').trigger('click')
    expect(wrapper.emitted('update:drawerOpen')).toEqual([[true]])
    expect(wrapper.emitted('update:panelOpen')).toBeUndefined()
  })

  it('keeps the panel path at desktop widths', async () => {
    const wrapper = mountBar({}, { panelOpen: true })
    Object.defineProperty(wrapper.element, 'offsetWidth', { value: 1200, configurable: true })
    await wrapper.find('.fbar-toggle').trigger('click')
    expect(wrapper.emitted('update:panelOpen')).toEqual([[false]])
  })

  it('renders the search/sort/panel slots, panel gated by panelOpen', async () => {
    const wrapper = mount(FilterBar, {
      props: { criteria, filters: { ...inactiveFilters }, panelOpen: false },
      slots: {
        search: '<input class="probe-search" />',
        sort: '<select class="probe-sort"></select>',
        panel: '<div class="probe-panel">panneau</div>',
      },
    })
    expect(wrapper.find('.fbar-search .probe-search').exists()).toBe(true)
    expect(wrapper.find('.probe-sort').exists()).toBe(true)
    expect(wrapper.find('.probe-panel').exists()).toBe(false)

    await wrapper.setProps({ panelOpen: true })
    expect(wrapper.find('.fbar-panel .probe-panel').exists()).toBe(true)
  })
})
