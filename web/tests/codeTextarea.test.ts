import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { mount } from '@vue/test-utils'

vi.mock('naive-ui', () => ({
  useThemeVars: () =>
    ref({
      inputColor: '#ffffff',
      borderColor: '#e0e0e6',
      primaryColor: '#6366f1',
      textColor1: '#333333',
      textColor3: '#999999',
      actionColor: '#f5f5f7'
    })
}))

import CodeTextarea from '@/components/CodeTextarea.vue'

describe('CodeTextarea', () => {
  it('renders a single gutter text node with accurate line numbers', async () => {
    const wrapper = mount(CodeTextarea, {
      props: { modelValue: '' }
    })

    const gutter = wrapper.find('.gutter')
    expect(gutter.exists()).toBe(true)
    expect(gutter.element.children.length).toBe(0)
    expect(gutter.text()).toBe('1')

    await wrapper.setProps({ modelValue: 'line1\nline2\n' })
    expect(gutter.text()).toBe('1\n2\n3')
  })

  it('handles large 3519-line templates with a single DOM node in gutter', () => {
    const largeDoc = Array.from({ length: 3519 }, (_, i) => `rule-${i + 1}`).join('\n')
    const wrapper = mount(CodeTextarea, {
      props: { modelValue: largeDoc }
    })
    const gutter = wrapper.find('.gutter')
    expect(gutter.element.children.length).toBe(0)
    const lines = gutter.text().split('\n')
    expect(lines).toHaveLength(3519)
    expect(lines[0]).toBe('1')
    expect(lines[3518]).toBe('3519')
  })

  it('emits update:modelValue on input and syncs gutter scrollTop on scroll', async () => {
    const wrapper = mount(CodeTextarea, {
      props: { modelValue: 'a\nb', readonly: false }
    })

    const textarea = wrapper.find('textarea.editor')
    await textarea.setValue('a\nb\nc')
    expect(wrapper.emitted('update:modelValue')).toEqual([['a\nb\nc']])

    ;(textarea.element as HTMLTextAreaElement).scrollTop = 120
    await textarea.trigger('scroll')
    expect((wrapper.find('.gutter').element as HTMLDivElement).scrollTop).toBe(120)
  })
})
