// lib/screens/read_screen.dart
// 文件閱讀模式：視障者對準文件拍照 → Gemini OCR → TTS 朗讀全文 → 可追問

import 'dart:convert';
import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../providers/app_provider.dart';

// 畫面狀態
enum _ReadState { init, cameraReady, capturing, processing, result, asking, qa }

class ReadScreen extends StatefulWidget {
  const ReadScreen({super.key});

  @override
  State<ReadScreen> createState() => _ReadScreenState();
}

class _ReadScreenState extends State<ReadScreen> {
  CameraController? _cam;
  _ReadState _state = _ReadState.init;

  String _extractedText = '';
  final List<Map<String, String>> _qa = []; // [{q, a}, ...]
  final TextEditingController _inputCtrl = TextEditingController();
  final ScrollController      _scrollCtrl = ScrollController();

  @override
  void initState() {
    super.initState();
    _initCamera();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<AppProvider>().speak(
        '文件閱讀模式。請將手機對準文件，點擊畫面任何位置即可拍照辨識。',
      );
    });
  }

  @override
  void dispose() {
    // 離開時恢復導航相機串流
    context.read<AppProvider>().resumeCameraStreaming();
    _cam?.dispose();
    _inputCtrl.dispose();
    _scrollCtrl.dispose();
    super.dispose();
  }

  // ── 初始化相機 ──────────────────────────────────────────────────────────────
  Future<void> _initCamera() async {
    // 暫停導航相機，避免占用衝突
    await context.read<AppProvider>().pauseCameraStreaming();

    try {
      final cameras = await availableCameras();
      if (cameras.isEmpty) {
        _announce('找不到相機，無法使用文件閱讀功能。');
        return;
      }
      final back = cameras.firstWhere(
        (c) => c.lensDirection == CameraLensDirection.back,
        orElse: () => cameras.first,
      );
      final ctrl = CameraController(
        back,
        ResolutionPreset.high,
        enableAudio: false,
        imageFormatGroup: ImageFormatGroup.jpeg,
      );
      await ctrl.initialize();
      // 明確關閉閃光燈
      await ctrl.setFlashMode(FlashMode.off);
      if (!mounted) return;
      _cam = ctrl;
      setState(() => _state = _ReadState.cameraReady);
    } catch (e) {
      if (mounted) _announce('相機初始化失敗，請重新開啟頁面。');
    }
  }

  // ── 拍照並 OCR ──────────────────────────────────────────────────────────────
  Future<void> _capture() async {
    if (_state != _ReadState.cameraReady || _cam == null) return;
    HapticFeedback.mediumImpact();
    // 在第一個 await 前取得 provider，避免 async gap 後使用 context
    final app = context.read<AppProvider>();
    setState(() => _state = _ReadState.capturing);

    XFile? photo;
    try {
      photo = await _cam!.takePicture();
    } catch (_) {
      _announce('拍照失敗，請再試一次。');
      setState(() => _state = _ReadState.cameraReady);
      return;
    }

    setState(() => _state = _ReadState.processing);
    _announce('辨識中，請稍候…');
    app.addDebugMessage('[文件閱讀] 拍照完成，開始 OCR 辨識…');
    try {
      final bytes  = await photo.readAsBytes();
      final b64    = base64Encode(bytes);
      app.addDebugMessage('[文件閱讀] 圖片大小：${(bytes.length / 1024).toStringAsFixed(0)} KB');
      final result = await app.readDocument(b64);
      final text   = (result['text'] as String? ?? '').trim();

      if (text.isEmpty || text.contains('【圖片中未發現文字】')) {
        app.addDebugMessage('[文件閱讀] 未偵測到文字');
        _announce('未偵測到文字，請確認文件清晰可見後重新拍照。');
        setState(() => _state = _ReadState.cameraReady);
        return;
      }

      app.addDebugMessage('[文件閱讀] OCR 成功（${text.length} 字）：${text.length > 100 ? '${text.substring(0, 100)}…' : text}');

      setState(() {
        _extractedText = text;
        _state = _ReadState.result;
      });

      // 自動朗讀全文
      _announce(text);

      // 朗讀完畢，詢問是否需要說明
      if (mounted) {
        setState(() => _state = _ReadState.asking);
        await Future.delayed(const Duration(milliseconds: 600));
        _announce('文件閱讀完畢。需要我說明這份文件的內容嗎？');
      }
    } catch (e) {
      debugPrint('[DOC-READ] 辨識失敗: $e');
      app.addDebugMessage('[文件閱讀] 辨識失敗：$e');
      _announce('辨識失敗：$e');
      setState(() => _state = _ReadState.cameraReady);
    }
  }

  // ── 請求說明 ────────────────────────────────────────────────────────────────
  Future<void> _requestExplain() async {
    setState(() => _state = _ReadState.processing);
    _announce('正在分析文件，請稍候…');
    await _doAsk('請說明這份文件的主要內容、重點事項，以及我需要特別注意的地方。');
  }

  // ── 追問 ────────────────────────────────────────────────────────────────────
  Future<void> _submitQuestion() async {
    final q = _inputCtrl.text.trim();
    if (q.isEmpty) return;
    _inputCtrl.clear();
    FocusScope.of(context).unfocus();
    setState(() => _state = _ReadState.processing);
    await _doAsk(q);
  }

  Future<void> _doAsk(String question) async {
    final app = context.read<AppProvider>();
    app.addDebugMessage('[文件閱讀] 追問：$question');
    try {
      final result = await app.explainDocument(_extractedText, question);
      final answer = (result['answer'] as String? ?? '').trim();
      app.addDebugMessage('[文件閱讀] 回答：${answer.length > 100 ? '${answer.substring(0, 100)}…' : answer}');
      setState(() {
        _qa.add({'q': question, 'a': answer});
        _state = _ReadState.qa;
      });
      _announce(answer);
      _scrollToBottom();
    } catch (e) {
      debugPrint('[DOC-READ] 查詢失敗: $e');
      app.addDebugMessage('[文件閱讀] 查詢失敗：$e');
      _announce('查詢失敗：$e');
      setState(() => _state = _ReadState.qa);
    }
  }

  // ── 重新拍照 ────────────────────────────────────────────────────────────────
  void _retake() {
    setState(() {
      _extractedText = '';
      _qa.clear();
      _state = _ReadState.cameraReady;
    });
    _announce('請重新對準文件，點擊畫面拍照。');
  }

  void _announce(String text) =>
      context.read<AppProvider>().speak(text);

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onHorizontalDragEnd: (d) {
        if ((d.primaryVelocity ?? 0) > 300) Navigator.pop(context);
      },
      child: Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text('文件閱讀'),
        automaticallyImplyLeading: false,
      ),
      body: _buildBody(),
      ), // Scaffold
    );   // GestureDetector
  }

  Widget _buildBody() {
    switch (_state) {
      case _ReadState.init:
        return _buildLoading('初始化相機…');

      case _ReadState.cameraReady:
        return _buildCameraView();

      case _ReadState.capturing:
        return _buildLoading('拍照中…');

      case _ReadState.processing:
        return _buildLoading(
          _extractedText.isEmpty ? '辨識文字中…' : '分析文件中…',
          subtitle: _extractedText.isEmpty
              ? '文件越複雜需要越多時間，請耐心等待'
              : null,
        );

      case _ReadState.result:
      case _ReadState.asking:
      case _ReadState.qa:
        return _buildResultView();
    }
  }

  // ── 全螢幕相機預覽 ────────────────────────────────────────────────────────
  Widget _buildCameraView() {
    return Semantics(
      label: '相機預覽。點擊畫面任何位置即可拍照辨識文件。',
      button: true,
      child: GestureDetector(
        onTap: _capture,
        behavior: HitTestBehavior.opaque,
        child: Stack(
          fit: StackFit.expand,
          children: [
            // 相機預覽
            if (_cam != null && _cam!.value.isInitialized)
              CameraPreview(_cam!),

            // 拍照提示
            Positioned(
              bottom: 0, left: 0, right: 0,
              child: Container(
                padding: const EdgeInsets.symmetric(vertical: 28),
                decoration: const BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [Colors.transparent, Colors.black87],
                  ),
                ),
                child: Column(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 32, vertical: 16),
                      decoration: BoxDecoration(
                        color: Colors.white12,
                        borderRadius: BorderRadius.circular(50),
                        border: Border.all(color: Colors.white30),
                      ),
                      child: const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.camera_alt, color: Colors.white, size: 28),
                          SizedBox(width: 12),
                          Text(
                            '點擊畫面拍照辨識',
                            style: TextStyle(
                                fontSize: 22,
                                fontWeight: FontWeight.bold,
                                color: Colors.white),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 12),
                    const Text(
                      '將手機對準文件，確保光線充足、文字清晰',
                      style: TextStyle(fontSize: 14, color: Colors.white54),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ── 載入中畫面 ────────────────────────────────────────────────────────────
  Widget _buildLoading(String message, {String? subtitle}) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const CircularProgressIndicator(color: Colors.white54, strokeWidth: 3),
            const SizedBox(height: 28),
            Text(
              message,
              textAlign: TextAlign.center,
              style: const TextStyle(
                  fontSize: 22, fontWeight: FontWeight.bold, color: Colors.white),
            ),
            if (subtitle != null) ...[
              const SizedBox(height: 10),
              Text(
                subtitle,
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 14, color: Colors.white38),
              ),
            ],
          ],
        ),
      ),
    );
  }

  // ── 辨識結果 + Q&A ────────────────────────────────────────────────────────
  Widget _buildResultView() {
    return Column(
      children: [
        // ── 捲動區：OCR 文字 + Q&A 歷史 ────────────────────────────────────
        Expanded(
          child: ListView(
            controller: _scrollCtrl,
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
            children: [

              // OCR 結果標題
              const _SectionHeader(
                icon: Icons.article_outlined,
                label: '辨識文字',
              ),

              const SizedBox(height: 8),

              // OCR 文字內容
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: const Color(0xFF1A1A1A),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: SelectableText(
                  _extractedText,
                  style: const TextStyle(
                      fontSize: 17, color: Colors.white, height: 1.7),
                ),
              ),

              const SizedBox(height: 20),

              // Q&A 歷史
              ..._qa.map((item) => _QABubble(
                    question: item['q']!,
                    answer:   item['a']!,
                  )),

              const SizedBox(height: 8),
            ],
          ),
        ),

        // ── 底部操作區 ──────────────────────────────────────────────────────
        _buildBottomBar(),
      ],
    );
  }

  Widget _buildBottomBar() {
    // 詢問是否需要說明
    if (_state == _ReadState.asking) {
      return Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // ── 重新拍照大按鈕 ────────────────────────────────────────────
          Semantics(
            label: '重新拍照，回到相機重新拍攝文件',
            button: true,
            child: GestureDetector(
              onTap: _retake,
              child: Container(
                width: double.infinity,
                color: const Color(0xFF212121),
                padding: const EdgeInsets.symmetric(vertical: 20),
                child: const Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.camera_alt, color: Colors.white70, size: 28),
                    SizedBox(width: 10),
                    Text('重新拍照',
                        style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.bold,
                            color: Colors.white70)),
                  ],
                ),
              ),
            ),
          ),
          Container(
            color: const Color(0xFF0D0D0D),
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text(
                  '需要我說明這份文件的內容嗎？',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 16, color: Colors.white70),
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    Expanded(
                      child: Semantics(
                        label: '需要說明，讓 AI 說明文件重點',
                        button: true,
                        child: ElevatedButton(
                          onPressed: _requestExplain,
                          style: ElevatedButton.styleFrom(
                            backgroundColor: const Color(0xFF1565C0),
                            padding: const EdgeInsets.symmetric(vertical: 16),
                            shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(12)),
                          ),
                          child: const Text('需要說明',
                              style: TextStyle(
                                  fontSize: 18, fontWeight: FontWeight.bold)),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Semantics(
                        label: '不需要說明，關閉提示',
                        button: true,
                        child: ElevatedButton(
                          onPressed: () => setState(() => _state = _ReadState.qa),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: const Color(0xFF424242),
                            padding: const EdgeInsets.symmetric(vertical: 16),
                            shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(12)),
                          ),
                          child: const Text('不需要',
                              style: TextStyle(
                                  fontSize: 18, fontWeight: FontWeight.bold)),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      );
    }

    // Q&A 輸入列
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        // ── 重新拍照大按鈕 ──────────────────────────────────────────────
        Semantics(
          label: '重新拍照，回到相機重新拍攝文件',
          button: true,
          child: GestureDetector(
            onTap: _retake,
            child: Container(
              width: double.infinity,
              color: const Color(0xFF212121),
              padding: const EdgeInsets.symmetric(vertical: 20),
              child: const Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.camera_alt, color: Colors.white70, size: 28),
                  SizedBox(width: 10),
                  Text('重新拍照',
                      style: TextStyle(
                          fontSize: 22,
                          fontWeight: FontWeight.bold,
                          color: Colors.white70)),
                ],
              ),
            ),
          ),
        ),
        Container(
      color: const Color(0xFF0D0D0D),
      padding: EdgeInsets.only(
        left: 12,
        right: 12,
        top: 10,
        bottom: MediaQuery.of(context).viewInsets.bottom + 16,
      ),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller:      _inputCtrl,
              style:           const TextStyle(color: Colors.white, fontSize: 16),
              textInputAction: TextInputAction.send,
              onSubmitted:     (_) => _submitQuestion(),
              decoration: InputDecoration(
                hintText:  '輸入問題追問…',
                hintStyle: const TextStyle(color: Colors.white38),
                filled:    true,
                fillColor: const Color(0xFF1E1E1E),
                contentPadding: const EdgeInsets.symmetric(
                    horizontal: 16, vertical: 12),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(24),
                  borderSide: BorderSide.none,
                ),
              ),
            ),
          ),
          const SizedBox(width: 8),
          Semantics(
            label: '送出問題',
            button: true,
            child: GestureDetector(
              onTap: _submitQuestion,
              child: Container(
                width: 48, height: 48,
                decoration: const BoxDecoration(
                  color: Color(0xFF1565C0),
                  shape: BoxShape.circle,
                ),
                child: const Icon(Icons.send, color: Colors.white, size: 22),
              ),
            ),
          ),
        ],
      ),
        ),  // Container（Q&A 輸入列）
      ],
    );   // Column
  }
}

