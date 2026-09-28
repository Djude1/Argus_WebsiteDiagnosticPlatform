import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../api";

const POLL_INTERVAL_MS = 3000;

const STATUS_LABEL = {
  idle: "尚未產生",
  generating: "產生中",
  ready: "已完成",
  failed: "產生失敗",
};

// 四類產物的分頁定義：key 對應後端 artifacts 的鍵
const ARTIFACT_TABS = [
  { key: "json_ld", label: "JSON-LD", hint: "全站一份，貼進首頁 <head> 內" },
  { key: "og_meta", label: "OG＋meta", hint: "首頁／代表頁的社群分享與搜尋摘要標籤" },
  { key: "llms_txt", label: "llms.txt", hint: "主機檔案，上傳到網站根目錄" },
  { key: "faq_schema", label: "FAQ Schema", hint: "僅當站上有 FAQ 內容依據時產生" },
];

// 逐欄位來源標註的狀態文案
const FIELD_STATUS_LABEL = {
  verified: "已驗證來源",
  placeholder: "請人工確認",
  rule: "規則產生",
  extracted: "原文摘錄",
  partial: "部分採用",
};

/**
 * 掃描報告頁的「修正產出」專區（ADR-0002）。
 *
 * 只在掃描完成後由 FindingsWorkspace 掛載。以爬取內容為事實基礎產生
 * 四類可直接採用的修正產出：觸發後輪詢狀態，ready 才載入產物；
 * 已完成的產出重看不重算、重複複製不會再計費。
 */
