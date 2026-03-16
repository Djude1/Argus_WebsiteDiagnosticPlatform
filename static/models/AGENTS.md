<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-14 | Updated: 2026-03-14 -->

# models

## Purpose
3D 模型檔案目錄，用於 Three.js IMU 可視化渲染。

## Key Files

| File | Description |
|------|-------------|
| `aiglass.glb` | AI 眼鏡 3D 模型 (GLB 格式) |

## For AI Agents

### Working In This Directory
- GLB (GL Transmission Format Binary) - 二進制 3D 模型格式
- 由 `../visualizer.js` 載入用於 IMU 姿態可視化

### Usage
```javascript
const loader = new GLTFLoader();
loader.load('/static/models/aiglass.glb', (gltf) => {
  scene.add(gltf.scene);
});
```

## Dependencies

### External
- Three.js GLTFLoader

<!-- MANUAL: -->
