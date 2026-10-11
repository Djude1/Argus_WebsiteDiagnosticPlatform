// 把 axios 的檔案回應存成下載：檔名以後端 Content-Disposition 為準（例如報告用報告編號
// argus-report-20261011-E03E.pdf，不露出內部掃描編號），取不到時才用 fallback。

/** 從 Content-Disposition 取出檔名（支援 filename*=UTF-8'' 與 filename="..."）。 */
export function filenameFromDisposition(header, fallback) {
  if (!header) return fallback;
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1].replace(/"/g, ""));
    } catch {
      // 編碼壞掉時改用一般的 filename
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain ? plain[1] : fallback;
}

export function saveBlobResponse(response, fallback) {
  const name = filenameFromDisposition(response.headers?.["content-disposition"], fallback);
  const url = URL.createObjectURL(response.data);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
}
