// lib/widgets/status_banner.dart
// 導航狀態橫幅：顯示目前導航模式與連線狀態

import 'package:flutter/material.dart';
import '../core/theme.dart';

class StatusBanner extends StatelessWidget {
  final String navStateLabel;
  final bool   connected;

  const StatusBanner({
    super.key,
    required this.navStateLabel,
    required this.connected,
  });

  @override
  Widget build(BuildContext context) {
    final isIdle = navStateLabel == '待機' || navStateLabel == 'IDLE';
    final bg = connected
        ? (isIdle ? AppTheme.surface : AppTheme.primary)
        : AppTheme.colorStop;

    return Semantics(
      label: connected
          ? '目前狀態：$navStateLabel'
          : '伺服器未連線',
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          children: [
            Icon(
              connected ? Icons.circle : Icons.wifi_off,
              color: Colors.white,
              size: 14,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                connected ? navStateLabel : '連線中斷，重連中…',
                style: const TextStyle(
                  color:      Colors.white,
                  fontSize:   18,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
