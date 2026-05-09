import { useState, useEffect, useCallback } from 'react'
import {
  getProducts, createProduct, updateProduct, deleteProduct, uploadProductFile,
  getFeatures, createFeature, updateFeature, deleteFeature,
  getSpecs,    createSpec,    updateSpec,    deleteSpec,
} from '../api'
import Modal from '../components/Modal'

function Field({ label, value, onChange, multiline, type = 'text' }) {
  return (
    <div className="mb-3">
      <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">{label}</label>
      {multiline ? (
        <textarea value={value ?? ''} onChange={e => onChange(e.target.value)} rows={3}
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:border-blue-400 resize-none" />
      ) : (
        <input type={type} value={value ?? ''} onChange={e => onChange(e.target.value)}
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:border-blue-400" />
      )}
    </div>
  )
}

const emptyProduct = { name: '', short_description: '', description: '', price: '', original_price: '', stock: 0, is_active: true, camera_height: 0.5 }

export default function Products() {
  const [products, setProducts]         = useState([])
  const [selected, setSelected]         = useState(null)
  const [searchTerm, setSearchTerm]     = useState('')
  const [activeTab, setActiveTab]       = useState('info')
  const [editForm, setEditForm]         = useState({})
  const [saving, setSaving]             = useState(false)
  const [saved, setSaved]               = useState(false)
  const [features, setFeatures]         = useState([])
  const [specs, setSpecs]               = useState([])
  const [modalType, setModalType]       = useState(null) // 'new-product' | 'feature' | 'spec'
  const [modalForm, setModalForm]       = useState({})
  const [modalSaving, setModalSaving]   = useState(false)
  const [editingItem, setEditingItem]   = useState(null)
  const [uploading, setUploading]       = useState(false)
  const [sortField, setSortField] = useState('')
  const [sortDir, setSortDir]     = useState('asc')

  // 排序切換函式
  function toggleSort(field) {
    if (sortField === field) {
      setSortDir(prev => prev === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDir('asc')
    }
  }

  // 排序圖示元件
  function SortIcon({ field }) {
    if (sortField !== field) return <span className="text-gray-400 ml-1">↕</span>
    return sortDir === 'asc' ? <span className="text-blue-500 ml-1">↑</span> : <span className="text-blue-500 ml-1">↓</span>
  }

  const loadProducts = useCallback(() =>
    getProducts().then(r => setProducts(r.data.results || r.data)), [])

  const loadDetails = useCallback((product) => {
    if (!product) return
    getFeatures(product.id).then(r => setFeatures(r.data.results ?? r.data))
    getSpecs(product.id).then(r => setSpecs(r.data.results ?? r.data))
  }, [])

  useEffect(() => { loadProducts() }, [loadProducts])

  // 每次 selected 改變（包含初次選取）時同步 editForm
  useEffect(() => {
    if (selected) setEditForm(prev => ({ ...selected, password: prev.password }))
  }, [selected?.id])

  const selectProduct = (p) => {
    setSelected(p)
    setSaved(false)
    setActiveTab('info')
    loadDetails(p)
  }

  // loadProducts 完成後更新 selected（確保顯示最新資料）
  const loadProductsAndSync = useCallback(() => {
    getProducts().then(r => {
      const list = r.data.results || r.data
      setProducts(list)
      setSelected(prev => {
        if (!prev) return prev
        const updated = list.find(p => p.id === prev.id)
        return updated || prev
      })
    })
  }, [])

  const handleFileUpload = async (field, file) => {
    if (!file || !selected) return
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append(field, file)
      const res = await uploadProductFile(selected.id, fd)
      setSelected(res.data)
      loadProductsAndSync()
    } catch { alert('上傳失敗') }
    finally { setUploading(false) }
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const res = await updateProduct(selected.id, editForm)
      setSelected(res.data)
      setSaved(true)
      loadProductsAndSync()
    } catch (e) { alert('儲存失敗：' + JSON.stringify(e.response?.data)) }
    finally { setSaving(false) }
  }

  const handleDelete = async () => {
    if (!confirm(`確定刪除「${selected.name}」？`)) return
    await deleteProduct(selected.id)
    setSelected(null)
    loadProductsAndSync()
  }

  // ── 功能特色 CRUD ──────────────────────────────────────────────
  const openFeatureModal = (item = null) => {
    setEditingItem(item)
    setModalForm(item ? { ...item } : { title: '', description: '', icon: '', order: features.length })
    setModalType('feature')
  }
  const openSpecModal = (item = null) => {
    setEditingItem(item)
    setModalForm(item ? { ...item } : { key: '', value: '', order: specs.length })
    setModalType('spec')
  }

  const handleModalSave = async () => {
    setModalSaving(true)
    try {
      if (modalType === 'feature') {
        if (editingItem) await updateFeature(editingItem.id, modalForm)
        else await createFeature(selected.id, modalForm)
        getFeatures(selected.id).then(r => setFeatures(r.data.results ?? r.data))
      } else if (modalType === 'spec') {
        if (editingItem) await updateSpec(editingItem.id, modalForm)
        else await createSpec(selected.id, modalForm)
        getSpecs(selected.id).then(r => setSpecs(r.data.results ?? r.data))
      } else if (modalType === 'new-product') {
        await createProduct(modalForm)
        loadProductsAndSync()
      }
      setModalType(null)
    } catch { alert('儲存失敗') }
    finally { setModalSaving(false) }
  }

  // 搜尋篩選：依商品名稱
  const filteredProducts = products.filter(p => {
    if (!searchTerm) return true
    const term = searchTerm.toLowerCase()
    return p.name && p.name.toLowerCase().includes(term)
  })

  // 排序後的商品列表
  const sortedProducts = [...filteredProducts].sort((a, b) => {
    if (!sortField) return 0
    const aVal = a[sortField] ?? ''
    const bVal = b[sortField] ?? ''
    const cmp = typeof aVal === 'number' ? aVal - bVal : String(aVal).localeCompare(String(bVal), 'zh-TW')
    return sortDir === 'asc' ? cmp : -cmp
  })

  const TABS = ['info', 'features', 'specs']
  const TAB_LABELS = { info: '基本資料', features: `功能特點 (${features.length})`, specs: `技術規格 (${specs.length})` }

  return (
    <div className="flex h-full">
      {/* 中欄：商品清單 */}
      <div className="w-64 bg-white border-r border-gray-100 flex-shrink-0 flex flex-col">
        {/* 搜尋 */}
        <div className="px-4 py-2 border-b border-gray-100">
          <input
            type="text"
            placeholder="搜尋商品名稱..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            className="w-full text-xs border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-blue-400"
          />
        </div>
        <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
          <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest">商品列表</h3>
          <button onClick={() => { setModalForm(emptyProduct); setModalType('new-product') }}
            className="text-xs px-2 py-1 bg-blue-600 text-white rounded hover:bg-blue-500">+ 新增</button>
        </div>
        {/* 排序欄位標題 */}
        <div className="px-4 py-2 border-b border-gray-100 flex items-center gap-1">
          <button onClick={() => toggleSort('name')} className="text-xs font-medium text-gray-500 hover:text-gray-700 transition-colors flex items-center gap-1">
            名稱<SortIcon field="name" />
          </button>
          <span className="text-gray-300 text-xs">|</span>
          <button onClick={() => toggleSort('price')} className="text-xs font-medium text-gray-500 hover:text-gray-700 transition-colors flex items-center gap-1">
            價格<SortIcon field="price" />
          </button>
          <span className="text-gray-300 text-xs">|</span>
          <button onClick={() => toggleSort('created_at')} className="text-xs font-medium text-gray-500 hover:text-gray-700 transition-colors flex items-center gap-1">
            建立日期<SortIcon field="created_at" />
          </button>
        </div>
        <div className="overflow-y-auto flex-1">
          {filteredProducts.length === 0 && products.length === 0 && (
            <div className="text-center text-gray-400 text-sm py-8">
              <div className="text-2xl mb-2">📭</div>
              <p>沒有商品</p>
            </div>
          )}
          {filteredProducts.length === 0 && products.length > 0 && (
            <div className="text-center text-gray-400 text-sm py-8">
              <div className="text-2xl mb-2">🔍</div>
              <p>沒有符合的商品</p>
            </div>
          )}
          {sortedProducts.map(p => (
            <button key={p.id} onClick={() => selectProduct(p)}
              className={`w-full text-left px-4 py-3 border-b border-gray-50 transition-colors ${
                selected?.id === p.id ? 'bg-blue-50 border-r-2 border-blue-600' : 'hover:bg-gray-50'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-gray-800 truncate">{p.name}</span>
                <span className={`text-xs px-1.5 py-0.5 rounded flex-shrink-0 ml-2 ${p.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                  {p.is_active ? '上架' : '下架'}
                </span>
              </div>
              <div className="text-xs text-gray-500 mt-0.5">NT${Number(p.price).toLocaleString()}</div>
            </button>
          ))}
        </div>
      </div>

      {/* 右欄：編輯區 */}
      <div className="flex-1 overflow-y-auto bg-white">
        {!selected ? (
          <div className="flex items-center justify-center h-full text-gray-400">
            <div className="text-center">
              <div className="text-4xl mb-2">📦</div>
              <p>請從左側選擇商品</p>
            </div>
          </div>
        ) : (
          <div className="max-w-2xl mx-auto px-8 py-6">
            {/* 頂部 */}
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-bold text-gray-800">{selected.name}</h2>
              <button onClick={handleDelete} className="text-xs text-red-500 hover:text-red-700 px-3 py-1.5 border border-red-200 rounded-lg hover:bg-red-50">
                刪除商品
              </button>
            </div>

            {/* Tabs */}
            <div className="flex border-b border-gray-100 mb-6">
              {TABS.map(tab => (
                <button key={tab} onClick={() => setActiveTab(tab)}
                  className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
                    activeTab === tab ? 'text-blue-600 border-blue-600' : 'text-gray-500 border-transparent hover:text-gray-700'
                  }`}
                >{TAB_LABELS[tab]}</button>
              ))}
            </div>

            {/* 基本資料 Tab */}
            {activeTab === 'info' && (
              <div>
                <div className="grid grid-cols-2 gap-x-4">
                  <Field label="商品名稱" value={editForm.name} onChange={v => setEditForm(p => ({...p, name: v}))} />
                  <Field label="庫存數量" value={editForm.stock} onChange={v => setEditForm(p => ({...p, stock: Number(v)}))} type="number" />
                  <Field label="售價" value={editForm.price} onChange={v => setEditForm(p => ({...p, price: v}))} type="number" />
                  <Field label="原價" value={editForm.original_price} onChange={v => setEditForm(p => ({...p, original_price: v}))} type="number" />
                </div>
                <Field label="攝影機高度（Y 軸，預設 0.5）" value={editForm.camera_height ?? 0.5} onChange={v => setEditForm(p => ({...p, camera_height: Number(v)}))} type="number" />
                <Field label="簡短描述" value={editForm.short_description} onChange={v => setEditForm(p => ({...p, short_description: v}))} />
                <Field label="詳細描述" value={editForm.description} onChange={v => setEditForm(p => ({...p, description: v}))} multiline />
                <div className="mb-4 flex items-center gap-2">
                  <input type="checkbox" id="is_active" checked={!!editForm.is_active}
                    onChange={e => setEditForm(p => ({...p, is_active: e.target.checked}))}
                    className="w-4 h-4 rounded border-gray-300 text-blue-600" />
                  <label htmlFor="is_active" className="text-sm text-gray-700">上架中（取消勾選即下架）</label>
                </div>

                {/* 檔案上傳區 */}
                <div className="mb-4 p-4 bg-gray-50 rounded-lg border border-dashed border-gray-200">
                  <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">媒體檔案</p>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-xs text-gray-500 mb-1">3D 模型 (.glb)</p>
                      {editForm.model_3d && (
                        <p className="text-xs text-blue-600 truncate mb-1">
                          目前：{String(editForm.model_3d).split('/').pop()}
                        </p>
                      )}
                      <input type="file" accept=".glb,.gltf" disabled={uploading}
                        onChange={e => handleFileUpload('model_3d', e.target.files[0])}
                        className="text-xs text-gray-600 w-full file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-xs file:bg-blue-50 file:text-blue-600 hover:file:bg-blue-100" />
                    </div>
                    <div>
                      <p className="text-xs text-gray-500 mb-1">商品圖片</p>
                      {editForm.image && (
                        <p className="text-xs text-blue-600 truncate mb-1">
                          目前：{String(editForm.image).split('/').pop()}
                        </p>
                      )}
                      <input type="file" accept="image/*" disabled={uploading}
                        onChange={e => handleFileUpload('image', e.target.files[0])}
                        className="text-xs text-gray-600 w-full file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-xs file:bg-blue-50 file:text-blue-600 hover:file:bg-blue-100" />
                    </div>
                  </div>
                  {uploading && <p className="text-xs text-blue-500 mt-2">上傳中...</p>}
                </div>

                <div className="flex items-center gap-3 pt-2 border-t border-gray-100">
                  <button onClick={handleSave} disabled={saving}
                    className="px-5 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-semibold rounded-lg transition-colors">
                    {saving ? '儲存中...' : '儲存變更'}
                  </button>
                  {saved && <span className="text-green-500 text-sm">✓ 已儲存</span>}
                </div>
              </div>
            )}

            {/* 功能特點 Tab */}
            {activeTab === 'features' && (
              <div>
                <div className="flex justify-end mb-3">
                  <button onClick={() => openFeatureModal()} className="text-xs px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-500">+ 新增功能</button>
                </div>
                <div className="space-y-2">
                  {features.map(f => (
                    <div key={f.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                      <div className="flex items-center gap-3">
                        <span className="text-xl">{f.icon}</span>
                        <div>
                          <span className="text-sm font-medium text-gray-800">{f.title}</span>
                          <p className="text-xs text-gray-500 line-clamp-1">{f.description}</p>
                        </div>
                      </div>
                      <div className="flex gap-2 ml-4">
                        <button onClick={() => openFeatureModal(f)} className="text-xs text-blue-600 hover:underline">編輯</button>
                        <button onClick={async () => { if(confirm('確定刪除？')) { await deleteFeature(f.id); getFeatures(selected.id).then(r => setFeatures(r.data.results ?? r.data)) } }} className="text-xs text-red-500 hover:underline">刪除</button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 技術規格 Tab */}
            {activeTab === 'specs' && (
              <div>
                <div className="flex justify-end mb-3">
                  <button onClick={() => openSpecModal()} className="text-xs px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-500">+ 新增規格</button>
                </div>
                <div className="space-y-2">
                  {specs.map(s => (
                    <div key={s.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                      <div className="flex gap-4">
                        <span className="text-sm text-gray-500 w-28 flex-shrink-0">{s.key}</span>
                        <span className="text-sm font-medium text-gray-800">{s.value}</span>
                      </div>
                      <div className="flex gap-2 ml-4">
                        <button onClick={() => openSpecModal(s)} className="text-xs text-blue-600 hover:underline">編輯</button>
                        <button onClick={async () => { if(confirm('確定刪除？')) { await deleteSpec(s.id); getSpecs(selected.id).then(r => setSpecs(r.data.results ?? r.data)) } }} className="text-xs text-red-500 hover:underline">刪除</button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Modal：新增/編輯功能特色 */}
      {modalType === 'feature' && (
        <Modal title={editingItem ? '編輯功能特點' : '新增功能特點'} onClose={() => setModalType(null)}>
          <Field label="圖示 (Emoji)" value={modalForm.icon} onChange={v => setModalForm(p => ({...p, icon: v}))} />
          <Field label="標題" value={modalForm.title} onChange={v => setModalForm(p => ({...p, title: v}))} />
          <Field label="說明" value={modalForm.description} onChange={v => setModalForm(p => ({...p, description: v}))} multiline />
          <Field label="排序" value={String(modalForm.order)} onChange={v => setModalForm(p => ({...p, order: Number(v)}))} type="number" />
          <div className="flex justify-end gap-2 pt-2">
            <button onClick={() => setModalType(null)} className="px-4 py-2 text-sm text-gray-600">取消</button>
            <button onClick={handleModalSave} disabled={modalSaving} className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg disabled:opacity-50">
              {modalSaving ? '儲存中...' : '儲存'}
            </button>
          </div>
        </Modal>
      )}

      {/* Modal：新增/編輯規格 */}
      {modalType === 'spec' && (
        <Modal title={editingItem ? '編輯技術規格' : '新增技術規格'} onClose={() => setModalType(null)}>
          <Field label="規格項目" value={modalForm.key} onChange={v => setModalForm(p => ({...p, key: v}))} />
          <Field label="規格值" value={modalForm.value} onChange={v => setModalForm(p => ({...p, value: v}))} />
          <Field label="排序" value={String(modalForm.order)} onChange={v => setModalForm(p => ({...p, order: Number(v)}))} type="number" />
          <div className="flex justify-end gap-2 pt-2">
            <button onClick={() => setModalType(null)} className="px-4 py-2 text-sm text-gray-600">取消</button>
            <button onClick={handleModalSave} disabled={modalSaving} className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg disabled:opacity-50">
              {modalSaving ? '儲存中...' : '儲存'}
            </button>
          </div>
        </Modal>
      )}

      {/* Modal：新增商品 */}
      {modalType === 'new-product' && (
        <Modal title="新增商品" onClose={() => setModalType(null)} size="lg">
          <div className="grid grid-cols-2 gap-x-4">
            <Field label="商品名稱" value={modalForm.name} onChange={v => setModalForm(p => ({...p, name: v}))} />
            <Field label="庫存" value={modalForm.stock} onChange={v => setModalForm(p => ({...p, stock: Number(v)}))} type="number" />
            <Field label="售價" value={modalForm.price} onChange={v => setModalForm(p => ({...p, price: v}))} type="number" />
            <Field label="原價" value={modalForm.original_price} onChange={v => setModalForm(p => ({...p, original_price: v}))} type="number" />
          </div>
          <Field label="簡短描述" value={modalForm.short_description} onChange={v => setModalForm(p => ({...p, short_description: v}))} />
          <Field label="詳細描述" value={modalForm.description} onChange={v => setModalForm(p => ({...p, description: v}))} multiline />
          <div className="flex justify-end gap-2 pt-2">
            <button onClick={() => setModalType(null)} className="px-4 py-2 text-sm text-gray-600">取消</button>
            <button onClick={handleModalSave} disabled={modalSaving} className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg disabled:opacity-50">
              {modalSaving ? '建立中...' : '建立商品'}
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}
