# XIAO ESP32-S3 Sense YOLO11 Obstacle Avoidance

This project implements an obstacle avoidance system using a XIAO ESP32-S3 Sense and YOLO11.

## Hardware Setup

*   **Board**: XIAO ESP32-S3 Sense
*   **Camera**: OV2640 (connected to board)
*   **Mic**: I2S Digital Mic (MSM261D3526H1CPM)
*   **IMU**: ICM42688P (I2C)

## Pinout Configuration

*   **Camera**: Standard XIAO ESP32S3 Sense pinout.
*   **I2C IMU**: SDA (D4), SCL (D5).
*   **I2S Mic (PDM Mode)**: CLK (GPIO 42), DAT (GPIO 41).

## Software Setup (Windows)

This project uses `uv` for dependency management.

1.  **Install uv**:
    *   Open PowerShell.
    *   Run: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`

2.  **Clone the Repository**:
    *   `git clone <your-repo-url>`
    *   `cd <repo-folder>`

3.  **Run the Application**:
    *   First, ensure your ESP32 is running and you know its IP address (check the Serial Monitor).
    *   Run the Python script with the stream URL:
        ```bash
        uv run main.py --url http://<ESP32_IP>/stream
        ```
        *Example*: `uv run main.py --url http://192.168.1.123/stream`

## Firmware

The firmware is located in the `firmware/` directory.

1.  Open `firmware/main/main.ino` in Arduino IDE.
2.  Install `ESP32` board support.
3.  Select Board: "XIAO_ESP32S3" (or similar).
4.  Enable PSRAM: "OPI PSRAM".
5.  Upload.
6.  Open Serial Monitor (115200 baud) to view the IP address.
