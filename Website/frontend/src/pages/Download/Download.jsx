import { Link } from 'react-router-dom'
import { useContent } from '../../context/ContentContext'
import ScrollReveal from '../../components/ScrollReveal'

export default function Download() {
  const { download: c } = useContent()

  const features = c.features || []
  const steps = c.steps || []

  return (
    <div className="pt-16">
      {/* Hero 區塊 */}
      <section className="relative py-20 overflow-hidden">
        {/* 網狀漸層底層 */}
        <div className="absolute inset-0 pointer-events-none mesh-gradient" />

        {/* 動態光球裝飾 */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-1/3 left-[10%] w-[400px] h-[400px] bg-warm-400/5 dark:bg-brand-600/10 rounded-full blur-[100px] animate-float" />
          <div className="absolute bottom-[10%] right-[15%] w-72 h-72 bg-warm-500/4 dark:bg-brand-500/8 rounded-full blur-[80px] animate-float-delayed" />
        </div>

        {/* 幾何裝飾 */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="geo-diamond absolute top-[18%] right-[10%] opacity-50" />
          <div className="geo-ring absolute bottom-[25%] left-[6%] opacity-30" />
        </div>

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
            <div className="inline-flex items-center gap-2 glass rounded-full px-4 py-2 text-sm text-warm-600 dark:text-brand-400 mb-6">
            <span className="w-2 h-2 bg-green-400 rounded-full" />
            {c.hero_badge || 'Android APP 現已開放下載'}
          </div>

          <h1 className="text-4xl md:text-5xl font-bold mb-6">
            <span className="text-gray-900 dark:text-white">{c.hero_title_1 || '配套 APP'}</span>
            <br />
<span className="text-transparent bg-clip-text bg-gradient-to-r from-warm-400 to-warm-600 dark:from-brand-400 dark:to-brand-600">
              {c.hero_title_2 || '解锁眼镜完整功能'}
            </span>
          </h1>

          <p className="text-gray-700 dark:text-gray-400 text-lg max-w-2xl mx-auto mb-10">
            {c.hero_description || '透過 AI Glasses 配套 APP，輕鬆完成設備配對、AI 設定與導航控制，讓您的智慧眼鏡發揮 100% 效能。'}
          </p>

          {/* 主要下載卡片 */}
          <div className="max-w-md mx-auto glass rounded-3xl p-8 glow-border">
            {/* APP icon 佔位 */}
            <div className="w-24 h-24 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-warm-500 to-warm-700 dark:from-brand-500 dark:to-brand-700 flex items-center justify-center shadow-lg shadow-warm-500/30 dark:shadow-brand-500/30">
              <svg xmlns="http://www.w3.org/2000/svg" className="w-12 h-12 text-gray-900 dark:text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            </div>

            <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-1">{c.app_name || 'AI Glasses 配套 APP'}</h2>
            <p className="text-gray-700 dark:text-gray-400 text-sm mb-2">
              版本 {c.app_version || '1.0.0'}  ·  {c.app_requirement || 'Android 8.0 以上'}
            </p>

            <div className="flex items-center justify-center gap-4 text-xs text-gray-700 dark:text-gray-400 mb-6">
              {[c.badge_1 || '安全驗證', c.badge_2 || '免費下載', c.badge_3 || '無廣告'].map((badge) => (
                <span key={badge} className="flex items-center gap-1">
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  {badge}
                </span>
              ))}
            </div>

            <a
              href={c.apk_url || '/media/downloads/aiglass.apk'}
              download
              className="btn-primary w-full flex items-center justify-center gap-3 text-base py-4"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              {c.btn_download || '下載 Android APK'}
            </a>

<p className="text-xs text-gray-700 dark:text-gray-400 mt-4">
              {c.hardware_note || '需搭配 AI 导航智慧眼镜硬件使用。'}
              <Link to="/purchase" className="text-warm-600 dark:text-brand-400 hover:text-warm-700 dark:hover:text-brand-300 hover:underline ml-1">
                {c.hardware_link_text || '購買硬體'}
              </Link>
            </p>
          </div>

          {/* iOS 說明 */}
          <p className="text-gray-700 dark:text-gray-400 text-sm mt-6">{c.ios_note || 'iOS 版本開發中，敬請期待。'}</p>
        </div>
      </section>

      {/* 功能特色 */}
      <section className="py-20 bg-white dark:bg-gray-900/50 relative">
        {/* 區段頂部漸層分隔線 */}
        <div className="section-divider absolute top-0 left-0 right-0" />
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <ScrollReveal>
            <h2 className="section-title">{c.features_title || 'APP 核心功能'}</h2>
            <p className="section-subtitle">
              {c.features_subtitle || '从设备配对到 AI 设定，一支 APP 完整管理您的智慧眼镜。'}
            </p>
          </ScrollReveal>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {features.map((f, i) => (
              <ScrollReveal key={f.id || f.title} delay={i * 0.1}>
                <div className="glass gradient-top-border rounded-2xl p-6 hover:glow-border transition-all duration-300 group">
                <div className="w-12 h-12 rounded-xl bg-warm-500/10 dark:bg-brand-500/10 text-warm-600 dark:text-brand-400 flex items-center justify-center mb-4 group-hover:bg-warm-500/20 dark:group-hover:bg-brand-500/20 transition-colors">
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d={f.icon_svg} />
                  </svg>
                </div>
                <h3 className="font-semibold text-gray-900 dark:text-white mb-2 group-hover:text-warm-600 dark:group-hover:text-brand-400 transition-colors">{f.title}</h3>
                <p className="text-gray-700 dark:text-gray-400 text-sm leading-relaxed">{f.description}</p>
                </div>
              </ScrollReveal>
            ))}
          </div>
        </div>
      </section>

      {/* 安裝步驟 */}
      <section className="py-20 relative">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <ScrollReveal>
            <h2 className="section-title">{c.steps_title || '四步驟快速上手'}</h2>
            <p className="section-subtitle">{c.steps_subtitle || '從下載到開始使用，只需幾分鐘。'}</p>
          </ScrollReveal>
          <div className="space-y-6 relative">
            {/* 步驟間的連接線 */}
            <div className="absolute left-[52px] top-[80px] bottom-[80px] w-px flow-connector hidden sm:block" />
            {steps.map((step, i) => (
              <ScrollReveal key={step.id || step.step_number} delay={i * 0.1}>
                <div className="flex gap-6 items-start glass step-accent-line rounded-2xl p-6 hover:glow-border transition-all duration-300">
                <div className="text-3xl font-bold text-warm-500/30 dark:text-brand-500/30 font-mono shrink-0 w-12 text-center">
                  {step.step_number}
                </div>
                <div>
                  <h3 className="font-semibold text-gray-900 dark:text-white mb-1">{step.title}</h3>
                  <p className="text-gray-700 dark:text-gray-400 text-sm leading-relaxed">{step.description}</p>
                </div>
                </div>
              </ScrollReveal>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 bg-white dark:bg-gray-900/50 relative">
        {/* 區段頂部漸層分隔線 */}
        <div className="section-divider absolute top-0 left-0 right-0" />
        <ScrollReveal className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <div className="glass rounded-3xl p-10 glow-border relative overflow-hidden">
            {/* 內部漸層裝飾 */}
            <div className="absolute inset-0 pointer-events-none bg-gradient-to-br from-warm-500/5 via-transparent to-cyan-500/5 dark:from-brand-500/5 dark:via-transparent dark:to-cyan-500/5" />
            <h2 className="text-2xl md:text-3xl font-bold text-gray-900 dark:text-white mb-4 relative z-10">{c.cta_title || '還沒有智慧眼鏡？'}</h2>
            <p className="text-gray-700 dark:text-gray-400 mb-8 relative z-10">{c.cta_description || '先購買硬體，再下載 APP，即可開始體驗 AI 穿戴未來。'}</p>
            <div className="flex flex-wrap gap-4 justify-center relative z-10">
              <Link to="/purchase" className="btn-primary">{c.cta_btn_buy || '立即購買眼鏡'}</Link>
              <Link to="/product" className="btn-outline">{c.cta_btn_specs || '查看產品規格'}</Link>
            </div>
          </div>
        </ScrollReveal>
      </section>
    </div>
  )
}
