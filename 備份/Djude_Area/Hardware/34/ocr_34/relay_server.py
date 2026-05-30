from flask import Flask, render_template_string, request, Response
import requests
import base64
import os

app = Flask(__name__)

# 配置區域
API_KEY = "AIzaSyD6EgZS9os8oXST0P0UEfoY1eN1XRVpNNc"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"

latest_frame_bytes = None

# 網頁介面：加入動畫提示與 Toast 通知
HTML_TEMPLATE = """
<!DOCTYPE html><html><head><title>智慧眼鏡高清調試</title><meta charset="utf-8">
<style>
    body { font-family: sans-serif; text-align: center; background: #2c3e50; color: white; padding: 20px; }
    .card { max-width: 850px; margin: auto; background: #34495e; padding: 20px; border-radius: 15px; box-shadow: 0 10px 20px rgba(0,0,0,0.3); }
    img { width: 100%; max-width: 800px; border-radius: 10px; border: 4px solid #ecf0f1; background: #000; }
    .btn { background: #e67e22; color: white; border: none; padding: 18px 30px; font-size: 20px; border-radius: 8px; cursor: pointer; margin-top: 20px; width: 100%; transition: 0.2s; font-weight: bold; }
    .btn:disabled { background: #7f8c8d; cursor: not-allowed; }
    #result { margin-top: 20px; padding: 20px; background: #ecf0f1; color: #2c3e50; text-align: left; font-size: 18px; border-radius: 8px; border-left: 8px solid #e67e22; }
    
    /* Toast 提示框樣式 */
    #toast {
        visibility: hidden; min-width: 250px; background-color: #27ae60; color: #fff; text-align: center;
        border-radius: 5px; padding: 16px; position: fixed; z-index: 1; left: 50%; bottom: 30px;
        transform: translateX(-50%); font-size: 17px;
    }
    #toast.show { visibility: visible; -webkit-animation: fadein 0.5s, fadeout 0.5s 2.5s; animation: fadein 0.5s, fadeout 0.5s 2.5s; }
    @keyframes fadein { from {bottom: 0; opacity: 0;} to {bottom: 30px; opacity: 1;} }
    @keyframes fadeout { from {bottom: 30px; opacity: 1;} to {bottom: 0; opacity: 0;} }
</style></head>
<body>
    <div class="card">
        <h2>智慧眼鏡 - 1 FPS 高清監控</h2>
        <img src="/video_feed" id="stream">
        <button class="btn" id="capBtn" onclick="capture()">📸 立即拍攝並辨識</button>
        <div id="result"><strong>AI 辨識結果：</strong><p id="ai_text">等待指令...</p></div>
    </div>
    <div id="toast">✅ 已成功送出拍攝請求！</div>

    <script>
        function showToast() {
            var x = document.getElementById("toast");
            x.className = "show";
            setTimeout(function(){ x.className = x.className.replace("show", ""); }, 3000);
        }

        function capture() {
            const btn = document.getElementById('capBtn');
            const resText = document.getElementById('ai_text');
            
            // 1. 顯示按下提示
            showToast();
            btn.disabled = true;
            btn.innerText = "⏳ 正在處理影像中...";
            resText.innerText = "🤖 AI 正在分析畫面，請稍候...";

            // 2. 發送辨識請求
            fetch('/identify', { method: 'POST' })
                .then(r => r.text())
                .then(data => { 
                    resText.innerText = data;
                    btn.disabled = false;
                    btn.innerText = "📸 立即拍攝並辨識";
                })
                .catch(err => {
                    resText.innerText = "連線失敗：" + err;
                    btn.disabled = false;
                });
        }
        setInterval(() => { document.getElementById('stream').src = "/video_feed?t=" + Date.now(); }, 1000);
    </script>
</body></html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/upload', methods=['POST'])
def upload():
    global latest_frame_bytes
    latest_frame_bytes = request.data
    with open("debug_image.jpg", "wb") as f:
        f.write(latest_frame_bytes)
    return "OK"

@app.route('/video_feed')
def video_feed():
    if latest_frame_bytes:
        return Response(latest_frame_bytes, mimetype='image/jpeg')
    return "No Frame", 404

@app.route('/identify', methods=['POST'])
def identify():
    if latest_frame_bytes is None: return "尚未接收到影像"
    try:
        b64 = base64.b64encode(latest_frame_bytes).decode('utf-8')
        payload = {
            "contents": [{"parts": [
                {"text": "你是一位視障輔助員，請詳細辨識圖中文字與環境。"},
                {"inline_data": {"mime_type": "image/jpeg", "data": b64}}
            ]}]
        }
        res = requests.post(GEMINI_URL, json=payload, timeout=35)
        return res.json()['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"辨識失敗: {str(e)}"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)