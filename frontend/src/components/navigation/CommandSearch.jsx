import { useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";

import { api } from "../../api";
import { CATEGORY_LABELS, SEVERITY_LABEL } from "../../shared/AppShared.jsx";
import { SearchIcon } from "../../shared/LineIcons";
import { useArgusStore } from "../../store";

// 頂部工具列的搜尋（⌘K／Ctrl+K）：找網站專案、目前網站的分頁，以及目前網站最新一次完成掃描的問題。
// 問題在第一次打開時才向 /api/projects/<id>/issues/ 取一次；選擇問題會到問題分析並以 ?q= 篩出該題。
// 對話框用 portal 掛到 body：導覽列有 backdrop-filter，會讓 position: fixed 被限制在導覽列內。

const SECTIONS = [
  { key: "", label: "總覽" },
  { key: "scans", label: "掃描與報告" },
  { key: "seo", label: "SEO 分析" },
  { key: "security", label: "資安分析" },
  { key: "issues", label: "問題分析" },
  { key: "pages", label: "頁面" },
  { key: "aeo", label: "AEO 問答" },
  { key: "settings", label: "專案設定" },
];
const MAX_PER_GROUP = 6;
const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || "");

export default function CommandSearch() {
  const projects = useArgusStore((s) => s.projects);
  const currentProjectId = useArgusStore((s) => s.currentProjectId);
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [issues, setIssues] = useState({ projectId: null, items: [] });
  const inputRef = useRef(null);
  const listId = useId();

  const current = (projects || []).find((p) => p.id === currentProjectId) || null;

  useEffect(() => {
    function onKey(event) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen(true);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setActive(0);
    inputRef.current?.focus();
    if (current && issues.projectId !== current.id) {
      api
        .get(`/projects/${current.id}/issues/`)
        .then((response) => setIssues({ projectId: current.id, items: response.data.issues || [] }))
        .catch(() => setIssues({ projectId: current.id, items: [] }));
    }
    // 只在打開時抓；issues 本身變動不需要重抓
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, current?.id]);

  const keyword = query.trim().toLowerCase();
  const results = useMemo(() => {
    const match = (text) => !keyword || text.toLowerCase().includes(keyword);
    const rows = [];
    for (const project of (projects || []).filter((p) => match(`${p.name} ${p.origin}`)).slice(0, MAX_PER_GROUP)) {
      rows.push({ group: "網站專案", id: `p-${project.id}`, label: project.name, hint: project.hostname, to: `/projects/${project.id}` });
    }
    if (current) {
      for (const section of SECTIONS.filter((s) => match(s.label))) {
        rows.push({
          group: `前往 ${current.name}`,
          id: `s-${section.key}`,
          label: section.label,
          to: `/projects/${current.id}${section.key ? `/${section.key}` : ""}`,
        });
      }
      if (keyword && issues.projectId === current.id) {
        for (const issue of issues.items.filter((i) => match(`${i.title} ${i.remediation || ""}`)).slice(0, MAX_PER_GROUP)) {
          rows.push({
            group: "問題與建議",
            id: `i-${issue.key}`,
            label: issue.title,
            hint: `${SEVERITY_LABEL[issue.severity] || issue.severity} · ${CATEGORY_LABELS[issue.category] || issue.category}`,
            to: `/projects/${current.id}/issues?q=${encodeURIComponent(issue.title)}`,
          });
        }
      }
    }
    return rows;
  }, [keyword, projects, current, issues]);

  function close() {
    setOpen(false);
  }

  function choose(row) {
    close();
    navigate(row.to);
  }

  function onInputKey(event) {
    if (event.key === "Escape") {
      close();
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((index) => Math.min(index + 1, results.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((index) => Math.max(index - 1, 0));
    } else if (event.key === "Enter" && results[active]) {
      event.preventDefault();
      choose(results[active]);
    }
  }

  let lastGroup = "";
  const dialog = (
    <div className="nav-command-backdrop" role="presentation" onPointerDown={(event) => event.target === event.currentTarget && close()}>
      <div className="nav-command" role="dialog" aria-modal="true" aria-label="搜尋">
        <div className="nav-command-input">
          <SearchIcon />
          <input
            ref={inputRef}
            type="search"
            value={query}
            placeholder="搜尋網站、分頁或問題…"
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={results[active] ? `${listId}-${results[active].id}` : undefined}
            onChange={(event) => {
              setQuery(event.target.value);
              setActive(0);
            }}
            onKeyDown={onInputKey}
          />
          <kbd className="nav-search-kbd">Esc</kbd>
        </div>
        <ul className="nav-command-list" id={listId} role="listbox" aria-label="搜尋結果">
          {results.length === 0 && <li className="nav-command-empty">找不到符合「{query}」的結果。</li>}
          {results.map((row, index) => {
            const heading = row.group !== lastGroup ? row.group : null;
            lastGroup = row.group;
            return (
              <li key={row.id} role="presentation">
                {heading && <p className="nav-command-group">{heading}</p>}
                <button
                  type="button"
                  id={`${listId}-${row.id}`}
                  role="option"
                  aria-selected={index === active}
                  className={`nav-command-item ${index === active ? "is-active" : ""}`}
                  onMouseEnter={() => setActive(index)}
                  onClick={() => choose(row)}
                >
                  <span>{row.label}</span>
                  {row.hint && <small>{row.hint}</small>}
                </button>
              </li>
            );
          })}
        </ul>
        {current && !keyword && <p className="nav-command-tip">輸入關鍵字可搜尋 {current.name} 最新一次掃描的問題與修補建議。</p>}
      </div>
    </div>
  );

  return (
    <>
      <button type="button" className="nav-search" onClick={() => setOpen(true)} aria-label="搜尋專案、問題或建議">
        <SearchIcon />
        <span className="nav-search-text">搜尋專案、問題或建議…</span>
        <kbd className="nav-search-kbd">{isMac ? "⌘" : "Ctrl"} K</kbd>
      </button>
      {open && createPortal(dialog, document.body)}
    </>
  );
}

export { CommandSearch };
