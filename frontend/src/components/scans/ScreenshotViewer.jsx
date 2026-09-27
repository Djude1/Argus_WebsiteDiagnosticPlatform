import { useEffect, useRef, useState } from "react";

import { api } from "../../api";
import { ArgusMark } from "../brand/ArgusMark";
import { CATEGORY_LABELS, SEVERITY_LABEL, isInProgress } from "../../shared/AppShared.jsx";
import { ImageIcon } from "../../shared/LineIcons.jsx";

const ZOOM_STEPS = [0.5, 0.75, 1, 1.5];

/**
 * 截圖檢視器：頁面截圖＋ finding 紅框高亮。
 * 紅框可點（反向跳到對應 finding）；可縮放（符合寬度／50–150%），
 * 選取有座標的 finding 時會把檢視區捲到紅框位置。
 */
function ScreenshotViewer({ scan, targetPage, findings, selectedFinding, onSelectFinding }) {
  const [imageUrl, setImageUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [scale, setScale] = useState(1);
  const [zoom, setZoom] = useState("fit"); // "fit" | number
  const [naturalWidth, setNaturalWidth] = useState(0);
  const imageRef = useRef(null);
  const viewportRef = useRef(null);

  useEffect(() => {
    let objectUrl = "";
    let cancelled = false;
    async function loadScreenshot() {
      // 立即清除舊截圖，避免 revoke 後的失效 URL 讓容器高度歸零，導致 highlight 不可見
      setImageUrl("");
      if (!scan || !targetPage) {
        return;
      }
      setLoading(true);
      try {
        const response = await api.get(`/scans/${scan.id}/pages/${targetPage.id}/screenshot/`, {
          responseType: "blob",
        });
        if (cancelled) return;
        objectUrl = URL.createObjectURL(response.data);
        setImageUrl(objectUrl);
      } catch {
        // 該頁面尚未產生截圖（爬蟲還沒跑到、或被 robots 擋）靜默失敗
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadScreenshot();
    return () => {
      cancelled = true;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
    // scan 只認 id：ScanDetailPage 每 2 秒 polling 會產生全新的 scan 物件參考，
    // 若把整個 scan 物件放進依賴陣列，即使內容沒變也會每次重新清空/重抓截圖，畫面閃爍。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scan?.id, targetPage]);

  // 紅框座標以截圖原始像素計；圖片實際寬度一變（視窗縮放、切換縮放倍率）就重算比例
  useEffect(() => {
    const image = imageRef.current;
    if (!image || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(() => {
      if (image.naturalWidth) setScale(image.clientWidth / image.naturalWidth);
    });
    observer.observe(image);
    return () => observer.disconnect();
  }, [imageUrl]);

  function handleImageLoad() {
    const image = imageRef.current;
    if (image && image.naturalWidth) {
      setNaturalWidth(image.naturalWidth);
      setScale(image.clientWidth / image.naturalWidth);
    }
  }

  // 高光框：有座標且屬於目前頁面的 finding
  const overlayFindings = findings.filter((finding) => finding.bounding_box && finding.page === targetPage?.id);

  // 站台層級或無 bounding_box 的 finding → 在截圖頂部畫 banner（讓使用者知道「有反應，但不是元素級」）
  const showSiteBanner = selectedFinding && !selectedFinding.bounding_box;

  // 確保「按了一定有反應」：沒 bounding_box 時退化為整頁紅色 pulse 外框；
  // 或選的是別頁的 finding（page 對不上 targetPage）也畫整頁外框提示。
  const showWholePageHighlight =
    selectedFinding &&
    (!selectedFinding.bounding_box || (selectedFinding.page && selectedFinding.page !== targetPage?.id));

  // 選到有座標的 finding：把檢視區捲到紅框（只捲檢視區，不帶動整頁）
  const activeBox =
    selectedFinding?.bounding_box && selectedFinding.page === targetPage?.id ? selectedFinding.bounding_box : null;
  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport || !activeBox || !imageUrl) return;
    const top = activeBox.y * scale - viewport.clientHeight / 3;
    const left = activeBox.x * scale - viewport.clientWidth / 3;
    viewport.scrollTo({ top: Math.max(0, top), left: Math.max(0, left), behavior: "smooth" });
  }, [activeBox, scale, imageUrl]);

  const zoomIndex = zoom === "fit" ? -1 : ZOOM_STEPS.indexOf(zoom);
  const fitPercent = Math.round(scale * 100);
  function zoomBy(direction) {
    if (zoom === "fit") {
      // 從「符合寬度」出發，找最接近目前比例的下一檔
      const next =
        direction > 0 ? ZOOM_STEPS.find((z) => z > scale + 0.01) : [...ZOOM_STEPS].reverse().find((z) => z < scale - 0.01);
      if (next) setZoom(next);
      return;
    }
    const next = ZOOM_STEPS[zoomIndex + direction];
    if (next) setZoom(next);
  }

  const inProgress = isInProgress(scan?.status);

  return (
    <div className="shot-viewer">
      <div className="shot-toolbar">
        <p className="shot-caption" title={targetPage?.url || ""}>
          <ImageIcon className="shot-caption-icon" />
          <span>{targetPage ? targetPage.title || targetPage.url : "尚未選擇頁面"}</span>
        </p>
        <div className="shot-tools">
          {imageUrl && (
            <div className="shot-zoom" role="group" aria-label="截圖縮放">
              <button type="button" className="shot-tool" onClick={() => zoomBy(-1)} aria-label="縮小">
                −
              </button>
              <span className="shot-zoom-level ag-num" aria-live="polite">
                {zoom === "fit" ? `${fitPercent}%` : `${Math.round(zoom * 100)}%`}
              </span>
              <button type="button" className="shot-tool" onClick={() => zoomBy(1)} aria-label="放大">
                +
              </button>
              <button
                type="button"
                className={`shot-tool is-text ${zoom === "fit" ? "active" : ""}`}
                onClick={() => setZoom("fit")}
                aria-pressed={zoom === "fit"}
              >
                符合寬度
              </button>
            </div>
          )}
          {targetPage && (
            <a
              className="shot-open-link"
              href={targetPage.final_url || targetPage.url}
              target="_blank"
              rel="noopener noreferrer"
              title="在新分頁開啟原網站（可實際互動，但會脫離 Argus 的紅框跳轉）"
            >
              開啟原網站 ↗
            </a>
          )}
        </div>
      </div>

      <div className="shot-viewport" ref={viewportRef}>
        {!imageUrl &&
          (loading ? (
            <div className="shot-state" aria-busy="true">
              <span className="shot-skeleton" aria-hidden="true" />
              <p className="hint-text">載入截圖中…</p>
            </div>
          ) : inProgress ? (
            <div className="shot-state">
              <ArgusMark size={48} scanning />
              <p className="hint-text">掃描進行中，截圖完成後自動顯示</p>
            </div>
          ) : (
            <div className="shot-state">
              <ImageIcon className="shot-state-icon" />
              <p className="hint-text">
                {targetPage
                  ? "此頁面沒有可用截圖（可能被 robots.txt 阻擋或回 4xx/5xx）。"
                  : "掃描完成並產生截圖後會顯示在此。"}
              </p>
            </div>
          ))}
        {imageUrl && (
          <div className={`shot-stage ${zoom === "fit" ? "is-fit" : ""}`}>
            <img
              alt={`${targetPage?.title || targetPage?.url || "頁面"} 截圖`}
              className="shot-image"
              ref={imageRef}
              src={imageUrl}
              onLoad={handleImageLoad}
              // 縮放倍率是動態計算值
              style={zoom === "fit" || !naturalWidth ? undefined : { width: `${naturalWidth * zoom}px` }}
            />
            {showSiteBanner && (
              <div className="site-banner-overlay">
                <span className={`severity ${selectedFinding.severity}`}>
                  {SEVERITY_LABEL[selectedFinding.severity] || selectedFinding.severity}
                </span>
                <span className={`category-pill cat-${selectedFinding.category}`}>
                  {(CATEGORY_LABELS[selectedFinding.category] || selectedFinding.category).toUpperCase()}
                </span>
                <span className="site-banner-title">{selectedFinding.title}</span>
                <span className="site-banner-note">站台層級問題，無單一元素位置</span>
              </div>
            )}
            {showWholePageHighlight && <div className="whole-page-highlight pointer-events-none" aria-hidden="true" />}
            <div className="pointer-events-none absolute inset-0">
              {overlayFindings.map((finding) => {
                const box = finding.bounding_box;
                const active = selectedFinding?.id === finding.id;
                // 紅框變可點：點下去自動選中對應 finding，達成「截圖 → 建議」反向跳轉。
                // 外層保留 pointer-events-none 不擋截圖右鍵；個別 highlight-box 在 CSS 中設 pointer-events-auto。
                return (
                  <div
                    className={`highlight-box sev-${finding.severity} ${active ? "active" : ""}`}
                    key={finding.id}
                    role="button"
                    tabIndex={0}
                    aria-label={`${SEVERITY_LABEL[finding.severity] || finding.severity}：${finding.title}`}
                    title={`${SEVERITY_LABEL[finding.severity] || finding.severity} / ${(
                      CATEGORY_LABELS[finding.category] || finding.category
                    ).toUpperCase()}：${finding.title}（點擊查看建議）`}
                    onClick={() => onSelectFinding?.(finding)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onSelectFinding?.(finding);
                      }
                    }}
                    style={{
                      left: `${box.x * scale}px`,
                      top: `${box.y * scale}px`,
                      width: `${box.width * scale}px`,
                      height: `${box.height * scale}px`,
                    }}
                  />
                );
              })}
            </div>
          </div>
        )}
      </div>
      {imageUrl && overlayFindings.length > 0 && (
        <p className="shot-legend">
          <span className="shot-legend-box" aria-hidden="true" />
          框線標示此頁 {overlayFindings.length} 個有元素位置的問題，點框線可跳到對應建議
        </p>
      )}
    </div>
  );
}

export default ScreenshotViewer;
