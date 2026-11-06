import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import './style.css'

const app = createApp(App)

// Spotlight-блик на карточках: обновляем --mx/--my под курсором (делегировано,
// троттлится через requestAnimationFrame, чтобы не дёргать макет на каждом move).
let spotlightPending = false
document.addEventListener('pointermove', (event) => {
  const card = event.target?.closest?.('.card')
  if (!card || spotlightPending) return
  spotlightPending = true
  requestAnimationFrame(() => {
    spotlightPending = false
    const rect = card.getBoundingClientRect()
    card.style.setProperty('--mx', `${event.clientX - rect.left}px`)
    card.style.setProperty('--my', `${event.clientY - rect.top}px`)
  })
})

// v-reveal: блок плавно появляется, когда попадает в зону видимости (прокрутка).
const revealObserver =
  typeof IntersectionObserver !== 'undefined'
    ? new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            if (entry.isIntersecting) {
              entry.target.classList.add('reveal-visible')
              revealObserver.unobserve(entry.target)
            }
          }
        },
        { threshold: 0.08, rootMargin: '0px 0px -8% 0px' },
      )
    : null

app.directive('reveal', {
  mounted(el, binding) {
    el.classList.add('reveal')
    if (binding.value) el.style.transitionDelay = `${binding.value}ms`
    if (revealObserver) revealObserver.observe(el)
    else el.classList.add('reveal-visible') // без IntersectionObserver — показываем сразу
  },
  unmounted(el) {
    revealObserver?.unobserve(el)
  },
})

app.use(router).mount('#app')
