import { useState, useEffect, useCallback } from 'react'
import {
  getContentSection, updateContentSection,
  getDlFeatures, createDlFeature, updateDlFeature, deleteDlFeature,
  getDlSteps,    createDlStep,    updateDlStep,    deleteDlStep,
  uploadApk,
} from '../api'
import Modal from '../components/Modal'

// ── 通用文字輸入 ─────────────────────────────────────────────────
function Field({ label, value, onChange, multiline = false, help }) {
  return (
    <div className="mb-4">
      <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">
        {label}
      </label>
      {multiline ? (
        <textarea
          value={value || ''}
          onChange={e => onChange(e.target.value)}
          rows={3}
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:border-blue-400 resize-none"
        />
      ) : (
        <input
          type="text"
          value={value || ''}
          onChange={e => onChange(e.target.value)}
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:border-blue-400"
        />
      )}
      {help && <p className="text-xs text-slate-400 mt-1">{help}</p>}
    </div>
  )
}

// ── 儲存按鈕列 ───────────────────────────────────────────────────
function SaveBar({ onSave, saving, saved }) {
  return (
    <div className="flex items-center gap-3 pt-2 border-t border-gray-100 mt-4">
      <button
        onClick={onSave}
        disabled={saving}
        className="px-5 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-semibold rounded-lg transition-colors"
      >
        {saving ? '儲存中...' : '儲存變更'}
      </button>
      {saved && (
        <span className="inline-flex items-center gap-1 text-sm text-green-600 bg-green-50 px-3 py-1 rounded-lg">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          已儲存
        </span>
      )}
    </div>
  )
}

