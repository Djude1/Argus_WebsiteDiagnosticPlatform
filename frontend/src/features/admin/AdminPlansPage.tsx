import { useCallback, useEffect, useState } from "react";

import { createPlan, deletePlan, fetchAdminPlans, updatePlan } from "../../api";
import { AdminField, AdminModal } from "../../components/admin/AdminModal";
import { AdminErrorState, AdminSkeleton } from "../../components/admin/AdminStates";
import { useConfirmDialogs } from "../../shared/AppShared.jsx";
import type { PricingPlan, PricingPlanInput } from "../../shared/apiContracts";
import { formatNtd, formatNumber } from "../../shared/formatters.js";
import { errorDetail, fieldErrors } from "./adminHelpers";
import { COST_PER_PAGE_NTD, planEconomics } from "./planEconomics";

// 後台購點方案管理。從 AdminPages.jsx 拆出並轉成 TypeScript，同時修正：
//   · 毛利試算高估成本 10 倍（見 planEconomics.ts）——每頁 coin 數改用後端提供的值
//   · 新增方案從未成功過：後端 code 必填，表單卻沒有這個欄位，送出一律 400；
//     而 handleSave 沒有錯誤處理，按「儲存」毫無反應。現在補上 code 欄位與錯誤回饋
//   · 載入失敗原本被吞掉並顯示「尚無方案」，改為錯誤＋重試；刪除失敗改為提示
//
// code 只在新增時可填：購點以 plan_code 送出、購點頁也以 code 判斷「推薦」方案，
// 事後改 code 會讓這些對不上，因此編輯時只顯示、不送出。

type Form = Required<Omit<PricingPlanInput, "sort_order">> & { sort_order: number };

const EMPTY_FORM: Form = {
  code: "", name: "", price_ntd: 0, coin_amount: 100, description: "", badge: "",
  is_active: true, sort_order: 0,
};

