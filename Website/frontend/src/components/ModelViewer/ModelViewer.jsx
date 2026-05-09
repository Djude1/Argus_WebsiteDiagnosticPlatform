import { Suspense, Component } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, useGLTF, Environment, ContactShadows, Clone } from '@react-three/drei'

/** Environment 獨立錯誤邊界：網路失敗時靜默略過，不影響模型渲染 */
class EnvironmentErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }
  static getDerivedStateFromError() {
    return { hasError: true }
  }
  render() {
    if (this.state.hasError) return null
    return this.props.children
  }
}

/** WebGL 錯誤防護：若 Canvas 崩潰，顯示靜態佔位框而非白屏 */
class CanvasErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }
  static getDerivedStateFromError() {
    return { hasError: true }
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="w-full h-full flex items-center justify-center bg-gray-900/50 rounded-2xl border border-white/10">
          <p className="text-gray-500 text-sm">3D 模型載入失敗，請重新整理頁面</p>
        </div>
      )
    }
    return this.props.children
  }
}

/** 載入並顯示 GLB 3D 模型（Clone 確保每個 Canvas 有獨立副本，避免 WebGL context 衝突）*/
function GlassesModel({ url }) {
  const { scene } = useGLTF(url)
  return (
    <Clone
      object={scene}
      scale={[2, 2, 2]}
      position={[0, -0.3, 0]}
    />
  )
}

useGLTF.preload('/media/models/aiglass.glb')

/** 載入中佔位顯示 */
function LoadingPlaceholder() {
  return (
    <mesh>
      <boxGeometry args={[1.5, 0.3, 0.6]} />
      <meshStandardMaterial color="#07a3d7" wireframe opacity={0.5} transparent />
    </mesh>
  )
}

/**
 * 3D 模型檢視元件
 * @param {string} modelUrl - GLB 模型的 URL
 * @param {number} [cameraHeight=0.5] - 攝影機高度（Y 軸），預設 0.5
 * @param {string} className - 容器的 CSS class
 */
export default function ModelViewer({ modelUrl, cameraHeight = 0.5, className = '' }) {
  return (
    <CanvasErrorBoundary>
    <div className={`model-canvas-container ${className}`}>
      <Canvas
        camera={{ position: [0, cameraHeight, 14], fov: 35 }}
        dpr={[1, 2]}
        gl={{ antialias: true, alpha: true }}
        style={{ background: 'transparent' }}
      >
        {/* 基礎燈光 */}
        <ambientLight intensity={0.5} />
        <directionalLight position={[5, 5, 5]} intensity={1} />
        <directionalLight position={[-5, -2, -5]} intensity={0.3} color="#1ec4f7" />
        <pointLight position={[0, 3, 0]} intensity={0.5} color="#48ddff" />

        {/* 環境反射：網路可用時載入，失敗則靜默略過 */}
        <EnvironmentErrorBoundary>
          <Suspense fallback={null}>
            <Environment preset="city" />
          </Suspense>
        </EnvironmentErrorBoundary>

        {/* 3D 模型 */}
        <Suspense fallback={<LoadingPlaceholder />}>
          {modelUrl && <GlassesModel url={modelUrl} />}
        </Suspense>

        {/* 地面陰影 */}
        <ContactShadows
          position={[0, -1.5, 0]}
          opacity={0.4}
          scale={6}
          blur={2}
          color="#1ec4f7"
        />

        {/* 使用者互動控制（旋轉、縮放）*/}
        <OrbitControls
          enablePan={false}
          enableZoom={true}
          minDistance={8}
          maxDistance={20}
          autoRotate
          autoRotateSpeed={1.5}
          minPolarAngle={Math.PI / 6}
          maxPolarAngle={Math.PI / 1.8}
        />
      </Canvas>
    </div>
    </CanvasErrorBoundary>
  )
}