// ── 輔助元件 ──────────────────────────────────────────────────────────────────

class _SectionHeader extends StatelessWidget {
  final IconData icon;
  final String   label;

  const _SectionHeader({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 18, color: Colors.white54),
        const SizedBox(width: 6),
        Text(label,
            style: const TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.bold,
                color: Colors.white54,
                letterSpacing: 1)),
      ],
    );
  }
}

class _QABubble extends StatelessWidget {
  final String question;
  final String answer;

  const _QABubble({required this.question, required this.answer});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // 問題
          Container(
            alignment: Alignment.centerRight,
            child: Container(
              constraints: BoxConstraints(
                  maxWidth: MediaQuery.of(context).size.width * 0.75),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              decoration: BoxDecoration(
                color: const Color(0xFF1565C0),
                borderRadius: BorderRadius.circular(16),
              ),
              child: Text(question,
                  style: const TextStyle(fontSize: 15, color: Colors.white)),
            ),
          ),
          const SizedBox(height: 8),
          // 回答
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: const Color(0xFF1A1A1A),
              borderRadius: BorderRadius.circular(12),
            ),
            child: SelectableText(
              answer,
              style: const TextStyle(
                  fontSize: 16, color: Colors.white, height: 1.65),
            ),
          ),
        ],
      ),
    );
  }
}
