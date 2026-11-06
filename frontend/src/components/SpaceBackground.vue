<script setup>
// Лёгкий 3D-фон для светлой темы: мягкие тёплые «облака» (крупные полупрозрачные
// спрайты) и лёгкая тёплая пыльца, медленно дрейфуют. Дёшево, уважает
// prefers-reduced-motion, останавливается в невидимой вкладке.
import { onMounted, onBeforeUnmount, ref } from 'vue'
import * as THREE from 'three'

const host = ref(null)

let renderer = null
let scene = null
let camera = null
let sparkles = null
let orbs = null
let rafId = null
let resizeObserver = null
let running = false
let reduced = false

const pointer = { x: 0, y: 0, tx: 0, ty: 0 }

// Тёплые приглушённые тона — заметны на кремовом фоне, но не перебивают контент.
const SPARKLE_PALETTE = [
  new THREE.Color('#e8a04c'),
  new THREE.Color('#f0b06a'),
  new THREE.Color('#df7d3a'),
  new THREE.Color('#d99a6c'),
  new THREE.Color('#c9a06a'),
  new THREE.Color('#b8ad9c'),
]

function radialTexture(stops) {
  // stops: [offset, 'rgba(...)'] — мягкое круглое пятно от центра к краю.
  const size = 128
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = size
  const ctx = canvas.getContext('2d')
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
  for (const [offset, color] of stops) g.addColorStop(offset, color)
  ctx.fillStyle = g
  ctx.fillRect(0, 0, size, size)
  return new THREE.CanvasTexture(canvas)
}

// Круглая мягкая точка для пыльцы. Текстура белая, цвет задаёт vertexColors.
function sparkleTexture() {
  return radialTexture([
    [0, 'rgba(255,255,255,1)'],
    [0.3, 'rgba(255,255,255,0.8)'],
    [0.6, 'rgba(255,255,255,0.2)'],
    [1, 'rgba(255,255,255,0)'],
  ])
}

function orbTexture(inner, mid) {
  return radialTexture([
    [0, inner],
    [0.4, mid],
    [1, 'rgba(0,0,0,0)'],
  ])
}

function makeSparkles() {
  const count = 150
  const positions = new Float32Array(count * 3)
  const colors = new Float32Array(count * 3)
  for (let i = 0; i < count; i++) {
    const radius = 22 + Math.random() * 40
    const theta = Math.random() * Math.PI * 2
    const phi = Math.acos(2 * Math.random() - 1)
    positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta)
    positions[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta)
    positions[i * 3 + 2] = radius * Math.cos(phi)
    const color = SPARKLE_PALETTE[Math.floor(Math.random() * SPARKLE_PALETTE.length)]
    const dim = 0.5 + Math.random() * 0.5
    colors[i * 3] = color.r * dim
    colors[i * 3 + 1] = color.g * dim
    colors[i * 3 + 2] = color.b * dim
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  const material = new THREE.PointsMaterial({
    size: 0.42,
    map: sparkleTexture(),
    vertexColors: true,
    transparent: true,
    opacity: 0.5,
    depthWrite: false,
    blending: THREE.NormalBlending,
    sizeAttenuation: true,
    alphaTest: 0.002,
  })
  return new THREE.Points(geometry, material)
}

function makeOrbs() {
  const group = new THREE.Group()
  const glows = [
    { color: '#ffb46b', x: -17, y: 8, z: -14, s: 46, o: 0.20 },
    { color: '#ff9e5e', x: 19, y: -12, z: -16, s: 52, o: 0.17 },
    { color: '#ff8a5c', x: 3, y: 18, z: -20, s: 40, o: 0.14 },
    { color: '#e7c1ff', x: -22, y: -15, z: -18, s: 38, o: 0.10 },
  ]
  glows.forEach((glow, index) => {
    const material = new THREE.SpriteMaterial({
      map: orbTexture(glow.color + 'b3', glow.color + '40'),
      transparent: true,
      opacity: glow.o,
      blending: THREE.NormalBlending,
      depthWrite: false,
    })
    const sprite = new THREE.Sprite(material)
    sprite.position.set(glow.x, glow.y, glow.z)
    sprite.scale.set(glow.s, glow.s, 1)
    sprite.userData.baseOpacity = glow.o
    sprite.userData.phase = index * 1.7
    sprite.userData.home = { x: glow.x, y: glow.y }
    group.add(sprite)
  })
  return group
}

