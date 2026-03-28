// lib/screens/nav_destination_screen.dart
// GPS 導航 — 目的地選擇畫面
// 視障友善：大按鈕、高對比、TalkBack 相容、觸覺回饋

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:geolocator/geolocator.dart';
import 'package:geocoding/geocoding.dart';
import '../providers/app_provider.dart';

/// 地點類別對應圖示與顏色
const _categoryMeta = <String, ({IconData icon, Color color, String label})>{
  'home':    (icon: Icons.home,          color: Color(0xFF1565C0), label: '住家'),
  'work':    (icon: Icons.work,          color: Color(0xFF00695C), label: '公司'),
  'medical': (icon: Icons.local_hospital,color: Color(0xFFC62828), label: '醫療'),
  'transit': (icon: Icons.directions_bus, color: Color(0xFF6A1B9A), label: '交通'),
  'food':    (icon: Icons.restaurant,    color: Color(0xFFE65100), label: '餐飲'),
  'other':   (icon: Icons.place,         color: Color(0xFF37474F), label: '其他'),
};

class NavDestinationScreen extends StatefulWidget {
  const NavDestinationScreen({super.key});

  @override
  State<NavDestinationScreen> createState() => _NavDestinationScreenState();
}

class _NavDestinationScreenState extends State<NavDestinationScreen> {
  @override
  void initState() {
    super.initState();
    // 進入導航頁時自動請求位置權限
    _requestLocationPermission();
  }

  /// 請求位置權限（視障友善：語音提示狀態）
  Future<void> _requestLocationPermission() async {
    final app = context.read<AppProvider>();
    try {
      final serviceEnabled = await Geolocator.isLocationServiceEnabled();
      if (!serviceEnabled) {
        app.speak('請開啟手機定位功能');
        return;
      }

      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
        if (permission == LocationPermission.denied) {
          app.speak('需要位置權限才能導航');
          return;
        }
      }
      if (permission == LocationPermission.deniedForever) {
        app.speak('位置權限已被永久拒絕，請至設定中開啟');
        return;
      }
    } catch (e) {
      debugPrint('[NavDest] 位置權限請求失敗: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppProvider>();
    final places = app.places;

    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // ── 頂部標題列 ─────────────────────────────────────────────
            _Header(onBack: () => Navigator.pop(context)),

            // ── 新增地點按鈕 ───────────────────────────────────────────
            _ActionBlock(
              label: '新增常用地點',
              icon: Icons.add_location_alt,
              color: const Color(0xFF2E7D32),
              semantics: '新增常用地點，點擊後輸入地點名稱與地址',
              onTap: () => _showPlaceEditor(context, app),
            ),

            const SizedBox(height: 2),

            // ── 地點列表 ───────────────────────────────────────────────
            Expanded(
              child: places.isEmpty
                  ? const _EmptyHint()
                  : ListView.separated(
                      padding: const EdgeInsets.only(bottom: 40),
                      itemCount: places.length,
                      separatorBuilder: (_, __) => const SizedBox(height: 2),
                      itemBuilder: (_, i) => _PlaceTile(
                        place: places[i],
                        onSelect: () => _onPlaceSelected(context, app, places[i]),
                        onEdit:   () => _showPlaceEditor(context, app, place: places[i]),
                        onDelete: () => _confirmDelete(context, app, places[i]),
                      ),
                    ),
            ),
          ],
        ),
      ),
    );
  }

  /// 選擇地點 → 啟動 GPS 導航（背景 Google Maps 報路 + 前景避障）
  void _onPlaceSelected(BuildContext context, AppProvider app,
      Map<String, dynamic> place) {
    HapticFeedback.heavyImpact();
    final lat = (place['latitude'] as num?)?.toDouble() ?? 0;
    final lng = (place['longitude'] as num?)?.toDouble() ?? 0;
    if (lat == 0 && lng == 0) {
      // 沒有座標時語音提示，不離開頁面
      app.speak('此地點沒有座標，請先編輯地點填入地址');
      return;
    }
    app.startGpsNavigation(place);
    Navigator.pop(context);
  }

  /// 刪除確認
  void _confirmDelete(BuildContext context, AppProvider app,
      Map<String, dynamic> place) {
    final name = place['name'] as String;
    final id = place['id'] as int;
    app.speak('確認刪除$name？');
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF1A1A2E),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: Text('刪除「$name」？',
            style: const TextStyle(
                fontSize: 22, fontWeight: FontWeight.bold, color: Colors.white)),
        content: const Text('刪除後無法復原',
            style: TextStyle(fontSize: 16, color: Colors.white70)),
        actions: [
          Semantics(
            label: '取消刪除',
            button: true,
            child: TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('取消',
                  style: TextStyle(fontSize: 18, color: Colors.white54)),
            ),
          ),
          Semantics(
            label: '確認刪除$name',
            button: true,
            child: ElevatedButton(
              style: ElevatedButton.styleFrom(backgroundColor: Colors.red.shade800),
              onPressed: () {
                app.deletePlace(id);
                app.speak('已刪除$name');
                Navigator.pop(ctx);
              },
              child: const Text('刪除',
                  style: TextStyle(fontSize: 18, color: Colors.white)),
            ),
          ),
        ],
      ),
    );
  }

  /// 新增 / 編輯地點（儲存時自動將地址轉座標）
  void _showPlaceEditor(BuildContext context, AppProvider app,
      {Map<String, dynamic>? place}) {
    app.speak(place != null ? '編輯地點' : '新增地點');
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => _PlaceEditorPage(
          place: place,
          onSave: (name, address, category) async {
            // 嘗試將地址轉為經緯度
            double lat = (place?['latitude'] as num?)?.toDouble() ?? 0;
            double lng = (place?['longitude'] as num?)?.toDouble() ?? 0;
            if (address.isNotEmpty) {
              try {
                final locations = await locationFromAddress(address);
                if (locations.isNotEmpty) {
                  lat = locations.first.latitude;
                  lng = locations.first.longitude;
                  debugPrint('[Geocoding] $address -> ($lat, $lng)');
                }
              } catch (e) {
                debugPrint('[Geocoding] 地址轉座標失敗: $e');
                // 轉換失敗不阻斷儲存，保留原座標
              }
            }

            if (place != null) {
              await app.updatePlace(place['id'] as int,
                  name: name, address: address, category: category,
                  latitude: lat, longitude: lng);
              app.speak('已更新$name');
            } else {
              await app.addPlace(
                  name: name, address: address, category: category,
                  latitude: lat, longitude: lng);
              app.speak('已新增$name');
            }
          },
        ),
      ),
    );
  }
}

