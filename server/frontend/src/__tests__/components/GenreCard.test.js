import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'

// Mutable holders shared with the hoisted mocks below.
const { routerPush, playerMock, opinionsMock, opinionState } = vi.hoisted(() => ({
  routerPush: vi.fn(),
  playerMock: { genrePlaying: null, close: vi.fn(), playRandom: vi.fn() },
  opinionsMock: { get: vi.fn(), set: vi.fn() },
  opinionState: { value: null },
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPush }),
}))

vi.mock('../../stores/audioPlayer', () => ({
  useAudioPlayer: () => playerMock,
}))

vi.mock('../../stores/opinions.js', () => ({
  useOpinionsStore: () => opinionsMock,
}))

import GenreCard from '../../components/GenreCard.vue'

function makeGenre(overrides = {}) {
  return {
    name: 'House',
    pillar: 'house',
    depth: 0,
    trackCount: 1180,
    artistCount: 86,
    inLibCount: 0,
    bpmLo: 120,
    bpmHi: 126,
    artworks: [],
    artists: [],
    ...overrides,
  }
}

describe('GenreCard', () => {
  beforeEach(() => {
    routerPush.mockReset()
    playerMock.genrePlaying = null
    playerMock.close.mockReset()
    playerMock.playRandom.mockReset()
    opinionsMock.set.mockReset()
    opinionState.value = null
    opinionsMock.get.mockImplementation(() => opinionState.value)
  })

  it('no longer renders the in-lib overlay badge', () => {
    const wrapper = mount(GenreCard, { props: { genre: makeGenre({ inLibCount: 79 }) } })
    expect(wrapper.find('.gc-lib').exists()).toBe(false)
  })

  it('colours the « En bib » stat when inLibCount > 0 (dot + value)', () => {
    const wrapper = mount(GenreCard, { props: { genre: makeGenre({ inLibCount: 79 }) } })
    const lib = wrapper.find('.gc-stat--lib')
    expect(lib.find('.v-pos').exists()).toBe(true)
    expect(lib.find('.v-pos').text()).toBe('79')
    expect(lib.find('.libdot').exists()).toBe(true)
    expect(lib.find('.v-empty').exists()).toBe(false)
  })

  it('shows a dash for « En bib » when inLibCount is 0 (no dot)', () => {
    const wrapper = mount(GenreCard, { props: { genre: makeGenre({ inLibCount: 0 }) } })
    const lib = wrapper.find('.gc-stat--lib')
    expect(lib.find('.v-empty').exists()).toBe(true)
    expect(lib.find('.v-pos').exists()).toBe(false)
    expect(lib.find('.libdot').exists()).toBe(false)
  })

  it('renders the signature line: pillar label · BPM range', () => {
    const wrapper = mount(GenreCard, { props: { genre: makeGenre({ bpmLo: 120, bpmHi: 126 }) } })
    expect(wrapper.find('.sig-pillar').text()).toBe('House')
    expect(wrapper.find('.sig-bpm').text()).toBe('120–126 BPM')
  })

  it('collapses the BPM signature to a single value when lo == hi and to a dash when absent', () => {
    const single = mount(GenreCard, { props: { genre: makeGenre({ bpmLo: 124, bpmHi: 124 }) } })
    expect(single.find('.sig-bpm').text()).toBe('124 BPM')

    const none = mount(GenreCard, { props: { genre: makeGenre({ bpmLo: 0, bpmHi: 0 }) } })
    expect(none.find('.sig-bpm').text()).toBe('–')
  })

  it('renders the three body stats: Tracks · Artistes · En bib', () => {
    const wrapper = mount(GenreCard, { props: { genre: makeGenre() } })
    const labels = wrapper.findAll('.gc-stat .k').map((k) => k.text())
    expect(labels).toEqual(['Tracks', 'Artistes', 'En bib'])
  })

  it('navigates to /style/:name on a card click', async () => {
    const wrapper = mount(GenreCard, { props: { genre: makeGenre({ name: 'Tech House' }) } })
    await wrapper.find('.genre-card').trigger('click')
    expect(routerPush).toHaveBeenCalledWith('/style/Tech%20House')
  })

  it('is a keyboard-reachable link (role + tabindex + Enter)', async () => {
    const wrapper = mount(GenreCard, { props: { genre: makeGenre() } })
    const card = wrapper.find('.genre-card')
    expect(card.attributes('role')).toBe('link')
    expect(card.attributes('tabindex')).toBe('0')
    await card.trigger('keydown.enter')
    expect(routerPush).toHaveBeenCalledWith('/style/House')
  })

  it('plays a random extract on the play button without navigating (stopPropagation)', async () => {
    const wrapper = mount(GenreCard, { props: { genre: makeGenre({ name: 'House' }) } })
    await wrapper.find('.gc-play').trigger('click')
    expect(playerMock.playRandom).toHaveBeenCalledWith('House')
    expect(routerPush).not.toHaveBeenCalled()
  })

  it('sets the genre opinion via LikeDislike without navigating', async () => {
    const wrapper = mount(GenreCard, { props: { genre: makeGenre({ name: 'House' }) } })
    await wrapper.find('.gc-acts .ld-btn.like').trigger('click')
    expect(opinionsMock.set).toHaveBeenCalledWith('genre', 'House', 'liked')
    expect(routerPush).not.toHaveBeenCalled()
  })

  it('reflects a liked opinion as a card state class', () => {
    opinionState.value = 'liked'
    const wrapper = mount(GenreCard, { props: { genre: makeGenre() } })
    expect(wrapper.find('.genre-card').classes()).toContain('liked')
  })

  it('renders artist avatar initials when an artist has no image', () => {
    const wrapper = mount(GenreCard, {
      props: {
        genre: makeGenre({
          artistCount: 1,
          artists: [{ id: 7, name: 'Amelie Lens', image: null }],
        }),
      },
    })
    const av = wrapper.find('.gc-avatars .av')
    expect(av.classes()).toContain('init')
    expect(av.text()).toBe('AL')
  })
})
