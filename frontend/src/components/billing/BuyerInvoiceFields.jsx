// 購點與訂閱共用的買受人／發票欄位、驗證、送出資料與綠界結帳表單送出。
// 發票由 Argus 依這些資料人工開立（2026-10-04 使用者決策），正式模式的文案要說清楚會開立。

// 綠界結帳只允許這兩個網址（測試／正式），避免後端被竄改時把使用者導到其他網站
const ECPAY_CHECKOUT_URLS = new Set([
  "https://payment-stage.ecpay.com.tw/Cashier/AioCheckOut/V5",
  "https://payment.ecpay.com.tw/Cashier/AioCheckOut/V5",
]);

export const EMPTY_BUYER = {
  buyer_name: "",
  buyer_email: "",
  invoice_type: "personal",
  company_name: "",
  tax_id: "",
  carrier_type: "cloud",
  carrier_id: "",
  agree_terms: false,
};

export function submitEcpayForm(payment) {
  if (!ECPAY_CHECKOUT_URLS.has(payment?.action) || !payment?.fields) {
    throw new Error("綠界付款設定不正確。");
  }
  const form = document.createElement("form");
  form.method = "POST";
  form.action = payment.action;
  for (const [name, value] of Object.entries(payment.fields)) {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = name;
    input.value = String(value);
    form.appendChild(input);
  }
  document.body.appendChild(form);
  form.submit();
}

// 與後端 PurchaseRequestSerializer 相同的檢查（後端才是防線，這裡提早提示）
export function validateBuyer(buyer, { live }) {
  const errs = {};
  if (!buyer.buyer_name.trim()) errs.buyer_name = "請填寫姓名";
  if (!buyer.buyer_email.trim()) errs.buyer_email = "請填寫 email";
  else if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(buyer.buyer_email)) {
    errs.buyer_email = "email 格式不正確";
  }
  if (buyer.invoice_type === "company") {
    if (!buyer.company_name.trim()) errs.company_name = "公司購買須填寫公司抬頭";
    if (!/^\d{8}$/.test(buyer.tax_id)) errs.tax_id = "統一編號需為 8 碼數字";
  } else if (buyer.carrier_type === "mobile_barcode") {
    if (!/^\/[0-9A-Z+\-.]{7}$/.test(buyer.carrier_id.trim().toUpperCase())) {
      errs.carrier_id = "手機條碼格式錯誤（首碼 / + 7 碼英數，例 /AB12CDE）";
    }
  } else if (buyer.carrier_type === "citizen_digital") {
    if (!/^[A-Z]{2}\d{14}$/.test(buyer.carrier_id.trim().toUpperCase())) {
      errs.carrier_id = "自然人憑證格式錯誤（2 碼英文 + 14 碼數字）";
    }
  }
  if (!buyer.agree_terms) errs.agree_terms = live ? "請確認資料並同意服務條款" : "請確認測試購買說明";
  return errs;
}

export function buyerPayload(buyer) {
  const company = buyer.invoice_type === "company";
  return {
    buyer_name: buyer.buyer_name.trim(),
    buyer_email: buyer.buyer_email.trim(),
    invoice_type: buyer.invoice_type,
    company_name: company ? buyer.company_name.trim() : "",
    tax_id: company ? buyer.tax_id.trim() : "",
    carrier_type: company ? "cloud" : buyer.carrier_type,
    carrier_id: company || buyer.carrier_type === "cloud" ? "" : buyer.carrier_id.trim().toUpperCase(),
    agree_terms: buyer.agree_terms,
  };
}

