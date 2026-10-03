import { useEffect, useId, useRef, useState } from "react";

import { api } from "../../api";
import { formatDate } from "../../shared/formatters";
import { BellIcon } from "../../shared/LineIcons";

// 頂部工具列的通知：站方公告（/api/admin/announcements/active/）。
// 已讀狀態沿用原本公告 toast 的 localStorage 鍵 ann_dismissed_<id>（只是個人便利設定，讀不到就全部視為未讀）。

function isRead(id) {
  try {
    return Boolean(localStorage.getItem(`ann_dismissed_${id}`));
  } catch {
    return false;
  }
}

function markRead(ids) {
  try {
    ids.forEach((id) => localStorage.setItem(`ann_dismissed_${id}`, "1"));
  } catch {
    // 儲存空間受限時只是下次仍顯示未讀
  }
}

export default function NotificationBell() {
  const [items, setItems] = useState([]);
  const [readIds, setReadIds] = useState(() => new Set());
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const panelId = useId();

  useEffect(() => {
    api
      .get("/admin/announcements/active/")
      .then((response) => {
        const list = response.data.announcements || [];
        setItems(list);
        setReadIds(new Set(list.filter((item) => isRead(item.id)).map((item) => item.id)));
      })
      .catch(() => setItems([]));
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    function onPointer(event) {
      if (wrapRef.current && !wrapRef.current.contains(event.target)) setOpen(false);
    }
    function onKey(event) {
      if (event.key === "Escape") {
        setOpen(false);
        wrapRef.current?.querySelector(".nav-bell")?.focus();
      }
    }
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const unread = items.filter((item) => !readIds.has(item.id)).length;

  function readAll() {
    markRead(items.map((item) => item.id));
    setReadIds(new Set(items.map((item) => item.id)));
  }

  return (
    <div className="nav-bell-wrap" ref={wrapRef}>
      <button
        type="button"
        className="nav-icon-button nav-bell"
        aria-label={unread ? `通知（${unread} 則未讀）` : "通知"}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
      >
        <BellIcon />
        {unread > 0 && <span className="nav-bell-dot" aria-hidden="true" />}
      </button>
      {open && (
        <div className="nav-popover nav-bell-panel" id={panelId} role="dialog" aria-label="通知">
          <div className="nav-popover-head">
            <strong>通知</strong>
            {unread > 0 && (
              <button type="button" className="nav-popover-action" onClick={readAll}>
                全部標為已讀
              </button>
            )}
          </div>
          {items.length === 0 ? (
            <p className="nav-popover-empty">目前沒有公告。</p>
          ) : (
            <ul className="nav-bell-list">
              {items.map((item) => (
                <li key={item.id} className={readIds.has(item.id) ? "" : "is-unread"}>
                  <p className="nav-bell-title">{item.title}</p>
                  <p className="nav-bell-content">{item.content}</p>
                  <p className="nav-bell-date">{formatDate(item.created_at)}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export { NotificationBell };
