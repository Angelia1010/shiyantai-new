<template>
  <div class="pump2d-wrap">
    <div class="info-box">
      <div class="port-name">{{ portName }}</div>
      <div v-if="mode === 'temperature'" class="info-row">
        <span class="label">温度</span>
        <span class="value" :style="{ color: getHeatColorCss(temperatureDisplay, 20, 90) }">{{ temperatureDisplay
          }}°C</span>
      </div>
      <div v-if="mode === 'pressure'" class="info-row">
        <span class="label">压力</span>
        <span class="value" :style="{ color: getHeatColorCss(pressureDisplay, 2, 35) }">{{ pressureDisplay }}MPa</span>
      </div>
    </div>
    <div class="canvas-box" id="two-container"></div>
  </div>
</template>

<script>
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader";
export default {
  name: "PumpModel2D",
  props: {
    portName: {
      type: String,
      required: true, // 必须传递
      // validator: (val) => ["供油口", "出油口", "排油口", "控制口"].includes(val),
    },
    viewDirection: {
      type: String,
      default: "z", // 支持 x, -x, y, -y, z, -z
      validator: (val) => ["x", "-x", "y", "-y", "z", "-z"].includes(val),
    },
    featureMap: {
      type: Object,
      required: false,
      default: null,
    },
    mode: {
      type: String,
      default: "temperature", // 'temperature' 或 'pressure'
      validator: (val) => ["temperature", "pressure"].includes(val),
    },
  },
  computed: {
    portFieldMap() {
      // 建立 portName 与 featureMap字段、模型mesh名称的对应关系
      return {
        "供油1-1": {
          pressure: "供油压力1-1",
          temperature: "供油温度1-1",
          meshName: "Mesh_500001",
        },
        "供油1-2": {
          pressure: "供油压力1-2",
          temperature: "供油温度1-2",
          meshName: "Mesh_563001",
        },
        "回油1-1": {
          pressure: "回油压力1-1",
          temperature: "回油温度1-1",
          meshName: "Mesh_510001",
        },
        "回油1-2": {
          pressure: "回油压力1-2",
          temperature: "回油温度1-2",
          meshName: "Mesh_561001",
        },
      };
    },
    temperatureDisplay() {
      const mapping = this.portFieldMap[this.portName];
      if (!mapping || !mapping.temperature) return "--";
      const obj = this.featureMap && this.featureMap[mapping.temperature];
      if (obj && typeof obj.avg === "number") {
        return obj.avg.toFixed(1);
      }
      return "--";
    },
    pressureDisplay() {
      const mapping = this.portFieldMap[this.portName];
      if (!mapping || !mapping.pressure) return "--";
      const obj = this.featureMap && this.featureMap[mapping.pressure];
      if (obj && typeof obj.avg === "number") {
        return obj.avg.toFixed(2);
      }
      return "--";
    },
    // 新增：根据 mode 返回当前显示值
    valueDisplay() {
      return this.mode === "pressure"
        ? this.pressureDisplay
        : this.temperatureDisplay;
    },
  },
  watch: {
    featureMap: {
      handler() {
        this.updatePortMaterialColor();
      },
      deep: true,
    },
    portName() {
      this.updatePortMaterialColor();
    },
    temperature() {
      this.updatePortMaterialColor();
    },
    pressure() {
      this.updatePortMaterialColor();
    },
  },
  mounted() {
    this.init();
    window.addEventListener("resize", this.onWindowResize, false);
  },
  beforeDestroy() {
    window.removeEventListener("resize", this.onWindowResize);
    if (this.animationId) cancelAnimationFrame(this.animationId);
    if (this.renderer) {
      this.renderer.dispose && this.renderer.dispose();
      this.renderer.forceContextLoss && this.renderer.forceContextLoss();
    }
    // 移除2D标签
    const label = this.$el.querySelector(".pump2d-label");
    if (label) label.remove();
  },
  methods: {
    get2DMaterialByName(name) {
      // 2D视图：直接复用3D的材质参数，保留透明度和金属感
      if (
        [
          "分油盘",
          "保持架",
          "滑轨组件",
          "壳体",
          "转子组件",
          "活塞组件",
          "滑靴组件",
          "主轴",
          "支座",
          "斜盘",
        ].includes(name)
      ) {
        return new THREE.MeshStandardMaterial({
          color: 0x99e0ff,
          metalness: 0.25,
          roughness: 0.18,
          opacity: 0.1,
          transparent: true,
        });
      } else if (/^滑靴[1-9]$/.test(name) || /^活塞[1-9]$/.test(name)) {
        return new THREE.MeshStandardMaterial({
          color: 0x99e0ff,
          metalness: 0.25,
          roughness: 0.18,
          opacity: 0.1,
          transparent: true,
        });
      } else {
        return new THREE.MeshStandardMaterial({
          color: 0x6a8caf, // 蓝灰色，更适合白色背景
          metalness: 0.35,
          roughness: 0.32,
        });
      }
    },
    init() {
      this.$nextTick(() => {
        // 兼容 Vue2/3，this.$el 可能为组件实例或 DOM 元素
        let container = null;
        if (this.$el instanceof HTMLElement) {
          container = this.$el.querySelector("#two-container");
        } else if (this.$el && this.$el.$el instanceof HTMLElement) {
          container = this.$el.$el.querySelector("#two-container");
        }
        if (!container) return;
        const width = 160;
        const height = 120;
        this.scene = new THREE.Scene();

        // 添加环境光和方向光，保证2D正交视图明亮
        const ambientLight = new THREE.AmbientLight(0xffffff, 1.2);
        this.scene.add(ambientLight);
        const dirLight = new THREE.DirectionalLight(0xffffff, 1.2);
        dirLight.position.set(5, 10, 10);
        this.scene.add(dirLight);

        // 正交相机，z轴朝向-1（俯视xy平面）
        const aspect = width / height;
        // 初始 viewSize 设为 4，和 onWindowResize 保持一致
        const viewSize = 10;
        this.camera = new THREE.OrthographicCamera(
          (-viewSize * aspect) / 2,
          (viewSize * aspect) / 2,
          viewSize / 2,
          -viewSize / 2,
          0.1,
          100
        );
        // 设置相机视角
        const cameraPos = { x: 0, y: 0, z: 10 };
        const lookAt = { x: 0, y: 0, z: 0 };
        switch (this.viewDirection) {
          case "x":
            cameraPos.x = 10;
            cameraPos.y = 0;
            cameraPos.z = 0;
            lookAt.x = 0;
            lookAt.y = 0;
            lookAt.z = 0;
            break;
          case "-x":
            cameraPos.x = -10;
            cameraPos.y = 0;
            cameraPos.z = 0;
            lookAt.x = 0;
            lookAt.y = 0;
            lookAt.z = 0;
            break;
          case "y":
            cameraPos.x = 0;
            cameraPos.y = 10;
            cameraPos.z = 0;
            lookAt.x = 0;
            lookAt.y = 0;
            lookAt.z = 0;
            break;
          case "-y":
            cameraPos.x = 0;
            cameraPos.y = -10;
            cameraPos.z = 0;
            lookAt.x = 0;
            lookAt.y = 0;
            lookAt.z = 0;
            break;
          case "z":
            cameraPos.x = 0;
            cameraPos.y = 0;
            cameraPos.z = 10;
            lookAt.x = 0;
            lookAt.y = 0;
            lookAt.z = 0;
            break;
          case "-z":
            cameraPos.x = 0;
            cameraPos.y = 0;
            cameraPos.z = -10;
            lookAt.x = 0;
            lookAt.y = 0;
            lookAt.z = 0;
            break;
        }
        this.camera.position.set(cameraPos.x, cameraPos.y, cameraPos.z);
        this.camera.lookAt(lookAt.x, lookAt.y, lookAt.z);
        this.renderer = new THREE.WebGLRenderer({
          alpha: true,
          antialias: true,
        });
        this.renderer.setClearColor(0x000000, 0); // 设置背景为透明

        this.renderer.setSize(width, height);
        container.appendChild(this.renderer.domElement);
        // 加载模型

        const loader = new GLTFLoader();
        loader.load("/model/shiyantai4.glb", (gltf) => {
          this.model = gltf.scene;
          // 材质替换为2D材质
          this.model.traverse((child) => {
            if (child.isMesh) {
              // 调试输出所有 mesh name
              //console.log("[PumpModel2D] mesh name:", child.name);
              const mapping = this.portFieldMap[this.portName];

              // 只显示当前 portName 对应的 mesh
              if (child.isMesh && mapping && child.name === mapping.meshName) {
                console.log(
                  "2D模型加载成功，当前口：",
                  this.portName,
                  "meshName:",
                  child.name
                );
                child.visible = true;
                this.portMesh = child;
              } else if (
                child.isMesh &&
                ["进油口", "出油口", "排油口", "控制口"].includes(child.name)
              ) {
                child.visible = false;
              }
              child.material = this.get2DMaterialByName(child.name);
            }
          });
          // 记录关键部件引用
          let jinYouKouMesh = null;
          // 初始化数组，防止 undefined 报错
          this.pistonLocators = [];
          this.pistons = [];
          this.slippers = [];
          this.model.traverse((child) => {
            if (child.name === "斜盘") this.swashMesh = child;
            if (child.name === "支座") this.baseMesh = child;
            if (child.name === "主轴") this.mainShaft = child;
            if (child.name === "转子组件") this.rotorAssembly = child;
            if (child.name === "活塞中心") this.pistonCenter = child;
            if (/^活塞定位[1-9]$/.test(child.name))
              this.pistonLocators.push(child);
            if (/^活塞[1-9]$/.test(child.name)) this.pistons.push(child);
            if (/^滑靴[1-9]$/.test(child.name)) this.slippers.push(child);
            if (child.name === "进油口") jinYouKouMesh = child;
          });
          // 记录活塞定位初始x/y
          this.locatorInitOffsets = this.pistonLocators.map((loc) => ({
            locator: loc,
            baseX: loc.position.x,
            baseY: loc.position.y,
          }));
          this.scene.add(this.model);

          this.animate();

          window.parent.postMessage({ type: "hideLoading" }, "*");
          window.parent.hideLoading();
        });
      });
    },
    onWindowResize() {
      // 固定canvas尺寸，不随窗口变化
      const width = 160;
      const height = 120;
      this.renderer.setSize(width, height);
      const aspect = width / height;
      const viewSize = 10;
      this.camera.left = (-viewSize * aspect) / 2;
      this.camera.right = (viewSize * aspect) / 2;
      this.camera.top = viewSize / 2;
      this.camera.bottom = -viewSize / 2;
      this.camera.updateProjectionMatrix();
    },
    animate() {
      this.animationId = requestAnimationFrame(this.animate);
      // 动画驱动与3D一致
      const now = performance.now();
      if (this.lastTimestamp === null) this.lastTimestamp = now;
      const delta = (now - this.lastTimestamp) / 1000;
      this.lastTimestamp = now;
      const speedRad = THREE.MathUtils.degToRad(this.rotateSpeedInner || 0);
      this.currentRotationX += speedRad * delta;
      if (this.currentRotationX > Math.PI * 2)
        this.currentRotationX -= Math.PI * 2;
      // 保证口的材质颜色实时刷新
      this.updatePortMaterialColor();
      this.renderer.render(this.scene, this.camera);
    },
    updatePumpMotion() {
      // 斜盘角度限制在0~-15度
      let angle = this.swashAngleInner;
      if (angle > 0) angle = 0;
      if (angle < -15) angle = -15;
      const angleRad = THREE.MathUtils.degToRad(angle);
      const rotRad = this.currentRotationX;
      // 活塞定位
      if (this.pistonLocators && this.locatorInitOffsets && this.pistonCenter) {
        for (let i = 0; i < this.pistonLocators.length; i++) {
          const locator = this.pistonLocators[i];
          const offset = this.locatorInitOffsets[i];
          const locatorWorld = new THREE.Vector3();
          const centerWorld = new THREE.Vector3();
          locator.getWorldPosition(locatorWorld);
          this.pistonCenter.getWorldPosition(centerWorld);
          const dy = centerWorld.y - locatorWorld.y;
          const dx = -dy * Math.tan(angleRad);
          locator.position.x = offset.baseX - dx;
        }
      }
      // 活塞/滑靴跟随定位
      if (this.pistonLocators && this.pistons && this.slippers) {
        for (let i = 0; i < this.pistonLocators.length; i++) {
          const locator = this.pistonLocators[i];
          locator.updateMatrixWorld();
          const pos = new THREE.Vector3();
          locator.getWorldPosition(pos);
          if (this.pistons[i] && this.pistons[i].parent) {
            const pistonLocal = pos.clone();
            this.pistons[i].parent.worldToLocal(pistonLocal);
            this.pistons[i].position.copy(pistonLocal);
          }
          if (this.slippers[i] && this.slippers[i].parent) {
            const slipperLocal = pos.clone();
            this.slippers[i].parent.worldToLocal(slipperLocal);
            this.slippers[i].position.copy(slipperLocal);
          }
        }
      }
      // 斜盘/支座旋转
      if (this.swashMesh) {
        const qZ = new THREE.Quaternion();
        qZ.setFromAxisAngle(new THREE.Vector3(0, 0, 1), angleRad);
        const qX = new THREE.Quaternion();
        qX.setFromAxisAngle(new THREE.Vector3(1, 0, 0), rotRad);
        this.swashMesh.quaternion.copy(qZ).multiply(qX);
      }
      if (this.baseMesh) {
        const qZ = new THREE.Quaternion();
        qZ.setFromAxisAngle(new THREE.Vector3(0, 0, 1), angleRad);
        this.baseMesh.quaternion.copy(qZ);
      }
      if (this.slippers && this.slippers.length > 0) {
        this.slippers.forEach((mesh) => {
          mesh.rotation.set(0, 0, 0);
          mesh.setRotationFromAxisAngle(new THREE.Vector3(0, 0, 1), angleRad);
        });
      }
      if (this.mainShaft) this.mainShaft.rotation.set(rotRad, 0, 0);
      if (this.rotorAssembly) this.rotorAssembly.rotation.set(rotRad, 0, 0);
      if (this.pistonCenter) this.pistonCenter.rotation.set(rotRad, 0, 0);
    },
    // 计算热力图色系颜色（蓝-青-绿-黄-橙-红）
    getHeatColor(val, min, max) {
      // 若 val 无效，返回默认色（蓝色）
      if (typeof val !== "number" || isNaN(val)) {
        return 0x99e0ff;
      }
      // 归一化到0~1
      const t = Math.max(0, Math.min(1, (val - min) / (max - min)));
      // 色带：0=蓝，0.2=青，0.4=绿，0.6=黄，0.8=橙，1=红
      const colors = [
        [0, 102, 255], // 蓝
        [0, 255, 255], // 青
        [0, 255, 0], // 绿
        [255, 255, 0], // 黄
        [255, 128, 0], // 橙
        [255, 0, 0], // 红
      ];
      const n = colors.length - 1;
      const idx = Math.floor(t * n);
      const frac = t * n - idx;
      const c0 = colors[idx];
      const c1 = colors[Math.min(idx + 1, n)];
      const r = Math.round(c0[0] + (c1[0] - c0[0]) * frac);
      const g = Math.round(c0[1] + (c1[1] - c0[1]) * frac);
      const b = Math.round(c0[2] + (c1[2] - c0[2]) * frac);
      return (r << 16) | (g << 8) | b;
    },
    getHeatColorCss(val, min, max) {
      // 若 val 无效，返回默认色（蓝色）
      if (typeof val !== "number" || isNaN(val)) {
        return "#99e0ff";
      }
      const hex = this.getHeatColor(val, min, max)
        .toString(16)
        .padStart(6, "0");
      return `#${hex}`;
    },
    // 新增：根据 mode 返回色带区间
    getColorRange() {
      if (this.mode === "pressure") {
        return { min: 2, max: 35 };
      } else {
        return { min: 20, max: 90 };
      }
    },
    // 更新指定口的材质颜色
    updatePortMaterialColor() {
      // 斜盘泵行业常见区间：
      // 温度：-20~120°C（常用区间 20~90°C）
      // 压力：0~40MPa（常用区间 2~35MPa）
      const tempMin = 20,
        tempMax = 90;
      const presMin = 2,
        presMax = 35;
      let val, min, max;
      if (this.mode === "pressure") {
        val = Number(this.pressureDisplay);
        min = presMin;
        max = presMax;
      } else {
        val = Number(this.temperatureDisplay);
        min = tempMin;
        max = tempMax;
      }
      const color = isNaN(val) ? 0x99e0ff : this.getHeatColor(val, min, max);
      if (this.portMesh && this.portMesh.material) {
        this.portMesh.material.color.setHex(color);
        this.portMesh.material.needsUpdate = true;
      }
    },
  },
};
</script>

