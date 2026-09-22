<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from '../i18n'

const props = defineProps({ src: String })
const { t } = useI18n()

const box = ref(null)
const pct = ref(0)
const fail = ref('')

// three is half a megabyte of parse; a run that never yields a mesh should not pay for
// it, so it is pulled in only when this component actually mounts.
let v = null
let ro = null
let dead = false

function fit() {
  if (!v || !box.value) return
  const w = box.value.clientWidth, h = box.value.clientHeight
  if (!w || !h) return
  v.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  v.renderer.setSize(w, h, false)
  v.camera.aspect = w / h
  v.camera.updateProjectionMatrix()
}

function reset() {
  if (!v) return
  v.camera.position.copy(v.home)
  v.controls.target.set(0, 0, 0)
  v.controls.autoRotate = true
  v.controls.update()
}

function place(obj) {
  const { THREE, camera, controls } = v
  // The mesh chains hand back shells whose winding and normals are not consistent;
  // single-sided culling makes half of them vanish from any given angle.
  obj.traverse((o) => {
    if (!o.isMesh) return
    for (const m of [].concat(o.material || [])) { m.side = THREE.DoubleSide; m.needsUpdate = true }
  })
  const span = new THREE.Box3().setFromObject(obj)
  const center = span.getCenter(new THREE.Vector3())
  const r = Math.max(span.getSize(new THREE.Vector3()).length() / 2, 1e-4)
  obj.position.sub(center)
  v.scene.add(obj)
  v.model = obj
  // The stage is not always square, so the narrower of the two angles has to fit.
  const fov = THREE.MathUtils.degToRad(camera.fov) * Math.min(1, camera.aspect || 1)
  const d = r / Math.sin(fov / 2)
  camera.position.set(d * 0.8, d * 0.45, d * 0.8)
  v.home = camera.position.clone()
  controls.minDistance = r * 0.12
  controls.maxDistance = r * 24
  controls.target.set(0, 0, 0)
  controls.update()
  pct.value = 100
}

async function boot() {
  const [THREE, { OrbitControls }, { GLTFLoader }] = await Promise.all([
    import('three'),
    import('three/addons/controls/OrbitControls.js'),
    import('three/addons/loaders/GLTFLoader.js'),
  ])
  if (dead || !box.value) return
  const canvas = document.createElement('canvas')
  box.value.appendChild(canvas)
  let renderer
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true })
  } catch {
    fail.value = t.value.meshNoGL
    return
  }
  const scene = new THREE.Scene()
  const camera = new THREE.PerspectiveCamera(35, 1, 0.01, 500)
  const controls = new OrbitControls(camera, canvas)
  controls.enableDamping = true
  controls.autoRotate = true
  controls.autoRotateSpeed = 1.1
  controls.addEventListener('start', () => { controls.autoRotate = false })
  scene.add(new THREE.HemisphereLight(0xffffff, 0x2a3550, 2.4))
  const key = new THREE.DirectionalLight(0xffffff, 2.2)
  key.position.set(1, 2.2, 1.6)
  scene.add(key)
  const rim = new THREE.DirectionalLight(0xffffff, 1.1)
  rim.position.set(-1.6, -0.4, -1.2)
  scene.add(rim)
  v = { THREE, renderer, scene, camera, controls, canvas, loader: new GLTFLoader(), model: null, home: null }
  ro = new ResizeObserver(fit)
  ro.observe(box.value)
  fit()
  renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene, camera) })
  v.loader.load(props.src, (g) => !dead && place(g.scene),
    (e) => e.total && (pct.value = Math.min(99, Math.round((e.loaded / e.total) * 100))),
    () => { if (!dead) fail.value = t.value.meshFail })
}

function teardown() {
  ro?.disconnect()
  ro = null
  if (!v) return
  const { renderer, controls, canvas, model, loader } = v
  loader.abort()
  controls.dispose()
  model?.traverse((o) => {
    o.geometry?.dispose()
    for (const m of [].concat(o.material || [])) {
      for (const k of ['map', 'normalMap', 'metalnessMap', 'roughnessMap', 'emissiveMap', 'aoMap']) m[k]?.dispose()
      m.dispose()
    }
  })
  renderer.setAnimationLoop(null)
  renderer.dispose()
  canvas.remove()
  v = null
}

onMounted(boot)
onBeforeUnmount(() => { dead = true; teardown() })
</script>

<template>
  <div ref="box" class="mv" @dblclick="reset">
    <p v-if="fail" class="lbnote">{{ fail }}</p>
    <p v-else-if="pct < 100" class="mvload mono">{{ t.meshLoading }} {{ pct }}%</p>
    <p v-else class="mvhint">{{ t.meshHint }}</p>
  </div>
</template>
