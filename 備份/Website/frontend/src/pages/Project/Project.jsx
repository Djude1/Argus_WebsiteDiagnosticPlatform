// AI 盲人輔助智慧眼鏡 — 專案介紹靜態頁面
// 說明：本頁面不需要 API 呼叫，所有內容均為靜態資料
import ScrollReveal from '../../components/ScrollReveal'

export default function Project() {
  // ── 核心功能資料 ──────────────────────────────────────────────────
  const coreFunctions = [
    {
      icon: '🦯',
      title: '盲道導航',
      subtitle: 'YOLO 分割 + 光流偵測',
      description:
        '利用 YOLO 分割模型即時偵測地面盲道輪廓，透過 Lucas-Kanade 光流演算法計算使用者偏移方向，以自然語音引導左右調整，確保視障者安全沿著盲道行走。',
      tags: ['YOLO-Seg', 'Lucas-Kanade', 'TTS 語音'],
      color: 'from-warm-500/20 to-warm-600/5',
      border: 'border-warm-500/20',
    },
    {
      icon: '🚦',
      title: '斑馬線輔助',
      subtitle: '等燈 → 安全過馬路',
      description:
        '自動辨識斑馬線幾何結構與交通號誌，偵測紅綠燈當前狀態。紅燈時靜待，偵測到綠燈後立即語音提示使用者「可以過馬路了」，陪伴每一次安全穿越路口。',
      tags: ['trafficlight.pt', '斑馬線偵測', '狀態機'],
      color: 'from-green-500/20 to-green-600/5',
      border: 'border-green-500/20',
    },
    {
      icon: '🔍',
      title: '物品尋找',
      subtitle: '開放詞彙 YOLOE',
      description:
        '使用者以語音說出想尋找的物品名稱（如「水杯」、「手機」），系統自動透過 Groq Llama 翻譯為英文標籤後交由 YOLOE 開放詞彙模型搜尋畫面，找到後語音回報方向與距離。',
      tags: ['YOLOE', 'Groq Llama', '開放詞彙'],
      color: 'from-purple-500/20 to-purple-600/5',
      border: 'border-purple-500/20',
    },
    {
      icon: '🎙️',
      title: '語音 AI 對話',
      subtitle: 'ASR + Gemini 2.5 Flash',
      description:
        '整合 Groq Whisper Large v3 Turbo 進行即時中文語音辨識，由 Gemini 2.5 Flash 處理自然語言理解與回應，再透過 Gemini TTS 合成語音回放，支援流暢中文語音對話互動。',
      tags: ['Groq Whisper', 'Gemini 2.5 Flash', 'Gemini TTS'],
      color: 'from-warm-500/20 to-warm-600/5 dark:from-brand-500/20 dark:to-brand-600/5',
      border: 'border-warm-500/20 dark:border-brand-500/20',
    },
  ]

  // ── 技術堆疊標籤 ──────────────────────────────────────────────────
  const techTags = [
    { label: 'Python 3.11', category: '後端' },
    { label: 'FastAPI', category: '後端' },
    { label: 'WebSocket', category: '通訊' },
    { label: 'YOLOv8', category: 'AI 推理' },
    { label: 'YOLOE', category: 'AI 推理' },
    { label: 'Lucas-Kanade', category: '演算法' },
    { label: 'Groq Whisper', category: '語音' },
    { label: 'Gemini 2.5 Flash', category: 'AI 對話' },
    { label: 'Gemini TTS', category: '語音合成' },
    { label: 'ESP32S3', category: '硬體' },
    { label: 'MediaPipe', category: '手勢' },
    { label: 'OpenCV', category: '影像處理' },
  ]

  // ── 硬體規格 ──────────────────────────────────────────────────────
  const hardwareSpecs = [
    {
      icon: '💻',
      name: 'Seeed XIAO ESP32S3',
      desc: '主控晶片，負責影像擷取、音訊收發、IMU 資料與 Wi-Fi 通訊',
    },
    {
      icon: '📷',
      name: 'OV2640 攝影機',
      desc: '1080p DVP 介面，即時串流 JPEG 影格至 Python 後端進行 AI 推理',
    },
    {
      icon: '🎤',
      name: 'PDM 數位麥克風',
      desc: 'PDM 介面拾音，PCM16 串流至後端 Groq Whisper 進行語音辨識',
    },
    {
      icon: '🔊',
      name: 'MAX98357A 喇叭',
      desc: 'I2S 數位功放，播放 TTS 合成語音與系統提示音效',
    },
    {
      icon: '📡',
      name: 'ICM42688 IMU',
      desc: '六軸慣性感測器（SPI），透過 UDP 傳送姿態資料輔助導航判斷',
    },
  ]

  return (
    <div className="pt-16">
      {/* ════════════════════════════════════════════════════════════
          Hero 區塊
      ════════════════════════════════════════════════════════════ */}
      <section className="relative min-h-[70vh] flex items-center overflow-hidden">
        {/* 網狀漸層底層 */}
        <div className="absolute inset-0 pointer-events-none mesh-gradient" />

        {/* 動態光球裝飾 */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-1/4 left-[10%] w-[400px] h-[400px] bg-warm-400/5 dark:bg-brand-600/10 rounded-full blur-[100px] animate-float" />
          <div className="absolute bottom-1/3 right-[15%] w-72 h-72 bg-warm-500/4 dark:bg-brand-500/8 rounded-full blur-[80px] animate-float-delayed" />
          <div className="absolute top-[55%] right-[35%] w-48 h-48 bg-cyan-400/3 dark:bg-brand-400/5 rounded-full blur-[60px] animate-float" />
        </div>

        {/* 幾何裝飾元素 */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="geo-diamond absolute top-[12%] right-[12%] opacity-60" />
          <div className="geo-ring absolute bottom-[15%] left-[8%] opacity-40" />
          <div className="geo-diamond absolute top-[45%] left-[3%] w-6 h-6 opacity-25" style={{ animationDelay: '-8s' }} />
          <div className="geo-ring absolute top-[20%] left-[40%] w-10 h-10 opacity-20" style={{ animationDelay: '-3s' }} />
        </div>

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 text-center">
          {/* 專案標籤 */}
            <div className="inline-flex items-center gap-2 glass rounded-full px-4 py-2 text-sm text-warm-600 dark:text-brand-400 mb-8">
            <span className="w-2 h-2 bg-warm-400 dark:bg-brand-400 rounded-full" />
            開源研究型專案 · 非商業販售
          </div>

          {/* 主標題 */}
          <h1 className="text-5xl md:text-7xl font-bold leading-tight mb-6">
            <span className="text-gray-900 dark:text-white">AI 盲人輔助</span>
            <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-warm-400 to-warm-600 dark:from-brand-400 dark:to-brand-600">
              智慧眼鏡
            </span>
          </h1>

          {/* 副標題 */}
          <p className="text-xl md:text-2xl text-gray-700 dark:text-gray-400 mb-10 max-w-2xl mx-auto leading-relaxed">
            讓科技成為視障者的眼睛
          </p>

          <p className="text-gray-700 dark:text-gray-400 max-w-3xl mx-auto leading-relaxed mb-12">
            結合 YOLO 影像辨識、光流導航演算法與大型語言模型，
            為視障人士打造即時語音引導系統。
            從盲道行走、安全過馬路到日常物品尋找，全程陪伴守護每一步。
          </p>

          {/* 統計數字 */}
          <div className="flex flex-wrap justify-center gap-8 md:gap-16">
            {[
              { num: '4+', label: '核心功能模組' },
              { num: 'YOLO', label: '本地 AI 推理' },
              { num: '即時', label: 'WebSocket 串流' },
              { num: '開源', label: '基於 OpenAIglasses' },
            ].map((stat) => (
              <div key={stat.label} className="text-center">
                <div className="text-3xl font-bold text-warm-600 dark:text-brand-400 mb-1">{stat.num}</div>
                <div className="text-sm text-gray-700 dark:text-gray-400">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ════════════════════════════════════════════════════════════
          專案概述卡片區（3 欄）
      ════════════════════════════════════════════════════════════ */}
      <section className="py-20 bg-white dark:bg-gray-900/50 relative">
        {/* 區段頂部漸層分隔線 */}
        <div className="section-divider absolute top-0 left-0 right-0" />
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <ScrollReveal>
            <h2 className="section-title">專案概述</h2>
            <p className="section-subtitle">
              從系統架構到解決問題，了解這個視障輔助系統的完整全貌
            </p>
          </ScrollReveal>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* 系統架構 */}
            <ScrollReveal delay={0 * 0.1}>
              <div className="glass gradient-top-border rounded-2xl p-8 hover:glow-border transition-all duration-300">
              <div className="w-12 h-12 rounded-xl bg-warm-500/20 dark:bg-brand-500/20 flex items-center justify-center text-2xl mb-5">
                🏗️
              </div>
              <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-3">系統架構</h3>
              <p className="text-gray-700 dark:text-gray-400 text-sm leading-relaxed">
                以 Python FastAPI 為核心伺服器，透過 WebSocket 與 ESP32S3 穿戴裝置即時通訊。
                影像幀由裝置攝影機串流至伺服器進行 YOLO 推理，語音透過 ASR 辨識後由 LLM 處理，
                TTS 合成回應再播放至耳機。
              </p>
              </div>
            </ScrollReveal>

            {/* 解決問題 */}
            <ScrollReveal delay={1 * 0.1}>
              <div className="glass gradient-top-border rounded-2xl p-8 hover:glow-border transition-all duration-300">
              <div className="w-12 h-12 rounded-xl bg-warm-500/20 dark:bg-brand-500/20 flex items-center justify-center text-2xl mb-5">
                🎯
              </div>
              <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-3">解決問題</h3>
              <p className="text-gray-700 dark:text-gray-400 text-sm leading-relaxed">
                台灣視障者在行走時面臨盲道辨識困難、過馬路危險判斷、物品尋找困難等挑戰。
                本系統透過即時 AI 影像分析與語音引導，提供低成本、高可靠的輔助方案，
                讓視障者能更自信地獨立出行。
              </p>
              </div>
            </ScrollReveal>

            {/* 技術創新 */}
            <ScrollReveal delay={2 * 0.1}>
              <div className="glass gradient-top-border rounded-2xl p-8 hover:glow-border transition-all duration-300">
              <div className="w-12 h-12 rounded-xl bg-purple-500/20 flex items-center justify-center text-2xl mb-5">
                💡
              </div>
              <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-3">技術創新</h3>
              <p className="text-gray-700 dark:text-gray-400 text-sm leading-relaxed">
                結合 YOLO 分割模型與 Lucas-Kanade 光流演算法實現精準盲道方向估計，
                搭配 YOLOE 開放詞彙偵測支援任意物品尋找，整合多個 AI 雲端服務實現
                毫秒級語音響應。
              </p>
              </div>
            </ScrollReveal>
          </div>
        </div>
      </section>

      {/* ════════════════════════════════════════════════════════════
          核心功能區（4 個大功能卡）
      ════════════════════════════════════════════════════════════ */}
      <section className="py-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <ScrollReveal>
            <h2 className="section-title">核心功能</h2>
            <p className="section-subtitle">
              四大核心功能模組，全方位守護視障者的每一步行走
            </p>
          </ScrollReveal>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {coreFunctions.map((func, i) => (
              <ScrollReveal key={func.title} delay={i * 0.1}>
              <div
                className={`glass rounded-2xl p-8 hover:glow-border transition-all duration-300 bg-gradient-to-br ${func.color} border ${func.border}`}
              >
                {/* 功能標題列 */}
                <div className="flex items-start gap-4 mb-5">
                  <div className="text-5xl flex-shrink-0">{func.icon}</div>
                  <div>
                    <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-1">{func.title}</h3>
                    <p className="text-sm text-warm-600 dark:text-brand-400 font-medium">{func.subtitle}</p>
                  </div>
                </div>

                {/* 功能說明 */}
                <p className="text-gray-700 dark:text-gray-400 leading-relaxed mb-5">{func.description}</p>

                {/* 技術標籤 */}
                <div className="flex flex-wrap gap-2">
                  {func.tags.map((tag) => (
                    <span
                      key={tag}
                      className="text-xs px-3 py-1 rounded-full bg-gray-100 border border-gray-200 dark:bg-white/5 dark:border-white/10 text-gray-700 dark:text-gray-300 hover:scale-105 transition-transform duration-200"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
              </ScrollReveal>
            ))}
          </div>
        </div>
      </section>

      {/* ════════════════════════════════════════════════════════════
          技術架構區（兩欄）
      ════════════════════════════════════════════════════════════ */}
      <section className="py-20 bg-white dark:bg-gray-900/50 relative">
        {/* 區段頂部漸層分隔線 */}
        <div className="section-divider absolute top-0 left-0 right-0" />
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <ScrollReveal>
            <h2 className="section-title">技術架構</h2>
            <p className="section-subtitle">
              從硬體裝置到雲端 AI，完整的技術鏈路
            </p>
          </ScrollReveal>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
            {/* 左欄：系統架構圖（文字版） */}
            <ScrollReveal>
            <div className="glass rounded-2xl p-8">
              <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-6 flex items-center gap-2">
                <span className="w-2 h-6 bg-warm-600 dark:bg-brand-400 rounded-full inline-block" />
                系統資料流向
              </h3>

              {/* 架構流程圖 */}
              <div className="space-y-2">
                {/* ESP32S3 */}
                <div className="glass rounded-xl px-5 py-3 border border-warm-500/30 dark:border-brand-500/30">
                  <div className="text-warm-600 dark:text-brand-400 font-semibold text-sm mb-1">ESP32S3 裝置</div>
                  <div className="text-xs text-gray-700 dark:text-gray-400">攝影機 · 麥克風 · IMU · 喇叭</div>
                </div>

                {/* 箭頭 — 流動連接線 */}
                <div className="flex justify-center">
                  <div className="flex flex-col items-center gap-1">
                    <div className="w-px h-4 flow-connector" />
                    <div className="text-xs text-gray-700 dark:text-gray-400">WebSocket / UDP</div>
                    <div className="w-px h-4 flow-connector" />
                    <div className="text-warm-500 dark:text-brand-500">▼</div>
                  </div>
                </div>

                {/* FastAPI */}
                <div className="glass rounded-xl px-5 py-3 border border-purple-500/30">
                  <div className="text-purple-400 font-semibold text-sm mb-1">Python FastAPI 伺服器</div>
                  <div className="text-xs text-gray-700 dark:text-gray-400">NavigationMaster 狀態機 · WebSocket 路由</div>
                </div>

                {/* 第二層分支 */}
                <div className="grid grid-cols-2 gap-3 pt-1">
                  {/* 影像分支 */}
                  <div>
                    <div className="flex justify-center mb-1">
                      <div className="text-amber-500/60 text-sm">▼</div>
                    </div>
                    <div className="glass rounded-xl px-4 py-3 border border-amber-500/20">
                      <div className="text-amber-600 dark:text-amber-400 font-semibold text-xs mb-1">YOLO 推理</div>
                      <div className="text-xs text-gray-700 dark:text-gray-400">盲道 / 斑馬線<br />障礙物 / 物品</div>
                    </div>
                  </div>

                  {/* 語音分支 */}
                  <div>
                    <div className="flex justify-center mb-1">
                      <div className="text-green-500/60 text-sm">▼</div>
                    </div>
                    <div className="glass rounded-xl px-4 py-3 border border-green-500/20">
                      <div className="text-green-400 font-semibold text-xs mb-1">ASR / LLM</div>
                      <div className="text-xs text-gray-700 dark:text-gray-400">Groq Whisper<br />Gemini 2.5 Flash</div>
                    </div>
                  </div>
                </div>

                {/* 箭頭 */}
                <div className="flex justify-center">
                  <div className="flex flex-col items-center gap-1">
                    <div className="text-warm-500 dark:text-brand-500">▼</div>
                    <div className="text-xs text-gray-700 dark:text-gray-400">Gemini TTS 合成</div>
                  </div>
                </div>

                {/* 輸出 */}
                <div className="glass rounded-xl px-5 py-3 border border-warm-500/30 dark:border-brand-500/30">
                  <div className="text-warm-600 dark:text-brand-400 font-semibold text-sm mb-1">語音回放</div>
                  <div className="text-xs text-gray-700 dark:text-gray-400">WAV 串流 → ESP32S3 喇叭 → 使用者聆聽</div>
                </div>
              </div>
            </div>
            </ScrollReveal>

            {/* 右欄：技術堆疊標籤 */}
            <ScrollReveal delay={0.2}>
            <div className="glass rounded-2xl p-8">
              <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-6 flex items-center gap-2">
                <span className="w-2 h-6 bg-warm-600 dark:bg-brand-400 rounded-full inline-block" />
                技術堆疊
              </h3>

              {/* 按類別分組顯示 */}
              {['後端', '通訊', 'AI 推理', '演算法', '語音', 'AI 對話', '語音合成', '硬體', '影像處理', '手勢'].map((cat) => {
                const items = techTags.filter((t) => t.category === cat)
                if (items.length === 0) return null
                return (
                  <div key={cat} className="mb-4">
                    <div className="text-xs text-gray-700 dark:text-gray-400 uppercase tracking-widest mb-2">{cat}</div>
                    <div className="flex flex-wrap gap-2">
                      {items.map((t) => (
                        <span
                           key={t.label}
                          className="text-sm px-3 py-1.5 rounded-lg bg-warm-500/10 dark:bg-brand-500/10 border border-warm-500/20 dark:border-brand-500/20 text-warm-700 dark:text-brand-300 font-medium hover:bg-warm-500/20 dark:hover:bg-brand-500/20 hover:scale-105 transition-all duration-200 cursor-default"
                        >
                          {t.label}
                        </span>
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
            </ScrollReveal>
          </div>
        </div>
      </section>

      {/* ════════════════════════════════════════════════════════════
          硬體規格區
      ════════════════════════════════════════════════════════════ */}
      <section className="py-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <ScrollReveal>
            <h2 className="section-title">硬體規格</h2>
            <p className="section-subtitle">
              以 Seeed Studio XIAO ESP32S3 為核心，整合攝影機、麥克風、喇叭與 IMU
            </p>
          </ScrollReveal>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-5">
            {hardwareSpecs.map((hw, i) => (
              <ScrollReveal key={hw.name} delay={i * 0.08}>
              <div
                className="glass gradient-top-border rounded-2xl p-6 hover:glow-border transition-all duration-300 group text-center"
              >
                <div className="text-4xl mb-4">{hw.icon}</div>
                <h3 className="font-semibold text-gray-900 dark:text-white text-sm mb-2 group-hover:text-warm-600 dark:group-hover:text-brand-400 transition-colors">
                  {hw.name}
                </h3>
                <p className="text-gray-700 dark:text-gray-400 text-xs leading-relaxed">{hw.desc}</p>
              </div>
              </ScrollReveal>
            ))}
          </div>
        </div>
      </section>

      {/* ════════════════════════════════════════════════════════════
          開源說明區
      ════════════════════════════════════════════════════════════ */}
      <section className="py-20 bg-white dark:bg-gray-900/50 relative">
        {/* 區段頂部漸層分隔線 */}
        <div className="section-divider absolute top-0 left-0 right-0" />
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <ScrollReveal direction="up" delay={0.2}>
          <div className="glass rounded-3xl p-12 glow-border relative overflow-hidden">
            {/* 內部漸層裝飾 */}
            <div className="absolute inset-0 pointer-events-none bg-gradient-to-br from-warm-500/5 via-transparent to-purple-500/5 dark:from-brand-500/5 dark:via-transparent dark:to-purple-500/5" />
            {/* GitHub 圖示 */}
            <div className="w-16 h-16 mx-auto mb-6 rounded-2xl bg-gray-100/5 dark:bg-white/5 flex items-center justify-center relative z-10">
              <svg
                className="w-8 h-8 text-gray-900 dark:text-white"
                fill="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  fillRule="evenodd"
                  d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483
                  0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608
                  1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951
                  0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65
                  0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337
                  1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688
                  0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855
                  0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017
                  C22 6.484 17.522 2 12 2z"
                  clipRule="evenodd"
                />
              </svg>
            </div>

            <h2 className="text-3xl font-bold text-gray-900 dark:text-white mb-4 relative z-10">開源專案</h2>
            <p className="text-gray-700 dark:text-gray-400 text-lg leading-relaxed mb-3 relative z-10">
              本專案基於{' '}
              <a
                href="https://github.com/AI-FanGe/OpenAIglasses_for_Navigation"
                target="_blank"
                rel="noopener noreferrer"
                className="text-warm-600 dark:text-brand-400 hover:text-warm-700 dark:hover:text-brand-300 underline underline-offset-4 transition-colors"
              >
                OpenAIglasses_for_Navigation
              </a>{' '}
              開源專案進行二次開發與功能強化。
            </p>
            <p className="text-gray-700 dark:text-gray-400 mb-8 relative z-10">
              感謝原作者 AI-FanGe 的開源貢獻，讓我們得以在此基礎上為視障族群打造更完善的輔助系統。
              本專案為學術研究用途，不進行商業販售。
            </p>

            <div className="flex flex-wrap gap-4 justify-center relative z-10">
              <a
                href="https://github.com/AI-FanGe/OpenAIglasses_for_Navigation"
                target="_blank"
                rel="noopener noreferrer"
                className="btn-outline inline-flex items-center gap-2"
              >
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                  <path
                    fillRule="evenodd"
                    d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483
                    0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608
                    1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951
                    0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65
                    0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337
                    1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688
                    0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855
                    0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017
                    C22 6.484 17.522 2 12 2z"
                    clipRule="evenodd"
                  />
                </svg>
                查看原始開源專案
              </a>
              <a
                href="https://www.modelscope.cn/models/archifancy/AIGlasses_for_navigation"
                target="_blank"
                rel="noopener noreferrer"
                className="btn-primary inline-flex items-center gap-2"
              >
                📦 下載模型檔案
              </a>
            </div>
          </div>
          </ScrollReveal>
        </div>
      </section>
    </div>
  )
}
