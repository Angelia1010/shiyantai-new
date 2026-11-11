/**
 * 试验台三维场景（three.js r128）。
 *
 * 与 Vue 无关，组件只需：
 *   const scene = new TestBenchScene(container, callbacks)
 *   scene.setView('overview') / setStyle('tech') / setColorMode('temperature')
 *   scene.updateData(featureMap) / setAlarms(['回油流量计1']) / focusComponent(key)
 *   scene.dispose()
 *
 * callbacks:
 *   onProgress(ratio)            模型加载进度 0–1
 *   onLoaded(components)         加载完成，参数为 [{ key, label, fields }]
 *   onError(message)
 *   onHover(info | null)         { key, label, x, y }，x/y 为相对容器的像素坐标
 *   onSelect(key | null)
 *   onLegend(legend | null)      { mode, min, max, unit }
 */
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader'
import { RGBELoader } from 'three/examples/jsm/loaders/RGBELoader'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls'
import { CSS2DObject, CSS2DRenderer } from 'three/examples/jsm/renderers/CSS2DRenderer'
import { COLOR_MODES, COMPONENTS, STYLES, VIEWS } from './components'
import { fieldUnit, formatValue } from '@/utils/features'

const MODEL_URL = '/model/shiyantai5.glb'
const ENV_URL = '/qwantani_dusk_1_puresky_4k.hdr'
const ASSEMBLY_NODE = '总装图'
const FLY_DURATION_MS = 900
const EDGE_THRESHOLD_DEG = 28 // 相邻面夹角大于该值才画轮廓线
const FOG_COLOR = 0x0a1424
const HOVER_EMISSIVE = new THREE.Color(0x2f6bff)
const SELECT_EMISSIVE = new THREE.Color(0x3f8cff)
const ALARM_COLOR = new THREE.Color(0xff3b3b)
const HIGHLIGHT_EDGE = new THREE.Color(0xe6f6ff)
const NEUTRAL_COLOR = new THREE.Color(0x2a3442)
const NEUTRAL_EDGE = new THREE.Color(0x29435f)
// 色标：蓝 → 青 → 绿 → 黄 → 红，与图例 CSS 渐变一致
export const COLOR_STOPS = ['#2563eb', '#06b6d4', '#22c55e', '#facc15', '#ef4444']
const STOP_COLORS = COLOR_STOPS.map(c => new THREE.Color(c))
// 显示悬浮数值标签的部件
const LABELED = ['被试件1高低压双联泵', '供油管路', '回油管路', '回油流量计1', '回油流量计2']

// 科技风动态效果
const INTRO_MS = 2600 // 加载后：镜头推进 + 模型自下而上“生成”
const SCAN_PERIOD_MS = 7000 // 扫描光带周期
const SCAN_SWEEP_MS = 2600 // 每次扫描用时
const RIPPLE_PERIOD_MS = 3600 // 地面波纹周期
const RIPPLE_COUNT = 3
const PARTICLE_COUNT = 260
const AUTO_ROTATE_IDLE_MS = 15000 // 无操作多久后开始缓慢自转

// 注入到部件材质与轮廓线材质的着色代码：扫描光带 + 生成动画（revealY 以上的片元丢弃）
const FX_VERTEX_DECL = 'varying vec3 vFxWorld;\n'
const FX_VERTEX_BODY = '#include <project_vertex>\nvFxWorld = (modelMatrix * vec4(transformed, 1.0)).xyz;'
const FX_FRAGMENT_DECL = `uniform float scanY;
uniform float scanWidth;
uniform vec3 scanColor;
uniform float scanStrength;
uniform float revealY;
varying vec3 vFxWorld;
`
const FX_FRAGMENT_BODY = `if (vFxWorld.y > revealY) discard;
float fxBand = scanStrength * (1.0 - smoothstep(0.0, scanWidth, abs(vFxWorld.y - scanY)));
float fxEdge = 1.0 - smoothstep(0.0, scanWidth * 0.6, abs(vFxWorld.y - revealY));
gl_FragColor.rgb += scanColor * (fxBand * FX_GAIN + fxEdge * 1.6);
#include <tonemapping_fragment>`

const easeInOutCubic = t => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)

function gradientColor(t, target) {
  const x = Math.min(1, Math.max(0, t)) * (STOP_COLORS.length - 1)
  const i = Math.min(STOP_COLORS.length - 2, Math.floor(x))
  return target.copy(STOP_COLORS[i]).lerp(STOP_COLORS[i + 1], x - i)
}

/** 模型节点名（GLTFLoader 会去掉名字里的 “.”，如 “回油流量计1.002” → “回油流量计1002”）→ 部件 key。 */
function matchComponent(nodeName) {
  let best = null
  for (const key of Object.keys(COMPONENTS)) {
    if (nodeName.startsWith(key) && (!best || key.length > best.length)) best = key
  }
  return best
}

function average(featureMap, fields) {
  let sum = 0
  let n = 0
  for (const f of fields || []) {
    const stat = featureMap && featureMap[f]
    if (stat && typeof stat.avg === 'number' && !Number.isNaN(stat.avg)) {
      sum += stat.avg
      n++
    }
  }
  return n ? sum / n : null
}