// ── 各頁面的欄位設定（field: 欄位名, label: 顯示標籤, multi: 多行）
const SECTIONS = {
  site: {
    label: '全站設定',
    groups: [
      { title: '品牌', fields: [
        { f: 'brand_short', l: '品牌縮寫' },
        { f: 'brand_name',  l: '品牌名稱' },
        { f: 'brand_description', l: '品牌描述', multi: true },
      ]},
      { title: '導覽列', fields: [
        { f: 'nav_home', l: '首頁' }, { f: 'nav_product', l: '產品介紹' },
        { f: 'nav_download', l: 'APP 下載' }, { f: 'nav_purchase', l: '立即購買' },
        { f: 'nav_team', l: '關於團隊' }, { f: 'nav_admin', l: '後台管理' },
      ]},
      { title: '頁尾', fields: [
        { f: 'footer_quick_links_title', l: '快速連結標題' },
        { f: 'footer_opensource_title',  l: '開源資源標題' },
        { f: 'footer_opensource_text',   l: '原始專案連結文字' },
        { f: 'footer_opensource_url',    l: '原始專案 URL' },
        { f: 'footer_copyright',         l: '版權聲明', multi: true },
      ]},
    ],
  },
  home: {
    label: '首頁',
    groups: [
      { title: 'Hero 區塊', fields: [
        { f: 'hero_badge',       l: '標籤文字' },
        { f: 'hero_title_1',     l: '主標題第一行' },
        { f: 'hero_title_2',     l: '主標題第二行' },
        { f: 'hero_description', l: '說明文字', multi: true },
        { f: 'hero_btn_buy',     l: '購買按鈕' },
        { f: 'hero_btn_detail',  l: '詳情按鈕' },
        { f: 'model_hint',       l: '3D 模型操作提示' },
      ]},
      { title: '統計數字', fields: [
        { f: 'stat_1_value', l: '統計1 數值' }, { f: 'stat_1_label', l: '統計1 標籤' },
        { f: 'stat_2_value', l: '統計2 數值' }, { f: 'stat_2_label', l: '統計2 標籤' },
        { f: 'stat_3_value', l: '統計3 數值' }, { f: 'stat_3_label', l: '統計3 標籤' },
      ]},
      { title: '特色亮點', fields: [
        { f: 'features_title',    l: '標題' },
        { f: 'features_subtitle', l: '副標題', multi: true },
      ]},
      { title: 'CTA 區塊', fields: [
        { f: 'cta_title',       l: '標題' },
        { f: 'cta_description', l: '說明', multi: true },
        { f: 'cta_btn_buy',     l: '購買按鈕' },
        { f: 'cta_btn_more',    l: '了解更多按鈕' },
      ]},
    ],
  },
  product: {
    label: '產品介紹頁',
    groups: [
      { title: '頁面文字', fields: [
        { f: 'back_link',    l: '返回首頁文字' },
        { f: 'model_hint',   l: '3D 模型提示' },
        { f: 'availability', l: '庫存狀態文字' },
        { f: 'btn_buy',      l: '購買按鈕' },
      ]},
      { title: '標籤頁名稱', fields: [
        { f: 'tab_features',    l: '功能特點 Tab' },
        { f: 'tab_specs',       l: '技術規格 Tab' },
        { f: 'tab_description', l: '詳細說明 Tab' },
      ]},
    ],
  },
  download: {
    label: 'APP 下載頁',
    groups: [
      { title: 'Hero 區塊', fields: [
        { f: 'hero_badge',       l: '標籤文字' },
        { f: 'hero_title_1',     l: '主標題第一行' },
        { f: 'hero_title_2',     l: '主標題第二行' },
        { f: 'hero_description', l: '說明文字', multi: true },
      ]},
      { title: '下載卡片', fields: [
        { f: 'app_name',        l: 'APP 名稱' },
        { f: 'app_version',     l: '版本號' },
        { f: 'app_requirement', l: '系統要求' },
        { f: 'apk_url',         l: 'APK 下載連結' },
        { f: 'btn_download',    l: '下載按鈕文字' },
        { f: 'badge_1',         l: '徽章 1' },
        { f: 'badge_2',         l: '徽章 2' },
        { f: 'badge_3',         l: '徽章 3' },
        { f: 'hardware_note',   l: '硬體搭配提示' },
        { f: 'ios_note',        l: 'iOS 版本說明' },
      ]},
      { title: '功能特色', fields: [
        { f: 'features_title',    l: '區塊標題' },
        { f: 'features_subtitle', l: '區塊副標題', multi: true },
      ]},
      { title: '安裝步驟', fields: [
        { f: 'steps_title',    l: '區塊標題' },
        { f: 'steps_subtitle', l: '區塊副標題', multi: true },
      ]},
      { title: 'CTA 區塊', fields: [
        { f: 'cta_title',       l: '標題' },
        { f: 'cta_description', l: '說明', multi: true },
        { f: 'cta_btn_buy',     l: '購買按鈕' },
        { f: 'cta_btn_specs',   l: '規格按鈕' },
      ]},
    ],
  },
  purchase: {
    label: '購買頁',
    groups: [
      { title: '頁面標題', fields: [
        { f: 'page_title', l: '頁面標題' },
        { f: 'subtitle',   l: '副標題', multi: true },
      ]},
      { title: '表單標籤', fields: [
        { f: 'label_name',    l: '姓名標籤' }, { f: 'placeholder_name',    l: '姓名預設文字' },
        { f: 'label_email',   l: 'Email 標籤' }, { f: 'placeholder_email',   l: 'Email 預設文字' },
        { f: 'label_phone',   l: '電話標籤' }, { f: 'placeholder_phone',   l: '電話預設文字' },
        { f: 'label_address', l: '地址標籤' },
        { f: 'placeholder_address', l: '地址預設文字', multi: true },
        { f: 'label_notes',   l: '備註標籤' }, { f: 'placeholder_notes',   l: '備註預設文字' },
      ]},
      { title: '按鈕', fields: [
        { f: 'btn_submit',     l: '提交按鈕' },
        { f: 'btn_submitting', l: '提交中文字' },
      ]},
      { title: '訂單成功頁', fields: [
        { f: 'success_title',        l: '成功標題' },
        { f: 'success_label_order',  l: '訂單編號標籤' },
        { f: 'success_label_buyer',  l: '購買人標籤' },
        { f: 'success_label_amount', l: '總金額標籤' },
        { f: 'success_email_hint',   l: 'Email 提示', multi: true },
        { f: 'btn_reorder',          l: '再次訂購按鈕' },
      ]},
    ],
  },
  team: {
    label: '團隊頁',
    groups: [
      { title: '頁面文字', fields: [
        { f: 'page_title', l: '頁面標題' },
        { f: 'subtitle',   l: '副標題', multi: true },
      ]},
      { title: '原專案參考者', fields: [
        { f: 'reference_title',       l: '區塊標題' },
        { f: 'reference_description', l: '說明文字', multi: true },
        { f: 'reference_link_text',   l: '連結文字' },
        { f: 'reference_link_url',    l: '連結 URL' },
      ]},
      { title: '開發團隊', fields: [
        { f: 'developer_title', l: '區塊標題' },
        { f: 'empty_message',   l: '無成員提示', multi: true },
      ]},
    ],
  },
}