// ════════════════════════════════════════════════════════════════════════════════
// 頂部標題列
// ════════════════════════════════════════════════════════════════════════════════
class _Header extends StatelessWidget {
  final VoidCallback onBack;
  const _Header({required this.onBack});

  @override
  Widget build(BuildContext context) {
    return Container(
      color: const Color(0xFF0D0D0D),
      padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
      child: Row(
        children: [
          Semantics(
            label: '返回上一頁',
            button: true,
            child: GestureDetector(
              onTap: () {
                HapticFeedback.mediumImpact();
                onBack();
              },
              child: const Padding(
                padding: EdgeInsets.all(8),
                child: Icon(Icons.arrow_back, color: Colors.white, size: 32),
              ),
            ),
          ),
          const SizedBox(width: 12),
          const Expanded(
            child: Text(
              '選擇目的地',
              style: TextStyle(
                  fontSize: 26,
                  fontWeight: FontWeight.bold,
                  color: Colors.white),
            ),
          ),
        ],
      ),
    );
  }
}

// ════════════════════════════════════════════════════════════════════════════════
// 無地點提示
// ════════════════════════════════════════════════════════════════════════════════
class _EmptyHint extends StatelessWidget {
  const _EmptyHint();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Semantics(
        label: '尚未儲存任何地點，請點擊上方新增常用地點',
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.add_location, size: 80, color: Colors.white24),
            const SizedBox(height: 16),
            const Text(
              '尚未儲存任何地點',
              style: TextStyle(fontSize: 22, color: Colors.white38),
            ),
            const SizedBox(height: 8),
            const Text(
              '請點擊上方「新增常用地點」',
              style: TextStyle(fontSize: 16, color: Colors.white24),
            ),
          ],
        ),
      ),
    );
  }
}

// ════════════════════════════════════════════════════════════════════════════════
// 操作色塊按鈕（新增地點）
// ════════════════════════════════════════════════════════════════════════════════
class _ActionBlock extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color color;
  final String semantics;
  final VoidCallback onTap;

  const _ActionBlock({
    required this.label,
    required this.icon,
    required this.color,
    required this.semantics,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: semantics,
      button: true,
      child: GestureDetector(
        onTap: () {
          HapticFeedback.heavyImpact();
          onTap();
        },
        child: Container(
          color: color,
          constraints: const BoxConstraints(minHeight: 80),
          padding: const EdgeInsets.symmetric(vertical: 18, horizontal: 24),
          child: Row(
            children: [
              Icon(icon, size: 36, color: Colors.white),
              const SizedBox(width: 16),
              Text(label,
                  style: const TextStyle(
                      fontSize: 26,
                      fontWeight: FontWeight.bold,
                      color: Colors.white)),
            ],
          ),
        ),
      ),
    );
  }
}

