import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ArtistSegmentSplitter from '../../components/admin/ArtistSegmentSplitter.vue'

describe('ArtistSegmentSplitter', () => {
  it('renders one segment chip per detected part', () => {
    const wrapper = mount(ArtistSegmentSplitter, {
      props: { raw: 'Adam Beyer & Ida Engberg & Foo' },
    })
    const chips = wrapper.findAll('.seg-chip')
    expect(chips.map((c) => c.find('.seg-chip-text').text())).toEqual([
      'Adam Beyer',
      'Ida Engberg',
      'Foo',
    ])
  })

  it('emits the kept tokens, excluding a deleted segment', async () => {
    const wrapper = mount(ArtistSegmentSplitter, {
      props: { raw: 'A & B & C' },
    })
    // Delete the last segment (C).
    const trashButtons = wrapper.findAll('.seg-trash')
    await trashButtons[2].trigger('click')

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
    await trashButtons[1].trigger('click')

    const confirmBtn = wrapper.find('.btn-seg-confirm')
    expect(confirmBtn.attributes('disabled')).toBeDefined()
    await confirmBtn.trigger('click')
    expect(wrapper.emitted('confirm')).toBeFalsy()
  })

  it('merges two units when their cut boundary is toggled off', async () => {
    const wrapper = mount(ArtistSegmentSplitter, {
      props: { raw: 'A & B & C' },
    })
    // Toggle off the first boundary → "A & B" becomes one segment.
    await wrapper.findAll('.seg-cut')[0].trigger('click')
    const chips = wrapper.findAll('.seg-chip')
    expect(chips.map((c) => c.find('.seg-chip-text').text())).toEqual(['A & B', 'C'])

    await wrapper.find('.btn-seg-confirm').trigger('click')
    expect(wrapper.emitted('confirm')[0][0]).toEqual(['A & B', 'C'])
  })

  it('pre-fills from initialTokens and lets a token be dropped (Flags tab)', async () => {
    const wrapper = mount(ArtistSegmentSplitter, {
      props: {
        raw: 'Adam Beyer & Ida Engberg',
        initialTokens: ['Adam Beyer', 'Ida Engberg'],
      },
    })
    const chips = wrapper.findAll('.seg-chip')
    expect(chips).toHaveLength(2)

    await wrapper.findAll('.seg-trash')[1].trigger('click')
    await wrapper.find('.btn-seg-confirm').trigger('click')
    expect(wrapper.emitted('confirm')[0][0]).toEqual(['Adam Beyer'])
  })

  it('emits cancel on the Annuler button', async () => {
    const wrapper = mount(ArtistSegmentSplitter, { props: { raw: 'A & B' } })
    await wrapper.find('.btn-seg-ghost').trigger('click')
    expect(wrapper.emitted('cancel')).toBeTruthy()
  })
})
