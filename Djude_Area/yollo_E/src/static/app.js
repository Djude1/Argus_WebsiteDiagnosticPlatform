/**
 * YOLO 即時物件辨識 - 前端應用程式
 *
 * 功能:
 * - 瀏覽器攝影機存取
 * - WebSocket 視頻串流傳輸
 * - 檢測結果即時顯示
 * - 檢測框繪製
 */

class YOLOWebApp {
    constructor() {
        // DOM 元素
        this.localVideo = document.getElementById('localVideo');
        this.overlayCanvas = document.getElementById('overlayCanvas');
        this.ctx = this.overlayCanvas.getContext('2d');

        // 除錯面板
        this.debugContent = document.getElementById('debugContent');
        this.clearDebugBtn = document.getElementById('clearDebugBtn');
        if (this.clearDebugBtn) {
            this.clearDebugBtn.addEventListener('click', () => this.clearDebug());
        }

        this.startBtn = document.getElementById('startBtn');
        this.stopBtn = document.getElementById('stopBtn');
        this.captureBtn = document.getElementById('captureBtn');
        this.settingsBtn = document.getElementById('settingsBtn');
        this.settingsPanel = document.getElementById('settingsPanel');
        this.closeSettings = document.getElementById('closeSettings');

        this.fpsDisplay = document.getElementById('fpsDisplay');
        this.objectCount = document.getElementById('objectCount');
        this.resultsContainer = document.getElementById('resultsContainer');
        this.noCameraMessage = document.getElementById('noCameraMessage');

        this.totalFrames = document.getElementById('totalFrames');
        this.avgFps = document.getElementById('avgFps');
        this.totalDetections = document.getElementById('totalDetections');
        this.connectionStatus = document.getElementById('connectionStatus');

        this.serverUrlInput = document.getElementById('serverUrl');
        this.resolutionSelect = document.getElementById('resolution');
        this.frameRateSelect = document.getElementById('frameRate');

        // 狀態
        this.isRunning = false;
        this.videoSocket = null;
        this.resultSocket = null;
        this.mediaStream = null;
        this.frameInterval = null;
        this.useHttpMode = false; // HTTP 後援模式
        this.httpApiUrl = ''; // HTTP API URL

        // 統計
        this.stats = {
            framesSent: 0,
            totalDetections: 0,
            fpsHistory: [],
            startTime: null
        };

        // 當前檢測結果
        this.currentDetections = [];

        // 畫布尺寸
        this.canvasWidth = 1280;
        this.canvasHeight = 720;

        // 初始化
        this.init();
    }

    init() {
        // 綁定事件
        this.startBtn.addEventListener('click', () => this.start());
        this.stopBtn.addEventListener('click', () => this.stop());
        this.captureBtn.addEventListener('click', () => this.capture());

        this.settingsBtn.addEventListener('click', () => {
            this.settingsPanel.classList.add('open');
        });

        this.closeSettings.addEventListener('click', () => {
            this.settingsPanel.classList.remove('open');
        });

        // 設定預設伺服器地址
        // 優先使用 localhost，因為 Dev Tunnel 可能不支援 WebSocket/HTTP 請求轉發
        const isDevTunnel = window.location.hostname.includes('devtunnels.ms') ||
                            window.location.hostname.includes('portmap.io') ||
                            window.location.hostname.includes('localtunnel');
        const isNonLocal = window.location.hostname !== 'localhost' &&
                           window.location.hostname !== '127.0.0.1' &&
                           !window.location.hostname.startsWith('192.168.') &&
                           !window.location.hostname.startsWith('10.') &&
                           !window.location.hostname.startsWith('172.16.');

        // 檢測環境並選擇適當的伺服器地址
        if (isDevTunnel || (window.location.protocol === 'https:' && isNonLocal)) {
            // Dev Tunnel 或公網 HTTPS：使用 localhost (假設用戶在本地運行伺服器)
            this.serverUrlInput.value = 'ws://localhost:8080';
            this.debugLog('檢測到 Dev Tunnel 或公網連線', 'warning');
            this.debugLog('已自動切換到 localhost:8080', 'info');
            this.debugLog('請確保本地伺服器正在運行', 'warning');
            this.showNotification('已切換到本地伺服器 (localhost:8080)', 'warning');
        } else {
            // 本地或內網環境：使用當前主機
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const defaultHost = window.location.hostname || 'localhost';
            const defaultPort = window.location.port || '8080';
            this.serverUrlInput.value = `${protocol}//${defaultHost}:${defaultPort}`;
        }

        // 視頻載入後設定畫布尺寸
        this.localVideo.addEventListener('loadedmetadata', () => {
            this.canvasWidth = this.localVideo.videoWidth;
            this.canvasHeight = this.localVideo.videoHeight;
            this.overlayCanvas.width = this.canvasWidth;
            this.overlayCanvas.height = this.canvasHeight;
        });

        // 頁面關閉時清理
        window.addEventListener('beforeunload', () => {
            this.stop();
        });

        // 記錄初始設定
        this.debugLog(`頁面已載入`);
        this.debugLog(`WebSocket URL: ${this.serverUrlInput.value}`);
        this.debugLog(`User Agent: ${navigator.userAgent.substring(0, 50)}...`);
        this.debugLog(`HTTPS: ${window.location.protocol === 'https:'}`);

        this.showNotification('準備就緒，點擊「開始偵測」啟動', 'success');
    }

