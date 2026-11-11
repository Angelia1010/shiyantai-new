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
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer'
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass'
import { ShaderPass } from 'three/examples/jsm/postprocessing/ShaderPass'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass'
import { GammaCorrectionShader } from 'three/examples/jsm/shaders/GammaCorrectionShader'
import { COLOR_MODES, COMPONENTS, STYLES, VIEWS } from './components'
import { fieldUnit, formatValue } from '@/utils/features'

const MODEL_URL = '/model/shiyantai5.glb'
const ENV_URL = '/qwantani_dusk_1_puresky_4k.hdr'
const ASSEMBLY_NODE = '总装图'
const FLY_DURATION_MS = 900
const EDGE_THRESHOLD_DEG = 40 // 相邻面夹角大于该值才画轮廓线（调大可减少细碎线条）
const FOG_COLOR = 0x08111f // 与背景渐变中段（地平线）一致，远处地面自然融入背景
// three.js r128 把 Color 的十六进制值当作线性空间，而输出是 sRGB，
// 直接用设计稿颜色会整体发白、发灰，所以统一先转换到线性空间
const srgb = hex => new THREE.Color(hex).convertSRGBToLinear()
const HOVER_EMISSIVE = srgb(0x2f6bff)
const SELECT_EMISSIVE = srgb(0x3f8cff)
const ALARM_COLOR = srgb(0xff3b3b)
const HIGHLIGHT_EDGE = srgb(0xe6f6ff)
const NEUTRAL_COLOR = srgb(0x2a3442)
const NEUTRAL_EDGE = srgb(0x29435f)
// 色标：蓝 → 青 → 绿 → 黄 → 红，与图例 CSS 渐变一致
export const COLOR_STOPS = ['#2563eb', '#06b6d4', '#22c55e', '#facc15', '#ef4444']
const STOP_COLORS = COLOR_STOPS.map(srgb)
// 显示悬浮标签的部件（管路贯穿整台设备，标签位置没有意义，不加）
// 值为引线长度（像素）：两个流量计挨得很近，引线一短一长把标签上下错开
const LABELED = { 被试件1高低压双联泵: 46, 回油流量计1: 34, 回油流量计2: 78 }

// 科技风动态效果
const INTRO_MS = 2600 // 加载后：镜头推进 + 模型自下而上“生成”
const SCAN_PERIOD_MS = 7000 // 扫描光带周期
const SCAN_SWEEP_MS = 2600 // 每次扫描用时
const RIPPLE_PERIOD_MS = 3600 // 地面波纹周期
const RIPPLE_COUNT = 3
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
// 管路“流动”光斑：以油液来源部件为起点，按距离向外移动（光斑头部朝流动方向），用本体颜色提亮
const FX_FLOW_DECL = 'uniform float fxTime;\nuniform float flowStrength;\nuniform vec3 flowSource;\n'
const FX_FLOW_BODY = `float flowPhase = fract(distance(vFxWorld, flowSource) * 2.2 - fxTime * 0.7);
gl_FragColor.rgb += diffuseColor.rgb * smoothstep(0.82, 1.0, flowPhase) * 2.2 * flowStrength;
`
const FX_FRAGMENT_BODY = `if (vFxWorld.y > revealY) discard;
float fxBand = scanStrength * (1.0 - smoothstep(0.0, scanWidth, abs(vFxWorld.y - scanY)));
float fxEdge = 1.0 - smoothstep(0.0, scanWidth * 0.6, abs(vFxWorld.y - revealY));
gl_FragColor.rgb += scanColor * (fxBand * FX_GAIN + fxEdge * 1.6);
#include <tonemapping_fragment>`

