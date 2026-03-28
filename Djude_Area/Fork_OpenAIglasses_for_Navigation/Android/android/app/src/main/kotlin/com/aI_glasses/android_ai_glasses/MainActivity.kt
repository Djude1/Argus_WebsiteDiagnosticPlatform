package com.aI_glasses.android_ai_glasses

import android.app.ActivityManager
import android.content.Context
import android.provider.Settings
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private val CHANNEL = "com.aiglasses/app_control"

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "bringToForeground" -> {
                        bringAppToForeground()
                        result.success(true)
                    }
                    "isDeveloperMode" -> {
                        result.success(isDeveloperModeEnabled())
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

    /** 檢查手機是否開啟開發人員選項 */
    private fun isDeveloperModeEnabled(): Boolean {
        return Settings.Global.getInt(
            contentResolver,
            Settings.Global.DEVELOPMENT_SETTINGS_ENABLED,
            0
        ) == 1
    }
}
