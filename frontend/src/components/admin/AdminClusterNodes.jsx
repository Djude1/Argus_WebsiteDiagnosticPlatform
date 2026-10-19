// 叢集節點卡：1 master + N worker 各一張。
//
// 每張卡的 CPU／記憶體條有兩種來源，必須標清楚：
//   usage    — metrics-server 的實際用量（有裝才有）
//   requests — 排在這個節點上的 pod 宣告的 requests 佔可分配量的比例（沒 metrics-server 時的退路）
// 兩者意義不同（requests 高不代表真的忙），卡片上一律寫明是哪一種，不混用。
//
// 沿用 .admin-sys-card 的卡片、數字與進度條樣式（原本的單一容器資源卡），
// 節點專屬的角色徽章、壓力籤在 72-admin-health.css。

const ROLE_LABEL = { master: "Master", worker: "Worker" };
const PRESSURE_LABEL = { MemoryPressure: "記憶體壓力", DiskPressure: "磁碟壓力", PIDPressure: "PID 壓力" };

export function formatBytes(bytes) {
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

function toneFor(percent) {
  if (percent === null || percent === undefined) return "idle";
  if (percent >= 90) return "bad";
  if (percent >= 75) return "warn";
  return "ok";
}

function formatCores(value) {
  if (value === null || value === undefined) return "—";
  return Number.isInteger(value) ? `${value}` : value.toFixed(2);
}

/** 一條資源列：有實際用量就顯示用量，否則顯示 requests 佔比並標明。 */
function ResourceBar({ label, usagePercent, requestsPercent, usageText, requestsText, metricsAvailable }) {
  const useUsage = metricsAvailable && usagePercent !== null && usagePercent !== undefined;
  const pct = useUsage ? usagePercent : requestsPercent;
  const tone = toneFor(pct);
  return (
    <div className={`admin-node-resource tone-${tone}`}>
      <div className="admin-node-resource-head">
        <span className="admin-sys-label">{label}</span>
        <span className="admin-sys-scope" title={useUsage ? "metrics-server 量到的實際用量" : "pod 宣告的 requests 佔可分配量的比例"}>
          {useUsage ? "用量" : "requests"}
        </span>
        <span className="admin-node-resource-pct">{pct === null || pct === undefined ? "—" : `${pct}%`}</span>
      </div>
      <div
        className="admin-sys-bar"
        role="progressbar"
        aria-valuenow={pct ?? 0}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${label} ${useUsage ? "用量" : "requests 佔比"}`}
      >
        <span className="admin-sys-bar-fill" style={{ width: `${Math.min(100, pct ?? 0)}%` }} />
      </div>
      <div className="admin-sys-foot">{useUsage ? usageText : requestsText}</div>
    </div>
  );
}

export function AdminClusterNodes({ cluster }) {
  if (!cluster?.available) return null;
  const metricsAvailable = Boolean(cluster.metrics?.available);
  return (
    <div className="admin-node-grid">
      {cluster.nodes.map((node) => {
        const problem = !node.ready || node.pressures.length > 0 || node.unschedulable;
        return (
          <article
            key={node.name}
            className={`admin-sys-card admin-node-card ${!node.ready ? "tone-bad" : problem ? "tone-warn" : ""}`}
            aria-label={`節點 ${node.name}`}
          >
            <div className="admin-node-head">
              <div className="admin-node-title">
                <span className={`admin-node-role is-${node.role}`}>{ROLE_LABEL[node.role] || node.role}</span>
                <strong className="admin-node-name">{node.name}</strong>
              </div>
              {/* 狀態用徽章＋文字，不只靠顏色 */}
              <span className={`admin-health-state admin-node-state ${node.ready ? "is-ok" : "is-bad"}`}>
                {node.ready ? "Ready" : "NotReady"}
              </span>
            </div>
            {(node.pressures.length > 0 || node.unschedulable) && (
              <div className="admin-node-chips">
                {node.unschedulable && <span className="admin-node-chip is-warn">不可排程（cordon）</span>}
                {node.pressures.map((p) => (
                  <span key={p} className="admin-node-chip is-warn">{PRESSURE_LABEL[p] || p}</span>
                ))}
              </div>
            )}
            <ResourceBar
              label="CPU"
              metricsAvailable={metricsAvailable}
              usagePercent={node.cpu.usage_percent}
              requestsPercent={node.cpu.requests_percent}
              usageText={`${formatCores(node.cpu.usage)} / ${formatCores(node.cpu.allocatable)} 核`}
              requestsText={`requests ${formatCores(node.cpu.requests)} / 可分配 ${formatCores(node.cpu.allocatable)} 核`}
            />
            <ResourceBar
              label="記憶體"
              metricsAvailable={metricsAvailable}
              usagePercent={node.memory.usage_percent}
              requestsPercent={node.memory.requests_percent}
              usageText={`${formatBytes(node.memory.usage_bytes)} / ${formatBytes(node.memory.allocatable_bytes)}`}
              requestsText={`requests ${formatBytes(node.memory.requests_bytes)} / 可分配 ${formatBytes(node.memory.allocatable_bytes)}`}
            />
            <dl className="admin-node-facts">
              <div><dt>Pod</dt><dd>{node.pods}{node.pods_capacity ? ` / ${node.pods_capacity}` : ""}</dd></div>
              <div><dt>kubelet</dt><dd>{node.kubelet_version || "—"}</dd></div>
              {node.internal_ip && <div><dt>內部 IP</dt><dd className="admin-mono">{node.internal_ip}</dd></div>}
            </dl>
          </article>
        );
      })}
    </div>
  );
}