// 聯絡資料＋發票偏好兩個 fieldset（購點步驟 2 與訂閱表單共用）
export function BuyerInvoiceFields({ buyer, setBuyer, errors, live }) {
  return (
    <>
      <fieldset className="billing-form-section">
        <legend className="billing-form-legend">
          <span className="billing-form-index">1</span>
          <span>聯絡資料</span>
        </legend>
        <p className="billing-form-description">{live ? "用於辨識訂單、寄送付款通知與電子發票。" : "用於辨識訂單並寄送測試購買收據。"}</p>
        <div className="billing-field-grid">
          <div className="wizard-field">
            <label htmlFor="buyer_name">姓名 <span>必填</span></label>
            <input
              id="buyer_name"
              className={`input ${errors.buyer_name ? "is-error" : ""}`}
              autoComplete="name"
              placeholder="例如：王小明"
              value={buyer.buyer_name}
              aria-invalid={Boolean(errors.buyer_name)}
              aria-describedby={errors.buyer_name ? "buyer_name_error" : undefined}
              onChange={(e) => setBuyer({ ...buyer, buyer_name: e.target.value })}
            />
            {errors.buyer_name && <p id="buyer_name_error" className="wizard-field-error" role="alert">{errors.buyer_name}</p>}
          </div>

          <div className="wizard-field">
            <label htmlFor="buyer_email">收據通知信箱 <span>必填</span></label>
            <input
              id="buyer_email"
              className={`input ${errors.buyer_email ? "is-error" : ""}`}
              type="email"
              autoComplete="email"
              inputMode="email"
              placeholder="you@example.com"
              value={buyer.buyer_email}
              aria-invalid={Boolean(errors.buyer_email)}
              aria-describedby={errors.buyer_email ? "buyer_email_error" : "buyer_email_hint"}
              onChange={(e) => setBuyer({ ...buyer, buyer_email: e.target.value })}
            />
            <p id="buyer_email_hint" className="wizard-field-hint">{live ? "付款結果與電子發票會寄到這個信箱。" : "付款結果與測試收據會寄到這個信箱。"}</p>
            {errors.buyer_email && <p id="buyer_email_error" className="wizard-field-error" role="alert">{errors.buyer_email}</p>}
          </div>
        </div>
      </fieldset>

      <fieldset className="billing-form-section">
        <legend className="billing-form-legend">
          <span className="billing-form-index">2</span>
          <span>收據與發票偏好</span>
        </legend>
        <p className="billing-form-description">
          {live ? "電子發票依這裡的資料開立，付款完成後寄到通知信箱（公司發票請填統編）。" : "此欄位只記錄測試訂單偏好；Stage 環境不會開立正式電子發票。"}
        </p>

        <div className="billing-choice-grid" role="group" aria-label="購買身分">
          <label className="billing-choice-card">
            <input
              type="radio"
              name="invoice_type"
              checked={buyer.invoice_type === "personal"}
              onChange={() => setBuyer({ ...buyer, invoice_type: "personal", carrier_type: "cloud", carrier_id: "" })}
            />
            <span className="billing-choice-copy">
              <strong>個人購買</strong>
              <small>可選擇是否記錄載具</small>
            </span>
          </label>
          <label className="billing-choice-card">
            <input
              type="radio"
              name="invoice_type"
              checked={buyer.invoice_type === "company"}
              onChange={() => setBuyer({ ...buyer, invoice_type: "company", carrier_type: "cloud", carrier_id: "" })}
            />
            <span className="billing-choice-copy">
              <strong>公司購買</strong>
              <small>需填寫公司抬頭與統編</small>
            </span>
          </label>
        </div>

        {buyer.invoice_type === "personal" && (
          <div className="billing-form-subsection" role="group" aria-labelledby="carrier_preference_label">
            <div className="billing-subsection-heading" id="carrier_preference_label">載具偏好</div>
            <div className="billing-carrier-grid">
              <label className="billing-choice-card is-compact">
                <input
                  type="radio"
                  name="carrier_type"
                  checked={buyer.carrier_type === "cloud"}
                  onChange={() => setBuyer({ ...buyer, carrier_type: "cloud", carrier_id: "" })}
                />
                <span className="billing-choice-copy">
                  <strong>不使用載具</strong>
                  <small>{live ? "電子發票寄送至通知信箱" : "收據寄送至通知信箱"}</small>
                </span>
              </label>
              <label className="billing-choice-card is-compact">
                <input
                  type="radio"
                  name="carrier_type"
                  checked={buyer.carrier_type === "mobile_barcode"}
                  onChange={() => setBuyer({ ...buyer, carrier_type: "mobile_barcode", carrier_id: "" })}
                />
                <span className="billing-choice-copy">
                  <strong>手機條碼</strong>
                  <small>／開頭加 7 碼英數</small>
                </span>
              </label>
              <label className="billing-choice-card is-compact">
                <input
                  type="radio"
                  name="carrier_type"
                  checked={buyer.carrier_type === "citizen_digital"}
                  onChange={() => setBuyer({ ...buyer, carrier_type: "citizen_digital", carrier_id: "" })}
                />
                <span className="billing-choice-copy">
                  <strong>自然人憑證</strong>
                  <small>2 碼英文加 14 碼數字</small>
                </span>
              </label>
            </div>
            {buyer.carrier_type !== "cloud" && (
              <div className="wizard-field billing-conditional-field">
                <label htmlFor="carrier_id">
                  {buyer.carrier_type === "mobile_barcode" ? "手機條碼" : "自然人憑證條碼"} <span>必填</span>
                </label>
                <input
                  id="carrier_id"
                  className={`input ${errors.carrier_id ? "is-error" : ""}`}
                  type="text"
                  autoCapitalize="characters"
                  spellCheck={false}
                  placeholder={buyer.carrier_type === "mobile_barcode" ? "/AB12CDE" : "AB12345678901234"}
                  value={buyer.carrier_id}
                  aria-invalid={Boolean(errors.carrier_id)}
                  aria-describedby={errors.carrier_id ? "carrier_id_error" : undefined}
                  onChange={(e) => setBuyer({ ...buyer, carrier_id: e.target.value.toUpperCase() })}
                />
                {errors.carrier_id && <p id="carrier_id_error" className="wizard-field-error" role="alert">{errors.carrier_id}</p>}
              </div>
            )}
          </div>
        )}

        {buyer.invoice_type === "company" && (
          <div className="billing-form-subsection billing-company-section">
            <div className="billing-field-grid">
              <div className="wizard-field">
                <label htmlFor="company_name">公司抬頭 <span>必填</span></label>
                <input
                  id="company_name"
                  className={`input ${errors.company_name ? "is-error" : ""}`}
                  type="text"
                  autoComplete="organization"
                  placeholder="例如：Argus 科技股份有限公司"
                  value={buyer.company_name || ""}
                  aria-invalid={Boolean(errors.company_name)}
                  aria-describedby={errors.company_name ? "company_name_error" : undefined}
                  onChange={(e) => setBuyer({ ...buyer, company_name: e.target.value })}
                />
                {errors.company_name && <p id="company_name_error" className="wizard-field-error" role="alert">{errors.company_name}</p>}
              </div>
              <div className="wizard-field">
                <label htmlFor="tax_id">統一編號 <span>必填・8 碼</span></label>
                <input
                  id="tax_id"
                  className={`input ${errors.tax_id ? "is-error" : ""}`}
                  type="text"
                  inputMode="numeric"
                  autoComplete="off"
                  placeholder="12345678"
                  value={buyer.tax_id || ""}
                  aria-invalid={Boolean(errors.tax_id)}
                  aria-describedby={errors.tax_id ? "tax_id_error" : undefined}
                  onChange={(e) => setBuyer({ ...buyer, tax_id: e.target.value.replace(/\D/g, "") })}
                  maxLength={8}
                />
                {errors.tax_id && <p id="tax_id_error" className="wizard-field-error" role="alert">{errors.tax_id}</p>}
              </div>
            </div>
          </div>
        )}
      </fieldset>

    </>
  );
}