/** 地面底座贴图：同心圆环 + 刻度 + 中心光晕。 */
function baseTexture() {
  const size = 1024
  const c = size / 2
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = size
  const ctx = canvas.getContext('2d')
  const glow = ctx.createRadialGradient(c, c, 0, c, c, c)
  glow.addColorStop(0, 'rgba(56,140,255,0.28)')
  glow.addColorStop(0.55, 'rgba(30,90,180,0.10)')
  glow.addColorStop(1, 'rgba(10,30,70,0)')
  ctx.fillStyle = glow
  ctx.fillRect(0, 0, size, size)

  const ring = (r, width, alpha) => {
    ctx.beginPath()
    ctx.arc(c, c, r * c, 0, Math.PI * 2)
    ctx.lineWidth = width
    ctx.strokeStyle = `rgba(90,190,255,${alpha})`
    ctx.stroke()
  }
  ring(0.42, 2, 0.35)
  ring(0.62, 1.5, 0.22)
  ring(0.9, 3, 0.3)
  ring(0.93, 1, 0.18)
  // 外圈刻度
  for (let i = 0; i < 120; i++) {
    const a = (i / 120) * Math.PI * 2
    const long = i % 10 === 0
    const r1 = 0.9 * c
    const r2 = (long ? 0.86 : 0.88) * c
    ctx.beginPath()
    ctx.moveTo(c + Math.cos(a) * r1, c + Math.sin(a) * r1)
    ctx.lineTo(c + Math.cos(a) * r2, c + Math.sin(a) * r2)
    ctx.lineWidth = long ? 2 : 1
    ctx.strokeStyle = `rgba(90,190,255,${long ? 0.45 : 0.22})`
    ctx.stroke()
  }
  // 四段弧线
  for (let k = 0; k < 4; k++) {
    const start = k * (Math.PI / 2) + 0.2
    ctx.beginPath()
    ctx.arc(c, c, 0.66 * c, start, start + Math.PI / 4)
    ctx.lineWidth = 4
    ctx.strokeStyle = 'rgba(56,189,248,0.4)'
    ctx.stroke()
  }
  const tex = new THREE.CanvasTexture(canvas)
  tex.encoding = THREE.sRGBEncoding
  tex.anisotropy = 4
  return tex
}

/** 发光圆点贴图（粒子用）。 */
function dotTexture() {
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = 64
  const ctx = canvas.getContext('2d')
  const g = ctx.createRadialGradient(32, 32, 0, 32, 32, 32)
  g.addColorStop(0, 'rgba(255,255,255,1)')
  g.addColorStop(0.25, 'rgba(160,220,255,0.8)')
  g.addColorStop(1, 'rgba(56,189,248,0)')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, 64, 64)
  return new THREE.CanvasTexture(canvas)
}

/** 地面光圈：细圆环 + 淡色圆盘，单位半径，通过 scale 控制大小。 */
function makeHalo(color) {
  const group = new THREE.Group()
  const ringMat = new THREE.MeshBasicMaterial({
    color, transparent: true, opacity: 0.9, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide
  })
  const discMat = new THREE.MeshBasicMaterial({
    color, transparent: true, opacity: 0.12, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide
  })
  const ring = new THREE.Mesh(new THREE.RingGeometry(0.9, 1, 96), ringMat)
  const inner = new THREE.Mesh(new THREE.RingGeometry(0.62, 0.65, 96), ringMat)
  const disc = new THREE.Mesh(new THREE.CircleGeometry(1, 96), discMat)
  ;[ring, inner, disc].forEach(m => {
    m.rotation.x = -Math.PI / 2
    m.raycast = () => {}
    group.add(m)
  })
  group.position.y = 0.004
  group.userData.materials = [ringMat, discMat]
  return group
}

export class TestBenchScene {
  constructor(container, callbacks = {}) {
    this.container = container
    this.cb = callbacks
    this.components = {} // key → { key, label, fields, colorBy, category, meshes, material, edgeMaterial, box, ... }
    this.pickables = []
    this.edgeObjects = []
    this.styleName = 'tech'
    this.colorMode = 'none'
    this.featureMap = {}
    this.ranges = { temperature: null, pressure: null }
    this.alarms = new Set()
    this.hoveredKey = null
    this.selectedKey = null
    this.fly = null
    this.pointer = { x: 0, y: 0, dirty: false, inside: false }
    this.disposed = false
    this.needsRender = true
    // 所有部件材质共用的特效参数：边缘光（菲涅尔）、扫描光带、生成动画
    this.fx = {
      rimColor: { value: new THREE.Color(0x38bdf8) },
      rimStrength: { value: STYLES.tech.rim },
      scanY: { value: -1e5 },
      scanWidth: { value: 0.1 },
      scanColor: { value: new THREE.Color(0x7dd3fc) },
      scanStrength: { value: 0 },
      revealY: { value: 1e5 }
    }
    this.effects = true // 科技风动态效果开关（写实风关闭）
    this.alarmHalos = {}
    this.lastInteraction = 0
    this.intro = null

    this._initRenderer()
    this._initScene()
    this._bindEvents()
    this._loadEnvironment()
    this._loadModel()
    this._animate = this._animate.bind(this)
    this.frameId = requestAnimationFrame(this._animate)
  }