    async start() {
        if (this.isRunning) return;

        try {
            // 取得解析度設定
            const [width, height] = this.resolutionSelect.value.split('x').map(Number);
            const frameRate = parseInt(this.frameRateSelect.value);

            this.debugLog(`啟動參數: ${width}x${height} @ ${frameRate}fps`);

            // 請求攝影機權限
            this.debugLog('正在請求攝影機權限...');
            this.showNotification('正在請求攝影機權限...', 'warning');

            this.mediaStream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: { ideal: width },
                    height: { ideal: height },
                    facingMode: 'environment' // 優先使用後鏡頭
                },
                audio: false
            });

            this.localVideo.srcObject = this.mediaStream;
            this.noCameraMessage.classList.add('hidden');

            // 等待視頻準備好
            await new Promise(resolve => {
                this.localVideo.onloadedmetadata = () => {
                    this.localVideo.play();
                    resolve();
                };
            });

            // 設定畫布尺寸
            this.canvasWidth = this.localVideo.videoWidth;
            this.canvasHeight = this.localVideo.videoHeight;
            this.overlayCanvas.width = this.canvasWidth;
            this.overlayCanvas.height = this.canvasHeight;

            // 連接 WebSocket
            await this.connectWebSocket();

            // 開始發送幀
            this.isRunning = true;
            this.stats.startTime = Date.now();
            this.startFrameSender(frameRate);

            // 更新 UI
            this.startBtn.disabled = true;
            this.stopBtn.disabled = false;
            this.captureBtn.disabled = false;

            this.showNotification('偵測已啟動', 'success');

        } catch (error) {
            console.error('[DEBUG] 啟動失敗:', error);
            console.error('[DEBUG] 錯誤類型:', error.constructor.name);
            console.error('[DEBUG] 錯誤訊息:', error.message);
            console.error('[DEBUG] 錯誤堆疊:', error.stack);

            // 顯示詳細錯誤訊息
            let errorMsg = error.message || '未知錯誤';
            if (errorMsg === 'undefined' || !errorMsg) {
                errorMsg = '連線失敗，請檢查伺服器位址';
            }
            this.showNotification(`啟動失敗: ${errorMsg}`, 'error');

            // 清理資源
            this.stop();
        }
    }

    async connectWebSocket() {
        const serverUrl = this.serverUrlInput.value;

        this.showNotification(`正在連接伺服器: ${serverUrl}`, 'warning');

        // 先嘗試 WebSocket，失敗則使用 HTTP 模式
        try {
            await this._tryWebSocketConnect(serverUrl);
            this.debugLog('WebSocket 連線成功', 'success');
        } catch (wsError) {
            this.debugLog(`WebSocket 連線失敗: ${wsError.message}`, 'warning');
            this.debugLog('切換至 HTTP 後援模式...', 'info');

            // 切換到 HTTP 模式
            await this._initHttpMode(serverUrl);
        }
    }

    async _tryWebSocketConnect(serverUrl) {
        return new Promise((resolve, reject) => {
            let resultConnected = false;
            let videoConnected = false;
            let connectionTimeout = setTimeout(() => {
                if (!resultConnected || !videoConnected) {
                    reject(new Error(`連接超時 (結果:${resultConnected ? '✓' : '✗'}, 視頻:${videoConnected ? '✓' : '✗'})`));
                }
            }, 5000); // 5秒超時 (更快以切換到 HTTP)

            try {
                // 結果 WebSocket
                console.log('[DEBUG] 連接結果 WebSocket:', `${serverUrl}/ws/result`);
                this.resultSocket = new WebSocket(`${serverUrl}/ws/result`);

                this.resultSocket.onopen = () => {
                    console.log('[DEBUG] 結果 WebSocket 已連接');
                    this.connectionStatus.className = 'connected';
                    resultConnected = true;
                    this.debugLog('結果 WebSocket 已連接', 'success');

                    if (resultConnected && videoConnected) {
                        clearTimeout(connectionTimeout);
                        resolve();
                    }
                };

                this.resultSocket.onmessage = (event) => {
                    console.log('[DEBUG] 收到檢測結果:', event.data);
                    try {
                        const result = JSON.parse(event.data);
                        this.handleDetectionResult(result);
                    } catch (e) {
                        console.error('[DEBUG] 解析結果失敗:', e, event.data);
                    }
                };

                this.resultSocket.onerror = (error) => {
                    console.error('[DEBUG] 結果 WebSocket 錯誤:', error);
                    this.connectionStatus.className = 'disconnected';
                    clearTimeout(connectionTimeout);
                    // 不要直接 reject，讓視頻 WebSocket 的錯誤來處理
                };

                this.resultSocket.onclose = (event) => {
                    console.log('[DEBUG] 結果 WebSocket 已斷開', event.code, event.reason);
                    this.connectionStatus.className = 'disconnected';
                };

                // 視頻 WebSocket
                console.log('[DEBUG] 連接視頻 WebSocket:', `${serverUrl}/ws/video`);
                this.videoSocket = new WebSocket(`${serverUrl}/ws/video`);

                this.videoSocket.onopen = () => {
                    console.log('[DEBUG] 視頻 WebSocket 已連接');
                    videoConnected = true;
                    this.debugLog('視頻 WebSocket 已連接', 'success');

                    if (resultConnected && videoConnected) {
                        clearTimeout(connectionTimeout);
                        resolve();
                    }
                };

                this.videoSocket.onerror = (error) => {
                    console.error('[DEBUG] 視頻 WebSocket 錯誤:', error);
                    clearTimeout(connectionTimeout);
                    reject(new Error(`WebSocket 連線失敗`));
                };

                this.videoSocket.onclose = (event) => {
                    console.log('[DEBUG] 視頻 WebSocket 已斷開', event.code, event.reason);
                };

            } catch (error) {
                console.error('[DEBUG] WebSocket 建立失敗:', error);
                clearTimeout(connectionTimeout);
                reject(error);
            }
        });
    }

    async _initHttpMode(serverUrl) {
        // 將 ws:// 或 wss:// 轉換為 http:// 或 https://
        let httpUrl = serverUrl.replace(/^wss?:\/\//, '');
        const protocol = serverUrl.startsWith('wss://') ? 'https://' : 'http://';
        this.httpApiUrl = `${protocol}${httpUrl}`;
        this.useHttpMode = true;

        this.debugLog(`HTTP API URL: ${this.httpApiUrl}`, 'info');
        this.showNotification('HTTP 模式已啟用', 'success');
        this.connectionStatus.className = 'connected';
    }

    startFrameSender(frameRate) {
        const interval = 1000 / frameRate;

        this.frameInterval = setInterval(() => {
            if (!this.isRunning) return;

            // WebSocket 模式檢查
            if (!this.useHttpMode) {
                if (!this.videoSocket || this.videoSocket.readyState !== WebSocket.OPEN) {
                    return;
                }
            }

            this.sendFrame();
        }, interval);
    }

    async sendFrame() {
        if (!this.localVideo.videoWidth) return;

        // 建立臨時畫布來擷取幀
        const tempCanvas = document.createElement('canvas');
        tempCanvas.width = this.canvasWidth;
        tempCanvas.height = this.canvasHeight;
        const tempCtx = tempCanvas.getContext('2d');

        // 繪製當前幀
        tempCtx.drawImage(this.localVideo, 0, 0, this.canvasWidth, this.canvasHeight);

        // 轉換為 base64
        const dataUrl = tempCanvas.toDataURL('image/jpeg', 0.8);

        // 發送到伺服器
        try {
            if (this.useHttpMode) {
                // HTTP 模式
                await this._sendFrameHttp(dataUrl);
            } else {
                // WebSocket 模式
                this.videoSocket.send(dataUrl);
            }

            // 更新統計
            this.stats.framesSent++;
            this.totalFrames.textContent = this.stats.framesSent;

            // 每 30 幀記錄一次
            if (this.stats.framesSent % 30 === 1) {
                this.debugLog(`已發送 ${this.stats.framesSent} 幀 (${this.useHttpMode ? 'HTTP' : 'WebSocket'})`, 'info');
            }
        } catch (e) {
            this.debugLog(`發送失敗: ${e.message}`, 'error');
        }
    }

    async _sendFrameHttp(dataUrl) {
        const requestStart = Date.now();
        const payloadSize = dataUrl.length;
        const requestUrl = `${this.httpApiUrl}/api/detect/v2`;

        try {
            // 顯示請求 URL (每 30 幀一次，避免日誌過多)
            if (!this._lastUrlLog || this.stats.framesSent - this._lastUrlLog >= 30) {
                this.debugLog(`API URL: ${requestUrl}`, 'info');
                this._lastUrlLog = this.stats.framesSent;
            }
            this.debugLog(`發送 HTTP 請求，資料大小: ${(payloadSize / 1024).toFixed(1)} KB`, 'info');

            const response = await fetch(requestUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ image: dataUrl })
            });

            const requestTime = Date.now() - requestStart;

            if (!response.ok) {
                // 嘗試讀取錯誤訊息
                let errorDetail = `HTTP ${response.status}`;
                try {
                    const errorData = await response.text();
                    if (errorData) {
                        errorDetail += `: ${errorData.substring(0, 100)}`;
                    }
                } catch (e) {
                    // 無法讀取錯誤詳情
                }
                this.debugLog(`HTTP 錯誤 (${requestTime}ms): ${errorDetail}`, 'error');
                throw new Error(errorDetail);
            }

            const result = await response.json();
            if (result.error) {
                this.debugLog(`伺服器錯誤: ${result.error}`, 'error');
                throw new Error(result.error);
            }

            this.debugLog(`HTTP 請求成功 (${requestTime}ms)`, 'success');

            // 處理檢測結果
            this.handleDetectionResult(result);
        } catch (e) {
            // 分類錯誤類型
            let errorType = '未知錯誤';
            let errorDetail = e.message || '無法識別的錯誤';

            if (errorDetail === 'Failed to fetch' || errorDetail === 'NetworkError') {
                errorType = '網路連線失敗';
                errorDetail += ` (URL: ${requestUrl})`;
                // 首次錯誤時顯示完整診斷資訊
                if (this._httpErrorCount === 1) {
                    this.debugLog(`===== 連線診斷 =====`, 'warning');
                    this.debugLog(`API URL: ${requestUrl}`, 'info');
                    this.debugLog(`請確保伺服器在 ${this.httpApiUrl} 運行`, 'warning');
                    this.debugLog(`可在設定中更改伺服器地址`, 'info');
                    this.debugLog(`==================`, 'warning');
                }
            } else if (errorDetail.includes('HTTP 413') || errorDetail.includes('413')) {
                errorType = '請求太大';
                errorDetail += ' - 請嘗試降低影像解析度';
            } else if (errorDetail.includes('HTTP 504') || errorDetail.includes('504')) {
                errorType = '伺服器超時';
                errorDetail += ' - 處理時間過長，請降低影像解析度或幀率';
            } else if (errorDetail.includes('HTTP 500')) {
                errorType = '伺服器內部錯誤';
                errorDetail += ' - 請檢查伺服器日誌';
            }

            // 每 10 個錯誤記錄一次完整堆疊
            if (!this._httpErrorCount) this._httpErrorCount = 0;
            this._httpErrorCount++;
            if (this._httpErrorCount % 10 === 1) {
                this.debugLog(`[${errorType}] ${errorDetail}`, 'error');
                console.error('[HTTP Debug]', errorType, errorDetail, e);
            } else {
                this.debugLog(`[${errorType}]`, 'error');
            }
        }
    }

    handleDetectionResult(result) {
        // 記錄收到結果
        this.debugLog(`收到結果: ${result.count} 個物件, FPS: ${result.fps}`, 'success');

        // 更新 FPS
        this.fpsDisplay.textContent = `FPS: ${result.fps}`;

        // 更新物件計數
        this.objectCount.textContent = `物件: ${result.count}`;

        // 更新統計
        this.stats.totalDetections += result.count;
        this.totalDetections.textContent = this.stats.totalDetections;

        // FPS 歷史
        this.stats.fpsHistory.push(result.fps);
        if (this.stats.fpsHistory.length > 30) {
            this.stats.fpsHistory.shift();
        }
        const avgFps = this.stats.fpsHistory.reduce((a, b) => a + b, 0) / this.stats.fpsHistory.length;
        this.avgFps.textContent = avgFps.toFixed(1);

        // 儲存檢測結果
        this.currentDetections = result.detections;

        // 繪製檢測框
        this.drawDetections(result.detections);

        // 更新結果列表
        this.updateResultsList(result.detections);
    }

    drawDetections(detections) {
        // 清除畫布
        this.ctx.clearRect(0, 0, this.canvasWidth, this.canvasHeight);

        if (!detections || detections.length === 0) return;

        // 計算縮放比例
        const scaleX = this.overlayCanvas.clientWidth / this.canvasWidth;
        const scaleY = this.overlayCanvas.clientHeight / this.canvasHeight;

        detections.forEach((det, index) => {
            if (!det.bbox) return;

            const [x1, y1, x2, y2] = det.bbox;

            // 縮放座標
            const scaledX1 = x1 * scaleX;
            const scaledY1 = y1 * scaleY;
            const scaledWidth = (x2 - x1) * scaleX;
            const scaledHeight = (y2 - y1) * scaleY;

            // 顏色根據信心度
            const hue = det.confidence * 120; // 0-120 (紅到綠)
            const color = `hsl(${hue}, 80%, 50%)`;

            // 繪製邊界框
            this.ctx.strokeStyle = color;
            this.ctx.lineWidth = 3;
            this.ctx.strokeRect(scaledX1, scaledY1, scaledWidth, scaledHeight);

            // 繪製標籤背景
            const label = `${det.class_name_cn} ${Math.round(det.confidence * 100)}%`;
            this.ctx.font = 'bold 14px Arial';
            const textWidth = this.ctx.measureText(label).width;

            this.ctx.fillStyle = color;
            this.ctx.fillRect(scaledX1, scaledY1 - 25, textWidth + 10, 25);

            // 繪製標籤文字
            this.ctx.fillStyle = 'white';
            this.ctx.fillText(label, scaledX1 + 5, scaledY1 - 7);

            // 如果有分割遮罩，繪製遮罩
            if (det.mask && det.mask.length > 0) {
                this.drawMask(det.mask, color);
            }
        });
    }

    drawMask(mask, color) {
        if (!mask || mask.length === 0) return;

        try {
            // mask 是二維陣列
            const maskArray = new Uint8ClampedArray(mask.flat());
            const imageData = new ImageData(
                new Uint8ClampedArray(this.canvasWidth * this.canvasHeight * 4),
                this.canvasWidth,
                this.canvasHeight
            );

            // 設定遮罩區域為半透明顏色
            for (let i = 0; i < maskArray.length; i++) {
                if (maskArray[i] > 0.5) {
                const idx = i * 4;
                imageData.data[idx] = 78;     // R
                imageData.data[idx + 1] = 204; // G
                imageData.data[idx + 2] = 163; // B
                imageData.data[idx + 3] = 100; // A
                }
            }

            this.ctx.putImageData(imageData, 0, 0);
        } catch (e) {
            // 忽略遮罩繪製錯誤
        }
    }

    updateResultsList(detections) {
        if (!detections || detections.length === 0) {
            this.resultsContainer.innerHTML = `
                <div class="empty-state">
                    <p>未檢測到物件</p>
                </div>
            `;
            return;
        }

        // 物件圖示對應
        const iconMap = {
            '手機': '📱',
            '手提包': '👜',
            '背包': '🎒',
            '水瓶': '🍶',
            '杯子': '🥤',
            '筆電': '💻',
            '鍵盤': '⌨️',
            '滑鼠': '🖱️',
            '遙控器': '🎮',
            '錢包': '💰',
            '鑰匙': '🔑',
            '書': '📚',
            '眼鏡': '👓',
            '手錶': '⌚',
            'default': '📦'
        };

        // 按信心度排序
        const sorted = [...detections].sort((a, b) => b.confidence - a.confidence);

        // 只顯示前 10 個
        const topDetections = sorted.slice(0, 10);

        this.resultsContainer.innerHTML = topDetections.map(det => `
            <div class="detection-item">
                <div class="name">
                    <span class="icon">${iconMap[det.class_name_cn] || iconMap['default']}</span>
                    <span>${det.class_name_cn}</span>
                </div>
                <span class="confidence">${Math.round(det.confidence * 100)}%</span>
            </div>
        `).join('');
    }

    stop() {
        if (!this.isRunning) return;

        this.isRunning = false;

        // 停止發送幀
        if (this.frameInterval) {
            clearInterval(this.frameInterval);
            this.frameInterval = null;
        }

        // 關閉 WebSocket
        if (this.videoSocket) {
            this.videoSocket.close();
            this.videoSocket = null;
        }

        if (this.resultSocket) {
            this.resultSocket.close();
            this.resultSocket = null;
        }

        // 停止攝影機
        if (this.mediaStream) {
            this.mediaStream.getTracks().forEach(track => track.stop());
            this.mediaStream = null;
        }

        // 清除視頻
        this.localVideo.srcObject = null;
        this.noCameraMessage.classList.remove('hidden');

        // 清除畫布
        this.ctx.clearRect(0, 0, this.canvasWidth, this.canvasHeight);

        // 更新 UI
        this.startBtn.disabled = false;
        this.stopBtn.disabled = true;
        this.captureBtn.disabled = true;

        this.connectionStatus.className = '';

        // 重置 HTTP 模式
        this.useHttpMode = false;
        this.httpApiUrl = '';

        this.debugLog('偵測已停止', 'info');
        this.showNotification('偵測已停止', 'warning');
    }

    capture() {
        if (!this.isRunning) return;

        // 建立包含檢測框的截圖
        const captureCanvas = document.createElement('canvas');
        captureCanvas.width = this.canvasWidth;
        captureCanvas.height = this.canvasHeight;
        const captureCtx = captureCanvas.getContext('2d');

        // 繪製視頻幀
        captureCtx.drawImage(this.localVideo, 0, 0);

        // 繪製檢測框
        captureCtx.drawImage(this.overlayCanvas, 0, 0);

        // 下載
        const link = document.createElement('a');
        link.download = `yolo_capture_${Date.now()}.png`;
        link.href = captureCanvas.toDataURL('image/png');
        link.click();

        this.showNotification('截圖已儲存', 'success');
    }

    showNotification(message, type = 'success') {
        const notification = document.getElementById('notification');
        notification.textContent = message;
        notification.className = `notification ${type} show`;

        setTimeout(() => {
            notification.classList.remove('show');
        }, 3000);

        // 同時寫入除錯面板
        this.debugLog(message, type);
    }

    debugLog(message, type = 'info') {
        if (!this.debugContent) return;

        const timestamp = new Date().toLocaleTimeString();
        const line = document.createElement('div');
        line.className = `debug-line debug-${type}`;
        line.textContent = `[${timestamp}] ${message}`;

        this.debugContent.appendChild(line);

        // 自動滾動到底部
        this.debugContent.scrollTop = this.debugContent.scrollHeight;

        // 限制行數
        while (this.debugContent.children.length > 50) {
            this.debugContent.removeChild(this.debugContent.firstChild);
        }
    }

    clearDebug() {
        if (this.debugContent) {
            this.debugContent.innerHTML = '';
        }
    }
}

// 初始化應用
document.addEventListener('DOMContentLoaded', () => {
    window.app = new YOLOWebApp();
});
