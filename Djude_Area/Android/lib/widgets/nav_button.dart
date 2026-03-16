// lib/widgets/nav_button.dart
// 視障友善大按鈕元件
// - 最小 80dp 高度
// - 高對比色塊
// - Semantics 標記（TalkBack 支援）
// - 觸覺回饋（振動）

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class NavButton extends StatelessWidget {
  final String    label;
  final String    semanticsLabel; // TalkBack 朗讀文字
  final IconData  icon;
  final Color     color;
  final VoidCallback? onPressed;
  final bool      isActive;       // 是否為目前啟用中的模式

  const NavButton({
    super.key,
    required this.label,
    required this.icon,
    required this.color,
    this.semanticsLabel = '',
    this.onPressed,
    this.isActive = false,
  });

  @override
  Widget build(BuildContext context) {
    final effectiveLabel = semanticsLabel.isNotEmpty ? semanticsLabel : label;
    return Semantics(
      label:   effectiveLabel,
      button:  true,
      enabled: onPressed != null,
      child: Material(
        color: isActive ? color : color.withValues(alpha: 0.75),
        borderRadius: BorderRadius.circular(16),
        elevation: isActive ? 8 : 2,
        child: InkWell(
          borderRadius: BorderRadius.circular(16),
          onTap: onPressed == null
              ? null
              : () {
                  HapticFeedback.mediumImpact();
                  onPressed!();
                },
          child: Container(
            height: 90,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Row(
              children: [
                Icon(icon, color: Colors.white, size: 36),
                const SizedBox(width: 16),
                Expanded(
                  child: Text(
                    label,
                    style: const TextStyle(
                      color:      Colors.white,
                      fontSize:   22,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
                if (isActive)
                  const Icon(Icons.circle, color: Colors.white, size: 14),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
