<template>
  <div id="three-container" style="width: 100%; height: 100%; position: relative"></div>
</template>

<script>
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls";
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { OutlinePass } from 'three/examples/jsm/postprocessing/OutlinePass.js';
export default {
  name: "PumpModel",
  mounted() {
    this.$nextTick(() => {
      const container = this.$el;
      const width = container.clientWidth;
      const height = container.clientHeight;
      this.scene = new THREE.Scene();
      this.camera = new THREE.PerspectiveCamera(75, width / height, 0.1, 1000);
      this.camera.position.z = 6;
      this.renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
      this.renderer.setClearColor(0x1d2530, 1); // 深色背景
      this.renderer.setSize(width, height);
      container.appendChild(this.renderer.domElement);
      // 添加环境光和方向光，增强立体感
      const ambientLight = new THREE.AmbientLight(0xffffff, 3); // 提高环境光强度
      this.scene.add(ambientLight);
      const directionalLight = new THREE.DirectionalLight(0xffffff, 1.5); // 提高主光源强度
      directionalLight.position.set(-5, 10, 7.5);
      directionalLight.castShadow = false;
      this.scene.add(directionalLight);
      const directionalLight2 = new THREE.DirectionalLight(0xffffff, 1); // 提高主光源强度
      directionalLight2.position.set(0, 10, 0);
      directionalLight2.castShadow = false;
      this.scene.add(directionalLight2);
      // 支持拖拽等操作
      this.controls = new OrbitControls(this.camera, this.renderer.domElement);
      this.controls.enableDamping = true;
      this.controls.dampingFactor = 0.1;
      this.controls.enableZoom = true;
      this.controls.enablePan = true;
      const loader = new GLTFLoader();
      loader.load("/model/shiyantai5.glb", (gltf) => {
        this.model = gltf.scene;

        // 模型接收/投射阴影
        this.model.traverse(child => {
          if (child.isMesh) {
            child.castShadow = true;
            child.receiveShadow = true;
          }
        });
        this.scene.add(this.model);

        this.animate();
      });
      // 渲染器开启阴影
      this.renderer.shadowMap.enabled = true;
      this.renderer.shadowMap.type = THREE.PCFSoftShadowMap; // 软阴影
      // 3. 【高级】添加环境贴图（IBL）——大幅提升金属/玻璃质感
      const pmremGenerator = new THREE.PMREMGenerator(this.renderer);
      pmremGenerator.compileEquirectangularShader();

      new THREE.TextureLoader().load('/qwantani_dusk_1_puresky_4k.hdr', (texture) => {
        const envMap = pmremGenerator.fromEquirectangular(texture).texture;
        this.scene.environment = envMap; // 全局环境光贴图
        texture.dispose();
        pmremGenerator.dispose();
      });
      // 创建深色科技风网格
      const gridHelper = new THREE.GridHelper(80, 80, 0x00aaff, 0x003355);
      gridHelper.material.opacity = 0.3;
      gridHelper.material.transparent = true; // 启用透明度
      gridHelper.position.y = -0.6;

      this.scene.add(gridHelper);


    });
  },
  methods: {
    animate() {
      requestAnimationFrame(this.animate);
      if (this.controls) this.controls.update();
      if (this.renderer && this.scene && this.camera) {
        this.renderer.render(this.scene, this.camera);
      }
    },

  },
};
</script>

<style scoped>
#three-container {
  /* border: 1px solid #00cc44 !important; */
  margin: 0 !important;
  padding: 0 !important;
  box-sizing: border-box;
  z-index: 1 !important;

}

canvas {
  display: block;
}
</style>