// 选择性辉光：只有加入 BLOOM_LAYER 的物体（管路轮廓线、光圈、波纹、粒子）发光
const BLOOM_MIX = 0.7 // 辉光叠加比例
const BLOOM_LAYER = 1
const MIX_SHADER = { // 正常画面 + 辉光
  vertexShader: `varying vec2 vUv;
void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
  fragmentShader: `uniform sampler2D baseTexture;
uniform sampler2D bloomTexture;
varying vec2 vUv;
void main() {
  vec4 base = texture2D(baseTexture, vUv);
  vec3 bloom = texture2D(bloomTexture, vUv).rgb;
  gl_FragColor = vec4(base.rgb + bloom * BLOOM_MIX, base.a);
}`
}

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

/**
 * 地面底座贴图：贴合模型占地的圆角矩形——内部淡光、发光边框、四角折线、长边刻度。
 * aspect 为宽/高，贴图按该比例绘制，拉伸到底座上时线条粗细保持一致。
 */
function footprintTexture(aspect, outlineOnly = false) {
  const w = 2048
  const h = Math.max(256, Math.round(w / aspect))
  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d')
  const m = 24 // 边距
  const r = Math.min(h, w) * 0.12 // 圆角
  const roundRect = (x, y, rw, rh, rr) => {
    ctx.beginPath()
    ctx.moveTo(x + rr, y)
    ctx.arcTo(x + rw, y, x + rw, y + rh, rr)
    ctx.arcTo(x + rw, y + rh, x, y + rh, rr)
    ctx.arcTo(x, y + rh, x, y, rr)
    ctx.arcTo(x, y, x + rw, y, rr)
    ctx.closePath()
  }
  if (outlineOnly) {
    // 波纹：只有一圈细边
    roundRect(m, m, w - 2 * m, h - 2 * m, r)
    ctx.lineWidth = 6
    ctx.strokeStyle = 'rgba(90,190,255,1)'
    ctx.stroke()
  } else {
    const fill = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2)
    fill.addColorStop(0, 'rgba(56,140,255,0.12)')
    fill.addColorStop(1, 'rgba(20,60,130,0.04)')
    roundRect(m, m, w - 2 * m, h - 2 * m, r)
    ctx.fillStyle = fill
    ctx.fill()
    ctx.lineWidth = 5
    ctx.strokeStyle = 'rgba(90,190,255,0.4)'
    ctx.stroke()
    roundRect(m + 28, m + 28, w - 2 * m - 56, h - 2 * m - 56, r * 0.8)
    ctx.lineWidth = 2
    ctx.strokeStyle = 'rgba(90,190,255,0.22)'
    ctx.stroke()
    // 四角折线
    ctx.lineWidth = 10
    ctx.strokeStyle = 'rgba(125,211,252,0.75)'
    const c = Math.min(h, w) * 0.22
    ;[[m, m, 1, 1], [w - m, m, -1, 1], [m, h - m, 1, -1], [w - m, h - m, -1, -1]].forEach(([x, y, dx, dy]) => {
      ctx.beginPath()
      ctx.moveTo(x + dx * (r + c), y)
      ctx.lineTo(x + dx * r, y)
      ctx.moveTo(x, y + dy * r)
      ctx.lineTo(x, y + dy * (r + c * 0.6))
      ctx.stroke()
    })
    // 长边刻度
    ctx.lineWidth = 3
    ctx.strokeStyle = 'rgba(90,190,255,0.35)'
    for (let x = m + r + 40; x < w - m - r - 20; x += 40) {
      const long = Math.round((x - m) / 40) % 5 === 0
      ;[m + 28, h - m - 28].forEach((y, k) => {
        ctx.beginPath()
        ctx.moveTo(x, y)
        ctx.lineTo(x, y + (k ? -1 : 1) * (long ? 26 : 14))
        ctx.stroke()
      })
    }
  }
  const tex = new THREE.CanvasTexture(canvas)
  tex.encoding = THREE.sRGBEncoding
  tex.anisotropy = 8
  return tex
}

/** 科技风背景：上暗下亮的竖直渐变（不透明，避免辉光与透明背景叠加出色块）。 */
function backgroundTexture() {
  const canvas = document.createElement('canvas')
  canvas.width = 4
  canvas.height = 512
  const ctx = canvas.getContext('2d')
  const g = ctx.createLinearGradient(0, 0, 0, 512)
  g.addColorStop(0, '#03070f')
  g.addColorStop(0.5, '#08111f')
  g.addColorStop(1, '#0a1628')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, 4, 512)
  const tex = new THREE.CanvasTexture(canvas)
  tex.encoding = THREE.sRGBEncoding
  return tex
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
      rimColor: { value: srgb(0x38bdf8) },
      rimStrength: { value: STYLES.tech.rim },
      scanY: { value: -1e5 },
      scanWidth: { value: 0.1 },
      scanColor: { value: srgb(0x7dd3fc) },
      scanStrength: { value: 0 },
      revealY: { value: 1e5 },
      fxTime: { value: 0 },
      flowStrength: { value: 1 }
    }
    this.effects = true // 科技风动态效果开关（写实风关闭）
    this.alarmHalos = {}
    this.lastInteraction = 0
    this.intro = null

    this._initRenderer()
    this._initScene()
    this._initPostprocessing()
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

    this.camera = new THREE.PerspectiveCamera(30, w / Math.max(h, 1), 0.01, 500)
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

    this.hemiLight = new THREE.HemisphereLight(0xdde6ff, 0x0b1220, 0.3)
    scene.add(this.hemiLight)

    const key = new THREE.DirectionalLight(0xffffff, 2.0) // 主光加强，拉开明暗层次
    key.castShadow = true
    key.shadow.mapSize.set(2048, 2048)
    key.shadow.bias = -0.0004
    key.shadow.normalBias = 0.02
    scene.add(key)
    scene.add(key.target)
    this.keyLight = key

    this.fillLight = new THREE.DirectionalLight(0x7fa8ff, 0.25)
    scene.add(this.fillLight)
    this.rimLight = new THREE.DirectionalLight(0x9fe1ff, 0.6)
    scene.add(this.rimLight)

    // 地面：阴影 + 科技底座贴图 + 两层网格（远处由雾淡出）
    this.ground = new THREE.Group()
    // 实体深色地面：接收阴影，让设备“落地”；远处由雾融入背景
    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(1, 1),
      new THREE.MeshStandardMaterial({ color: srgb(0x070d18), metalness: 0.1, roughness: 0.9, envMapIntensity: 0.3 })
    )
    floor.rotation.x = -Math.PI / 2
    floor.position.y = -0.001
    floor.receiveShadow = true
    this.ground.add(floor)
    this.floor = floor

    const base = new THREE.Mesh(
      new THREE.PlaneGeometry(1, 1),
      new THREE.MeshBasicMaterial({ transparent: true, depthWrite: false, opacity: 0 }) // 贴图在模型加载后按占地比例生成
    )
    base.rotation.x = -Math.PI / 2
    base.position.y = 0.001
    this.ground.add(base)
    this.basePlate = base

    const grid = new THREE.GridHelper(1, 24, 0x1e4a78, 0x1e4a78)
    grid.material.transparent = true
    grid.material.opacity = 0.12
    grid.position.y = 0.0005
    this.ground.add(grid)
    this.grids = [grid]

    scene.add(this.ground)

    // 动态效果：地面波纹、选中/告警光圈（尺寸在模型加载后确定）
    this.fxGroup = new THREE.Group()
    this.ripples = []
    // 波纹：与底座同形状的圆角矩形边框，从底座边缘向外扩散
    for (let i = 0; i < RIPPLE_COUNT; i++) {
      const ripple = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({
        color: 0x38bdf8, transparent: true, opacity: 0, depthWrite: false,
        blending: THREE.AdditiveBlending, side: THREE.DoubleSide
      }))
      ripple.rotation.x = -Math.PI / 2
      ripple.position.y = 0.003
      ripple.layers.enable(BLOOM_LAYER)
      this.fxGroup.add(ripple)
      this.ripples.push(ripple)
    }
    this.selectHalo = makeHalo(0x38bdf8)
    this.selectHalo.visible = false
    scene.add(this.selectHalo)
    scene.add(this.fxGroup)
    this._glow(this.selectHalo)
  }

  /**
   * 后期处理：两次渲染实现选择性辉光。
   * 1. bloomComposer：非发光物体换成纯黑（透明物体隐藏），只对发光物体做 UnrealBloom
   * 2. finalComposer：正常渲染 + 叠加辉光 + 转 sRGB
   * 任何一步失败都退回普通渲染，不影响使用。
   */
  _initPostprocessing() {
    try {
      const renderer = this.renderer
      const { clientWidth: w, clientHeight: h } = this.container
      this.bloomLayer = new THREE.Layers()
      this.bloomLayer.set(BLOOM_LAYER)
      this.darkMaterial = new THREE.MeshBasicMaterial({ color: 0x000000 })

      const bloomComposer = new EffectComposer(renderer)
      bloomComposer.renderToScreen = false
      bloomComposer.addPass(new RenderPass(this.scene, this.camera))
      this.bloomPass = new UnrealBloomPass(new THREE.Vector2(w, h), 1, 0.4, 0)
      bloomComposer.addPass(this.bloomPass)

      // WebGL2 下用多重采样渲染目标，保证细线条抗锯齿
      const size = renderer.getDrawingBufferSize(new THREE.Vector2())
      const params = { minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter, format: THREE.RGBAFormat }
      const target = renderer.capabilities.isWebGL2 && THREE.WebGLMultisampleRenderTarget
        ? new THREE.WebGLMultisampleRenderTarget(size.x, size.y, params)
        : new THREE.WebGLRenderTarget(size.x, size.y, params)
      const finalComposer = new EffectComposer(renderer, target)
      finalComposer.addPass(new RenderPass(this.scene, this.camera))
      const mix = new ShaderPass(new THREE.ShaderMaterial({
        uniforms: {
          baseTexture: { value: null },
          bloomTexture: { value: bloomComposer.renderTarget2.texture }
        },
        vertexShader: MIX_SHADER.vertexShader,
        fragmentShader: MIX_SHADER.fragmentShader.replace('BLOOM_MIX', BLOOM_MIX.toFixed(2))
      }), 'baseTexture')
      mix.needsSwap = true
      finalComposer.addPass(mix)
      finalComposer.addPass(new ShaderPass(GammaCorrectionShader))

      // 传入自定义渲染目标时 EffectComposer 默认像素比为 1，高分屏下会以一半分辨率渲染导致发糊
      const pixelRatio = renderer.getPixelRatio()
      bloomComposer.setPixelRatio(pixelRatio)
      finalComposer.setPixelRatio(pixelRatio)
      this.bloomComposer = bloomComposer
      this.finalComposer = finalComposer
      this.hiddenForBloom = []
      this.swappedForBloom = []
    } catch (e) {
      console.warn('辉光后期处理不可用，使用普通渲染', e)
      this.bloomComposer = this.finalComposer = null
    }
  }

  /** 把物体加入辉光层。 */
  _glow(obj) {
    obj.traverse(o => o.layers.enable(BLOOM_LAYER))
  }

  _render() {
    const bloom = this.bloomComposer && this.bloomEnabled
    if (!bloom) {
      this.renderer.render(this.scene, this.camera)
      return
    }
    try {
      // 第一遍：只保留发光物体
      const fog = this.scene.fog
      const background = this.scene.background
      this.scene.fog = null
      this.scene.background = null
      this.scene.traverse(obj => {
        if (!(obj.isMesh || obj.isLine || obj.isPoints) || !obj.visible) return
        if (this.bloomLayer.test(obj.layers)) return
        if (obj.material.transparent) {
          obj.visible = false
          this.hiddenForBloom.push(obj)
        } else {
          this.swappedForBloom.push([obj, obj.material])
          obj.material = this.darkMaterial
        }
      })
      this.bloomComposer.render()
      this.hiddenForBloom.forEach(obj => { obj.visible = true })
      this.swappedForBloom.forEach(([obj, material]) => { obj.material = material })
      this.hiddenForBloom.length = 0
      this.swappedForBloom.length = 0
      this.scene.fog = fog
      this.scene.background = background
      // 第二遍：正常画面 + 辉光
      this.finalComposer.render()
    } catch (e) {
      console.warn('辉光渲染失败，改用普通渲染', e)
      this.bloomComposer = null
      this.renderer.render(this.scene, this.camera)
    }
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
  _enhance(material, { rim = false, gain = 1, flow = false } = {}) {
    const fx = this.fx
    if (flow) material.userData.flowSource = { value: new THREE.Vector3() }
    material.onBeforeCompile = shader => {
      Object.assign(shader.uniforms, {
        scanY: fx.scanY, scanWidth: fx.scanWidth, scanColor: fx.scanColor,
        scanStrength: fx.scanStrength, revealY: fx.revealY
      })
      shader.vertexShader = FX_VERTEX_DECL + shader.vertexShader.replace('#include <project_vertex>', FX_VERTEX_BODY)
      let frag = FX_FRAGMENT_DECL + shader.fragmentShader.replace(
        '#include <tonemapping_fragment>',
        (flow ? FX_FLOW_BODY : '') + FX_FRAGMENT_BODY.replace('FX_GAIN', gain.toFixed(2))
      )
      if (flow) {
        shader.uniforms.fxTime = fx.fxTime
        shader.uniforms.flowStrength = fx.flowStrength
        shader.uniforms.flowSource = material.userData.flowSource
        frag = FX_FLOW_DECL + frag
      }
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
    material.customProgramCacheKey = () => `fx-${rim}-${gain}-${flow}`
  }

  _makeComponentMaterials(category) {
    const material = new THREE.MeshStandardMaterial({ color: 0xffffff })
    this._enhance(material, { rim: true, gain: 0.6, flow: /Pipe$/.test(category) })
    const edgeMaterial = new THREE.LineBasicMaterial({
      color: 0x38bdf8,
      transparent: true,
      opacity: 0.55,
      depthWrite: false,
      blending: THREE.NormalBlending
    })
    this._enhance(edgeMaterial, { gain: 2.2 })
    return { category, material, edgeMaterial, baseColor: new THREE.Color(), baseEdge: new THREE.Color(), glow: 0, edgeOpacity: 0.55 }
  }

  _assignComponents(assembly) {
    const replaced = new Set() // CAD 自带的材质，替换后释放
    // CAD 导出时给大部分零件套了一个 60% 不透明的默认材质（并不是真的玻璃），
    // 除机架外一律按实体显示；机架的这些面板做成淡淡的半透明，避免挡住里面的流量计
    const panel = new THREE.MeshStandardMaterial({
      color: 0x3a4a60, metalness: 0.2, roughness: 0.6, transparent: true, opacity: 0.22, depthWrite: false
    })
    this._enhance(panel, { gain: 0.8 })
    this.panelMaterial = panel
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
      const mainMats = comp || this.defaultMaterials
      const meshes = []
      child.traverse(obj => { if (obj.isMesh) meshes.push(obj) })
      const childSize = new THREE.Box3().setFromObject(child).getSize(new THREE.Vector3())
      const childMax = Math.max(childSize.x, childSize.y, childSize.z)
      meshes.forEach(obj => {
        // 被试件里又大又薄的零件（底板、安装面板）用中性色，只让泵体本身保持醒目
        let mats = mainMats
        if (comp && mainMats.category === 'testPiece' && this._isLargePlate(obj, childMax)) {
          if (!comp.sub) comp.sub = this._makeComponentMaterials('testPieceBase')
          mats = comp.sub
        }
        const wasTransparent = obj.material && obj.material.transparent && obj.material.opacity < 0.95
        const asPanel = wasTransparent && mats.category === 'frame'
        if (obj.material) replaced.add(obj.material)
        obj.material = asPanel ? panel : mats.material
        obj.castShadow = !asPanel
        obj.receiveShadow = true
        // 轮廓线作为子对象，跟随网格变换
        const edges = new THREE.LineSegments(new THREE.EdgesGeometry(obj.geometry, EDGE_THRESHOLD_DEG), mats.edgeMaterial)
        edges.raycast = () => {} // 不参与拾取
        mats.edges = mats.edges || []
        mats.edges.push(edges)
        // 只有管路轮廓线发光；管路本体和其他轮廓不发光，保持清晰
        if (/Pipe$/.test(mats.category)) edges.layers.enable(BLOOM_LAYER)
        obj.add(edges)
        if (comp) {
          obj.userData.componentKey = key
          comp.meshes.push(obj)
          if (comp.selectable) this.pickables.push(obj)
        }
      })
      if (comp) comp.box.union(new THREE.Box3().setFromObject(child))
    })
    replaced.forEach(m => m.dispose())

    // 管路流动光斑的起点：来源部件的中心
    Object.values(this.components).forEach(comp => {
      const from = COMPONENTS[comp.key].flowFrom
      const source = from && this.components[from]
      const uniform = comp.material.userData.flowSource
      if (uniform && source) source.box.getCenter(uniform.value)
    })
  }

  /** 是否为“大而薄”的板状零件：最薄方向不到最长方向的 8%，且长度超过所属部件的 30%。 */
  _isLargePlate(mesh, parentMax) {
    const size = new THREE.Box3().setFromObject(mesh).getSize(new THREE.Vector3())
    const dims = [size.x, size.y, size.z].sort((a, b) => a - b)
    return dims[2] > parentMax * 0.3 && dims[0] < dims[2] * 0.08
  }

  /** 部件用到的所有材质组（主体 + 被试件底板等）。 */
  _matSets(comp) {
    return comp.sub ? [comp, comp.sub] : [comp]
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
    this.floor.scale.set(span * 12, span * 12, 1)
    // 底座贴合模型占地（x 方向 × z 方向），留出边距
    const pad = Math.min(size.x, size.z) * 0.35
    const footW = size.x + pad * 2
    const footD = size.z + pad * 2
    const center = box.getCenter(new THREE.Vector3())
    this.footprint = { w: footW, d: footD }
    this.basePlate.scale.set(footW, footD, 1)
    this.basePlate.position.x = center.x
    this.basePlate.position.z = center.z
    this.basePlate.material.map = footprintTexture(footW / footD)
    this.basePlate.material.opacity = 1
    this.basePlate.material.needsUpdate = true
    const rippleMap = footprintTexture(footW / footD, true)
    this.ripples.forEach(r => {
      r.material.map = rippleMap
      r.material.needsUpdate = true
      r.position.x = center.x
      r.position.z = center.z
    })
    this.grids.forEach(g => g.scale.setScalar(span * 3))
    this.fog = new THREE.Fog(srgb(FOG_COLOR), radius * 3.5, radius * 9)
    this.fx.scanWidth.value = size.y * 0.05

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
    Object.entries(LABELED).forEach(([key, lead]) => {
      const comp = this.components[key]
      if (!comp) return
      // CSS2DRenderer 会改写外层元素的 transform，偏移放在内层：
      // 外层中心对准锚点，内层上移“自身一半高度 + 引线长度”，引线向下正好落在锚点上
      const wrapper = document.createElement('div')
      const el = document.createElement('div')
      el.className = 'tb-label'
      el.style.setProperty('--lead', `${lead}px`)
      wrapper.appendChild(el)
      el.innerHTML = '<div class="tb-label__name"></div><div class="tb-label__value"></div><i class="tb-label__dot"></i>'
      el.querySelector('.tb-label__name').textContent = comp.label
      const obj = new CSS2DObject(wrapper)
      obj.position.copy(this._labelAnchor(comp))
      this.scene.add(obj)
      comp.label2d = { obj, el, valueEl: el.querySelector('.tb-label__value') }
    })
  }

  /** 标签锚点：部件主体（体积最大且不是底板的零件）顶面中心。 */
  _labelAnchor(comp) {
    let best = null
    let bestVolume = -1
    comp.meshes.forEach(mesh => {
      if (comp.sub && mesh.material === comp.sub.material) return
      const b = new THREE.Box3().setFromObject(mesh)
      const s = b.getSize(new THREE.Vector3())
      const v = s.x * s.y * s.z
      if (v > bestVolume) {
        bestVolume = v
        best = b
      }
    })
    const box = best || comp.box
    const c = box.getCenter(new THREE.Vector3())
    return c.setY(box.max.y)
  }

  // ------------------------------------------------------------------ 对外接口
  /** 切换外观：'tech' 科技风 / 'real' 写实。 */
  setStyle(name) {
    this.styleName = STYLES[name] ? name : 'tech'
    const style = STYLES[this.styleName]
    this.renderer.toneMappingExposure = style.exposure
    this.fx.rimStrength.value = style.rim
    this.scene.fog = style.fog && this.fog ? this.fog : null
    this.grids.forEach(g => { g.visible = style.fog })
    this.edgesOn = !!style.edges
    this.effects = !!style.effects
    this.fxGroup.visible = this.effects
    this.bloomEnabled = !!style.bloom
    if (style.fog && !this.bgTexture) this.bgTexture = backgroundTexture()
    this.scene.background = style.fog ? this.bgTexture : null // 写实风用容器 CSS 背景
    if (style.bloom && this.bloomPass) {
      this.bloomPass.strength = style.bloom.strength
      this.bloomPass.radius = style.bloom.radius
    }
    this.fx.flowStrength.value = this.effects ? 1 : 0
    if (!this.effects) {
      this.fx.scanStrength.value = 0
      this.controls.autoRotate = false
    }

    const apply = mats => {
      const preset = style.materials[mats.category] || style.materials.default
      mats.material.metalness = preset.metalness
      mats.material.roughness = preset.roughness
      mats.material.envMapIntensity = style.envIntensity
      mats.baseColor.setHex(preset.color).convertSRGBToLinear()
      mats.baseEdge.setHex(preset.edge || 0x38bdf8).convertSRGBToLinear()
      mats.glow = preset.glow || 0
      mats.edgeOpacity = preset.edgeOpacity === undefined ? 0.55 : preset.edgeOpacity
      mats.material.color.copy(mats.baseColor)
      mats.material.emissive.copy(mats.baseColor).multiplyScalar(mats.glow)
      mats.edgeMaterial.color.copy(mats.baseEdge)
      mats.edgeMaterial.opacity = mats.edgeOpacity
    }
    Object.values(this.components).forEach(comp => this._matSets(comp).forEach(apply))
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
      this._glow(halo)
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
    this.fx.fxTime.value = now / 1000

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
      const grow = t * this.footprint.d * 1.2 // 四边同时向外扩
      ripple.scale.set(this.footprint.w + grow, this.footprint.d + grow, 1)
      ripple.material.opacity = 0.18 * (1 - t) * Math.min(1, t * 6)
    })

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
    if (this.bloomComposer) {
      this.bloomComposer.setSize(w, h)
      this.finalComposer.setSize(w, h)
    }
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
    // 聚焦模式：选中部件后，其余部件（告警部件除外）变成半透明“幽灵”
    const focus = this.selectedKey
    for (const comp of Object.values(this.components)) {
      const ghost = !!focus && comp.key !== focus && !this.alarms.has(comp.key)
      this._matSets(comp).forEach((mats, i) => {
        const mat = mats.material
        const edge = mats.edgeMaterial
        if (i === 0 && comp.displayColor) mat.color.copy(comp.displayColor)
        else mat.color.copy(mats.baseColor)
        edge.color.copy(i === 0 && comp.displayEdge ? comp.displayEdge : mats.baseEdge)
        edge.opacity = mats.edgeOpacity
        mat.emissive.copy(mat.color).multiplyScalar(mats.glow) // 关键部件微微自发光
        mat.emissiveIntensity = 1
        if (comp.key === this.selectedKey || comp.key === this.hoveredKey) {
          const selected = comp.key === this.selectedKey
          mat.emissive.copy(selected ? SELECT_EMISSIVE : HOVER_EMISSIVE)
          mat.emissiveIntensity = selected ? 0.35 : 0.3
          edge.color.copy(HIGHLIGHT_EDGE)
          edge.opacity = Math.max(mats.edgeOpacity, selected ? 0.9 : 0.85)
        }
        this._setGhost(mats, ghost)
        // 轮廓线默认只画在少数类别上（细碎零件全画会糊成一片），选中/悬停时显示
        const showEdges = this.edgesOn && edge.opacity > 0.01
        ;(mats.edges || []).forEach(e => { e.visible = showEdges })
      })
      if (comp.label2d) comp.label2d.el.classList.toggle('is-ghost', ghost)
    }
    if (this.defaultMaterials) {
      this._setGhost(this.defaultMaterials, !!focus)
      ;(this.defaultMaterials.edges || []).forEach(e => { e.visible = this.edgesOn })
    }
    if (this.panelMaterial) this.panelMaterial.opacity = focus ? 0.05 : 0.22
    this._updateLabels()
  }

  _setGhost(mats, ghost) {
    const mat = mats.material
    if (mat.transparent !== ghost) {
      mat.transparent = ghost
      mat.depthWrite = !ghost
      mat.needsUpdate = true
    }
    mat.opacity = ghost ? 0.12 : 1
    if (ghost) mats.edgeMaterial.opacity = Math.min(mats.edgeOpacity, 0.12)
  }

  _updateLabels() {
    for (const comp of Object.values(this.components)) {
      if (!comp.label2d) continue
      // 着色模式下显示与颜色对应的测点，否则显示部件的第一个有数据的测点
      const candidates = (this.colorMode !== 'none' && comp.colorBy[this.colorMode]) || comp.fields
      const field = candidates.find(f => this.featureMap[f]) || candidates[0]
      const stat = field && this.featureMap[field]
      comp.label2d.valueEl.textContent = stat ? `${formatValue(stat.avg)} ${fieldUnit(field)}`.trim() : ''
      comp.label2d.el.classList.toggle('no-data', !stat) // 没有数据时只显示名称，标签更小
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
      this._render()
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
    ;[this.bloomComposer, this.finalComposer].forEach(c => {
      if (!c) return
      c.renderTarget1.dispose()
      c.renderTarget2.dispose()
    })
    if (this.bloomPass && this.bloomPass.dispose) this.bloomPass.dispose()
    if (this.darkMaterial) this.darkMaterial.dispose()
    if (this.bgTexture) this.bgTexture.dispose()
    this.renderer.dispose()
    if (this.renderer.forceContextLoss) this.renderer.forceContextLoss()
    el.remove()
    this.labelRenderer.domElement.remove()
  }
}
