// 網站專案的圖示：有掃描時抓到的 favicon（SiteProject.favicon，data URL）就顯示它，
// 沒有（尚未掃描、網站沒有圖示）就顯示名稱首字。圖片是裝飾性的，名稱一律另有文字。
export default function SiteFavicon({ project, size = "md", className = "" }) {
  const initial = (project?.name || project?.hostname || "?").trim().charAt(0).toUpperCase();
  return (
    <span className={`site-favicon is-${size} ${className}`} aria-hidden="true">
      {project?.favicon ? <img src={project.favicon} alt="" /> : initial}
    </span>
  );
}

export { SiteFavicon };
