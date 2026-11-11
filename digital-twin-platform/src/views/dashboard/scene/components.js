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
    material: 'pump',
    fields: ['燃油泵实际转速', 'P1进口压力', 'P2低压出口压力', 'P3高压出口压力', 'T3进口温度', 'T4高压出口温度', '振动传感器1-1']
  },
  被试件2: {
    label: '被试件 2',
    material: 'pump',
    fields: ['电传实际转速', '电传扭矩', '振动传感器2-1', '振动传感器3-1']
  },
  被试件2周边管路: { label: '被试件 2 周边管路', material: 'pipe', fields: ['T5出口温度'] },
  供油管路: {
    label: '供油管路',
    material: 'pipe',
    fields: ['供油压力1-1', '供油压力1-2', '供油温度1-1', '供油温度1-2', '供油流量1-1', '供油流量1-2'],
    colorBy: { temperature: ['供油温度1-1', '供油温度1-2'], pressure: ['供油压力1-1', '供油压力1-2'] }
  },
  回油管路: {
    label: '回油管路',
    material: 'pipe',
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
  循环油路: { label: '循环油路', material: 'pipe', fields: [] },
  底座支架: { label: '底座支架', material: 'frame', fields: [], selectable: false }
}

/** 诊断报告中的流量计名称 → 模型部件，用于异常定位。 */
export const DIAGNOSIS_TARGETS = {
  回路1流量计: '回油流量计1',
  回路2流量计: '回油流量计2'
}

/**
 * 两套外观：
 * - tech  科技风：深蓝半金属本体 + 发光轮廓线 + 边缘光
 * - real  写实：工业材质
 * 每个材质类别给出本体参数（MeshStandardMaterial）和轮廓线颜色。
 */
export const STYLES = {
  tech: {
    label: '科技',
    exposure: 1.0,
    envIntensity: 0.35,
    rim: 0.85,
    edges: true,
    fog: true,
    materials: {
      pump: { color: 0x163a63, metalness: 0.55, roughness: 0.38, edge: 0x5cc8ff },
      pipe: { color: 0x0f3550, metalness: 0.6, roughness: 0.35, edge: 0x38bdf8 },
      instrument: { color: 0x4a3a12, metalness: 0.5, roughness: 0.4, edge: 0xfbbf24 },
      equipment: { color: 0x14304e, metalness: 0.5, roughness: 0.42, edge: 0x60a5fa },
      tank: { color: 0x11314f, metalness: 0.45, roughness: 0.45, edge: 0x22d3ee },
      frame: { color: 0x0c1b2c, metalness: 0.4, roughness: 0.6, edge: 0x1e5a8a },
      default: { color: 0x12304d, metalness: 0.5, roughness: 0.45, edge: 0x3b82f6 }
    }
  },
  real: {
    label: '写实',
    exposure: 0.85,
    envIntensity: 0.7,
    rim: 0,
    edges: false,
    fog: false,
    materials: {
      pump: { color: 0x9aa3ad, metalness: 0.85, roughness: 0.35 },
      pipe: { color: 0x8e959e, metalness: 0.9, roughness: 0.28 },
      instrument: { color: 0xc08a2c, metalness: 0.7, roughness: 0.35 },
      equipment: { color: 0x5d6875, metalness: 0.6, roughness: 0.45 },
      tank: { color: 0x2f5876, metalness: 0.35, roughness: 0.5 },
      frame: { color: 0x2c323b, metalness: 0.45, roughness: 0.7 },
      default: { color: 0x7b838e, metalness: 0.7, roughness: 0.42 }
    }
  }
}

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
