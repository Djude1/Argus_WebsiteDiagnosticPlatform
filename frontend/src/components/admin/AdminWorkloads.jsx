// Argus 工作負載：argus／argus-zap／argus-kali 三個 namespace 的 pod，依 app 分組。
//
// 看的是「每個元件有幾個 pod、就緒幾個、各在哪個節點、重啟幾次」——
// worker pod 一直 CrashLoopBackOff、三個 web 全擠在同一台 worker 節點，在這張表一眼看得出來。
// 狀態文字優先用 container 的 waiting reason（CrashLoopBackOff 比 phase=Running 有用），
// 由後端 cluster_status._pod_status 決定。

import { formatRelative } from "../../shared/formatters.js";

function podTone(pod) {
  if (pod.phase === "Succeeded") return "ok";
  if (pod.phase === "Failed" || /BackOff|Error|Evicted|OOM/i.test(pod.reason || "")) return "bad";
  if (!pod.ready) return "warn";
  return "ok";
}

export function AdminWorkloads({ cluster }) {
  if (!cluster?.available) return null;
  if (!cluster.workloads.length) {
    return <p className="admin-empty">叢集裡沒有 Argus 的 pod</p>;
  }
  return (
    <div className="admin-table-scroll">
      <table className="admin-table compact admin-workload-table">
        <thead>
          <tr>
            <th>Pod</th>
            <th>節點</th>
            <th>狀態</th>
            <th className="num">重啟</th>
            <th>啟動</th>
          </tr>
        </thead>
        {cluster.workloads.map((workload) => {
          const degraded = workload.total > 0 && workload.ready < workload.total;
          return (
            <tbody key={`${workload.namespace}/${workload.app}`}>
              <tr className={`admin-workload-group ${degraded ? "is-degraded" : ""}`}>
                <td colSpan={5}>
                  <span className="admin-workload-app">{workload.app}</span>
                  <span className="admin-cell-secondary"> {workload.namespace}</span>
                  <span className={`admin-health-state admin-workload-ready ${degraded ? "is-warn" : "is-ok"}`}>
                    就緒 {workload.ready} / {workload.total}
                  </span>
                </td>
              </tr>
              {workload.pods.map((pod) => {
                const tone = podTone(pod);
                return (
                  <tr key={pod.name}>
                    <td className="admin-cell-mono">{pod.name}</td>
                    <td>{pod.node || "—"}</td>
                    <td>
                      <span className={`admin-order-status tone-${tone === "ok" ? "good" : tone}`}>
                        <span className="admin-order-status-dot" aria-hidden="true" />
                        {pod.reason || pod.phase}
                      </span>
                    </td>
                    <td className={`num ${pod.restarts >= 3 ? "tx-neg" : ""}`}>{pod.restarts}</td>
                    <td title={pod.started_at || undefined}>{pod.started_at ? formatRelative(pod.started_at) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          );
        })}
      </table>
    </div>
  );
}
