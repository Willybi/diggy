import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import CollectionsView from '../../views/CollectionsView.vue'

// Mutable holders shared with the hoisted mocks below.
const { apiMock, routerPush } = vi.hoisted(() => ({
  apiMock: { get: vi.fn(), post: vi.fn(), delete: vi.fn(), patch: vi.fn() },
  routerPush: vi.fn(),
}))

vi.mock('../../utils/api.js', () => ({ default: apiMock }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPush }),
}))

function makeFolders() {
  return [
    { id: 1, name: 'Techno', position: 0, created_at: null, collection_count: 2 },
    { id: 2, name: 'House', position: 1, created_at: null, collection_count: 0 },
  ]
}

function makeCollections() {
  return [
    { id: 10, name: 'Peak time', type: 'playlist', folder_id: 1, created_at: null, item_count: 12 },
    { id: 11, name: 'Warmup', type: 'playlist', folder_id: 1, created_at: null, item_count: 4 },
    {
      id: 12,
      name: 'Sans maison',
      type: 'playlist',
      folder_id: null,
      created_at: null,
      item_count: 7,
    },
  ]
}

// GET is polymorphic on URL: `/folders` → folders, else collections.
function wireGet() {
  apiMock.get.mockImplementation((url) =>
    url.includes('folders')
      ? Promise.resolve({ data: makeFolders() })
      : Promise.resolve({ data: makeCollections() }),
  )
}

async function mountView() {
  const wrapper = mount(CollectionsView)
  await flushPromises()
  return wrapper
}

describe('CollectionsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    wireGet()
    apiMock.post.mockResolvedValue({ data: {} })
    apiMock.patch.mockResolvedValue({ data: {} })
    apiMock.delete.mockResolvedValue({})
    vi.stubGlobal(
      'confirm',
      vi.fn(() => true),
    )
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders folders, their collections, and a "Sans dossier" group', async () => {
    const wrapper = await mountView()
    // 2 folders + the orphans section.
    expect(wrapper.findAll('.folder')).toHaveLength(3)
    // 3 collections total, all rendered as cards.
    expect(wrapper.findAll('.coll-card')).toHaveLength(3)
    // The orphan group is present with its single collection.
    const orphanSection = wrapper.find('.orphans')
    expect(orphanSection.exists()).toBe(true)
    expect(orphanSection.text()).toContain('Sans dossier')
    expect(orphanSection.findAll('.coll-card')).toHaveLength(1)
    expect(orphanSection.text()).toContain('Sans maison')
  })

  it('collapses and expands a folder', async () => {
    const wrapper = await mountView()
    const firstFolder = wrapper.findAll('.folder')[0]
    expect(firstFolder.find('.folder-body').exists()).toBe(true)
    await firstFolder.find('.folder-toggle').trigger('click')
    expect(firstFolder.find('.folder-body').exists()).toBe(false)
    await firstFolder.find('.folder-toggle').trigger('click')
    expect(firstFolder.find('.folder-body').exists()).toBe(true)
  })

  it('creates a folder', async () => {
    const wrapper = await mountView()
    await wrapper.find('.btn-folder').trigger('click')
    const input = wrapper.find('.modal-box input')
    await input.setValue('Ambient')
    await wrapper.find('.btn-confirm').trigger('click')
    expect(apiMock.post).toHaveBeenCalledWith('/api/collections/folders', { name: 'Ambient' })
    await flushPromises()
    // A refetch follows (collections + folders).
    expect(apiMock.get).toHaveBeenCalledWith('/api/collections/folders')
  })

  it('renames a folder', async () => {
    const wrapper = await mountView()
    const firstFolder = wrapper.findAll('.folder')[0]
    // The rename button is the first .ico-btn in the folder head.
    await firstFolder.find('.folder-actions .ico-btn').trigger('click')
    const input = wrapper.find('.modal-box input')
    expect(input.element.value).toBe('Techno')
    await input.setValue('Techno Hard')
    await wrapper.find('.btn-confirm').trigger('click')
    expect(apiMock.patch).toHaveBeenCalledWith('/api/collections/folders/1', {
      name: 'Techno Hard',
    })
  })

  it('deletes a folder (confirmed) and orphans its collections', async () => {
    const wrapper = await mountView()
    const firstFolder = wrapper.findAll('.folder')[0]
    await firstFolder.find('.ico-del').trigger('click')
    expect(globalThis.confirm).toHaveBeenCalled()
    expect(apiMock.delete).toHaveBeenCalledWith('/api/collections/folders/1')
  })

  it('does not delete a folder when the confirm is dismissed', async () => {
    globalThis.confirm.mockReturnValueOnce(false)
    const wrapper = await mountView()
    await wrapper.findAll('.folder')[0].find('.ico-del').trigger('click')
    expect(apiMock.delete).not.toHaveBeenCalled()
  })

  it('assigns a collection to a folder via the select', async () => {
    const wrapper = await mountView()
    // The orphan collection (id 12) is the last card; move it into folder 2.
    const orphanSelect = wrapper.find('.orphans .assign-select')
    await orphanSelect.setValue('2')
    expect(apiMock.patch).toHaveBeenCalledWith('/api/collections/12/folder', { folder_id: 2 })
  })

  it('detaches a collection (Sans dossier) via the select', async () => {
    const wrapper = await mountView()
    // A collection inside folder 1 (id 10) moved back to no folder.
    const inFolderSelect = wrapper.findAll('.folder')[0].find('.assign-select')
    await inFolderSelect.setValue('')
    expect(apiMock.patch).toHaveBeenCalledWith('/api/collections/10/folder', { folder_id: null })
  })

  it('creates a collection (unchanged flow)', async () => {
    const wrapper = await mountView()
    await wrapper.find('.btn-add').trigger('click')
    const input = wrapper.find('.modal-box input')
    await input.setValue('Nouvelle')
    await wrapper.find('.btn-confirm').trigger('click')
    expect(apiMock.post).toHaveBeenCalledWith('/api/collections/', { name: 'Nouvelle' })
  })

  it('navigates to a collection when its card body is clicked', async () => {
    const wrapper = await mountView()
    await wrapper.find('.coll-card').trigger('click')
    expect(routerPush).toHaveBeenCalledWith('/collections/10')
  })
})