// ── APK 上傳區塊（僅 download 頁使用）────────────────────────────
function ApkUploader({ currentUrl, onUploaded }) {
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress]  = useState(null) // null | 'uploading' | 'done' | 'error'

  const handleFile = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    setUploading(true)
    setProgress('uploading')
    try {
      const fd = new FormData()
      fd.append('apk', file)
      const res = await uploadApk(fd)
      onUploaded(res.data.apk_url)
      setProgress('done')
    } catch {
      setProgress('error')
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  return (
    <div className="mb-6">
      <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3 pb-2 border-b border-gray-100">
        上傳 APK 檔案
      </h4>
      <div className="flex items-center gap-4 p-4 bg-blue-50 rounded-lg border border-blue-100">
        <div className="flex-1">
          <p className="text-xs text-slate-500 mb-1">目前連結：<span className="font-mono text-slate-700">{currentUrl || '（未設定）'}</span></p>
          <input
            type="file"
            accept=".apk"
            disabled={uploading}
            onChange={handleFile}
            className="text-sm text-gray-600 w-full file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-blue-600 file:text-white hover:file:bg-blue-500 disabled:opacity-50"
          />
        </div>
        {progress === 'uploading' && <span className="text-xs text-blue-600 shrink-0">上傳中...</span>}
        {progress === 'done'      && <span className="text-xs text-green-600 shrink-0">✓ 上傳成功</span>}
        {progress === 'error'     && <span className="text-xs text-red-500 shrink-0">✗ 上傳失敗</span>}
      </div>
    </div>
  )
}

// ── Singleton 頁面表單 ────────────────────────────────────────────
function SectionForm({ sectionKey }) {
  const [data, setData]     = useState({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved]   = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState(null)
  const config = SECTIONS[sectionKey]

  useEffect(() => {
    setData({})
    setSaved(false)
    setError(null)
    setLoading(true)
    getContentSection(sectionKey)
      .then(r => setData(r.data))
      .catch(err => {
        console.error('載入頁面設定失敗:', err)
        setError('載入設定失敗，請稍後再試')
      })
      .finally(() => setLoading(false))
  }, [sectionKey])

  const set = (field, value) => {
    setData(p => ({ ...p, [field]: value }))
    setSaved(false)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await updateContentSection(sectionKey, data)
      setSaved(true)
    } catch (e) {
      alert('儲存失敗：' + JSON.stringify(e.response?.data))
    } finally {
      setSaving(false)
    }
  }

  if (!config) return null

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-gray-400">
        <div className="w-8 h-8 border-2 border-blue-400 border-t-transparent rounded-full animate-spin mb-3" />
        <span className="text-sm">載入設定中...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-gray-400">
        <div className="text-3xl mb-2">⚠️</div>
        <p className="text-sm text-gray-500 mb-3">{error}</p>
        <button
          onClick={() => {
            setError(null)
            setLoading(true)
            getContentSection(sectionKey)
              .then(r => { setData(r.data); setError(null) })
              .catch(() => setError('載入設定失敗，請稍後再試'))
              .finally(() => setLoading(false))
          }}
          className="text-xs px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 transition-colors"
        >
          重新載入
        </button>
      </div>
    )
  }

  return (
    <div>
      {sectionKey === 'download' && (
        <ApkUploader
          currentUrl={data.apk_url}
          onUploaded={(url) => set('apk_url', url)}
        />
      )}
      {config.groups.map((group) => (
        <div key={group.title} className="mb-6">
          <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3 pb-2 border-b border-gray-100">
            {group.title}
          </h4>
          <div className="grid grid-cols-2 gap-x-4">
            {group.fields.map(({ f, l, multi }) => (
              <div key={f} className={multi ? 'col-span-2' : ''}>
                <Field
                  label={l}
                  value={data[f]}
                  onChange={v => set(f, v)}
                  multiline={multi}
                />
              </div>
            ))}
          </div>
        </div>
      ))}
      <SaveBar onSave={handleSave} saving={saving} saved={saved} />
    </div>
  )
}

