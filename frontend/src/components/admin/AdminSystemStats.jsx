import { formatNumber } from "../../shared/formatters.js";

// 系統資源卡片：CPU／記憶體／磁碟／網路／運行時間。
//
// 每張卡片都標示 scope（容器／主機）。這不是裝飾——後端跑在 K8s pod 裡，
// CPU 與記憶體若讀到的是宿主機數字，拿它當 Argus 的資源使用率會嚴重誤導
// （節點 64G、pod 限 1G 時顯示「記憶體 8%」等於沒說）。標示清楚才不會誤判。

function formatBytes(bytes) {
  if (bytes === null || bytes === undefined) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = Number(bytes);
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${value.toFixed(value >= 100 || i === 0 ? 0 : 1)} ${units[i]}`;
}

function formatUptime(seconds) {
  if (seconds === null || seconds === undefined) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d} 天 ${h} 小時`;
  if (h > 0) return `${h} 小時 ${m} 分`;
  return `${m} 分`;
}

function toneFor(percent) {
  if (percent === null || percent === undefined) return "idle";
  if (percent >= 90) return "bad";
  if (percent >= 75) return "warn";
  return "ok";
}

const SCOPE_LABEL = { container: "容器", host: "主機" };

function UsageCard({ label, metric, footer }) {
  if (!metric?.available) {
    return (
      <div className="admin-sys-card">
        <div className="admin-sys-head">
          <span className="admin-sys-label">{label}</span>
        </div>
        <div className="admin-sys-unavailable">
          無法取得{metric?.reason ? `（${metric.reason}）` : ""}
        </div>
      </div>
    );
  }
  const pct = metric.percent;
  const tone = toneFor(pct);
  return (
    <div className={`admin-sys-card tone-${tone}`}>
      <div className="admin-sys-head">
        <span className="admin-sys-label">{label}</span>
        {metric.scope && (
          <span className="admin-sys-scope" title="這組數字的量測範圍">
            {SCOPE_LABEL[metric.scope] || metric.scope}
          </span>
        )}
      </div>
      <div className="admin-sys-value">
        {pct}<span className="admin-sys-unit">%</span>
      </div>
      <div
        className="admin-sys-bar"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${label} 使用率`}
      >
        <span className="admin-sys-bar-fill" style={{ width: `${Math.min(100, pct)}%` }} />
      </div>
      {footer && <div className="admin-sys-foot">{footer}</div>}
    </div>
  );
}

export function AdminSystemStats({ system, netRate }) {
  if (!system) return null;
  const { cpu, memory, disk, network, uptime, hostname } = system;

  return (
    <>
      <div className="admin-sys-grid">
        <UsageCard
          label="CPU"
          metric={cpu}
          footer={
            cpu?.available
              ? [
                  `${cpu.cores} 核`,
                  cpu.quota_cores ? `限額 ${cpu.quota_cores} 核` : null,
                  cpu.load_avg ? `負載 ${cpu.load_avg["1min"]}` : null,
                ].filter(Boolean).join(" · ")
              : null
          }
        />
        <UsageCard
          label="記憶體"
          metric={memory}
          footer={
            memory?.available
              ? `${formatBytes(memory.used_bytes)} / ${formatBytes(memory.total_bytes)}`
              : null
          }
        />
        <UsageCard
          label="磁碟"
          metric={disk}
          footer={
            disk?.available
              ? `${formatBytes(disk.used_bytes)} / ${formatBytes(disk.total_bytes)}（${disk.path}）`
              : null
          }
        />
        <div className="admin-sys-card">
          <div className="admin-sys-head">
            <span className="admin-sys-label">網路</span>
          </div>
          {network?.available ? (
            <>
              {/* 速率由前端用兩次輪詢的差分算出；只輪詢一次時顯示「量測中」 */}
              <div className="admin-sys-value sm">
                {netRate
                  ? `↓ ${formatBytes(netRate.rx)}/s`
                  : <span className="admin-sys-pending">量測中…</span>}
              </div>
              <div className="admin-sys-foot">
                {netRate ? `↑ ${formatBytes(netRate.tx)}/s · ` : ""}
                累計 ↓ {formatBytes(network.rx_bytes)} ↑ {formatBytes(network.tx_bytes)}
              </div>
            </>
          ) : (
            <div className="admin-sys-unavailable">無法取得</div>
          )}
        </div>
      </div>

      <div className="admin-sys-meta">
        <span><strong>主機名稱</strong> {hostname || "—"}</span>
        <span><strong>程序運行</strong> {formatUptime(uptime?.process_seconds)}</span>
        <span><strong>主機開機</strong> {formatUptime(uptime?.host_seconds)}</span>
        {cpu?.load_avg && (
          <span>
            <strong>平均負載</strong>{" "}
            {cpu.load_avg["1min"]} / {cpu.load_avg["5min"]} / {cpu.load_avg["15min"]}
          </span>
        )}
      </div>
      {/* 程序運行時間短於主機開機時間很多時，代表 pod 近期重啟過——值得注意 */}
      {uptime?.process_seconds !== undefined && uptime.process_seconds < 600 && (
        <p className="admin-page-note">
          此 Django 程序啟動未滿 10 分鐘（{formatNumber(uptime.process_seconds)} 秒），
          若非剛部署，可能是 pod 近期重啟過。
        </p>
      )}
    </>
  );
}