// ════════════════════════════════════════════════════════════════════════════════
// 地點列表項目
// ════════════════════════════════════════════════════════════════════════════════
class _PlaceTile extends StatelessWidget {
  final Map<String, dynamic> place;
  final VoidCallback onSelect;
  final VoidCallback onEdit;
  final VoidCallback onDelete;

  const _PlaceTile({
    required this.place,
    required this.onSelect,
    required this.onEdit,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    final name     = place['name'] as String? ?? '';
    final address  = place['address'] as String? ?? '';
    final category = place['category'] as String? ?? 'other';
    final meta     = _categoryMeta[category] ?? _categoryMeta['other']!;

    return Semantics(
      label: '$name，${meta.label}，${address.isNotEmpty ? address : '無地址'}。'
          '點擊開始導航，長按編輯或刪除',
      button: true,
      child: GestureDetector(
        onTap: () {
          HapticFeedback.heavyImpact();
          onSelect();
        },
        onLongPress: () {
          HapticFeedback.mediumImpact();
          _showActions(context);
        },
        child: Container(
          color: meta.color.withValues(alpha: 0.85),
          constraints: const BoxConstraints(minHeight: 90),
          padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 24),
          child: Row(
            children: [
              Icon(meta.icon, size: 40, color: Colors.white),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(name,
                        style: const TextStyle(
                            fontSize: 26,
                            fontWeight: FontWeight.bold,
                            color: Colors.white)),
                    if (address.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Text(address,
                            style: const TextStyle(
                                fontSize: 16, color: Colors.white70),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis),
                      ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, size: 32, color: Colors.white54),
            ],
          ),
        ),
      ),
    );
  }

  void _showActions(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1A1A2E),
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(16))),
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(height: 12),
            Container(width: 40, height: 4,
                decoration: BoxDecoration(
                    color: Colors.white24,
                    borderRadius: BorderRadius.circular(2))),
            const SizedBox(height: 20),
            _SheetAction(
              icon: Icons.edit,
              label: '編輯地點',
              onTap: () { Navigator.pop(ctx); onEdit(); },
            ),
            _SheetAction(
              icon: Icons.delete,
              label: '刪除地點',
              color: Colors.red.shade300,
              onTap: () { Navigator.pop(ctx); onDelete(); },
            ),
            const SizedBox(height: 16),
          ],
        ),
      ),
    );
  }
}

class _SheetAction extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;

  const _SheetAction({
    required this.icon,
    required this.label,
    required this.onTap,
    this.color = Colors.white,
  });

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: label,
      button: true,
      child: ListTile(
        leading: Icon(icon, color: color, size: 28),
        title: Text(label,
            style: TextStyle(fontSize: 22, color: color)),
        onTap: () {
          HapticFeedback.mediumImpact();
          onTap();
        },
        contentPadding: const EdgeInsets.symmetric(horizontal: 24, vertical: 4),
      ),
    );
  }
}

// ════════════════════════════════════════════════════════════════════════════════
// 地點編輯頁（新增 / 編輯）— 全螢幕表單，大輸入框
// ════════════════════════════════════════════════════════════════════════════════
class _PlaceEditorPage extends StatefulWidget {
  final Map<String, dynamic>? place;
  final Future<void> Function(String name, String address, String category) onSave;

  const _PlaceEditorPage({this.place, required this.onSave});

  @override
  State<_PlaceEditorPage> createState() => _PlaceEditorPageState();
}

class _PlaceEditorPageState extends State<_PlaceEditorPage> {
  final _nameCtrl    = TextEditingController();
  final _addressCtrl = TextEditingController();
  String _category   = 'other';
  bool _saving       = false;

  bool get _isEdit => widget.place != null;

