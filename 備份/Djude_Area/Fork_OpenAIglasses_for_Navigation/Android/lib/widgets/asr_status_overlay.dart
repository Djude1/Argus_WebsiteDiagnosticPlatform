// lib/widgets/asr_status_overlay.dart
// 全域 ASR 狀態 overlay — 套用到所有頁面右上角，讓使用者隨時看到：
//   ① 麥克風是否被 server 偵測到聲音（listening / processing）
//   ② 即時辨識中的文字（partial），確認 server 真的有聽懂

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/app_provider.dart';

class AsrStatusOverlay extends StatefulWidget {
  final Widget child;
  const AsrStatusOverlay({super.key, required this.child});

  @override
  State<AsrStatusOverlay> createState() => _AsrStatusOverlayState();
}

class _AsrStatusOverlayState extends State<AsrStatusOverlay>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pulseCtrl;

  @override
  void initState() {
    super.initState();
    // 不在 initState 直接 repeat：standby 時無 chip 顯示，動畫白跑浪費 CPU
    // 改由 _buildChip 依 isListening 控制啟停（透過 addPostFrameCallback 避開 build 期間呼叫）
    _pulseCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    );
  }

  @override
  void dispose() {
    _pulseCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        widget.child,
        // 不攔截事件：底層按鈕仍可點擊
        Positioned(
          top: 0,
          left: 0,
          right: 0,
          child: IgnorePointer(
            child: SafeArea(
              child: Consumer<AppProvider>(
                builder: (_, app, __) => _buildChip(app),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildChip(AppProvider app) {
    final state = app.asrState;
    if (state == 'standby') {
      // standby 不顯示 chip，順便停止動畫節省 CPU
      if (_pulseCtrl.isAnimating) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) _pulseCtrl.stop();
        });
      }
      return const SizedBox.shrink();
    }

    final isListening = state == 'listening';
    // listening: 0.8s 快 pulse（強提示「正在收音」）
    // processing: 1.4s 慢 pulse（柔和提示「AI 處理中」，視覺上跟 listening 區分）
    final desiredDuration = isListening
        ? const Duration(milliseconds: 800)
        : const Duration(milliseconds: 1400);
    if (_pulseCtrl.duration != desiredDuration) {
      _pulseCtrl.duration = desiredDuration;
    }
    if (!_pulseCtrl.isAnimating) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _pulseCtrl.repeat(reverse: true);
      });
    }
    // 顏色刻意拉開對比：amber 黃 vs cyan 藍（比 blue.700 更亮、更醒目）
    final color   = isListening ? Colors.amber.shade800 : Colors.cyan.shade700;
    final icon    = isListening ? Icons.mic            : Icons.auto_awesome;
    final label   = isListening ? '聆聽中'             : 'AI 處理中';
    final partial = app.asrPartialText.trim();

    Widget chip = Container(
      margin: const EdgeInsets.only(top: 8, right: 12),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: color.withOpacity(0.88),
        borderRadius: BorderRadius.circular(20),
        boxShadow: const [
          BoxShadow(color: Colors.black54, blurRadius: 6, offset: Offset(0, 2)),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: Colors.white, size: 18),
          const SizedBox(width: 6),
          Text(label, style: const TextStyle(
            color: Colors.white, fontSize: 14, fontWeight: FontWeight.bold,
          )),
          if (partial.isNotEmpty) ...[
            const SizedBox(width: 8),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 220),
              child: Text(
                partial,
                style: const TextStyle(color: Colors.white, fontSize: 13),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ],
      ),
    );

    // 兩種狀態都套用 pulse，但節奏與不透明度範圍不同 →
    // listening 快速明滅（警覺感）；processing 柔和呼吸（穩定感）
    final beginOpacity = isListening ? 0.55 : 0.75;
    chip = FadeTransition(
      opacity: Tween<double>(begin: beginOpacity, end: 1.0).animate(_pulseCtrl),
      child: chip,
    );

    return Align(
      alignment: Alignment.topRight,
      child: Semantics(
        label: isListening
            ? (partial.isEmpty
                ? '正在聆聽您的語音指令'
                : '正在聆聽，目前辨識：$partial')
            : '正在處理語音指令',
        liveRegion: true,
        child: chip,
      ),
    );
  }
}