// ── APP 功能特色清單 ──────────────────────────────────────────────
function FeaturesList() {
  const [items, setItems]   = useState([])
  const [modal, setModal]   = useState(null) // null | 'add' | {item}
  const [form, setForm]     = useState({ title: '', description: '', icon_svg: '', order: 0 })
  const [saving, setSaving] = useState(false)

  const load = useCallback(() => getDlFeatures().then(r => setItems(r.data)), [])
  useEffect(() => { load() }, [load])

  const openEdit = (item) => { setForm({ ...item }); setModal(item) }
  const openAdd  = ()     => { setForm({ title: '', description: '', icon_svg: '', order: items.length }); setModal('add') }

  const handleSave = async () => {
    setSaving(true)
    try {
      if (modal === 'add') await createDlFeature(form)
      else await updateDlFeature(modal.id, form)
      await load(); setModal(null)
    } catch (e) { alert('儲存失敗') }
    finally { setSaving(false) }
  }

  const handleDelete = async (id) => {
    if (!window.confirm('確定刪除此功能特色？')) return
    await deleteDlFeature(id); load()
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest">APP 功能特色</h4>
        <button onClick={openAdd} className="text-xs px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-500">+ 新增</button>
      </div>
      <div className="space-y-2">
        {items.map(item => (
          <div key={item.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
            <div>
              <span className="text-sm font-medium text-gray-800">{item.title}</span>
              <p className="text-xs text-gray-500 mt-0.5 line-clamp-1">{item.description}</p>
            </div>
            <div className="flex gap-2 ml-4 flex-shrink-0">
              <button onClick={() => openEdit(item)} className="text-xs text-blue-600 hover:underline">編輯</button>
              <button onClick={() => handleDelete(item.id)} className="text-xs text-red-500 hover:underline">刪除</button>
            </div>
          </div>
        ))}
      </div>
      {modal && (
        <Modal title={modal === 'add' ? '新增功能特色' : '編輯功能特色'} onClose={() => setModal(null)}>
          <Field label="標題" value={form.title} onChange={v => setForm(p => ({...p, title: v}))} />
          <Field label="說明" value={form.description} onChange={v => setForm(p => ({...p, description: v}))} multiline />
          <Field label="排序" value={String(form.order)} onChange={v => setForm(p => ({...p, order: Number(v)}))} />
          <div className="flex justify-end gap-2 pt-2">
            <button onClick={() => setModal(null)} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800">取消</button>
            <button onClick={handleSave} disabled={saving} className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-500 disabled:opacity-50">
              {saving ? '儲存中...' : '儲存'}
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── 安裝步驟清單 ─────────────────────────────────────────────────
function StepsList() {
  const [items, setItems]   = useState([])
  const [modal, setModal]   = useState(null)
  const [form, setForm]     = useState({ step_number: '', title: '', description: '', order: 0 })
  const [saving, setSaving] = useState(false)

  const load = useCallback(() => getDlSteps().then(r => setItems(r.data)), [])
  useEffect(() => { load() }, [load])

  const openEdit = (item) => { setForm({ ...item }); setModal(item) }
  const openAdd  = ()     => { setForm({ step_number: `0${items.length + 1}`, title: '', description: '', order: items.length }); setModal('add') }

  const handleSave = async () => {
    setSaving(true)
    try {
      if (modal === 'add') await createDlStep(form)
      else await updateDlStep(modal.id, form)
      await load(); setModal(null)
    } catch { alert('儲存失敗') }
    finally { setSaving(false) }
  }

  const handleDelete = async (id) => {
    if (!window.confirm('確定刪除此步驟？')) return
    await deleteDlStep(id); load()
  }

  return (
    <div className="mt-8">
      <div className="flex justify-between items-center mb-4">
        <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest">安裝步驟</h4>
        <button onClick={openAdd} className="text-xs px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-500">+ 新增</button>
      </div>
      <div className="space-y-2">
        {items.map(item => (
          <div key={item.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
            <div className="flex items-center gap-3">
              <span className="text-lg font-bold text-blue-400/50 font-mono w-8">{item.step_number}</span>
              <div>
                <span className="text-sm font-medium text-gray-800">{item.title}</span>
                <p className="text-xs text-gray-500 mt-0.5 line-clamp-1">{item.description}</p>
              </div>
            </div>
            <div className="flex gap-2 ml-4 flex-shrink-0">
              <button onClick={() => openEdit(item)} className="text-xs text-blue-600 hover:underline">編輯</button>
              <button onClick={() => handleDelete(item.id)} className="text-xs text-red-500 hover:underline">刪除</button>
            </div>
          </div>
        ))}
      </div>
      {modal && (
        <Modal title={modal === 'add' ? '新增安裝步驟' : '編輯安裝步驟'} onClose={() => setModal(null)}>
          <Field label="步驟編號" value={form.step_number} onChange={v => setForm(p => ({...p, step_number: v}))} />
          <Field label="標題" value={form.title} onChange={v => setForm(p => ({...p, title: v}))} />
          <Field label="說明" value={form.description} onChange={v => setForm(p => ({...p, description: v}))} multiline />
          <div className="flex justify-end gap-2 pt-2">
            <button onClick={() => setModal(null)} className="px-4 py-2 text-sm text-gray-600">取消</button>
            <button onClick={handleSave} disabled={saving} className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-500 disabled:opacity-50">
              {saving ? '儲存中...' : '儲存'}
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── 中欄項目清單 ─────────────────────────────────────────────────
const MIDDLE_ITEMS = [
  { key: 'site',     label: '全站設定',    icon: '🌐' },
  { key: 'home',     label: '首頁',        icon: '🏠' },
  { key: 'product',  label: '產品介紹頁',  icon: '📱' },
  { key: 'download', label: 'APP 下載頁',  icon: '⬇️' },
  { key: 'purchase', label: '購買頁',      icon: '🛒' },
  { key: 'team',     label: '團隊頁',      icon: '👥' },
  { key: 'dl-features', label: 'APP 功能特色', icon: '✨', isList: true },
  { key: 'dl-steps',    label: '安裝步驟',     icon: '📋', isList: true },
]

export default function PageContent() {
  const [activeKey, setActiveKey] = useState('site')
  const active = MIDDLE_ITEMS.find(i => i.key === activeKey)

  return (
    <div className="flex h-full">
      {/* 中欄 */}
      <div className="w-64 bg-white border-r border-gray-100 flex-shrink-0 overflow-y-auto">
        <div className="px-4 py-3 border-b border-gray-100">
          <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest">頁面內容管理</h3>
        </div>
        <nav className="py-2">
          {MIDDLE_ITEMS.map((item, idx) => {
            const isDivider = idx === 6
            return (
              <div key={item.key}>
                {isDivider && <div className="mx-4 my-2 border-t border-gray-100" />}
                <button
                  onClick={() => setActiveKey(item.key)}
                  className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors text-left ${
                    activeKey === item.key
                      ? 'bg-blue-50 text-blue-700 font-medium border-r-2 border-blue-600'
                      : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                  }`}
                >
                  <span className="text-base w-5 text-center">{item.icon}</span>
                  {item.label}
                </button>
              </div>
            )
          })}
        </nav>
      </div>

      {/* 右欄：編輯區 */}
      <div className="flex-1 overflow-y-auto bg-white">
        <div className="max-w-2xl mx-auto px-8 py-6">
          <h2 className="text-lg font-bold text-gray-800 mb-6">
            {active?.icon} {active?.label}
          </h2>
          {activeKey === 'dl-features' && <FeaturesList />}
          {activeKey === 'dl-steps'    && <StepsList />}
          {!['dl-features', 'dl-steps'].includes(activeKey) && (
            <SectionForm sectionKey={activeKey} />
          )}
        </div>
      </div>
    </div>
  )
}
