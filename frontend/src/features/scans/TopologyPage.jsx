import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import ReactFlow, { Background, Controls, Handle, MarkerType, MiniMap, Position } from "reactflow";
import "reactflow/dist/style.css";

import { api } from "../../api";
import { ArgusMark } from "../../components/brand/ArgusMark";
import { SEVERITY_LABEL } from "../../shared/AppShared.jsx";
import { DocIcon, FlagIcon, HomeIcon, LockIcon } from "../../shared/LineIcons.jsx";

function shortenUrl(url) {
  try {
    const u = new URL(url);
    const tail = u.pathname + u.search || "/";
    return tail.length > 28 ? `${tail.slice(0, 25)}...` : tail;
  } catch {
    return url.slice(0, 28);
  }
}

function hostnameOf(url) {
  try {
    return new URL(url).hostname;
  } catch {
    return "";
  }
}

// 從首頁出發做 BFS 樹狀 layout。
// root = depth=0 的節點（爬蟲入口），找不到就用 id 最小者。
// children = 從 outgoing_links 第一次抵達的下游節點（避免迴圈）。
// 每個 subtree 預先算 leaf 數，父節點 y = 子節點群中心，得到對稱不重疊的樹。
// 走不到的孤島塞到樹下方獨立區。
function buildTreeLayout(apiNodes, apiEdges) {
  const COL_W = 280;
  const ROW_H = 96;
  if (apiNodes.length === 0) return { positions: {}, rootId: null, orphanIds: [] };

  const sorted = [...apiNodes].sort((a, b) => (a.depth ?? 99) - (b.depth ?? 99) || a.id - b.id);
  const root = sorted[0];

  const adj = {};
  apiNodes.forEach((n) => {
    adj[n.id] = [];
  });
  apiEdges.forEach((e) => {
    if (adj[e.source] && !adj[e.source].includes(e.target)) {
      adj[e.source].push(e.target);
    }
  });

  const parent = { [root.id]: null };
  const visited = new Set([root.id]);
  const queue = [root.id];
  while (queue.length) {
    const cur = queue.shift();
    for (const child of adj[cur] || []) {
      if (!visited.has(child)) {
        visited.add(child);
        parent[child] = cur;
        queue.push(child);
      }
    }
  }

  const children = {};
  apiNodes.forEach((n) => {
    children[n.id] = [];
  });
  Object.keys(parent).forEach((id) => {
    const p = parent[Number(id)];
    if (p != null) children[p].push(Number(id));
  });
  Object.values(children).forEach((arr) => arr.sort((a, b) => a - b));

  const leafCount = {};
  function calcLeaves(id) {
    if (!children[id] || children[id].length === 0) {
      leafCount[id] = 1;
      return 1;
    }
    let s = 0;
    for (const c of children[id]) s += calcLeaves(c);
    leafCount[id] = s;
    return s;
  }
  calcLeaves(root.id);

  const positions = {};
  function assign(id, depth, yStart) {
    const span = leafCount[id] * ROW_H;
    positions[id] = { x: depth * COL_W, y: yStart + span / 2 };
    let curY = yStart;
    for (const c of children[id]) {
      const cSpan = leafCount[c] * ROW_H;
      assign(c, depth + 1, curY);
      curY += cSpan;
    }
  }
  assign(root.id, 0, 0);

  const treeMaxY = Math.max(...Object.values(positions).map((p) => p.y), 0);
  const orphans = apiNodes.filter((n) => !visited.has(n.id));
  const ORPHAN_TOP = treeMaxY + 160;
  const ORPHANS_PER_ROW = 4;
  orphans.forEach((n, i) => {
    positions[n.id] = {
      x: (i % ORPHANS_PER_ROW) * COL_W,
      y: ORPHAN_TOP + Math.floor(i / ORPHANS_PER_ROW) * (ROW_H + 24),
    };
  });

  return { positions, rootId: root.id, orphanIds: orphans.map((n) => n.id) };
}

function TopologyCustomNode({ data }) {
  const toneClass = `tone-${data.tone}`;
  let Icon = DocIcon;
  if (data.isRoot) Icon = HomeIcon;
  else if (data.blocked) Icon = LockIcon;
  else if (data.isOrphan) Icon = FlagIcon;

  let statusText = "無問題";
  if (data.blocked) statusText = "被阻擋";
  else if (data.finding_count > 0) statusText = `${data.finding_count} 個問題`;

  return (
    <div
      className={`topology-card ${toneClass} ${data.isRoot ? "is-root" : ""} ${data.isOrphan ? "is-orphan" : ""} ${
        data.blocked ? "is-blocked" : ""
      }`}
    >
      <Handle type="target" position={Position.Left} className="topology-handle" />
      <div className="topology-card-icon" aria-hidden="true">
        <Icon />
      </div>
      <div className="topology-card-body">
        <div className="topology-card-title" title={data.url}>
          {data.isRoot ? "首頁" : data.shortUrl}
        </div>
        <div className="topology-card-host">{data.hostname}</div>
        <div className="topology-card-meta">
          <span className={`topology-status-dot ${toneClass}`} aria-hidden="true" />
          <span>{statusText}</span>
          {data.max_severity && !data.blocked ? (
            <span className={`severity ${data.max_severity} topology-sev-chip`}>
              {SEVERITY_LABEL[data.max_severity] || data.max_severity}
            </span>
          ) : null}
        </div>
      </div>
      <Handle type="source" position={Position.Right} className="topology-handle" />
    </div>
  );
}

