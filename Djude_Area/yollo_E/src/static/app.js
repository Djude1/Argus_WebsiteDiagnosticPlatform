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
        const defaultHost = window.location.hostname || 'localhost';
        const defaultPort = window.location.port || '8000';
        this.serverUrlInput.value = `ws://${defaultHost}:${defaultPort}`;

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

        this.showNotification('準備就緒，點擊「開始偵測」啟動', 'success');
    }

    async start() {
        if (this.isRunning) return;

        try {
            // 取得解析度設定
            const [width, height] = this.resolutionSelect.value.split('x').map(Number);
            const frameRate = parseInt(this.frameRateSelect.value);

            // 請求攝影機權限
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
            console.error('啟動失敗:', error);
            this.showNotification(`啟動失敗: ${error.message}`, 'error');
        }
    }

    async connectWebSocket() {
        const serverUrl = this.serverUrlInput.value;

        return new Promise((resolve, reject) => {
            try {
                // 結果 WebSocket
                this.resultSocket = new WebSocket(`${serverUrl}/ws/result`);

                this.resultSocket.onopen = () => {
                    console.log('結果 WebSocket 已連接');
                    this.connectionStatus.className = 'connected';
                    resolve();
                };

                this.resultSocket.onmessage = (event) => {
                    this.handleDetectionResult(JSON.parse(event.data));
                };

                this.resultSocket.onerror = (error) => {
                    console.error('結果 WebSocket 錯誤:', error);
                    this.connectionStatus.className = 'disconnected';
                };

                this.resultSocket.onclose = () => {
                    console.log('結果 WebSocket 已斷開');
                    this.connectionStatus.className = 'disconnected';
                };

                // 視頻 WebSocket
                this.videoSocket = new WebSocket(`${serverUrl}/ws/video`);

                this.videoSocket.onopen = () => {
                    console.log('視頻 WebSocket 已連接');
                };

                this.videoSocket.onerror = (error) => {
                    console.error('視頻 WebSocket 錯誤:', error);
                    reject(error);
                };

            } catch (error) {
                reject(error);
            }
        });
    }

    startFrameSender(frameRate) {
        const interval = 1000 / frameRate;

        this.frameInterval = setInterval(() => {
            if (!this.isRunning || !this.videoSocket || this.videoSocket.readyState !== WebSocket.OPEN) {
                return;
            }

            this.sendFrame();
        }, interval);
    }

    sendFrame() {
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
        this.videoSocket.send(dataUrl);

        // 更新統計
        this.stats.framesSent++;
        this.totalFrames.textContent = this.stats.framesSent;
    }

    handleDetectionResult(result) {
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
    }
}

// 初始化應用
document.addEventListener('DOMContentLoaded', () => {
    window.app = new YOLOWebApp();
});