function onResize() {
  if (!renderer || !host.value) return
  const { clientWidth, clientHeight } = host.value
  renderer.setSize(clientWidth, clientHeight, false)
  camera.aspect = clientWidth / clientHeight
  camera.updateProjectionMatrix()
}

function onPointer(event) {
  const { innerWidth, innerHeight } = window
  pointer.tx = (event.clientX / innerWidth) * 2 - 1
  pointer.ty = (event.clientY / innerHeight) * 2 - 1
}

function onVisibility() {
  running = !document.hidden
  if (running && !rafId) tick()
  else if (!running && rafId) { cancelAnimationFrame(rafId); rafId = null }
}

function tick() {
  rafId = requestAnimationFrame(tick)
  if (!running) return
  const now = performance.now()
  const t = now * 0.00004
  const pulse = now * 0.0007

  pointer.x += (pointer.tx - pointer.x) * 0.03
  pointer.y += (pointer.ty - pointer.y) * 0.03

  if (sparkles) {
    sparkles.rotation.y += 0.00012
    sparkles.rotation.z += 0.00003
    sparkles.rotation.x += pointer.y * 0.0004
    sparkles.material.opacity = 0.44 + Math.sin(t * 1.1) * 0.08
  }
  if (orbs) {
    orbs.rotation.y += 0.00005
    orbs.children.forEach((sprite) => {
      if (!sprite.material) return
      sprite.material.opacity =
        sprite.userData.baseOpacity * (1 + Math.sin(pulse + sprite.userData.phase) * 0.2)
      // Медленный дрейф вокруг исходной точки.
      const drift = Math.sin(pulse * 0.6 + sprite.userData.phase) * 1.6
      sprite.position.x = sprite.userData.home.x + drift
      sprite.position.y = sprite.userData.home.y + Math.cos(pulse * 0.5 + sprite.userData.phase) * 1.2
    })
  }
  camera.position.x += (pointer.x * 1.4 - camera.position.x) * 0.02
  camera.position.y += (-pointer.y * 1.0 - camera.position.y) * 0.02
  camera.lookAt(0, 0, 0)
  renderer.render(scene, camera)
}

onMounted(() => {
  reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const el = host.value

  renderer = new THREE.WebGLRenderer({ alpha: true, antialias: false, powerPreference: 'low-power' })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.setSize(el.clientWidth, el.clientHeight, false)
  el.appendChild(renderer.domElement)
  renderer.domElement.style.position = 'absolute'
  renderer.domElement.style.inset = '0'

  scene = new THREE.Scene()
  camera = new THREE.PerspectiveCamera(58, el.clientWidth / el.clientHeight, 0.1, 200)
  camera.position.z = 30

  orbs = makeOrbs()
  scene.add(orbs)
  sparkles = makeSparkles()
  scene.add(sparkles)

  // Первый кадр рисуем сразу — во «скрытой» вкладке (headless) цикл не стартует.
  renderer.render(scene, camera)

  if (!reduced) {
    resizeObserver = new ResizeObserver(onResize)
    resizeObserver.observe(el)
    window.addEventListener('pointermove', onPointer, { passive: true })
    document.addEventListener('visibilitychange', onVisibility)
    running = !document.hidden
    tick()
  }
})

onBeforeUnmount(() => {
  if (rafId) cancelAnimationFrame(rafId)
  running = false
  if (resizeObserver) resizeObserver.disconnect()
  window.removeEventListener('pointermove', onPointer)
  document.removeEventListener('visibilitychange', onVisibility)
  if (renderer) {
    renderer.dispose()
    if (sparkles) { sparkles.geometry.dispose(); sparkles.material.map?.dispose(); sparkles.material.dispose() }
    if (orbs) {
      orbs.traverse((obj) => { if (obj.material) { obj.material.map?.dispose(); obj.material.dispose() } })
    }
    if (renderer.domElement.parentNode) renderer.domElement.parentNode.removeChild(renderer.domElement)
    renderer = null
  }
})
</script>

<template>
  <div ref="host" class="pointer-events-none fixed inset-0 z-0 overflow-hidden" aria-hidden="true"></div>
</template>
