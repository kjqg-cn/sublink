import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import {
  escapeDraftNodes,
  extractRemoteSubUrls,
  flattenDecodedNodes
} from '@/utils/parseNodes'
import { DRAFT_NODES_STORAGE_KEY } from '@/utils/storage'

const mockDecodeSub = vi.fn()
const mockPush = vi.fn()
const mockMessage = {
  success: vi.fn(),
  warning: vi.fn(),
  error: vi.fn()
}

vi.mock('@/api', () => ({
  decodeSub: (...args: unknown[]) => mockDecodeSub(...args)
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush })
}))

vi.mock('naive-ui', () => ({
  useMessage: () => mockMessage,
  NCard: defineComponent({ setup(_, { slots }) { return () => h('div', slots.default?.()) } }),
  NSpace: defineComponent({ setup(_, { slots }) { return () => h('div', slots.default?.()) } }),
  NTag: defineComponent({ setup(_, { slots }) { return () => h('span', { class: 'n-tag' }, slots.default?.()) } }),
  NButton: defineComponent({
    props: { loading: Boolean, disabled: Boolean },
    emits: ['click'],
    setup(props, { emit, slots }) {
      return () =>
        h(
          'button',
          { disabled: props.disabled, onClick: () => emit('click') },
          slots.default?.()
        )
    }
  })
}))

import ParseView from '@/views/ParseView.vue'

describe('parseNodes helpers', () => {
  it('extracts multiple http(s) URLs from mixed input', () => {
    const urls = extractRemoteSubUrls(
      '备注\nhttps://a.example.com/sub/1\n  http://b.example.com:8080/x?k=1  '
    )
    expect(urls).toEqual(['https://a.example.com/sub/1', 'http://b.example.com:8080/x?k=1'])
    expect(extractRemoteSubUrls('not-a-url')).toEqual([])
  })

  it('flattens multi-line chunks and filters empty lines', () => {
    const flattened = flattenDecodedNodes([
      'vless://a@1.1.1.1:443#N1\r\n\r\n  vless://b@2.2.2.2:443#N2  ',
      'hy2://pwd@3.3.3.3:443#N3\n   '
    ])
    expect(flattened).toEqual([
      'vless://a@1.1.1.1:443#N1',
      'vless://b@2.2.2.2:443#N2',
      'hy2://pwd@3.3.3.3:443#N3'
    ])
  })

  it('escapes backslashes and pipes symmetrically for draft nodes', () => {
    const escaped = escapeDraftNodes([
      'vless://u@h:443#A|B\\C',
      'trojan://p@h:443#normal'
    ])
    expect(escaped).toBe('vless://u@h:443#A\\|B\\\\C\ntrojan://p@h:443#normal')
  })
})

describe('ParseView component', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.clearAllMocks()
  })

  const mountParseView = () =>
    mount(ParseView, {
      global: {
        stubs: {
          CodeTextarea: defineComponent({
            props: { modelValue: { type: String, default: '' } },
            emits: ['update:modelValue'],
            setup(props, { emit }) {
              return () =>
                h('textarea', {
                  value: props.modelValue,
                  onInput: (e: Event) =>
                    emit('update:modelValue', (e.target as HTMLTextAreaElement).value)
                })
            }
          })
        }
      }
    })

  it('shows error and skips API when input has no http(s) URL', async () => {
    const wrapper = mountParseView()
    await wrapper.find('textarea').setValue('just plain text')
    const parseBtn = wrapper.findAll('button').find((b) => b.text() === '开始解析')!
    await parseBtn.trigger('click')
    expect(mockDecodeSub).not.toHaveBeenCalled()
    expect(mockMessage.error).toHaveBeenCalledWith('格式不正确，请粘贴 http(s) 订阅链接')
  })

  it('flattens decoded multiline chunks, renders true node count, and escapes draft into sessionStorage', async () => {
    mockDecodeSub.mockResolvedValue({
      code: 200,
      msg: ['vless://u1@1.1.1.1:443#HK|01\r\nvless://u2@2.2.2.2:443#JP\\02', 'hy2://p@3.3.3.3:443#US']
    })

    const wrapper = mountParseView()
    await wrapper.find('textarea').setValue('https://sub.example.com/1\nhttps://sub.example.com/2')
    const parseBtn = wrapper.findAll('button').find((b) => b.text() === '开始解析')!
    await parseBtn.trigger('click')
    await flushPromises()

    expect(mockDecodeSub).toHaveBeenCalledWith([
      'https://sub.example.com/1',
      'https://sub.example.com/2'
    ])
    expect(mockMessage.success).toHaveBeenCalledWith('成功解析 3 条节点')
    expect(wrapper.find('.n-tag').text()).toContain('共 3 条节点')

    const createBtn = wrapper.findAll('button').find((b) => b.text() === '以此创建订阅')!
    await createBtn.trigger('click')

    expect(sessionStorage.getItem(DRAFT_NODES_STORAGE_KEY)).toBe(
      'vless://u1@1.1.1.1:443#HK\\|01\nvless://u2@2.2.2.2:443#JP\\\\02\nhy2://p@3.3.3.3:443#US'
    )
    expect(mockPush).toHaveBeenCalledWith('/subs/create')
  })

  it('warns without navigating when sessionStorage quota fails', async () => {
    mockDecodeSub.mockResolvedValue({
      code: 200,
      msg: ['vless://u1@1.1.1.1:443#HK']
    })

    const wrapper = mountParseView()
    await wrapper.find('textarea').setValue('https://sub.example.com/1')
    await wrapper.findAll('button').find((b) => b.text() === '开始解析')!.trigger('click')
    await flushPromises()

    vi.spyOn(window.sessionStorage, 'setItem').mockImplementation(() => {
      throw new DOMException('Quota exceeded', 'QuotaExceededError')
    })

    await wrapper.findAll('button').find((b) => b.text() === '以此创建订阅')!.trigger('click')
    expect(mockMessage.warning).toHaveBeenCalledWith(
      '解析结果过大或浏览器禁用存储，请点击「复制全部」后手动粘贴创建'
    )
    expect(mockPush).not.toHaveBeenCalled()
  })
})
