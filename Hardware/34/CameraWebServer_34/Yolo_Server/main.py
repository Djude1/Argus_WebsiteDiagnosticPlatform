import cv2
import requests
import numpy as np

# 這是你剛才成功的 IP 地址，注意端口是 81 且路徑是 /stream
url = "http://192.168.137.189:81/stream"

def main():
    # 使用 OpenCV 的 VideoCapture 抓取網路串流
    cap = cv2.VideoCapture(url)

    if not cap.isOpened():
        print("錯誤：無法開啟影像流。請確認 ESP32 是否在同一個網路，且網頁介面已關閉。")
        return

    print("正在抓取影像... 按下 'q' 鍵可結束程式。")

    while True:
        # 讀取每一幀
        ret, frame = cap.read()

        if not ret:
            print("無法讀取影格，正在重新連線...")
            cap.open(url)
            continue

        # --- 這裡就是之後放置 YOLO 辨識程式碼的地方 ---
        # 範例：results = model(frame) 
        # ------------------------------------------

        # 顯示影像視窗
        cv2.imshow("XIAO ESP32-S3 Vision Aid", frame)

        # 按下 'q' 鍵退出循環
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # 釋放資源
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()