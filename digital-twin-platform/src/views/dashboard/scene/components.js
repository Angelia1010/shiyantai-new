/**
 * 试验台三维模型的部件配置。
 *
 * 模型 public/model/shiyantai5.glb 的总装体位于节点 “总装图” 下，每个一级子节点是一个部件，
 * 名称带 “.002” 之类的导出后缀，匹配时会去掉。
 *
 * - label     界面上显示的名称
 * - material  材质类别（见 STYLES.*.materials）
 * - fields    该部件相关的测点（来自试验数据列名），点击部件时显示
 * - colorBy   “温度/压力”着色模式下用于给该部件上色的测点（取均值）
 *
 * 测点与部件的对应关系是按部件名称推断的，如与实际管路不符，直接修改这里即可。
 */
export const COMPONENTS = {
  被试件1高低压双联泵: {
    label: '被试件 1 · 高低压双联泵',
    material: 'testPiece',
    fields: ['燃油泵实际转速', 'P1进口压力', 'P2低压出口压力', 'P3高压出口压力', 'T3进口温度', 'T4高压出口温度', '振动传感器1-1']
  },
  被试件2: {
    label: '被试件 2',
    material: 'testPiece',
    fields: ['电传实际转速', '电传扭矩', '振动传感器2-1', '振动传感器3-1']
  },
  被试件2周边管路: { label: '被试件 2 周边管路', material: 'supplyPipe', fields: ['T5出口温度'] },
  供油管路: {
    label: '供油管路',
    material: 'supplyPipe',
    fields: ['供油压力1-1', '供油压力1-2', '供油温度1-1', '供油温度1-2', '供油流量1-1', '供油流量1-2'],
    colorBy: { temperature: ['供油温度1-1', '供油温度1-2'], pressure: ['供油压力1-1', '供油压力1-2'] }
  },
  回油管路: {
    label: '回油管路',
    material: 'returnPipe',
    fields: ['回油压力1-1', '回油压力1-2', '回油压力2-1', '回油压力2-2', '回油温度1-1', '回油温度1-2'],
    colorBy: { temperature: ['回油温度1-1', '回油温度1-2'], pressure: ['回油压力1-1', '回油压力1-2'] }
  },
  回油流量计1: {
    label: '回路 1 流量计',
    material: 'instrument',
    fields: ['回油流量1-1', '回油温度1-1', '回油压力1-1'],
    colorBy: { temperature: ['回油温度1-1'], pressure: ['回油压力1-1'] }
  },
  回油流量计2: {
    label: '回路 2 流量计',
    material: 'instrument',
    fields: ['回油流量1-2', '回油温度1-2', '回油压力1-2'],
    colorBy: { temperature: ['回油温度1-2'], pressure: ['回油压力1-2'] }
  },
  供油油箱温度传感器: { label: '供油油箱温度传感器', material: 'instrument', fields: ['T20加热出口温度'] },
  管道式加热器: {
    label: '管道式加热器',
    material: 'equipment',
    fields: ['T20加热出口温度'],
    colorBy: { temperature: ['T20加热出口温度'] }
  },
  温控系统_板式换热器: { label: '温控系统 · 板式换热器', material: 'equipment', fields: [] },
  离心泵_油路块: { label: '离心泵 · 油路块', material: 'equipment', fields: [] },
  循环油箱: { label: '循环油箱', material: 'tank', fields: [] },
  循环油路: { label: '循环油路', material: 'loopPipe', fields: [] },
  底座支架: { label: '底座支架', material: 'frame', fields: [], selectable: false }
}

/** 诊断报告中的流量计名称 → 模型部件，用于异常定位。 */
export const DIAGNOSIS_TARGETS = {
  回路1流量计: '回油流量计1',
  回路2流量计: '回油流量计2'
}

/**
 * 两套外观：
 * - tech  科技风：关键部件（被试件、管路、油箱、仪表）用各自的醒目颜色并带发光轮廓，
 *         辅助设备和底座用中性灰压暗，与深蓝背景拉开对比；带边缘光和动态效果
 * - real  写实：工业金属材质
 *
 * 材质类别参数：
 *   color/metalness/roughness  本体（MeshStandardMaterial）
 *   glow         自发光强度（本体颜色 × glow），让细小的管路也清晰可见
 *   edge         轮廓线颜色；edgeOpacity 轮廓线不透明度（辅助部件调低，减少杂乱）
 */
