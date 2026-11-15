import type { Directive } from 'vue'

type ActivatableElement = HTMLElement & { __keyActivate?: (event: KeyboardEvent) => void }

/**
 * v-key-activate — makes a clickable non-button element usable from the keyboard:
 * it becomes focusable, is announced as a button, and Enter / Space trigger its click.
 */
export const vKeyActivate: Directive<ActivatableElement> = {
  mounted(el) {
    if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '0')
    if (!el.hasAttribute('role')) el.setAttribute('role', 'button')

    el.__keyActivate = (event: KeyboardEvent) => {
      if (event.target !== el || event.isComposing) return
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault()
        el.click()
      }
    }
    el.addEventListener('keydown', el.__keyActivate)
  },
  unmounted(el) {
    if (el.__keyActivate) el.removeEventListener('keydown', el.__keyActivate)
  },
}