export function AdminPlansPage() {
  const [plans, setPlans] = useState<PricingPlan[]>([]);
  const [coinPerPage, setCoinPerPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editing, setEditing] = useState<PricingPlan | "new" | null>(null);
  const [form, setForm] = useState<Form>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const { confirmDialog, notifyDialog, dialogHost } = useConfirmDialogs();

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await fetchAdminPlans();
      setPlans(data.items);
      setCoinPerPage(data.coin_per_page);
    } catch (err) {
      setLoadError(errorDetail(err, "無法載入方案"));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  function openEditor(target: PricingPlan | "new") {
    setForm(target === "new" ? EMPTY_FORM : {
      code: target.code,
      name: target.name,
      price_ntd: target.price_ntd,
      coin_amount: target.coin_amount,
      description: target.description,
      badge: target.badge,
      is_active: target.is_active,
      sort_order: target.sort_order,
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
      if (editing === "new") {
        await createPlan(form);
      } else {
        const { code: _code, ...patch } = form; // code 建立後不可改
        await updatePlan(editing.id, patch);
      }
      setEditing(null);
      load();
    } catch (err) {
      const byField = fieldErrors(err);
      setErrors(byField);
      if (Object.keys(byField).length === 0) setSaveError(errorDetail(err, "儲存失敗，請稍後再試。"));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: number) {
    if (!(await confirmDialog("確定刪除此方案？", { danger: true }))) return;
    try {
      await deletePlan(id);
      load();
    } catch (err) {
      notifyDialog(errorDetail(err, "刪除失敗，請稍後再試。"));
    }
  }

  const coinPerNtd = (plan: PricingPlan) => plan.price_ntd > 0 ? (plan.coin_amount / plan.price_ntd).toFixed(2) : "—";
  const preview = planEconomics(form, coinPerPage);

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <h1 className="admin-page-title">方案管理</h1>
        <button className="admin-btn primary" onClick={() => openEditor("new")}>＋ 新增方案</button>
      </header>

      <p className="admin-page-note">
        定價建議：每掃描一頁內部成本約 NT$ {COST_PER_PAGE_NTD}（含 MiniMax token 與伺服器攤提）
        {coinPerPage > 0 && <>，五維全選每頁扣 {coinPerPage} coin（以此估算頁數與成本）</>}；
        毛利率 80% 以上算健康，低於 50% 請重新定價。
      </p>

      {loadError && <AdminErrorState message="無法載入方案" detail={loadError} onRetry={load} />}
      {!loadError && loading && <AdminSkeleton variant="card" rows={4} label="載入方案中" />}
      {!loadError && !loading && (
        <div className="admin-plans-grid">
          {plans.map((plan) => {
            const econ = planEconomics(plan, coinPerPage);
            return (
              <div key={plan.id} className={`admin-plan-card ${plan.is_active ? "" : "is-inactive"}`}>
                {plan.badge && <span className="admin-plan-badge">{plan.badge}</span>}
                <h3 className="admin-plan-name">{plan.name}</h3>
                <p className="admin-plan-price">NT$ {plan.price_ntd.toLocaleString()}</p>
                <p className="admin-plan-coin">{plan.coin_amount.toLocaleString()} Coin</p>
                <p className="admin-plan-rate">{coinPerNtd(plan)} coin/NT$ · ≈ {econ.pagesEstimate.toLocaleString()} 頁掃描</p>

                <dl className="admin-plan-econ">
                  <dt>內部成本</dt>
                  <dd>NT$ {econ.cost.toLocaleString()}</dd>
                  <dt>毛利</dt>
                  <dd className={`tone-${econ.tone}`}>
                    NT$ {econ.margin.toLocaleString()}（{econ.marginPct}%）
                  </dd>
                </dl>

                {plan.description && <p className="admin-plan-desc">{plan.description}</p>}
                <div className="admin-plan-actions">
                  <button onClick={() => openEditor(plan)}>編輯</button>
                  <button className="danger" onClick={() => handleDelete(plan.id)}>刪除</button>
                  <span className={plan.is_active ? "status-active" : "status-inactive"}>
                    {plan.is_active ? "啟用" : "停用"}
                  </span>
                </div>
              </div>
            );
          })}
          {!plans.length && <div className="admin-empty">尚無方案</div>}
        </div>
      )}

      <AdminModal
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "新增方案" : "編輯方案"}
        size="sm"
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
        <AdminField
          id="plan-code"
          label="方案代碼"
          required={editing === "new"}
          hint={editing === "new" ? "英數與連字號，建立後不可修改（購點以此識別方案）" : "建立後不可修改"}
          error={errors.code}
        >
          {(field) => (
            <input
              {...field}
              className="admin-input admin-cell-mono"
              value={form.code}
              readOnly={editing !== "new"}
              onChange={(e) => setForm({ ...form, code: e.target.value })}
            />
          )}
        </AdminField>
        <AdminField id="plan-name" label="方案名稱" required error={errors.name}>
          {(field) => (
            <input {...field} className="admin-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          )}
        </AdminField>
        <div className="admin-field-row">
          <AdminField id="plan-price" label="價格 NT$" required error={errors.price_ntd}>
            {(field) => (
              <input {...field} className="admin-input" type="number" min={0} value={form.price_ntd} onChange={(e) => setForm({ ...form, price_ntd: Number(e.target.value) })} />
            )}
          </AdminField>
          <AdminField id="plan-coin" label="Coin 數" required error={errors.coin_amount}>
            {(field) => (
              <input {...field} className="admin-input" type="number" min={0} value={form.coin_amount} onChange={(e) => setForm({ ...form, coin_amount: Number(e.target.value) })} />
            )}
          </AdminField>
        </div>
        <AdminField id="plan-badge" label="徽章" hint="選填，顯示在方案卡片右上角" error={errors.badge}>
          {(field) => (
            <input {...field} className="admin-input" value={form.badge} onChange={(e) => setForm({ ...form, badge: e.target.value })} />
          )}
        </AdminField>
        <AdminField id="plan-desc" label="描述" error={errors.description}>
          {(field) => (
            <textarea {...field} className="admin-input" rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          )}
        </AdminField>
        <div className={`admin-plan-econ-preview tone-${preview.tone}`}>
          內部成本 {formatNtd(preview.cost)} · 毛利 {formatNtd(preview.margin)}（{preview.marginPct}%，{preview.toneLabel}） · ≈ {formatNumber(preview.pagesEstimate)} 頁
        </div>
        <label className="admin-checkbox">
          <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /> 啟用
        </label>
      </AdminModal>
      {dialogHost}
    </div>
  );
}