  // ------------------------------------------------------------------ 初始化
  _initRenderer() {
    const { clientWidth: w, clientHeight: h } = this.container
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    renderer.setSize(w, h)
    renderer.setClearColor(0x000000, 0) // 背景由容器 CSS 渐变提供
    renderer.outputEncoding = THREE.sRGBEncoding
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = STYLES.tech.exposure
    renderer.shadowMap.enabled = true
    renderer.shadowMap.type = THREE.PCFSoftShadowMap
    renderer.shadowMap.autoUpdate = false // 模型和灯光都是静止的，阴影只在加载后算一次
    renderer.domElement.style.display = 'block'
    this.container.appendChild(renderer.domElement)
    this.renderer = renderer

    const labelRenderer = new CSS2DRenderer()
    labelRenderer.setSize(w, h)
    Object.assign(labelRenderer.domElement.style, { position: 'absolute', top: '0', left: '0', pointerEvents: 'none' })
    this.container.appendChild(labelRenderer.domElement)
    this.labelRenderer = labelRenderer

    this.camera = new THREE.PerspectiveCamera(35, w / Math.max(h, 1), 0.01, 500)
    this.camera.position.set(8, 6, 10)

    const controls = new OrbitControls(this.camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controls.screenSpacePanning = true
    controls.maxPolarAngle = Math.PI * 0.49 // 不能转到地面以下
    controls.rotateSpeed = 0.7
    controls.autoRotateSpeed = 0.35
    controls.addEventListener('change', () => { this.needsRender = true })
    controls.addEventListener('start', () => { this.lastInteraction = performance.now() })
    this.controls = controls
  }

  _initScene() {
    const scene = new THREE.Scene()
    this.scene = scene

    this.hemiLight = new THREE.HemisphereLight(0xdde6ff, 0x101828, 0.55)
    scene.add(this.hemiLight)

    const key = new THREE.DirectionalLight(0xffffff, 1.3)
    key.castShadow = true
    key.shadow.mapSize.set(2048, 2048)
    key.shadow.bias = -0.0004
    key.shadow.normalBias = 0.02
    scene.add(key)
    scene.add(key.target)
    this.keyLight = key

    this.fillLight = new THREE.DirectionalLight(0x7fa8ff, 0.5)
    scene.add(this.fillLight)
    this.rimLight = new THREE.DirectionalLight(0x9fe1ff, 0.8)
    scene.add(this.rimLight)

    // 地面：阴影 + 科技底座贴图 + 两层网格（远处由雾淡出）
    this.ground = new THREE.Group()
    const shadowPlane = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.ShadowMaterial({ opacity: 0.45 }))
    shadowPlane.rotation.x = -Math.PI / 2
    shadowPlane.receiveShadow = true
    this.ground.add(shadowPlane)
    this.shadowPlane = shadowPlane

    const base = new THREE.Mesh(
      new THREE.PlaneGeometry(1, 1),
      new THREE.MeshBasicMaterial({ map: baseTexture(), transparent: true, depthWrite: false })
    )
    base.rotation.x = -Math.PI / 2
    base.position.y = 0.001
    this.ground.add(base)
    this.basePlate = base

    const fineGrid = new THREE.GridHelper(1, 80, 0x1d4f7d, 0x16304c)
    fineGrid.material.transparent = true
    fineGrid.material.opacity = 0.22
    this.ground.add(fineGrid)
    const coarseGrid = new THREE.GridHelper(1, 16, 0x2e78b8, 0x2e78b8)
    coarseGrid.material.transparent = true
    coarseGrid.material.opacity = 0.18
    coarseGrid.position.y = 0.0005
    this.ground.add(coarseGrid)
    this.grids = [fineGrid, coarseGrid]

    scene.add(this.ground)

    // 动态效果：地面波纹、上升粒子、选中/告警光圈（尺寸在模型加载后确定）
    this.fxGroup = new THREE.Group()
    this.ripples = []
    for (let i = 0; i < RIPPLE_COUNT; i++) {
      const ripple = new THREE.Mesh(
        new THREE.RingGeometry(0.97, 1, 128),
        new THREE.MeshBasicMaterial({
          color: 0x38bdf8, transparent: true, opacity: 0, depthWrite: false,
          blending: THREE.AdditiveBlending, side: THREE.DoubleSide
        })
      )
      ripple.rotation.x = -Math.PI / 2
      ripple.position.y = 0.003
      this.fxGroup.add(ripple)
      this.ripples.push(ripple)
    }
    this.selectHalo = makeHalo(0x38bdf8)
    this.selectHalo.visible = false
    scene.add(this.selectHalo)
    scene.add(this.fxGroup)
  }