function FixOutputSection({ scan }) {
  const [fixStatus, setFixStatus] = useState("idle");
  const [statusError, setStatusError] = useState("");
  const [artifacts, setArtifacts] = useState(null);
  const [activeTab, setActiveTab] = useState("json_ld");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copiedKey, setCopiedKey] = useState("");
  const cancelledRef = useRef(false);

  const loadArtifacts = useCallback(async () => {
    try {
      const { data } = await api.get(`/scans/${scan.id}/fix-output/artifacts/`);
      if (!cancelledRef.current) setArtifacts(data.artifacts || null);
    } catch {
      // ready 之後拿不到就維持 null，下一次輪詢／操作會再拉
    }
  }, [scan.id]);

  const pollStatus = useCallback(
    (onReady) => {
      const tick = async () => {
        try {
          const { data } = await api.get(`/scans/${scan.id}/fix-output/status/`);
          if (cancelledRef.current) return;
          setFixStatus(data.status || "idle");
          setStatusError(data.error || "");
          if (data.status === "ready") {
            await loadArtifacts();
            if (onReady) onReady();
          } else if (data.status === "generating") {
            setTimeout(tick, POLL_INTERVAL_MS);
          }
        } catch {
          if (!cancelledRef.current) setTimeout(tick, POLL_INTERVAL_MS);
        }
      };
      setTimeout(tick, POLL_INTERVAL_MS);
    },
    [scan.id, loadArtifacts],
  );

  useEffect(() => {
    cancelledRef.current = false;
    let timer = null;

    async function bootstrap() {
      try {
        const { data } = await api.get(`/scans/${scan.id}/fix-output/status/`);
        if (cancelledRef.current) return;
        setFixStatus(data.status || "idle");
        setStatusError(data.error || "");
        if (data.status === "ready") {
          await loadArtifacts();
        } else if (data.status === "generating") {
          timer = pollStatus();
        }
      } catch {
        // 狀態拿不到就維持 idle：使用者按產生時會再碰到錯誤
      }
    }
    bootstrap();

    return () => {
      cancelledRef.current = true;
      if (timer) clearTimeout(timer);
    };
  }, [scan.id, loadArtifacts, pollStatus]);

  async function handleGenerate() {
    setBusy(true);
    setError("");
    try {
      const { data } = await api.post(`/scans/${scan.id}/fix-output/trigger/`);
      if (data?.fix_output) {
        setFixStatus(data.fix_output.status);
        setStatusError(data.fix_output.error || "");
      }
      if (data?.dispatched) {
        setArtifacts(null);
        pollStatus();
      } else if (data?.fix_output?.status === "ready") {
        await loadArtifacts();
      }
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(detail || "無法觸發修正產出。");
    } finally {
      setBusy(false);
    }
  }

  async function handleCopy(key) {
    const artifact = artifacts?.[key];
    if (!artifact) return;
    try {
      await navigator.clipboard.writeText(artifact.content || "");
      setCopiedKey(key);
      setTimeout(() => setCopiedKey(""), 2000);
    } catch {
      setError("複製失敗，請手動選取。");
    }
  }

  async function handleDownload() {
    setError("");
    try {
      const response = await api.get(
        `/scans/${scan.id}/fix-output/artifacts/`,
        { params: { download: "llms_txt" }, responseType: "blob" },
      );
      const url = URL.createObjectURL(response.data);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "llms.txt";
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("下載失敗，請稍後再試。");
    }
  }

  const availableTabs = ARTIFACT_TABS.filter(
    (tab) => !artifacts || tab.key in artifacts,
  );
  const activeArtifact =
    artifacts && (artifacts[activeTab] || artifacts[availableTabs[0]?.key]);

  return (
    <section className="fixoutput-box">
      <div className="fixoutput-header">
        <div>
          <p className="fixoutput-title">🛠️ 修正產出</p>
          <p className="fixoutput-desc">
            以本次掃描爬到的內容為事實基礎，產生可直接貼上的修正內容。
            爬不到的欄位以【請填寫：…】標示，請人工確認後再替換。
          </p>
        </div>
        <span className={`fixoutput-status status-${fixStatus}`}>
          {STATUS_LABEL[fixStatus] || fixStatus}
        </span>
      </div>

      {fixStatus !== "ready" && (
        <button
          className="primary-button fixoutput-action"
          type="button"
          disabled={busy || fixStatus === "generating"}
          onClick={handleGenerate}
        >
          {fixStatus === "generating"
            ? "產生中…"
            : fixStatus === "failed"
              ? "重新產生"
              : busy
                ? "處理中…"
                : "產生修正內容"}
        </button>
      )}

      {fixStatus === "failed" && statusError && (
        <p className="fixoutput-note error">失敗原因：{statusError}。重新產生前不會重複扣點。</p>
      )}

      {error && <p className="fixoutput-note error">{error}</p>}

      {fixStatus === "ready" && artifacts && (
        <>
          <div className="fixoutput-tabs" role="tablist">
            {availableTabs.map((tab) => (
              <button
                key={tab.key}
                type="button"
                role="tab"
                aria-selected={activeTab === tab.key}
                className={`fixoutput-tab ${activeTab === tab.key ? "active" : ""}`}
                onClick={() => setActiveTab(tab.key)}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {activeArtifact && (
            <div className="fixoutput-panel">
              <p className="fixoutput-hint">
                {ARTIFACT_TABS.find((t) => t.key === activeTab)?.hint}
              </p>

              <div className="fixoutput-actions">
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => handleCopy(activeTab)}
                >
                  {copiedKey === activeTab ? "已複製 ✓" : "一鍵複製"}
                </button>
                {activeTab === "llms_txt" && (
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={handleDownload}
                  >
                    下載 llms.txt
                  </button>
                )}
              </div>

              <pre className="fixoutput-code">{activeArtifact.content}</pre>

              <FieldAnnotations fields={activeArtifact.fields} />
            </div>
          )}
        </>
      )}
    </section>
  );
}

/** 逐欄位來源標註：placeholder 欄位以警示色突顯「請人工確認」。 */
function FieldAnnotations({ fields }) {
  const entries = Object.entries(fields || {});
  if (!entries.length) return null;
  return (
    <div className="fixoutput-fields">
      <p className="fixoutput-fields-title">欄位來源標註</p>
      <ul>
        {entries.map(([name, annotation]) => (
          <li key={name} className={`fixoutput-field status-${annotation?.status}`}>
            <span className="fixoutput-field-name">{name}</span>
            <span className="fixoutput-field-status">
              {FIELD_STATUS_LABEL[annotation?.status] || annotation?.status || "—"}
            </span>
            {annotation?.source_url && (
              <a
                className="fixoutput-field-source"
                href={annotation.source_url}
                target="_blank"
                rel="noreferrer"
              >
                來源頁 ↗
              </a>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default FixOutputSection;
