import { onUnmounted, watch } from 'vue'

type CloseHandler = () => void

// Open dialogs, oldest first. Escape only closes the most recently opened one.
const openDialogs: CloseHandler[] = []
let listening = false

function onKeydown(event: KeyboardEvent) {
  if (event.key !== 'Escape' || event.isComposing || event.defaultPrevented) return
  const top = openDialogs[openDialogs.length - 1]
  if (!top) return
  event.preventDefault()
  top()
}

function register(handler: CloseHandler) {
  openDialogs.push(handler)
  if (!listening) {
    window.addEventListener('keydown', onKeydown)
    listening = true
  }
}

function unregister(handler: CloseHandler) {
  const index = openDialogs.lastIndexOf(handler)
  if (index !== -1) openDialogs.splice(index, 1)
  if (openDialogs.length === 0 && listening) {
    window.removeEventListener('keydown', onKeydown)
    listening = false
  }
}

/**
 * Close a dialog with the Escape key while `isOpen()` is true.
 * Dialogs stack: only the topmost open dialog reacts.
 */
export function useEscapeClose(isOpen: () => boolean, close: CloseHandler) {
  const handler: CloseHandler = () => close()

  watch(
    isOpen,
    (open) => {
      if (open) register(handler)
      else unregister(handler)
    },
    { immediate: true }
  )

  onUnmounted(() => unregister(handler))
}