const TOPOLOGY_NODE_TYPES = { topology: TopologyCustomNode };

// 邊與箭頭走品牌 token：ReactFlow 把這兩個值寫進 style，CSS 變數可以生效
const EDGE_STYLE = { stroke: "var(--ag-border-accent)", strokeWidth: 1.6 };
const EDGE_MARKER = { type: MarkerType.ArrowClosed, width: 16, height: 16, color: "var(--ag-border-accent)" };

function TopologyState({ title, text, tone }) {
  return (
    <section className="panel scan-state-card" role={tone === "error" ? "alert" : undefined}>
      <ArgusMark size={48} scanning={tone === "loading"} />
      <p className="scan-state-title">{title}</p>
      {text && <p className="hint-text">{text}</p>}
    </section>
  );
}

function TopologyPage() {
  const { scanId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api
      .get(`/scans/${scanId}/topology/`)
      .then((r) => {
        if (!cancelled) setData(r.data);
      })
      .catch(() => {
        if (!cancelled) setLoadError("無法載入拓樸資料，可能掃描尚未完成或無權限。");
      });
    return () => {
      cancelled = true;
    };
  }, [scanId]);

  const { nodes, edges, stats } = useMemo(() => {
    if (!data) return { nodes: [], edges: [], stats: null };

    const { positions, rootId, orphanIds = [] } = buildTreeLayout(data.nodes, data.edges);
    const orphanSet = new Set(orphanIds);

    const rfNodes = data.nodes.map((n) => {
      const pos = positions[n.id] || { x: 0, y: 0 };
      return {
        id: String(n.id),
        type: "topology",
        position: pos,
        className: `tone-${n.tone}`,
        data: {
          url: n.url,
          hostname: hostnameOf(n.url),
          shortUrl: shortenUrl(n.url),
          tone: n.tone,
          finding_count: n.finding_count,
          max_severity: n.max_severity,
          blocked: n.blocked,
          isRoot: n.id === rootId,
          isOrphan: orphanSet.has(n.id),
        },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
      };
    });

    const rfEdges = data.edges.map((e, i) => ({
      id: `e${i}-${e.source}-${e.target}`,
      source: String(e.source),
      target: String(e.target),
      type: "smoothstep",
      animated: false,
      markerEnd: EDGE_MARKER,
      style: EDGE_STYLE,
    }));

    const summary = {
      total: data.nodes.length,
      with_findings: data.nodes.filter((n) => n.finding_count > 0).length,
      blocked: data.nodes.filter((n) => n.blocked).length,
      orphans: orphanIds.length,
    };

    return { nodes: rfNodes, edges: rfEdges, stats: summary };
  }, [data]);

  function handleNodeClick(_, node) {
    navigate(`/scans/${scanId}?page=${node.id}`);
  }

  if (loadError) return <TopologyState title="拓樸圖無法顯示" text={loadError} tone="error" />;
  if (!data) return <TopologyState title="正在繪製網站拓樸…" tone="loading" />;
  if (data.nodes.length === 0) {
    return <TopologyState title="沒有可顯示的頁面節點" text="本次掃描的爬蟲沒有產生任何頁面。" />;
  }

  return (
    <section className="panel topology-panel" aria-labelledby="topology-title">
      <header className="topology-header">
        <div className="topology-title-row">
          <div>
            <p className="ag-eyebrow">網站拓樸</p>
            <h1 className="section-title" id="topology-title">
              {hostnameOf(data.nodes[0]?.url || "")}
            </h1>
          </div>
          {stats ? (
            <dl className="topology-stats">
              <div>
                <dt>頁面</dt>
                <dd className="ag-num">{stats.total}</dd>
              </div>
              <div className="tone-bad">
                <dt>有問題</dt>
                <dd className="ag-num">{stats.with_findings}</dd>
              </div>
              <div className="tone-medium">
                <dt>被阻擋</dt>
                <dd className="ag-num">{stats.blocked}</dd>
              </div>
              {stats.orphans > 0 ? (
                <div>
                  <dt>孤立頁</dt>
                  <dd className="ag-num">{stats.orphans}</dd>
                </div>
              ) : null}
            </dl>
          ) : null}
        </div>
        <p className="hint-text">
          以首頁為根節點，沿著實際連結往外分支。節點顏色代表該頁問題嚴重度；點任一節點回到報告的該頁。
        </p>
        <ul className="topology-legend" aria-label="圖例">
          <li className="legend-chip tone-good">無問題／輕微</li>
          <li className="legend-chip tone-medium">中度問題</li>
          <li className="legend-chip tone-bad">高／嚴重問題</li>
          <li className="legend-chip is-root">
            <HomeIcon className="legend-icon" />
            首頁（根）
          </li>
          <li className="legend-chip is-orphan">
            <FlagIcon className="legend-icon" />
            孤立頁（虛線）
          </li>
        </ul>
      </header>
      <div className="topology-canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={TOPOLOGY_NODE_TYPES}
          onNodeClick={handleNodeClick}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          nodesDraggable
          nodesConnectable={false}
          minZoom={0.2}
          maxZoom={1.5}
          proOptions={{ hideAttribution: true }}
          defaultEdgeOptions={{ type: "smoothstep" }}
        >
          <Controls showInteractive={false} />
          <MiniMap
            zoomable
            pannable
            nodeClassName={(n) => `topology-mini-node tone-${n.data?.tone || "good"}`}
            nodeStrokeWidth={2}
          />
          <Background gap={24} size={1} />
        </ReactFlow>
      </div>
    </section>
  );
}

export { TopologyPage };
