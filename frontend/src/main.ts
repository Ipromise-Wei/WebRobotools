import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'
import './style.css'

const pinia = createPinia()
const auth = useAuthStore(pinia)

router.beforeEach(async (to) => {
  if (!auth.ready) await auth.initialize()

  if (to.name === 'login') {
    if (!auth.authenticated) return true
    const redirect = typeof to.query.redirect === 'string' ? to.query.redirect : ''
    return redirect.startsWith('/') && !redirect.startsWith('//') && redirect !== '/login'
      ? redirect
      : '/'
  }

  if (!auth.authenticated) {
    return {
      name: 'login',
      query: to.fullPath === '/' ? undefined : { redirect: to.fullPath },
    }
  }
  return true
})

createApp(App).use(pinia).use(router).mount('#app')
