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

        // 除錯面板收合
        this.debugPanel = document.getElementById('debugPanel');
        this.debugToggleBtn = document.getElementById('debugToggleBtn');
        this.debugCollapseBtn = document.getElementById('debugCollapseBtn');

        // 標註狀態面板
        this.annotationPanel = document.getElementById('annotationPanel');
        this.annotationContent = document.getElementById('annotationContent');
        this.annotationFooter = document.getElementById('annotationFooter');
        this.annotationToggleBtn = document.getElementById('annotationToggleBtn');

        // 反饋狀態
        this._feedbackStatsInterval = null;

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

        // 物品註冊元素
        this.newClassEnInput = document.getElementById('newClassEn');
        this.newClassCnInput = document.getElementById('newClassCn');
        this.addClassBtn = document.getElementById('addClassBtn');
        this.refreshClassesBtn = document.getElementById('refreshClassesBtn');
        this.classList = document.getElementById('classList');

        // 狀態
        this.isRunning = false;
        this.videoSocket = null;
        this.resultSocket = null;
        this.mediaStream = null;
        this.frameInterval = null;
        this.useHttpMode = false; // HTTP 後援模式
        this.httpApiUrl = ''; // HTTP API URL

        // 幀發送控制
        this._isProcessing = false;  // 是否正在等待伺服器回應
        this._frameLoopActive = false;  // 自適應迴圈是否啟用

        // 效能優化：重用 canvas 和 Image 物件，避免每幀都 GC
        this._tempCanvas = document.createElement('canvas');
        this._tempCtx = this._tempCanvas.getContext('2d');
        this._serverImg = new Image();
        this._lastResultsHtml = '';  // 結果列表快取，避免重複 DOM 操作

        // 統計
        this.stats = {
            framesSent: 0,
            totalDetections: 0,
            fpsHistory: [],
            startTime: null
        };

        // 當前檢測結果
        this.currentDetections = [];
        this._lastDetectionTime = 0;  // 最後收到偵測結果的時間

        // 畫布尺寸
        this.canvasWidth = 640;
        this.canvasHeight = 480;

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

        // 除錯面板收合
        if (this.debugToggleBtn) {
            this.debugToggleBtn.addEventListener('click', () => {
                this.debugPanel.classList.toggle('collapsed');
            });
        }
        if (this.debugCollapseBtn) {
            this.debugCollapseBtn.addEventListener('click', () => {
                this.debugPanel.classList.add('collapsed');
            });
        }

        // 標註面板收合
        if (this.annotationToggleBtn) {
            this.annotationToggleBtn.addEventListener('click', () => {
                const content = this.annotationContent;
                const footer = this.annotationFooter;
                const isCollapsed = content.classList.toggle('collapsed');
                footer.classList.toggle('collapsed', isCollapsed);
                this.annotationToggleBtn.textContent = isCollapsed ? '+' : '−';
            });
        }

        // 定時更新標註統計
        this._feedbackStatsInterval = setInterval(() => this._updateAnnotationPanel(), 10000);
        this._updateAnnotationPanel();

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

        // 物品註冊事件
        if (this.addClassBtn) {
            this.addClassBtn.addEventListener('click', () => this.addClass());
        }
        if (this.refreshClassesBtn) {
            this.refreshClassesBtn.addEventListener('click', () => this.loadClasses());
        }
        // Enter 鍵快速新增
        if (this.newClassEnInput) {
            this.newClassEnInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') this.addClass();
            });
        }
        if (this.newClassCnInput) {
            this.newClassCnInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') this.addClass();
            });
        }

        // 初始載入偵測類別列表
        this.loadClasses();

        // 點擊偵測框更正功能
        this.overlayCanvas.addEventListener('click', (e) => this._handleCanvasClick(e));

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

    _initHttpFallback() {
        // 重新初始化 HTTP 連線（用於連續超時後的恢復）
        this.debugLog('重新初始化 HTTP 連線...', 'info');

        // 重新取得當前頁面的 server URL
        const currentUrl = window.location.href;
        const serverUrl = currentUrl.replace(/^https?:\/\//, 'wss://');
        const wsUrl = serverUrl.endsWith('/') ? serverUrl.slice(0, -1) : serverUrl;

        // 重新設定 HTTP URL
        const httpUrl = wsUrl.replace(/^wss?:\/\//, '');
        const protocol = window.location.protocol === 'https:' ? 'https://' : 'http://';
        this.httpApiUrl = `${protocol}${httpUrl}`;

        this.debugLog(`HTTP URL 已重設為: ${this.httpApiUrl}`, 'success');
        this.showNotification('已重新連線', 'success');
    }

    startFrameSender(frameRate) {
        // HTTP 模式：使用自適應迴圈（送一幀→等回應→再送下一幀）
        // WebSocket 模式：使用限速 interval 防止堆積
        if (this.useHttpMode) {
            this._frameLoopActive = true;
            this._runAdaptiveLoop();
        } else {
            const interval = 1000 / frameRate;
            this.frameInterval = setInterval(() => {
                if (!this.isRunning) return;
                if (!this.videoSocket || this.videoSocket.readyState !== WebSocket.OPEN) return;
                // WebSocket 模式也加入節流：上一幀未處理完就跳過
                if (this._isProcessing) return;
                this.sendFrame();
            }, interval);
        }
    }

    async _runAdaptiveLoop() {
        // 自適應迴圈：送出→等回應→立即送下一幀，自動匹配伺服器處理速度
        while (this._frameLoopActive && this.isRunning) {
            try {
                await this.sendFrame();
            } catch (e) {
                // 錯誤時短暫等待再重試，避免瘋狂重試
                await new Promise(r => setTimeout(r, 500));
            }
            // 極短間隔讓瀏覽器有時間更新 UI
            await new Promise(r => setTimeout(r, 10));
        }
    }

    async sendFrame() {
        if (!this.localVideo.videoWidth) return;

        // 擷取當前最新幀（重用 canvas 避免 GC 壓力）
        if (this._tempCanvas.width !== this.canvasWidth || this._tempCanvas.height !== this.canvasHeight) {
            this._tempCanvas.width = this.canvasWidth;
            this._tempCanvas.height = this.canvasHeight;
        }
        this._tempCtx.drawImage(this.localVideo, 0, 0, this.canvasWidth, this.canvasHeight);
        const dataUrl = this._tempCanvas.toDataURL('image/jpeg', 0.8);

        // 標記正在處理
        this._isProcessing = true;

        try {
            if (this.useHttpMode) {
                await this._sendFrameHttp(dataUrl);
            } else {
                this.videoSocket.send(dataUrl);
            }

            // 更新統計
            this.stats.framesSent++;
            this.totalFrames.textContent = this.stats.framesSent;

            if (this.stats.framesSent % 30 === 1) {
                this.debugLog(`已發送 ${this.stats.framesSent} 幀 (${this.useHttpMode ? 'HTTP' : 'WebSocket'})`, 'info');
            }
        } catch (e) {
            this.debugLog(`發送失敗: ${e.message}`, 'error');
        } finally {
            this._isProcessing = false;
        }
    }

    async _sendFrameHttp(dataUrl) {
        const requestStart = Date.now();
        const payloadSize = dataUrl.length;
        const requestUrl = `${this.httpApiUrl}/api/detect/v2`;

        // 設定請求超時（10 秒，降低以更快偵測連線問題）
        const TIMEOUT_MS = 10000;
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

        // 連續超時計數器
        if (!this._consecutiveTimeouts) this._consecutiveTimeouts = 0;

        // 每 30 幀才輸出詳細 debug，減少 DOM 操作
        const requestId = `req_${Date.now()}`;
        const verboseLog = (this.stats.framesSent % 30 === 0);

        try {
            // 首次或每 30 幀顯示完整連線資訊
            if (!this._lastUrlLog || this.stats.framesSent - this._lastUrlLog >= 30) {
                this.debugLog(`──── 連線資訊 ────`, 'info');
                this.debugLog(`API URL: ${requestUrl}`, 'info');
                this.debugLog(`httpApiUrl: ${this.httpApiUrl}`, 'info');
                this.debugLog(`頁面來源: ${window.location.origin}`, 'info');
                this.debugLog(`Tunnel 偵測: ${window.location.hostname.includes('devtunnels.ms') ? '是' : '否'}`, 'info');
                this.debugLog(`線上狀態: ${navigator.onLine ? '線上' : '離線'}`, 'info');
                this.debugLog(`──────────────────`, 'info');
                this._lastUrlLog = this.stats.framesSent;
            }

            const fetchStart = Date.now();
            const response = await fetch(requestUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ image: dataUrl }),
                signal: controller.signal
            });

            const fetchTime = Date.now() - fetchStart;
            if (verboseLog) this.debugLog(`[${requestId}] 回應 ← ${fetchTime}ms (HTTP ${response.status})`, 'info');

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
                this.debugLog(`[${requestId}] HTTP 錯誤 (${requestTime}ms): ${errorDetail}`, 'error');
                throw new Error(errorDetail);
            }

            const jsonStart = Date.now();
            const result = await response.json();
            const jsonTime = Date.now() - jsonStart;

            if (result.error) {
                this.debugLog(`[${requestId}] 伺服器錯誤: ${result.error}`, 'error');
                throw new Error(result.error);
            }

            // 每 30 幀才輸出完成日誌，減少 DOM 操作
            if (verboseLog) this.debugLog(`[${requestId}] ✓ ${requestTime}ms (fetch:${fetchTime}ms, json:${jsonTime}ms)`, 'success');

            // 重置連續超時計數器
            this._consecutiveTimeouts = 0;

            // 處理檢測結果
            this.handleDetectionResult(result);
        } catch (e) {
            // 清除超時計時器
            clearTimeout(timeoutId);
            const errorTime = Date.now() - requestStart;

            // 分類錯誤類型
            let errorType = '未知錯誤';
            let errorDetail = e.message || '無法識別的錯誤';

            if (e.name === 'AbortError') {
                errorType = '請求超時';
                errorDetail = `請求超過 ${TIMEOUT_MS/1000} 秒，已自動取消`;
                this._consecutiveTimeouts++;
                this._hadTimeoutSinceLastResult = true;  // 標記超時，下次收到結果時不計算 FPS

                this.debugLog(`[${requestId}] ⚠️ ${errorType} (${errorTime}ms) 連續: ${this._consecutiveTimeouts}`, 'warning');
                this.debugLog(`[${requestId}] 可能原因: Tunnel 斷線 / 網路不穩 / 伺服器過載`, 'warning');

                // 超時後清除舊的偵測結果
                this.currentDetections = [];
                this.ctx.clearRect(0, 0, this.canvasWidth, this.canvasHeight);

                // 連續 3 次超時，嘗試重新建立連線
                if (this._consecutiveTimeouts >= 3) {
                    this.debugLog(`[${requestId}] 連續超時 ${this._consecutiveTimeouts} 次，嘗試重新連線...`, 'warning');
                    this._consecutiveTimeouts = 0;
                    // 重新初始化 HTTP 連線
                    this._initHttpFallback();
                }
                return;  // 不顯示錯誤通知，直接跳過這幀
            } else if (errorDetail === 'Failed to fetch' || errorDetail === 'NetworkError') {
                errorType = '網路連線失敗';
                this.debugLog(`[${requestId}] ❌ ${errorType} (${errorTime}ms): ${errorDetail}`, 'error');
                this.debugLog(`[${requestId}] URL: ${requestUrl}`, 'error');
                this.debugLog(`[${requestId}] 線上狀態: ${navigator.onLine ? '線上' : '離線'}`, 'error');
                // 首次錯誤時顯示完整診斷資訊
                if (!this._httpErrorCount || this._httpErrorCount === 1) {
                    this.debugLog(`[${requestId}] ===== 連線診斷 =====`, 'warning');
                    this.debugLog(`[${requestId}] API URL: ${requestUrl}`, 'info');
                    this.debugLog(`[${requestId}] httpApiUrl: ${this.httpApiUrl}`, 'info');
                    this.debugLog(`[${requestId}] 頁面來源: ${window.location.origin}`, 'info');
                    this.debugLog(`[${requestId}] 請確保伺服器正在運行`, 'warning');
                    this.debugLog(`[${requestId}] ==================`, 'warning');
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
        // 計算真實端到端 FPS（基於收到結果的時間差）
        const now = Date.now();
        if (this._lastResultTime && !this._hadTimeoutSinceLastResult) {
            const timeDiff = now - this._lastResultTime;
            const realFps = timeDiff > 0 ? 1000 / timeDiff : 0;

            // 記錄收到結果（顯示兩種 FPS）
            this.debugLog(`收到結果: ${result.count} 個物件, 伺服器FPS: ${result.fps}, 真實FPS: ${realFps.toFixed(1)}`, 'success');

            // 更新 FPS 顯示（使用真實 FPS）
            this.fpsDisplay.textContent = `FPS: ${realFps.toFixed(1)}`;

            // 使用真實 FPS 計算歷史
            this.stats.fpsHistory.push(realFps);
        } else {
            // 首次收到結果或有超時，使用伺服器 FPS
            this.debugLog(`收到結果: ${result.count} 個物件, FPS: ${result.fps}`, 'success');
            this.fpsDisplay.textContent = `FPS: ${result.fps}`;
            this.stats.fpsHistory.push(result.fps);
        }
        this._lastResultTime = now;
        this._hadTimeoutSinceLastResult = false;  // 重置超時標記

        // 更新物件計數
        this.objectCount.textContent = `物件: ${result.count}`;

        // 更新統計
        this.stats.totalDetections += result.count;
        this.totalDetections.textContent = this.stats.totalDetections;

        // FPS 歷史（限制長度）
        if (this.stats.fpsHistory.length > 30) {
            this.stats.fpsHistory.shift();
        }
        const avgFps = this.stats.fpsHistory.reduce((a, b) => a + b, 0) / this.stats.fpsHistory.length;
        this.avgFps.textContent = avgFps.toFixed(1);

        // 儲存檢測結果（帶時間戳）
        this.currentDetections = result.detections;
        this._lastDetectionTime = Date.now();

        // 如果伺服器返回了處理後的畫面，直接顯示它（確保偵測框與畫面同步）
        if (result.annotated_frame) {
            this._drawServerFrame(result.annotated_frame);
        } else {
            // 備援：本地繪製檢測框
            this.drawDetections(result.detections);
        }

        // 更新結果列表
        this.updateResultsList(result.detections);
    }

    _drawServerFrame(base64Data) {
        // 將伺服器返回的處理後畫面繪製到 canvas 上（重用 Image 物件避免 GC）
        this._serverImg.onload = () => {
            this.ctx.clearRect(0, 0, this.canvasWidth, this.canvasHeight);
            this.ctx.drawImage(this._serverImg, 0, 0, this.canvasWidth, this.canvasHeight);
        };
        this._serverImg.onerror = () => {
            this.debugLog('無法載入伺服器畫面', 'error');
        };
        this._serverImg.src = `data:image/jpeg;base64,${base64Data}`;
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

        const newHtml = topDetections.map(det => `
            <div class="detection-item">
                <div class="name">
                    <span class="icon">${iconMap[det.class_name_cn] || iconMap['default']}</span>
                    <span>${det.class_name_cn}</span>
                </div>
                <span class="confidence">${Math.round(det.confidence * 100)}%</span>
            </div>
        `).join('');

        // 內容相同時跳過 DOM 更新，避免不必要的重繪
        if (newHtml !== this._lastResultsHtml) {
            this.resultsContainer.innerHTML = newHtml;
            this._lastResultsHtml = newHtml;
        }
    }

    stop() {
        if (!this.isRunning) return;

        this.isRunning = false;

        // 停止發送幀
        this._frameLoopActive = false;  // 終止自適應迴圈
        this._isProcessing = false;
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

        // 恢復本地視頻顯示
        if (this.localVideo) {
            this.localVideo.style.opacity = '1';
        }

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

        // 面板收合時跳過非錯誤日誌的 DOM 操作，避免無效 reflow
        if (type !== 'error' && this.debugPanel?.classList.contains('collapsed')) return;

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

    // ============================================
    // 點擊偵測框更正功能
    // ============================================

    _handleCanvasClick(e) {
        // 檢查是否有偵測結果
        if (!this.currentDetections || this.currentDetections.length === 0) {
            return;
        }

        // 取得點擊位置（相對於 canvas）
        const rect = this.overlayCanvas.getBoundingClientRect();
        const scaleX = this.canvasWidth / rect.width;
        const scaleY = this.canvasHeight / rect.height;
        const clickX = (e.clientX - rect.left) * scaleX;
        const clickY = (e.clientY - rect.top) * scaleY;

        // 檢查點擊是否在某個偵測框內
        for (let i = this.currentDetections.length - 1; i >= 0; i--) {
            const det = this.currentDetections[i];
            if (!det.bbox) continue;

            const [x1, y1, x2, y2] = det.bbox;
            if (clickX >= x1 && clickX <= x2 && clickY >= y1 && clickY <= y2) {
                // 找到被點擊的偵測框
                this._showCorrectionDialog(det, i);
                return;
            }
        }
    }

    _showCorrectionDialog(detection, index) {
        // 建立反饋 modal
        const overlay = document.createElement('div');
        overlay.className = 'feedback-modal-overlay';

        const currentName = detection.class_name_cn || detection.class_name;
        const currentNameEn = detection.class_name;

        overlay.innerHTML = `
            <div class="feedback-modal">
                <h3>偵測反饋</h3>
                <div class="detection-info">
                    <div>偵測結果: <strong>${currentName}</strong> (${currentNameEn})</div>
                    <div>信心度: ${(detection.confidence * 100).toFixed(1)}%</div>
                </div>
                <div class="btn-group">
                    <button class="btn-confirm" data-action="confirm">✅ 正確</button>
                    <button class="btn-correct" data-action="correct">✏️ 這不是 ${currentName}</button>
                    <div class="correction-input" id="correctionInput">
                        <div class="correction-class-list" id="correctionClassList">
                            <div style="color: var(--text-secondary); padding: 8px; text-align: center;">載入中...</div>
                        </div>
                        <div class="correction-manual">
                            <input type="text" id="correctionNameInput" placeholder="或輸入名稱（中文/英文皆可）" />
                            <button id="correctionSubmit">確認</button>
                        </div>
                    </div>
                    <button class="btn-false-positive" data-action="false_positive">❌ 誤報（不是物品）</button>
                    <button class="btn-cancel" data-action="cancel">取消</button>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);

        // 裁剪偵測區域截圖
        let croppedImage = null;
        try {
            const [x1, y1, x2, y2] = detection.bbox;
            const tempCanvas = document.createElement('canvas');
            const cropW = x2 - x1;
            const cropH = y2 - y1;
            tempCanvas.width = cropW;
            tempCanvas.height = cropH;
            const tempCtx = tempCanvas.getContext('2d');

            // 從本地視頻裁剪
            const videoW = this.localVideo.videoWidth;
            const videoH = this.localVideo.videoHeight;
            const scaleX = videoW / this.canvasWidth;
            const scaleY = videoH / this.canvasHeight;
            tempCtx.drawImage(
                this.localVideo,
                x1 * scaleX, y1 * scaleY, cropW * scaleX, cropH * scaleY,
                0, 0, cropW, cropH
            );
            croppedImage = tempCanvas.toDataURL('image/jpeg', 0.85);
        } catch (e) {
            this.debugLog(`截圖裁剪失敗: ${e.message}`, 'warning');
        }

        // 事件處理
        overlay.addEventListener('click', (e) => {
            const action = e.target.dataset?.action;
            if (!action) return;

            if (action === 'cancel') {
                overlay.remove();
                return;
            }

            if (action === 'correct') {
                const correctionDiv = document.getElementById('correctionInput');
                correctionDiv.classList.add('show');
                // 載入已註冊類別清單供選擇
                this._loadCorrectionClassList(overlay, detection, croppedImage);
                return;
            }

            if (action === 'confirm' || action === 'false_positive') {
                this._submitFeedback(action, detection, null, croppedImage);
                overlay.remove();
            }
        });

        // 手動輸入更正提交（支援中文或英文）
        const submitBtn = overlay.querySelector('#correctionSubmit');
        if (submitBtn) {
            submitBtn.addEventListener('click', () => {
                const nameInput = overlay.querySelector('#correctionNameInput').value.trim();
                if (!nameInput) {
                    this.showNotification('請輸入正確的名稱（中文或英文皆可）', 'warning');
                    return;
                }
                // 直接送出，後端會自動處理中文→英文轉換
                this._submitFeedback('correct', detection, nameInput, croppedImage);
                overlay.remove();
            });
        }

        // 點擊背景關閉
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) overlay.remove();
        });
    }

    async _submitFeedback(type, detection, correctClass, imageBase64) {
        try {
            const body = {
                type: type,
                class_name: detection.class_name,
                confidence: detection.confidence,
                bbox: detection.bbox,
                correct_class: correctClass || undefined,
                image: imageBase64 || undefined,
            };

            const res = await fetch(`${this._getApiBaseUrl()}/api/feedback`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });

            const data = await res.json();

            if (data.success) {
                const msgs = {
                    confirm: `已確認「${detection.class_name_cn || detection.class_name}」正確`,
                    correct: `已更正為「${correctClass}」`,
                    false_positive: `已標記為誤報`,
                };
                this.showNotification(msgs[type] || '反饋已提交', 'success');
                this._updateAnnotationPanel();

                // 如果是更正，重新載入類別列表
                if (type === 'correct') {
                    await this.loadClasses();
                }
            } else {
                this.showNotification(`反饋失敗: ${data.error || '未知錯誤'}`, 'error');
            }
        } catch (e) {
            this.showNotification(`反饋失敗: ${e.message}`, 'error');
            this.debugLog(`反饋失敗: ${e.message}`, 'error');
        }
    }

    async _updateAnnotationPanel() {
        try {
            const res = await fetch(`${this._getApiBaseUrl()}/api/feedback/stats`);
            const stats = await res.json();

            if (!this.annotationContent) return;

            if (stats.total === 0) {
                this.annotationContent.innerHTML = '<div class="annotation-empty">尚無反饋資料</div>';
                this.annotationFooter.textContent = '總反饋: 0 筆';
                return;
            }

            let html = '';
            const byClass = stats.by_class || {};
            for (const [cls, counts] of Object.entries(byClass)) {
                const total = (counts.confirm || 0) + (counts.correct || 0) + (counts.false_positive || 0);
                const fpRatio = (counts.false_positive || 0) / total;

                let statusClass = 'good';
                let statusIcon = '✅';
                if (total < 5) {
                    statusClass = 'warning';
                    statusIcon = '⚠️';
                } else if (fpRatio > 0.5) {
                    statusClass = 'bad';
                    statusIcon = '❌';
                }

                html += `<div class="annotation-item">
                    <span class="class-name">${cls}</span>
                    <span class="count ${statusClass}">${statusIcon} ${total} 次</span>
                </div>`;
            }

            this.annotationContent.innerHTML = html;
            this.annotationFooter.textContent = `總反饋: ${stats.total} 筆`;
        } catch (e) {
            // 靜默失敗，不影響使用
        }
    }

    async _loadCorrectionClassList(overlay, detection, croppedImage) {
        // 載入已註冊類別清單，供使用者直接點選正確類別
        const listDiv = overlay.querySelector('#correctionClassList');
        if (!listDiv) return;

        // 設定 5 秒超時
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);

        try {
            const res = await fetch(`${this._getApiBaseUrl()}/api/classes`, {
                signal: controller.signal
            });
            clearTimeout(timeoutId);

            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            const classes = (data.classes || []).filter(c => c.name_en !== detection.class_name);

            if (classes.length === 0) {
                listDiv.innerHTML = '<div style="color: var(--text-secondary); padding: 8px; text-align: center;">無其他類別</div>';
                return;
            }

            listDiv.innerHTML = classes.map(c => {
                const label = c.name_cn ? `${c.name_cn} (${c.name_en})` : c.name_en;
                return `<button class="correction-class-btn" data-class-en="${c.name_en}">${label}</button>`;
            }).join('');

            // 點選類別按鈕直接提交
            listDiv.querySelectorAll('.correction-class-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const classEn = btn.dataset.classEn;
                    this._submitFeedback('correct', detection, classEn, croppedImage);
                    overlay.remove();
                });
            });
        } catch (e) {
            clearTimeout(timeoutId);
            const errorMsg = e.name === 'AbortError' ? '載入逾時，請手動輸入' : `載入失敗: ${e.message}`;
            listDiv.innerHTML = `<div style="color: var(--text-secondary); padding: 8px;">${errorMsg}</div>`;
        }
    }

    // ============================================
    // 物品註冊功能
    // ============================================

    _getApiBaseUrl() {
        // 根據頁面位置推導 HTTP API 基底 URL
        return window.location.origin;
    }

    async loadClasses() {
        try {
            const res = await fetch(`${this._getApiBaseUrl()}/api/classes`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();

            this._renderClassList(data.classes || [], data.active_count, data.max_active);
        } catch (e) {
            if (this.classList) {
                this.classList.innerHTML = `<div class="empty-state"><p>無法載入類別列表</p></div>`;
            }
            this.debugLog(`載入類別列表失敗: ${e.message}`, 'warning');
        }
    }

    _renderClassList(classes, activeCount, maxActive) {
        if (!this.classList) return;

        // 更新槽位計數器
        const header = this.classList.closest('.card')?.querySelector('.class-list-header span');
        if (header && activeCount !== undefined) {
            header.textContent = `啟用中 ${activeCount}/${maxActive}`;
        }

        if (!classes || classes.length === 0) {
            this.classList.innerHTML = `<div class="empty-state"><p>尚無偵測類別</p></div>`;
            return;
        }

        this.classList.innerHTML = classes.map(c => {
            const displayName = c.name_cn || c.name_en;
            const isCustom = c.source === 'custom';
            const isActive = c.active !== false;
            const activeClass = isActive ? 'active' : 'inactive';

            // 啟用/停用切換按鈕
            const toggleBtn = `<button class="tag-toggle" data-name="${c.name_en}" data-active="${isActive}" title="${isActive ? '停用' : '啟用'}">${isActive ? '●' : '○'}</button>`;

            // 自訂類別才有移除按鈕
            const removeBtn = isCustom
                ? `<button class="tag-remove" data-name="${c.name_en}" title="移除">&times;</button>`
                : '';

            return `<div class="class-tag ${c.source} ${activeClass}">
                ${toggleBtn}
                <span class="tag-name-cn">${displayName}</span>
                <span class="tag-name-en">${c.name_en}</span>
                ${removeBtn}
            </div>`;
        }).join('');

        // 綁定切換按鈕事件
        this.classList.querySelectorAll('.tag-toggle').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const nameEn = e.currentTarget.dataset.name;
                const isActive = e.currentTarget.dataset.active === 'true';
                this.toggleClass(nameEn, !isActive);
            });
        });

        // 綁定移除按鈕事件
        this.classList.querySelectorAll('.tag-remove').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const nameEn = e.target.dataset.name;
                this.removeClass(nameEn);
            });
        });
    }

    async addClass() {
        const nameCn = (this.newClassCnInput?.value || '').trim();
        const nameEn = (this.newClassEnInput?.value || '').trim();

        if (!nameCn) {
            this.showNotification('請輸入中文名稱', 'warning');
            this.newClassCnInput?.focus();
            return;
        }

        try {
            this.addClassBtn.disabled = true;
            this.addClassBtn.textContent = '新增中...';

            const res = await fetch(`${this._getApiBaseUrl()}/api/classes`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name_cn: nameCn, name_en: nameEn }),
            });

            const data = await res.json();

            if (data.error === 'slots_full') {
                // 槽位已滿，顯示替換建議
                this._showSlotFullDialog(data, nameCn, nameEn);
                return;
            }

            if (data.error) {
                this.showNotification(data.error, 'warning');
                return;
            }

            if (data.success) {
                this.showNotification(data.message, 'success');
                this.newClassEnInput.value = '';
                this.newClassCnInput.value = '';
                await this.loadClasses();
            }
        } catch (e) {
            this.showNotification(`新增失敗: ${e.message}`, 'error');
            this.debugLog(`新增類別失敗: ${e.message}`, 'error');
        } finally {
            if (this.addClassBtn) {
                this.addClassBtn.disabled = false;
                this.addClassBtn.textContent = '新增物品';
            }
        }
    }

    _showSlotFullDialog(data, pendingCn, pendingEn) {
        /**
         * 顯示槽位已滿的替換對話框
         * 建議停用 LRU 類別，讓使用者確認後自動替換
         */
        const lru = data.lru_suggestion;
        if (!lru) {
            this.showNotification(data.message, 'warning');
            return;
        }

        const lruLabel = lru.name_cn ? `${lru.name_cn}（${lru.name_en}）` : lru.name_en;
        const lastInfo = lru.last_detected
            ? `最後偵測：${lru.last_detected}`
            : '從未偵測到';

        // 建立覆蓋層
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.innerHTML = `
            <div class="slot-full-dialog">
                <h3>偵測槽位已滿（${data.active_count}/${data.max_active}）</h3>
                <p>建議停用最久未使用的類別：</p>
                <div class="lru-suggestion">
                    <span class="lru-name">${lruLabel}</span>
                    <span class="lru-info">${lastInfo}</span>
                </div>
                <p>停用後將自動新增「${pendingCn || pendingEn}」</p>
                <div class="slot-dialog-actions">
                    <button class="btn-confirm" id="slotConfirmBtn">確認替換</button>
                    <button class="btn-cancel" id="slotCancelBtn">取消</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);

        // 確認：先停用 LRU 類別，再新增
        overlay.querySelector('#slotConfirmBtn').addEventListener('click', async () => {
            overlay.remove();
            await this.toggleClass(lru.name_en, false);
            // 重新嘗試新增
            await this.addClass();
        });

        // 取消
        overlay.querySelector('#slotCancelBtn').addEventListener('click', () => {
            overlay.remove();
        });
    }

    async toggleClass(nameEn, active) {
        try {
            const res = await fetch(`${this._getApiBaseUrl()}/api/classes/toggle`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name_en: nameEn, active }),
            });

            const data = await res.json();

            if (data.error === 'slots_full') {
                this.showNotification(data.message, 'warning');
                return;
            }

            if (data.error) {
                this.showNotification(data.error, 'warning');
                return;
            }

            if (data.success) {
                this.showNotification(data.message, 'success');
                await this.loadClasses();
            }
        } catch (e) {
            this.showNotification(`切換失敗: ${e.message}`, 'error');
        }
    }

    async removeClass(nameEn) {
        try {
            const res = await fetch(`${this._getApiBaseUrl()}/api/classes`, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name_en: nameEn }),
            });

            const data = await res.json();

            if (data.error) {
                this.showNotification(data.error, 'warning');
                return;
            }

            if (data.success) {
                this.showNotification(data.message, 'success');
                await this.loadClasses();
            }
        } catch (e) {
            this.showNotification(`移除失敗: ${e.message}`, 'error');
        }
    }
}

// 初始化應用
document.addEventListener('DOMContentLoaded', () => {
    window.app = new YOLOWebApp();
});