  @override
  void initState() {
    super.initState();
    if (_isEdit) {
      _nameCtrl.text    = widget.place!['name']     as String? ?? '';
      _addressCtrl.text = widget.place!['address']  as String? ?? '';
      _category         = widget.place!['category'] as String? ?? 'other';
    }
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _addressCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final name = _nameCtrl.text.trim();
    if (name.isEmpty) {
      context.read<AppProvider>().speak('請輸入地點名稱');
      return;
    }
    setState(() => _saving = true);
    await widget.onSave(name, _addressCtrl.text.trim(), _category);
    if (mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // ── 標題列 ────────────────────────────────────────────────
            Container(
              color: const Color(0xFF0D0D0D),
              padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
              child: Row(
                children: [
                  Semantics(
                    label: '取消並返回',
                    button: true,
                    child: GestureDetector(
                      onTap: () => Navigator.pop(context),
                      child: const Padding(
                        padding: EdgeInsets.all(8),
                        child: Icon(Icons.close, color: Colors.white, size: 32),
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      _isEdit ? '編輯地點' : '新增地點',
                      style: const TextStyle(
                          fontSize: 26,
                          fontWeight: FontWeight.bold,
                          color: Colors.white),
                    ),
                  ),
                ],
              ),
            ),

            // ── 表單 ─────────────────────────────────────────────────
            Expanded(
              child: ListView(
                padding: const EdgeInsets.all(20),
                children: [
                  // 名稱
                  Semantics(
                    label: '地點名稱輸入框',
                    textField: true,
                    child: TextField(
                      controller: _nameCtrl,
                      style: const TextStyle(fontSize: 22, color: Colors.white),
                      decoration: _inputDeco('地點名稱', '例：家、公司、醫院'),
                      textInputAction: TextInputAction.next,
                    ),
                  ),
                  const SizedBox(height: 20),

                  // 地址
                  Semantics(
                    label: '地址輸入框',
                    textField: true,
                    child: TextField(
                      controller: _addressCtrl,
                      style: const TextStyle(fontSize: 22, color: Colors.white),
                      decoration: _inputDeco('地址', '例：台北市信義區信義路五段7號'),
                      textInputAction: TextInputAction.done,
                    ),
                  ),
                  const SizedBox(height: 24),

                  // 類別選擇
                  const Text('類別',
                      style: TextStyle(fontSize: 20, color: Colors.white70)),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 10,
                    runSpacing: 10,
                    children: _categoryMeta.entries.map((e) {
                      final selected = _category == e.key;
                      return Semantics(
                        label: '${e.value.label}${selected ? "，已選擇" : ""}',
                        button: true,
                        child: GestureDetector(
                          onTap: () {
                            HapticFeedback.selectionClick();
                            setState(() => _category = e.key);
                          },
                          child: AnimatedContainer(
                            duration: const Duration(milliseconds: 200),
                            padding: const EdgeInsets.symmetric(
                                horizontal: 18, vertical: 12),
                            decoration: BoxDecoration(
                              color: selected
                                  ? e.value.color
                                  : e.value.color.withValues(alpha: 0.3),
                              borderRadius: BorderRadius.circular(12),
                              border: selected
                                  ? Border.all(color: Colors.white, width: 2)
                                  : null,
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(e.value.icon,
                                    size: 24,
                                    color: selected
                                        ? Colors.white
                                        : Colors.white54),
                                const SizedBox(width: 8),
                                Text(e.value.label,
                                    style: TextStyle(
                                        fontSize: 18,
                                        color: selected
                                            ? Colors.white
                                            : Colors.white54,
                                        fontWeight: selected
                                            ? FontWeight.bold
                                            : FontWeight.normal)),
                              ],
                            ),
                          ),
                        ),
                      );
                    }).toList(),
                  ),
                ],
              ),
            ),

            // ── 儲存按鈕 ─────────────────────────────────────────────
            Semantics(
              label: _saving ? '儲存中' : '儲存地點',
              button: true,
              child: GestureDetector(
                onTap: _saving ? null : _save,
                child: Container(
                  color: _saving
                      ? const Color(0xFF424242)
                      : const Color(0xFF1565C0),
                  constraints: const BoxConstraints(minHeight: 80),
                  child: Center(
                    child: _saving
                        ? const CircularProgressIndicator(color: Colors.white)
                        : const Text('儲存',
                            style: TextStyle(
                                fontSize: 28,
                                fontWeight: FontWeight.bold,
                                color: Colors.white)),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  InputDecoration _inputDeco(String label, String hint) => InputDecoration(
        labelText: label,
        hintText: hint,
        labelStyle: const TextStyle(fontSize: 20, color: Colors.white54),
        hintStyle: const TextStyle(fontSize: 18, color: Colors.white24),
        enabledBorder: const OutlineInputBorder(
          borderSide: BorderSide(color: Colors.white24),
        ),
        focusedBorder: const OutlineInputBorder(
          borderSide: BorderSide(color: Colors.blue, width: 2),
        ),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 18),
      );
}
