import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { i18n } from './i18n'
import { vKeyActivate } from './directives/keyActivate'
import { installUiLanguageFetch } from './services/uiLanguageHeader'
import { installGlobalTooltip } from './utils/globalTooltip'
import { refreshMediaToken, startMediaTokenRefresh } from './services/api'
import './assets/main.css'

// Favicons in web citations come from arbitrary sites; when one fails to load,
// swap in the generic globe icon that is rendered right after it.
document.addEventListener(
  'error',
  (event) => {
    const target = event.target
    if (target instanceof HTMLImageElement && target.classList.contains('web-favicon')) {
      target.style.display = 'none'
      const fallback = target.nextElementSibling
      if (fallback instanceof SVGElement) fallback.style.display = 'inline'
    }
  },
  true,
)

installUiLanguageFetch()
installGlobalTooltip()

const app = createApp(App)
app.directive('key-activate', vKeyActivate)
app.use(i18n)
app.use(router)

// Preview images and audio need a media token in their URL; get one before the first
// render (at most ~3 s), then keep it fresh in the background.
void Promise.race([refreshMediaToken(), new Promise((resolve) => setTimeout(resolve, 3000))]).finally(() => {
  app.mount('#app')
  startMediaTokenRefresh()
})
