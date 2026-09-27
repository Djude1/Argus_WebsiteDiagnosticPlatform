import { useEffect, useMemo, useRef, useState } from "react";

import { CATEGORY_LABELS, SEVERITY_LABEL, isInProgress } from "../../shared/AppShared.jsx";
import { ChevronIcon } from "../../shared/LineIcons.jsx";

const SEVERITY_RANK = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };

// 同分類、同標題的 finding 合併為一群組，例如 11 個「頁面未使用 HTTPS」併成一筆，
// 展開後列出每個頁面。
function buildFindingGroups(findings) {
  const groupMap = new Map();
  for (const finding of findings) {
    const key = `${finding.category}::${finding.title}`;
    let group = groupMap.get(key);
    if (!group) {
      group = {
        key,
        category: finding.category,
        title: finding.title,
        severity: finding.severity,
        items: [],
      };
      groupMap.set(key, group);
    }
    group.items.push(finding);
    // 群組嚴重度取群內最高
    if (SEVERITY_RANK[finding.severity] < SEVERITY_RANK[group.severity]) {
      group.severity = finding.severity;
    }
  }
  return Array.from(groupMap.values()).sort((a, b) => {
    const sev = SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity];
    if (sev !== 0) return sev;
    if (a.category !== b.category) return a.category.localeCompare(b.category);
    return b.items.length - a.items.length;
  });
}

function categoryTag(category) {
  return (CATEGORY_LABELS[category] || category || "").toUpperCase();
}

function FindingsGroupList({ findings, pages, scanStatus, totalFindings, selectedFinding, onSelectFinding }) {
  const groups = useMemo(() => buildFindingGroups(findings), [findings]);
  const pageMap = useMemo(() => {
    const map = new Map();
    for (const page of pages) {
      map.set(page.id, page);
    }
    return map;
  }, [pages]);

  // 自動展開包含目前 selectedFinding 的群組，並把該群組捲到清單可視範圍
  const [expanded, setExpanded] = useState(() => new Set());
  const groupRefs = useRef({});
  const listRef = useRef(null);
  useEffect(() => {
    if (!selectedFinding) return;
    const key = `${selectedFinding.category}::${selectedFinding.title}`;
    setExpanded((prev) => {
      if (prev.has(key)) return prev;
      const next = new Set(prev);
      next.add(key);
      return next;
    });
    // 反向跳轉用：截圖紅框被點時，只捲動清單本身，不帶動整頁
    const el = groupRefs.current[key];
    const list = listRef.current;
    if (el && list) {
      const top = el.offsetTop; // .findings-list 是 position: relative
      if (top < list.scrollTop || top > list.scrollTop + list.clientHeight - 48) {
        list.scrollTo({ top: Math.max(0, top - 8), behavior: "smooth" });
      }
    }
  }, [selectedFinding]);

  function toggle(key) {
    const wasExpanded = expanded.has(key);
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
    // 從關閉變展開時，同步選中該群組第一個 finding，
    // 讓使用者點一次群組標題就能同時看到紅色高光框與詳細內容，不必再點子項。
    if (!wasExpanded) {
      const group = groups.find((g) => g.key === key);
      if (group && group.items.length > 0) {
        onSelectFinding(group.items[0]);
      }
    }
  }

  if (!groups.length) {
    return (
      <div className="findings-empty">
        <p className="findings-empty-title">
          {totalFindings
            ? "沒有符合篩選條件的項目"
            : isInProgress(scanStatus)
              ? "尚未發現任何項目"
              : "這次掃描沒有發現問題"}
        </p>
        <p className="hint-text">
          {totalFindings
            ? "調整上方的頁面、嚴重度或分類篩選看看。"
            : isInProgress(scanStatus)
              ? "掃描進行中，發現的問題會即時出現在這裡。"
              : "目前涵蓋的規則都通過了。"}
        </p>
      </div>
    );
  }

  return (
    <div className="findings-list" ref={listRef}>
      {groups.map((group) => {
        const isExpanded = expanded.has(group.key);
        const containsSelected =
          selectedFinding &&
          selectedFinding.category === group.category &&
          selectedFinding.title === group.title;
        return (
          <div
            key={group.key}
            ref={(el) => {
              if (el) groupRefs.current[group.key] = el;
            }}
            className={`finding-group sev-${group.severity} ${containsSelected ? "active" : ""} ${
              isExpanded ? "is-expanded" : ""
            }`}
          >
            <button
              className="finding-group-header"
              type="button"
              onClick={() => toggle(group.key)}
              aria-expanded={isExpanded}
            >
              <span className={`severity ${group.severity}`}>
                {SEVERITY_LABEL[group.severity] || group.severity}
              </span>
              <span className="finding-group-title">{group.title}</span>
              <span className={`category-pill cat-${group.category}`}>{categoryTag(group.category)}</span>
              <span className="finding-group-count ag-num" title={`${group.items.length} 處`}>
                {group.items.length}
              </span>
              <ChevronIcon className="finding-group-chevron" />
            </button>
            {isExpanded && (
              <ul className="finding-group-items">
                {group.items.map((finding) => {
                  const page = finding.page ? pageMap.get(finding.page) : null;
                  const label = page?.url || page?.final_url || "（站台層級）";
                  const isSelected = selectedFinding?.id === finding.id;
                  return (
                    <li key={finding.id}>
                      <button
                        className={`finding-item ${isSelected ? "active" : ""}`}
                        type="button"
                        onClick={() => onSelectFinding(finding)}
                        title={label}
                        aria-current={isSelected ? "true" : undefined}
                      >
                        <span className="finding-item-url">{label}</span>
                        {finding.evidence && <span className="finding-item-evidence">{finding.evidence}</span>}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default FindingsGroupList;