<style scoped>
body {
  margin: 0;
  overflow: hidden;
}

canvas {
  display: block;
}

#info {
  display: none;
  position: absolute;
  top: 10px;
  left: 10px;
  color: white;
  font-size: 20px;
  background-color: rgba(0, 0, 0, 0.5);
  padding: 10px;
  border-radius: 5px;
}

.dg.a {
  margin-top: 200px !important;
}

.header .header-left {
  /* width: 25%; */
  /* height: 62px; */
  color: white;
  text-align: center;
  line-height: 62px;
  /* float: left; */
}

.header .header-center .header-title {
  text-align: center;
  color: #ffffff;
  font-size: 24px;
  text-shadow: 0 0 18px #00d8ff;
  line-height: 62px;
}

.header .header-img {
  background: url("/model/img/head.gif") no-repeat center center;
  background-size: 100%;
  /* height: 100%; */
  /* width: 100%; */
  /* position: absolute; */
  /* top: 24px; */
}

.header .header-right {
  /* width: 25%; */
  /* height: 62px; */
  color: #fff;
  line-height: 62px;
  /* float: left; */
}

.header .header-bottom {
  /* width: calc(100% - 24px); */
  /* height: 10px; */
  background: url("/model/img/header.png") no-repeat;
  background-size: calc(100% - 12px) 100%;
  /* margin-left: 18px; */
  /* position: absolute; */
  /* top: 62px; */
}

/* 其余内容和canvas相关样式保留 */
.pump2d-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 160px;
  box-sizing: border-box;
  /* border: 1px solid #00cc44 !important; */
  margin: 0 !important;
  padding: 0 !important;
}

.info-box {
  width: 100%;
  margin-bottom: -10px;
  margin-top: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  font-size: 13px;
  color: #333;
}

.canvas-box {
  width: 160px;
  height: 120px;
  position: relative;
}

.info-row {
  display: flex;
  justify-content: space-evenly;
  width: 98%;
  margin: 0 0 1px 0;
  gap: 2px;
}

.label {
  color: #666;
  margin-right: 1px;
  min-width: 28px;
}

.value {
  color: #222;
  font-weight: 500;
  min-width: 36px;
  text-align: right;
}

.port-name {
  font-weight: bold;
  font-size: 15px;
  color: #1976d2;
  margin-bottom: 10px;
  letter-spacing: 1px;
}
</style>