  /** 按模型尺寸生成上升粒子。 */
  _createParticles(box, radius) {
    const positions = new Float32Array(PARTICLE_COUNT * 3)
    const speeds = new Float32Array(PARTICLE_COUNT)
    const height = (box.max.y - box.min.y) * 1.6
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const a = Math.random() * Math.PI * 2
      const r = radius * (0.25 + Math.random() * 0.95)
      positions[i * 3] = Math.cos(a) * r
      positions[i * 3 + 1] = Math.random() * height
      positions[i * 3 + 2] = Math.sin(a) * r
      speeds[i] = height * (0.02 + Math.random() * 0.05) // 每秒上升高度
    }
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    const material = new THREE.PointsMaterial({
      size: radius * 0.012,
      map: dotTexture(),
      color: 0x7dd3fc,
      transparent: true,
      opacity: 0.75,
      depthWrite: false,
      blending: THREE.AdditiveBlending
    })
    this.particles = new THREE.Points(geometry, material)
    this.particles.raycast = () => {}
    this.particles.userData = { speeds, height }
    this.fxGroup.add(this.particles)
  }

  _loadEnvironment() {
    const pmrem = new THREE.PMREMGenerator(this.renderer)
    pmrem.compileEquirectangularShader()
    new RGBELoader()
      .setDataType(THREE.UnsignedByteType)
      .load(ENV_URL, texture => {
        if (this.disposed) return
        this.envMap = pmrem.fromEquirectangular(texture).texture
        this.scene.environment = this.envMap
        texture.dispose()
        pmrem.dispose()
        this.needsRender = true
      }, undefined, () => {
        // 没有 HDR 文件时只用灯光照明，并适当提亮
        pmrem.dispose()
        this.hemiLight.intensity = 1.0
        this.needsRender = true
      })
  }

  _loadModel() {
    new GLTFLoader().load(
      MODEL_URL,
      gltf => {
        if (this.disposed) return
        try {
          this._setupModel(gltf.scene)
        } catch (e) {
          console.error(e)
          this.cb.onError && this.cb.onError('模型解析失败：' + e.message)
        }
      },
      xhr => {
        // 下载占进度的 90%，剩下的留给生成轮廓线
        if (xhr.lengthComputable && this.cb.onProgress) this.cb.onProgress(0.9 * xhr.loaded / xhr.total)
      },
      err => {
        console.error(err)
        this.cb.onError && this.cb.onError(`模型加载失败，请确认 public${MODEL_URL} 存在`)
      }
    )
  }

  // ------------------------------------------------------------------ 模型
  _setupModel(root) {
    // 模型导出时混入了若干未缩放的零件副本，只保留包含总装体的那一支
    const assembly = root.getObjectByName(ASSEMBLY_NODE)
    if (assembly) {
      let top = assembly
      while (top.parent && top.parent !== root) top = top.parent
      root.children.filter(c => c !== top).forEach(c => root.remove(c))
    }

    // 摆正：底面落在 y=0，水平居中
    const pivot = new THREE.Group()
    pivot.add(root)
    root.updateMatrixWorld(true)
    const box = new THREE.Box3().setFromObject(root)
    const center = box.getCenter(new THREE.Vector3())
    root.position.set(-center.x, -box.min.y, -center.z)
    this.scene.add(pivot)
    this.model = pivot
    pivot.updateMatrixWorld(true)

    this._assignComponents(assembly || root)
    this._fitEnvironment()
    this._createLabels()
    this.setStyle(this.styleName)
    this.setView('overview', false)
    this._startIntro()
    this.renderer.shadowMap.needsUpdate = true
    this.needsRender = true

    this.cb.onProgress && this.cb.onProgress(1)
    this.cb.onLoaded && this.cb.onLoaded(
      Object.values(this.components).map(c => ({ key: c.key, label: c.label, fields: c.fields }))
    )
  }

  /**
   * 给材质注入特效着色代码：
   * - 扫描光带 / 生成动画（所有材质）
   * - 菲涅尔边缘光（rim=true 的实体材质）：视线越掠过表面越亮，营造“全息”质感
   */
  _enhance(material, { rim = false, gain = 1 } = {}) {
    const fx = this.fx
    material.onBeforeCompile = shader => {
      Object.assign(shader.uniforms, {
        scanY: fx.scanY, scanWidth: fx.scanWidth, scanColor: fx.scanColor,
        scanStrength: fx.scanStrength, revealY: fx.revealY
      })
      shader.vertexShader = FX_VERTEX_DECL + shader.vertexShader.replace('#include <project_vertex>', FX_VERTEX_BODY)
      let frag = FX_FRAGMENT_DECL + shader.fragmentShader.replace(
        '#include <tonemapping_fragment>',
        FX_FRAGMENT_BODY.replace('FX_GAIN', gain.toFixed(2))
      )
      if (rim) {
        shader.uniforms.rimColor = fx.rimColor
        shader.uniforms.rimStrength = fx.rimStrength
        frag = 'uniform vec3 rimColor;\nuniform float rimStrength;\n' + frag.replace(
          '#include <emissivemap_fragment>',
          `#include <emissivemap_fragment>
          float rimF = 1.0 - clamp(abs(dot(normalize(normal), normalize(vViewPosition))), 0.0, 1.0);
          totalEmissiveRadiance += rimColor * pow(rimF, 2.2) * rimStrength;`
        )
      }
      shader.fragmentShader = frag
    }
    // 不同注入参数要编译成不同的着色器程序
    material.customProgramCacheKey = () => `fx-${rim}-${gain}`
  }

  _makeComponentMaterials(category) {
    const material = new THREE.MeshStandardMaterial({ color: 0xffffff })
    this._enhance(material, { rim: true, gain: 0.6 })
    const edgeMaterial = new THREE.LineBasicMaterial({
      color: 0x38bdf8,
      transparent: true,
      opacity: 0.55,
      depthWrite: false,
      blending: THREE.AdditiveBlending
    })
    this._enhance(edgeMaterial, { gain: 2.2 })
    return { category, material, edgeMaterial, baseColor: new THREE.Color(), baseEdge: new THREE.Color() }
  }

  _assignComponents(assembly) {
    const replaced = new Set() // CAD 自带的材质，替换后释放
    const glass = new THREE.MeshStandardMaterial({
      color: 0x7fb8e8, metalness: 0.1, roughness: 0.05, transparent: true, opacity: 0.25, depthWrite: false
    })
    this._enhance(glass, { gain: 0.8 })
    this.glassMaterial = glass
    this.defaultMaterials = this._makeComponentMaterials('default')

    assembly.children.forEach(child => {
      const key = matchComponent(child.name)
      const conf = key ? COMPONENTS[key] : null
      let comp = key ? this.components[key] : null
      if (key && !comp) {
        comp = this.components[key] = {
          key,
          label: conf.label,
          fields: conf.fields || [],
          colorBy: conf.colorBy || {},
          selectable: conf.selectable !== false,
          meshes: [],
          box: new THREE.Box3(),
          ...this._makeComponentMaterials(conf.material || 'default')
        }
      }
      const mats = comp || this.defaultMaterials
      const meshes = []
      child.traverse(obj => { if (obj.isMesh) meshes.push(obj) })
      meshes.forEach(obj => {
        const wasTransparent = obj.material && obj.material.transparent && obj.material.opacity < 0.95
        if (obj.material) replaced.add(obj.material)
        obj.material = wasTransparent ? glass : mats.material
        obj.castShadow = !wasTransparent
        obj.receiveShadow = true
        // 轮廓线作为子对象，跟随网格变换
        const edges = new THREE.LineSegments(new THREE.EdgesGeometry(obj.geometry, EDGE_THRESHOLD_DEG), mats.edgeMaterial)
        edges.raycast = () => {} // 不参与拾取
        obj.add(edges)
        this.edgeObjects.push(edges)
        if (comp) {
          obj.userData.componentKey = key
          comp.meshes.push(obj)
          if (comp.selectable) this.pickables.push(obj)
        }
      })
      if (comp) comp.box.union(new THREE.Box3().setFromObject(child))
    })
    replaced.forEach(m => m.dispose())
  }

  /** 按模型尺寸调整相机远近裁剪面、阴影范围、地面、雾。 */
  _fitEnvironment() {
    const box = new THREE.Box3().setFromObject(this.model)
    const size = box.getSize(new THREE.Vector3())
    const radius = box.getBoundingSphere(new THREE.Sphere()).radius
    this.modelBox = box
    this.modelRadius = radius

    this.camera.near = radius / 200
    this.camera.far = radius * 40
    this.camera.updateProjectionMatrix()
    this.controls.minDistance = radius * 0.12
    this.controls.maxDistance = radius * 6

    const span = Math.max(size.x, size.z)
    this.shadowPlane.scale.set(span * 4, span * 4, 1)
    this.basePlate.scale.set(span * 1.45, span * 1.45, 1)
    this.grids.forEach(g => g.scale.setScalar(span * 6))
    this.fog = new THREE.Fog(FOG_COLOR, radius * 2.2, radius * 6.5)
    this.fx.scanWidth.value = size.y * 0.05
    this.rippleSpan = span
    this._createParticles(box, radius)

    const key = this.keyLight
    key.position.set(radius * 1.2, radius * 2, radius * 0.9)
    key.target.position.set(0, 0, 0)
    const cam = key.shadow.camera
    cam.left = cam.bottom = -radius * 1.2
    cam.right = cam.top = radius * 1.2
    cam.near = radius * 0.1
    cam.far = radius * 5
    cam.updateProjectionMatrix()
    this.fillLight.position.set(-radius * 1.5, radius * 0.8, radius)
    this.rimLight.position.set(-radius * 0.5, radius * 1.2, -radius * 2)
  }

  _createLabels() {
    LABELED.forEach(key => {
      const comp = this.components[key]
      if (!comp) return
      const el = document.createElement('div')
      el.className = 'tb-label'
      el.innerHTML = '<div class="tb-label__name"></div><div class="tb-label__value">--</div>'
      el.querySelector('.tb-label__name').textContent = comp.label
      const obj = new CSS2DObject(el)
      const center = comp.box.getCenter(new THREE.Vector3())
      obj.position.set(center.x, comp.box.max.y + this.modelRadius * 0.05, center.z)
      this.scene.add(obj)
      comp.label2d = { obj, el, valueEl: el.querySelector('.tb-label__value') }
    })
  }

  // ------------------------------------------------------------------ 对外接口
  /** 切换外观：'tech' 科技风 / 'real' 写实。 */
  setStyle(name) {
    this.styleName = STYLES[name] ? name : 'tech'
    const style = STYLES[this.styleName]
    this.renderer.toneMappingExposure = style.exposure
    this.rimUniforms.rimStrength.value = style.rim
    this.scene.fog = style.fog && this.fog ? this.fog : null
    this.grids.forEach(g => { g.visible = style.fog })
    this.edgeObjects.forEach(e => { e.visible = style.edges })
    this.effects = !!style.effects
    this.fxGroup.visible = this.effects
    if (!this.effects) {
      this.fx.scanStrength.value = 0
      this.controls.autoRotate = false
    }

    const apply = mats => {
      const preset = style.materials[mats.category] || style.materials.default
      mats.material.metalness = preset.metalness
      mats.material.roughness = preset.roughness
      mats.material.envMapIntensity = style.envIntensity
      mats.baseColor.setHex(preset.color)
      mats.baseEdge.setHex(preset.edge || 0x38bdf8)
      mats.material.color.copy(mats.baseColor)
      mats.edgeMaterial.color.copy(mats.baseEdge)
    }
    Object.values(this.components).forEach(apply)
    if (this.defaultMaterials) apply(this.defaultMaterials)
    this._applyColors()
    this._applyHighlights()
  }

  /** 切换预设视角，或聚焦到某个部件（name 为部件 key）。 */
  setView(name, animate = true) {
    const view = VIEWS[name]
    const focusKey = view ? view.focus : name
    const comp = focusKey && this.components[focusKey]
    const box = comp ? comp.box : this.modelBox
    if (!box) return
    const dir = new THREE.Vector3(...(view ? view.direction : [1, 0.7, 1])).normalize()
    const margin = view ? view.distance : 1.6
    const target = box.getCenter(new THREE.Vector3())
    const dist = Math.max(this._fitDistance(box, target, dir) * margin, this.controls.minDistance * 1.2)
    const position = target.clone().addScaledVector(dir, dist)
    this.lastInteraction = performance.now()
    if (!animate) {
      this.camera.position.copy(position)
      this.controls.target.copy(target)
      this.controls.update()
      this.needsRender = true
      return
    }
    this.fly = {
      start: performance.now(),
      fromPos: this.camera.position.clone(),
      fromTarget: this.controls.target.clone(),
      toPos: position,
      toTarget: target
    }
  }

  /** 从 dir 方向看向 target 时，让整个 box 刚好装进画面所需的相机距离（考虑画面宽高比）。 */
  _fitDistance(box, target, dir) {
    const forward = dir.clone() // 由目标指向相机
    const worldUp = Math.abs(forward.y) > 0.99 ? new THREE.Vector3(0, 0, -1) : new THREE.Vector3(0, 1, 0)
    const right = new THREE.Vector3().crossVectors(worldUp, forward).normalize()
    const up = new THREE.Vector3().crossVectors(forward, right).normalize()
    const tanV = Math.tan(THREE.MathUtils.degToRad(this.camera.fov / 2))
    const tanH = tanV * this.camera.aspect
    let dist = 0
    const p = new THREE.Vector3()
    for (let i = 0; i < 8; i++) {
      p.set(i & 1 ? box.max.x : box.min.x, i & 2 ? box.max.y : box.min.y, i & 4 ? box.max.z : box.min.z).sub(target)
      const depth = p.dot(forward)
      dist = Math.max(dist, depth + Math.abs(p.dot(right)) / tanH, depth + Math.abs(p.dot(up)) / tanV)
    }
    return dist
  }

  focusComponent(key) {
    if (!this.components[key]) return
    this.select(key)
    this.setView(key)
  }

  select(key) {
    this.selectedKey = key && this.components[key] ? key : null
    this._placeHalo(this.selectHalo, this.selectedKey)
    this._applyHighlights()
    this.cb.onSelect && this.cb.onSelect(this.selectedKey)
  }

  setColorMode(mode) {
    this.colorMode = COLOR_MODES[mode] ? mode : 'none'
    this._applyColors()
    this._applyHighlights()
  }

  setLabelsVisible(visible) {
    Object.values(this.components).forEach(c => { if (c.label2d) c.label2d.obj.visible = visible })
    this.needsRender = true
  }

  /** 最新一帧特征 { 测点: { avg, min, max } }。 */
  updateData(featureMap) {
    this.featureMap = featureMap || {}
    this._extendRanges()
    this._applyColors()
    this._applyHighlights()
  }

  setAlarms(keys) {
    this.alarms = new Set((keys || []).filter(k => this.components[k]))
    // 告警部件脚下的红色光圈
    Object.keys(this.alarmHalos).forEach(key => {
      if (this.alarms.has(key)) return
      const halo = this.alarmHalos[key]
      this.scene.remove(halo)
      halo.traverse(o => { if (o.geometry) o.geometry.dispose() })
      halo.userData.materials.forEach(m => m.dispose())
      delete this.alarmHalos[key]
    })
    this.alarms.forEach(key => {
      if (this.alarmHalos[key]) return
      const halo = makeHalo(0xff3b3b)
      this._placeHalo(halo, key)
      this.scene.add(halo)
      this.alarmHalos[key] = halo
    })
    this._applyHighlights()
  }

  /** 把光圈放到部件正下方的地面上。 */
  _placeHalo(halo, key) {
    const comp = key && this.components[key]
    halo.visible = !!comp
    if (!comp) return
    const center = comp.box.getCenter(new THREE.Vector3())
    const size = comp.box.getSize(new THREE.Vector3())
    halo.position.x = center.x
    halo.position.z = center.z
    halo.userData.radius = Math.max(size.x, size.z) * 0.62 + this.modelRadius * 0.03
    halo.scale.setScalar(halo.userData.radius)
    this.needsRender = true
  }

  /** 加载完成动画：镜头从远处推进，模型自下而上生成。 */
  _startIntro() {
    const toPos = this.camera.position.clone()
    const toTarget = this.controls.target.clone()
    const fromPos = toTarget.clone().addScaledVector(toPos.clone().sub(toTarget), 2.1)
    fromPos.y += this.modelRadius * 0.5
    this.camera.position.copy(fromPos)
    this.fly = { start: performance.now(), duration: INTRO_MS, fromPos, fromTarget: toTarget.clone(), toPos, toTarget }
    this.intro = { start: performance.now(), minY: this.modelBox.min.y, maxY: this.modelBox.max.y }
    this.fx.revealY.value = this.modelBox.min.y
    this.lastInteraction = performance.now()
  }

  /** 每帧更新动态效果，返回本帧是否需要重绘。 */
  _updateEffects(now) {
    let active = false
    if (this.intro) {
      const t = Math.min(1, (now - this.intro.start) / INTRO_MS)
      const pad = this.fx.scanWidth.value
      this.fx.revealY.value = this.intro.minY - pad + (this.intro.maxY - this.intro.minY + 2 * pad) * easeInOutCubic(t)
      if (t >= 1) {
        this.intro = null
        this.fx.revealY.value = 1e5
        this.lastScan = now
      }
      active = true
    }
    if (!this.effects || !this.modelBox) return active

    // 周期扫描光带
    if (!this.intro) {
      const phase = (now - (this.lastScan || now)) % SCAN_PERIOD_MS
      if (phase < SCAN_SWEEP_MS) {
        const t = phase / SCAN_SWEEP_MS
        const pad = this.fx.scanWidth.value * 2
        this.fx.scanY.value = this.modelBox.min.y - pad + (this.modelBox.max.y - this.modelBox.min.y + 2 * pad) * t
        this.fx.scanStrength.value = Math.sin(Math.PI * t)
      } else {
        this.fx.scanStrength.value = 0
      }
    }

    // 地面波纹
    this.ripples.forEach((ripple, i) => {
      const t = ((now / RIPPLE_PERIOD_MS) + i / RIPPLE_COUNT) % 1
      ripple.scale.setScalar(this.rippleSpan * (0.2 + 0.55 * t))
      ripple.material.opacity = 0.45 * (1 - t) * Math.min(1, t * 6)
    })

    // 上升粒子
    if (this.particles) {
      const dt = Math.min(0.05, (now - (this.lastFrame || now)) / 1000)
      const pos = this.particles.geometry.attributes.position
      const { speeds, height } = this.particles.userData
      for (let i = 0; i < speeds.length; i++) {
        let y = pos.getY(i) + speeds[i] * dt
        if (y > height) y -= height
        pos.setY(i, y)
      }
      pos.needsUpdate = true
    }

    // 光圈呼吸
    const breathe = 1 + 0.06 * Math.sin(now / 400)
    const halos = [this.selectHalo, ...Object.values(this.alarmHalos)]
    halos.forEach(h => { if (h.visible && h.userData.radius) h.scale.setScalar(h.userData.radius * breathe) })

    // 一段时间无操作后缓慢自转（选中部件时不转）
    this.controls.autoRotate = !this.intro && !this.fly && !this.selectedKey &&
      now - this.lastInteraction > AUTO_ROTATE_IDLE_MS
    return true
  }

  resize() {
    const { clientWidth: w, clientHeight: h } = this.container
    if (!w || !h) return
    this.renderer.setSize(w, h)
    this.labelRenderer.setSize(w, h)
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
    this.needsRender = true
  }

  // ------------------------------------------------------------------ 着色、标签、高亮
  _extendRanges() {
    for (const mode of ['temperature', 'pressure']) {
      for (const comp of Object.values(this.components)) {
        const v = average(this.featureMap, comp.colorBy[mode])
        if (v === null) continue
        const r = this.ranges[mode]
        this.ranges[mode] = r ? { min: Math.min(r.min, v), max: Math.max(r.max, v) } : { min: v, max: v }
      }
    }
  }

  /** 计算每个部件当前应显示的本体色和轮廓色（不含高亮）。 */
  _applyColors() {
    const mode = this.colorMode
    const range = this.ranges[mode]
    for (const comp of Object.values(this.components)) {
      comp.displayColor = comp.displayColor || new THREE.Color()
      comp.displayEdge = comp.displayEdge || new THREE.Color()
      if (mode === 'none') {
        comp.displayColor.copy(comp.baseColor)
        comp.displayEdge.copy(comp.baseEdge)
        continue
      }
      const v = average(this.featureMap, comp.colorBy[mode])
      if (v === null || !range) {
        comp.displayColor.copy(NEUTRAL_COLOR)
        comp.displayEdge.copy(NEUTRAL_EDGE)
      } else {
        const span = range.max - range.min
        gradientColor(span > 1e-9 ? (v - range.min) / span : 0.5, comp.displayColor)
        comp.displayEdge.copy(comp.displayColor)
      }
    }
    this.needsRender = true
    if (this.cb.onLegend) {
      this.cb.onLegend(mode !== 'none' && range ? { mode, unit: COLOR_MODES[mode].unit, ...range } : null)
    }
  }

  _applyHighlights() {
    for (const comp of Object.values(this.components)) {
      const mat = comp.material
      const edge = comp.edgeMaterial
      if (comp.displayColor) mat.color.copy(comp.displayColor)
      if (comp.displayEdge) edge.color.copy(comp.displayEdge)
      edge.opacity = 0.55
      mat.emissive.setRGB(0, 0, 0)
      mat.emissiveIntensity = 1
      if (comp.key === this.selectedKey || comp.key === this.hoveredKey) {
        const selected = comp.key === this.selectedKey
        mat.emissive.copy(selected ? SELECT_EMISSIVE : HOVER_EMISSIVE)
        mat.emissiveIntensity = selected ? 0.45 : 0.3
        edge.color.copy(HIGHLIGHT_EDGE)
        edge.opacity = selected ? 1 : 0.85
      }
    }
    this._updateLabels()
  }

  _updateLabels() {
    for (const comp of Object.values(this.components)) {
      if (!comp.label2d) continue
      // 着色模式下显示与颜色对应的测点，否则显示部件的第一个有数据的测点
      const candidates = (this.colorMode !== 'none' && comp.colorBy[this.colorMode]) || comp.fields
      const field = candidates.find(f => this.featureMap[f]) || candidates[0]
      const stat = field && this.featureMap[field]
      comp.label2d.valueEl.textContent = stat ? `${formatValue(stat.avg)} ${fieldUnit(field)}`.trim() : '--'
      comp.label2d.el.title = field || ''
      comp.label2d.el.classList.toggle('is-alarm', this.alarms.has(comp.key))
      comp.label2d.el.classList.toggle('is-active', comp.key === this.selectedKey)
    }
    this.needsRender = true
  }

  // ------------------------------------------------------------------ 交互
  _bindEvents() {
    const el = this.renderer.domElement
    this._onMove = e => {
      const rect = el.getBoundingClientRect()
      this.pointer.x = e.clientX - rect.left
      this.pointer.y = e.clientY - rect.top
      this.pointer.dirty = true
      this.pointer.inside = true
    }
    this._onLeave = () => {
      this.pointer.inside = false
      this.pointer.dirty = true
    }
    this._onDown = e => {
      this.downAt = { x: e.clientX, y: e.clientY }
      this.lastInteraction = performance.now()
    }
    this._onUp = e => {
      if (!this.downAt || e.button !== 0) return
      const moved = Math.hypot(e.clientX - this.downAt.x, e.clientY - this.downAt.y)
      this.downAt = null
      if (moved > 4) return // 拖动视角，不算点击
      const key = this._pick(e.clientX, e.clientY)
      if (key) this.focusComponent(key)
      else this.select(null)
    }
    el.addEventListener('pointermove', this._onMove)
    el.addEventListener('pointerleave', this._onLeave)
    el.addEventListener('pointerdown', this._onDown)
    el.addEventListener('pointerup', this._onUp)

    if (window.ResizeObserver) {
      this.resizeObserver = new ResizeObserver(() => this.resize())
      this.resizeObserver.observe(this.container)
    } else {
      this._onResize = () => this.resize()
      window.addEventListener('resize', this._onResize)
    }
    this.raycaster = new THREE.Raycaster()
  }

  _pick(clientX, clientY) {
    if (!this.pickables.length) return null
    const rect = this.renderer.domElement.getBoundingClientRect()
    const ndc = new THREE.Vector2(
      ((clientX - rect.left) / rect.width) * 2 - 1,
      -((clientY - rect.top) / rect.height) * 2 + 1
    )
    this.raycaster.setFromCamera(ndc, this.camera)
    const hit = this.raycaster.intersectObjects(this.pickables, false)[0]
    return hit ? hit.object.userData.componentKey : null
  }

  _processHover() {
    if (!this.pointer.dirty) return
    this.pointer.dirty = false
    const rect = this.renderer.domElement.getBoundingClientRect()
    const key = this.pointer.inside ? this._pick(rect.left + this.pointer.x, rect.top + this.pointer.y) : null
    if (key !== this.hoveredKey) {
      this.hoveredKey = key
      this.renderer.domElement.style.cursor = key ? 'pointer' : ''
      this._applyHighlights()
    }
    if (this.cb.onHover) {
      this.cb.onHover(key ? { key, label: this.components[key].label, x: this.pointer.x, y: this.pointer.y } : null)
    }
  }

  // ------------------------------------------------------------------ 渲染循环
  _animate(now) {
    if (this.disposed) return
    this.frameId = requestAnimationFrame(this._animate)

    if (this.fly) {
      const t = Math.min(1, (now - this.fly.start) / (this.fly.duration || FLY_DURATION_MS))
      const k = easeInOutCubic(t)
      this.camera.position.lerpVectors(this.fly.fromPos, this.fly.toPos, k)
      this.controls.target.lerpVectors(this.fly.fromTarget, this.fly.toTarget, k)
      if (t >= 1) this.fly = null
    }
    const animating = this._updateEffects(now)
    this.lastFrame = now
    this.controls.update()
    this._processHover()

    if (this.alarms.size) {
      const pulse = 0.5 + 0.5 * Math.sin(now / 220)
      this.alarms.forEach(key => {
        const comp = this.components[key]
        comp.material.emissive.copy(ALARM_COLOR)
        comp.material.emissiveIntensity = 0.15 + 0.45 * pulse
        comp.edgeMaterial.color.copy(ALARM_COLOR)
        comp.edgeMaterial.opacity = 0.4 + 0.6 * pulse
      })
    }

    // 按需渲染：画面没有变化时不重绘，降低 GPU 占用
    if (this.needsRender || animating || this.fly || this.alarms.size) {
      this.needsRender = false
      this.renderer.render(this.scene, this.camera)
      this.labelRenderer.render(this.scene, this.camera)
    }
  }

  dispose() {
    this.disposed = true
    cancelAnimationFrame(this.frameId)
    const el = this.renderer.domElement
    el.removeEventListener('pointermove', this._onMove)
    el.removeEventListener('pointerleave', this._onLeave)
    el.removeEventListener('pointerdown', this._onDown)
    el.removeEventListener('pointerup', this._onUp)
    if (this.resizeObserver) this.resizeObserver.disconnect()
    if (this._onResize) window.removeEventListener('resize', this._onResize)
    this.controls.dispose()

    const materials = new Set()
    this.scene.traverse(obj => {
      if (obj.geometry) obj.geometry.dispose()
      if (obj.material) [].concat(obj.material).forEach(m => materials.add(m))
    })
    materials.forEach(m => {
      if (m.map) m.map.dispose()
      m.dispose()
    })
    if (this.envMap) this.envMap.dispose()
    this.renderer.dispose()
    if (this.renderer.forceContextLoss) this.renderer.forceContextLoss()
    el.remove()
    this.labelRenderer.domElement.remove()
  }
}