export const STYLES = {
  tech: {
    label: '科技',
    exposure: 1.2,
    envIntensity: 0.4,
    rim: 0.35,
    edges: true,
    fog: true,
    effects: true, // 扫描光带、波纹、粒子、自转
    materials: {
      testPiece: { color: 0xe07a2e, metalness: 0.45, roughness: 0.4, glow: 0.18, edge: 0xffb070, edgeOpacity: 0.7 },
      supplyPipe: { color: 0x14b8d8, metalness: 0.4, roughness: 0.35, glow: 0.45, edge: 0x67e8f9, edgeOpacity: 0.8 },
      returnPipe: { color: 0x22c55e, metalness: 0.4, roughness: 0.35, glow: 0.45, edge: 0x86efac, edgeOpacity: 0.8 },
      loopPipe: { color: 0x8b5cf6, metalness: 0.4, roughness: 0.35, glow: 0.4, edge: 0xc4b5fd, edgeOpacity: 0.7 },
      tank: { color: 0x2f6fd6, metalness: 0.35, roughness: 0.4, glow: 0.12, edge: 0x93c5fd, edgeOpacity: 0.6 },
      instrument: { color: 0xeab308, metalness: 0.4, roughness: 0.35, glow: 0.3, edge: 0xfde68a, edgeOpacity: 0.8 },
      equipment: { color: 0x7d8ba0, metalness: 0.45, roughness: 0.5, glow: 0, edge: 0xa9bacd, edgeOpacity: 0.2 },
      frame: { color: 0x3a4658, metalness: 0.4, roughness: 0.7, glow: 0, edge: 0x5b6d85, edgeOpacity: 0.15 },
      default: { color: 0x5b6879, metalness: 0.5, roughness: 0.5, glow: 0, edge: 0x8aa0b8, edgeOpacity: 0.15 }
    }
  },
  real: {
    label: '写实',
    exposure: 1.0,
    envIntensity: 0.7,
    rim: 0,
    edges: false,
    fog: false,
    effects: false,
    materials: {
      testPiece: { color: 0x9aa3ad, metalness: 0.85, roughness: 0.35 },
      supplyPipe: { color: 0x8e959e, metalness: 0.9, roughness: 0.28 },
      returnPipe: { color: 0x8e959e, metalness: 0.9, roughness: 0.28 },
      loopPipe: { color: 0x8e959e, metalness: 0.9, roughness: 0.28 },
      tank: { color: 0x2f5876, metalness: 0.35, roughness: 0.5 },
      instrument: { color: 0xc08a2c, metalness: 0.7, roughness: 0.35 },
      equipment: { color: 0x5d6875, metalness: 0.6, roughness: 0.45 },
      frame: { color: 0x2c323b, metalness: 0.45, roughness: 0.7 },
      default: { color: 0x7b838e, metalness: 0.7, roughness: 0.42 }
    }
  }
}

/** 科技风下的颜色图例（三维视图左下角）。 */
export const LEGEND = [
  { label: '被试件', category: 'testPiece' },
  { label: '供油管路', category: 'supplyPipe' },
  { label: '回油管路', category: 'returnPipe' },
  { label: '循环油路', category: 'loopPipe' },
  { label: '油箱', category: 'tank' },
  { label: '流量计/传感器', category: 'instrument' },
  { label: '辅助设备', category: 'equipment' }
].map(item => ({ ...item, color: '#' + STYLES.tech.materials[item.category].color.toString(16).padStart(6, '0') }))

/**
 * 预设视角：相对模型包围盒中心的方向（会自动归一化）和距离倍数。
 * focus 指定部件时，以该部件的包围盒为准。
 */
export const VIEWS = {
  overview: { label: '总览', direction: [1, 0.75, 1.15], distance: 1.25 },
  front: { label: '正视', direction: [0, 0.18, 1], distance: 1.35 },
  top: { label: '俯视', direction: [0.001, 1, 0.02], distance: 1.3 },
  pump: { label: '被试件', direction: [1, 0.6, 1], distance: 1.6, focus: '被试件1高低压双联泵' },
  tank: { label: '油箱区', direction: [-1, 0.7, 1], distance: 1.8, focus: '循环油箱' }
}

/** 着色模式。 */
export const COLOR_MODES = {
  none: { label: '原色' },
  temperature: { label: '温度', unit: '°C' },
  pressure: { label: '压力', unit: 'MPa' }
}
