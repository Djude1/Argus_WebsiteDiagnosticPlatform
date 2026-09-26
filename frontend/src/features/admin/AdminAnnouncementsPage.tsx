import { useCallback, useEffect, useState } from "react";

import {
  createAnnouncement,
  deleteAnnouncement,
  fetchAdminAnnouncements,
  updateAnnouncement,
} from "../../api";
import { AdminField, AdminModal } from "../../components/admin/AdminModal";
import { AdminErrorState, AdminSkeleton } from "../../components/admin/AdminStates";
import { useConfirmDialogs } from "../../shared/AppShared.jsx";
import type { Announcement, AnnouncementInput } from "../../shared/apiContracts";
import { useArgusStore } from "../../store";
import { errorDetail, fieldErrors } from "./adminHelpers";

// 公告管理（僅超級管理員）。從 AdminPages.jsx 拆出並轉成 TypeScript，同時補上
// 原本完全沒有的錯誤回饋：
//   · 載入失敗：原本會顯示「尚無公告」——把「讀不到」說成「沒有」，改為錯誤＋重試
//   · 儲存失敗：原本按「儲存」後毫無反應（例外未處理，彈窗留著但沒有任何訊息）；
//     改為欄位錯誤顯示在對應欄位旁、其他錯誤顯示在彈窗內，並在送出中停用按鈕
//   · 刪除失敗：原本同樣無聲無息，改為提示

type Form = Required<Pick<AnnouncementInput, "title" | "content" | "type" | "active_days" | "is_active">>;

const EMPTY_FORM: Form = { title: "", content: "", type: "temporary", active_days: 7, is_active: true };

export function AdminAnnouncementsPage() {
  const me = useArgusStore((s) => s.me);
  const [list, setList] = useState<Announcement[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Announcement | "new" | null>(null);
  const [form, setForm] = useState<Form>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const { confirmDialog, notifyDialog, dialogHost } = useConfirmDialogs();

  const loadList = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      setList((await fetchAdminAnnouncements()).announcements);
    } catch (err) {
      setLoadError(errorDetail(err, "無法載入公告"));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    if (me?.is_superuser) loadList();
  }, [me, loadList]);

  if (!me?.is_superuser) {
    return <div className="admin-error">需要超級管理員權限才能查看。</div>;
  }

  function openEditor(target: Announcement | "new") {
    setForm(target === "new" ? EMPTY_FORM : {
      title: target.title,
      content: target.content,
      type: target.type,
      active_days: target.active_days,
      is_active: target.is_active,
    });
    setErrors({});
    setSaveError(null);
    setEditing(target);
  }

  async function handleSave() {
    if (!editing) return;
    setSaving(true);
    setErrors({});
    setSaveError(null);
    try {
      if (editing === "new") await createAnnouncement(form);
      else await updateAnnouncement(editing.id, form);
      setEditing(null);
      loadList();
    } catch (err) {
      const byField = fieldErrors(err);
      setErrors(byField);
      // 有欄位錯誤就顯示在欄位旁；沒有（網路、權限等）才顯示整體訊息
      if (Object.keys(byField).length === 0) setSaveError(errorDetail(err, "儲存失敗，請稍後再試。"));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: number) {
    if (!(await confirmDialog("確定刪除此公告？", { danger: true }))) return;
    try {
      await deleteAnnouncement(id);
      loadList();
    } catch (err) {
      notifyDialog(errorDetail(err, "刪除失敗，請稍後再試。"));
    }
  }

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <h1 className="admin-page-title">公告管理</h1>
        <button className="admin-btn primary" onClick={() => openEditor("new")}>＋ 新增公告</button>
      </header>

      {loadError && <AdminErrorState message="無法載入公告" detail={loadError} onRetry={loadList} />}
      {!loadError && loading && <AdminSkeleton variant="card" rows={3} label="載入公告中" />}
      {!loadError && !loading && (
        <div className="admin-ann-list">
          {list.map((ann) => (
            <div key={ann.id} className={`admin-ann-card ${ann.is_active ? "" : "inactive"}`}>
              <div className="admin-ann-card-header">
                <span className="admin-ann-title">{ann.title}</span>
                <span className={`admin-ann-type ${ann.type}`}>
                  {ann.type === "permanent" ? "常駐" : `臨時（${ann.active_days}天）`}
                </span>
              </div>
              <p className="admin-ann-preview">{ann.content.slice(0, 80)}…</p>
              <div className="admin-ann-actions">
                <button onClick={() => openEditor(ann)}>編輯</button>
                <button className="danger" onClick={() => handleDelete(ann.id)}>刪除</button>
                <span className={ann.is_active ? "status-active" : "status-inactive"}>
                  {ann.is_active ? "啟用" : "停用"}
                </span>
              </div>
            </div>
          ))}
          {!list.length && <div className="admin-empty">尚無公告</div>}
        </div>
      )}

      <AdminModal
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "新增公告" : "編輯公告"}
        size="lg"
        footer={
          <>
            <button type="button" className="admin-btn" onClick={() => setEditing(null)}>取消</button>
            <button type="button" className="admin-btn primary" disabled={saving} onClick={handleSave}>
              {saving ? "儲存中…" : "儲存"}
            </button>
          </>
        }
      >
        {saveError && <div className="admin-feedback tone-bad" role="alert">{saveError}</div>}
        <AdminField id="ann-title" label="標題" required error={errors.title}>
          {(field) => (
            <input {...field} className="admin-input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          )}
        </AdminField>
        <AdminField id="ann-content" label="內容" required error={errors.content}>
          {(field) => (
            <textarea {...field} className="admin-input" rows={6} value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} />
          )}
        </AdminField>
        <fieldset className="admin-radio-group">
          <legend className="admin-field-label">公告類型</legend>
          <label><input type="radio" name="type" checked={form.type === "temporary"} onChange={() => setForm({ ...form, type: "temporary" })} /> 臨時公告</label>
          <label><input type="radio" name="type" checked={form.type === "permanent"} onChange={() => setForm({ ...form, type: "permanent" })} /> 常駐公告</label>
        </fieldset>
        {form.type === "temporary" && (
          <AdminField id="ann-days" label="顯示天數" hint="超過天數後自動停止顯示" error={errors.active_days}>
            {(field) => (
              <input {...field} className="admin-input admin-input-narrow" type="number" min={1} max={365} value={form.active_days} onChange={(e) => setForm({ ...form, active_days: Number(e.target.value) })} />
            )}
          </AdminField>
        )}
        <label className="admin-checkbox">
          <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /> 啟用
        </label>
      </AdminModal>
      {dialogHost}
    </div>
  );
}
