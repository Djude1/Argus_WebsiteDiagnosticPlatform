package com.aI_glasses.android_ai_glasses

import android.app.ActivityManager
import android.content.Context
import android.content.Intent
import android.media.AudioManager
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File

class MainActivity : FlutterActivity() {
    private val CHANNEL = "com.aiglasses/app_control"

    // Maps 啟動前的原始媒體音量，用於導航結束後還原
    private var _savedMusicVolume: Int = -1

    // CPU 採樣狀態（讀 /proc/self/stat，APP 自身 CPU 時間，SELinux 允許）
    private var _lastCpuTicks: Long = 0L
    private var _lastCpuTimeMs: Long = 0L
    private var _lastCpuPercent: Int = 0

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "bringToForeground" -> {
                        bringAppToForeground()
                        result.success(true)
                    }
                    "launchMapsBackground" -> {
                        val uri = call.argument<String>("uri") ?: ""
                        launchMapsAndStayInApp(uri)
                        result.success(true)
                    }
                    "stopMapsNavigation" -> {
                        stopGoogleMapsNavigation()
                        result.success(true)
                    }
                    "isDeveloperMode" -> {
                        result.success(isDeveloperModeEnabled())
                    }
                    "getCpuPercent" -> {
                        result.success(readAppCpuPercent())
                    }
                    else -> result.notImplemented()
                }
            }
    }

    /** 將 APP 切回前景 */
    private fun bringAppToForeground() {
        val am = getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        am.appTasks.firstOrNull()?.moveToFront()
    }

    /**
     * 在背景啟動 Google Maps 導航，APP 保持前景不跳走。
     * 原理：先啟動 Maps Intent，然後立即把自己拉回前景。
     * 使用 Handler.postDelayed 確保 Maps 已收到 Intent 後再切回。
     *
     * 音量策略：Maps 語音走 STREAM_MUSIC，我們的 TTS 走 STREAM_TTS。
     * 啟動 Maps 前把 STREAM_MUSIC 降到 30%，讓 Maps 變成低聲背景引導，
     * 避障警告（STREAM_TTS）維持全量，優先傳達給使用者。
     */
    private fun launchMapsAndStayInApp(uriString: String) {
        try {
            // 壓低媒體音量（Maps 語音會使用此 stream）
            lowerMusicVolume()

            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(uriString)).apply {
                setPackage("com.google.android.apps.maps")
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            startActivity(intent)

            // 極短延遲後立即切回 APP（讓 Maps 有時間接收 Intent）
            val handler = Handler(Looper.getMainLooper())
            handler.postDelayed({ bringAppToForeground() }, 500)
            handler.postDelayed({ bringAppToForeground() }, 1500)
            handler.postDelayed({ bringAppToForeground() }, 3000)
        } catch (e: Exception) {
            // Maps 未安裝，靜默失敗
        }
    }

    /** 將 STREAM_MUSIC 降到 30%，儲存原始音量以便還原 */
    private fun lowerMusicVolume() {
        try {
            val am = getSystemService(Context.AUDIO_SERVICE) as AudioManager
            val maxVol = am.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
            _savedMusicVolume = am.getStreamVolume(AudioManager.STREAM_MUSIC)
            val lowVol = (maxVol * 0.3).toInt().coerceAtLeast(1)
            am.setStreamVolume(AudioManager.STREAM_MUSIC, lowVol, 0)
        } catch (_: Exception) {}
    }

    /** 還原 STREAM_MUSIC 到 Maps 啟動前的音量 */
    private fun restoreMusicVolume() {
        try {
            if (_savedMusicVolume >= 0) {
                val am = getSystemService(Context.AUDIO_SERVICE) as AudioManager
                am.setStreamVolume(AudioManager.STREAM_MUSIC, _savedMusicVolume, 0)
                _savedMusicVolume = -1
            }
        } catch (_: Exception) {}
    }

    /** 停止 Google Maps 導航（關閉其 Activity），並還原媒體音量 */
    private fun stopGoogleMapsNavigation() {
        try {
            restoreMusicVolume()
            val am = getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
            // 找到 Google Maps 的 task 並移除
            for (task in am.appTasks) {
                val info = task.taskInfo
                if (info.baseActivity?.packageName == "com.google.android.apps.maps") {
                    task.finishAndRemoveTask()
                    return
                }
            }
        } catch (_: Exception) {}
    }

    /**
     * 讀取 APP 自身 CPU 使用率（%）。
     * 使用 /proc/self/stat（APP 自己的 process stat，SELinux 允許），
     * 兩次快照差分計算 utime+stime 的消耗速率，除以 CPU 核心數得到 %。
     */
    private fun readAppCpuPercent(): Int {
        return try {
            val parts = File("/proc/self/stat").readText().trim().split(" ")
            val utime = parts[13].toLong()
            val stime = parts[14].toLong()
            val totalTicks = utime + stime
            val nowMs = System.currentTimeMillis()

            val elapsedMs   = nowMs - _lastCpuTimeMs
            val tickDiff    = totalTicks - _lastCpuTicks
            _lastCpuTicks   = totalTicks
            _lastCpuTimeMs  = nowMs

            if (elapsedMs <= 0 || _lastCpuTimeMs == nowMs) return _lastCpuPercent

            // Android 時鐘頻率通常為 100 ticks/s
            val hz       = 100L
            val cores    = Runtime.getRuntime().availableProcessors().coerceAtLeast(1)
            val pct = (tickDiff * 1000L / hz / elapsedMs * 100L / cores).toInt()
            _lastCpuPercent = pct.coerceIn(0, 100)
            _lastCpuPercent
        } catch (_: Exception) {
            _lastCpuPercent
        }
    }

    /** 檢查手機是否開啟開發人員選項 */
    private fun isDeveloperModeEnabled(): Boolean {
        return Settings.Global.getInt(
            contentResolver,
            Settings.Global.DEVELOPMENT_SETTINGS_ENABLED,
            0
        ) == 1
    }
}
