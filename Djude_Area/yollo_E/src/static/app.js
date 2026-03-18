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
        this.copyDebugBtn = document.getElementById('copyDebugBtn');
        if (this.clearDebugBtn) {
            this.clearDebugBtn.addEventListener('click', () => this.clearDebug());
        }
        if (this.copyDebugBtn) {
            this.copyDebugBtn.addEventListener('click', () => this.copyDebug());
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

        // 複製 URL 按鈕
        this.copyUrlBtn = document.getElementById('copyUrlBtn');
        if (this.copyUrlBtn) {
            this.copyUrlBtn.addEventListener('click', () => this.copyUrl());
        }

        // 設定預設伺服器地址
        // 自動根據頁面協議選擇 ws:// 或 wss://
        const isDevTunnel = window.location.hostname.includes('devtunnels.ms') ||
                            window.location.hostname.includes('portmap.io') ||
                            window.location.hostname.includes('localtunnel') ||
                            window.location.hostname.includes('trycloudflare.com') ||
                            window.location.hostname.includes('ngrok');

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const defaultHost = window.location.hostname || 'localhost';

        // 隧道服務或標準埠（port 為空）時不加埠號，由隧道服務自動代理
        let serverUrl;
        if (isDevTunnel || !window.location.port) {
            serverUrl = `${protocol}//${defaultHost}`;
        } else {
            serverUrl = `${protocol}//${defaultHost}:${window.location.port}`;
        }
        this.serverUrlInput.value = serverUrl;

        // 顯示環境提示
        if (isDevTunnel) {
            this.debugLog('檢測到隧道服務，使用同源連線', 'info');
        } else if (window.location.protocol === 'https:' && window.location.port) {
            this.debugLog('HTTPS 模式', 'info');
            this.debugLog('請確保後端使用 --ssl 參數啟動', 'warning');
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

        // 檢測混合內容問題 (HTTPS 頁面 + HTTP API)
        const pageIsHttps = window.location.protocol === 'https:';
        const apiIsHttp = this.httpApiUrl.startsWith('http://');

        if (pageIsHttps && apiIsHttp) {
            this.debugLog('====================================', 'error');
            this.debugLog('⚠️ 混合內容警告', 'error');
            this.debugLog('頁面: HTTPS | API: HTTP', 'error');
            this.debugLog('瀏覽器會阻止此連線！', 'error');
            this.debugLog('====================================', 'error');
            this.debugLog('解決方案:', 'warning');
            this.debugLog('後端啟動時添加 --ssl 參數:', 'info');
            this.debugLog('python -m src.web_server --ssl --port 8443', 'success');
            this.debugLog('然後訪問: https://你的域名:8443', 'info');
            this.debugLog('====================================', 'error');
            this.showNotification('⚠️ 需要後端啟用 HTTPS (--ssl)', 'error');
        } else {
            this.debugLog(`HTTP(S) API URL: ${this.httpApiUrl}`, 'info');
            this.showNotification('HTTP 模式已啟用', 'success');
        }
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
            // 首次或每 30 幀顯示完整連線資訊
            if (!this._lastUrlLog || this.stats.framesSent - this._lastUrlLog >= 30) {
                this.debugLog(`──── 連線資訊 ────`, 'info');
                this.debugLog(`API URL: ${requestUrl}`, 'info');
                this.debugLog(`httpApiUrl: ${this.httpApiUrl}`, 'info');
                this.debugLog(`頁面來源: ${window.location.origin}`, 'info');
                this.debugLog(`──────────────────`, 'info');
                this._lastUrlLog = this.stats.framesSent;
            }

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

        // 注意：canvas 與 video 均使用 object-fit: contain，
        // 且 canvas 內部解析度已與影像一致，因此 bbox 座標直接繪製即可，無需縮放。

        detections.forEach((det, index) => {
            if (!det.bbox) return;

            const [x1, y1, x2, y2] = det.bbox;
            const boxW = x2 - x1;
            const boxH = y2 - y1;

            // 顏色根據信心度 (0-120: 紅到綠)
            const hue = det.confidence * 120;
            const color = `hsl(${hue}, 80%, 50%)`;
            const colorTransparent = `hsla(${hue}, 80%, 50%, 0.15)`;

            // 繪製半透明填充
            this.ctx.fillStyle = colorTransparent;
            this.ctx.fillRect(x1, y1, boxW, boxH);

            // 繪製邊界框
            this.ctx.strokeStyle = color;
            this.ctx.lineWidth = 3;
            this.ctx.strokeRect(x1, y1, boxW, boxH);

            // 繪製標籤
            const label = `${det.class_name_cn} ${Math.round(det.confidence * 100)}%`;
            const fontSize = Math.max(16, Math.round(this.canvasHeight / 40));
            this.ctx.font = `bold ${fontSize}px "Microsoft JhengHei", "PingFang TC", "Noto Sans TC", Arial, sans-serif`;
            const textMetrics = this.ctx.measureText(label);
            const textHeight = fontSize;
            const padding = 6;
            const labelW = textMetrics.width + padding * 2;
            const labelH = textHeight + padding * 2;

            // 標籤位置：優先放框上方，空間不足時放框內上方
            const labelY = (y1 - labelH > 0) ? y1 - labelH : y1;

            // 標籤背景（圓角效果）
            this.ctx.fillStyle = color;
            this.ctx.beginPath();
            this._roundRect(x1, labelY, labelW, labelH, 4);
            this.ctx.fill();

            // 標籤文字
            this.ctx.fillStyle = 'white';
            this.ctx.textBaseline = 'middle';
            this.ctx.fillText(label, x1 + padding, labelY + labelH / 2);

            // 如果有分割遮罩，繪製遮罩
            if (det.mask && det.mask.length > 0) {
                this.drawMask(det.mask, color);
            }
        });
    }

    _roundRect(x, y, w, h, r) {
        // 繪製圓角矩形路徑
        this.ctx.moveTo(x + r, y);
        this.ctx.lineTo(x + w - r, y);
        this.ctx.arcTo(x + w, y, x + w, y + r, r);
        this.ctx.lineTo(x + w, y + h - r);
        this.ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
        this.ctx.lineTo(x + r, y + h);
        this.ctx.arcTo(x, y + h, x, y + h - r, r);
        this.ctx.lineTo(x, y + r);
        this.ctx.arcTo(x, y, x + r, y, r);
        this.ctx.closePath();
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

    copyDebug() {
        if (!this.debugContent) return;

        // 取得所有日誌文字
        const logLines = this.debugContent.querySelectorAll('.debug-line');
        const logText = Array.from(logLines)
            .map(line => line.textContent)
            .join('\n');

        // 使用 Clipboard API 複製
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(logText).then(() => {
                this.showNotification('日誌已複製到剪貼簿', 'success');
                this.debugLog('[系統] 日誌已複製', 'success');
            }).catch(err => {
                // 復備方法
                this._fallbackCopy(logText);
            });
        } else {
            this._fallbackCopy(logText);
        }
    }

    copyUrl() {
        const currentUrl = window.location.href;

        // 使用 Clipboard API 複製
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(currentUrl).then(() => {
                this.showNotification('連結已複製到剪貼簿', 'success');
                this.debugLog(`[系統] 已複製連結: ${currentUrl}`, 'success');
            }).catch(err => {
                this._fallbackCopy(currentUrl);
            });
        } else {
            this._fallbackCopy(currentUrl);
        }
    }

    _fallbackCopy(text) {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();

        try {
            document.execCommand('copy');
            this.showNotification('日誌已複製到剪貼簿', 'success');
            this.debugLog('[系統] 日誌已複製', 'success');
        } catch (err) {
            this.debugLog('[系統] 複製失敗: ' + err.message, 'error');
        }

        document.body.removeChild(textarea);
    }
}

// 初始化應用
document.addEventListener('DOMContentLoaded', () => {
    window.app = new YOLOWebApp();
});
