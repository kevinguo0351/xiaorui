import 'dart:async';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'audio.dart';
import 'session.dart';

void main() => runApp(const XiaoruiApp());

class XiaoruiApp extends StatelessWidget {
  const XiaoruiApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: '小瑞',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      useMaterial3: true,
      fontFamilyFallback: const ['XiaoruiChinese'],
      scaffoldBackgroundColor: const Color(0xfff8f3ea),
      colorScheme: ColorScheme.fromSeed(
        seedColor: const Color(0xff54735b),
        surface: const Color(0xfffffcf6),
      ),
      textTheme: const TextTheme(
        bodyLarge: TextStyle(fontSize: 22, height: 1.5),
        bodyMedium: TextStyle(fontSize: 22, height: 1.5),
        titleLarge: TextStyle(fontSize: 28, fontWeight: FontWeight.w600),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size(56, 56),
          textStyle: const TextStyle(fontSize: 22),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          minimumSize: const Size(56, 56),
          textStyle: const TextStyle(fontSize: 22),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          minimumSize: const Size(56, 56),
          textStyle: const TextStyle(fontSize: 22),
        ),
      ),
    ),
    home: const CompanionPage(),
  );
}

class CompanionPage extends StatefulWidget {
  const CompanionPage({super.key});
  @override
  State<CompanionPage> createState() => _CompanionPageState();
}

class _CompanionPageState extends State<CompanionPage>
    with WidgetsBindingObserver {
  late final SessionController session;
  late final VoiceAudio audio;
  bool recording = false, starting = false, hold = false, finalizing = false;
  String partial = '', voiceError = '', speed = 'slow', name = '';
  int recordingGeneration = 0;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    session = SessionController()..addListener(_refresh);
    audio = VoiceAudio(
      onPartial: (text) {
        if (mounted) setState(() => partial = text);
      },
      onFinal: (text) {
        if (!mounted) return;
        setState(() => finalizing = false);
        if (text.trim().isNotEmpty) {
          unawaited(session.submit(text));
        } else {
          setState(() => voiceError = '没有听到内容，请再试一次。');
        }
      },
      onError: (error) {
        if (mounted) {
          setState(() {
            voiceError = error;
            recording = false;
            starting = false;
            finalizing = false;
          });
        }
      },
      onRecording: (value) {
        if (mounted) setState(() => recording = value);
      },
    );
    session.onReply = (text) {
      if (mounted && !recording && !starting) {
        unawaited(
          audio.speak(
            text.length > 1200 ? text.substring(0, 1200) : text,
            speed: speed,
          ),
        );
      }
    };
    unawaited(_load());
    unawaited(session.connect());
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    if (mounted) {
      setState(() {
        hold = prefs.getBool('hold') ?? false;
        speed = prefs.getString('speed') ?? 'slow';
        name = prefs.getString('name') ?? '';
      });
    }
  }

  void _refresh() {
    if (mounted) setState(() {});
  }

  Future<void> _start() async {
    if (starting ||
        recording ||
        finalizing ||
        !session.readOnly ||
        !session.ready ||
        !session.speechConfigured) {
      return;
    }
    session.interrupt();
    final generation = ++recordingGeneration;
    setState(() {
      starting = true;
      voiceError = '';
      partial = '';
    });
    await audio.stopPlayback();
    if (!mounted || generation != recordingGeneration) return;
    await audio.start();
    if (mounted && generation == recordingGeneration) {
      setState(() => starting = false);
    }
  }

  Future<void> _finish() async {
    if (starting) {
      await _cancel();
      return;
    }
    if (!recording) return;
    setState(() => finalizing = true);
    await audio.finish();
  }

  Future<void> _cancel() async {
    recordingGeneration++;
    await audio.cancel();
    if (mounted) {
      setState(() {
        recording = false;
        starting = false;
        finalizing = false;
        partial = '';
      });
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed) {
      session.interrupt();
      unawaited(_cancel());
      unawaited(audio.stopPlayback());
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    session.removeListener(_refresh);
    session.dispose();
    unawaited(audio.dispose());
    super.dispose();
  }

  Future<void> _typing() async {
    await _cancel();
    await audio.stopPlayback();
    session.interrupt();
    if (!mounted) return;
    final input = TextEditingController();
    final text = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => Padding(
        padding: EdgeInsets.fromLTRB(
          24,
          8,
          24,
          MediaQuery.viewInsetsOf(context).bottom + 24,
        ),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text('慢慢写，我在这里'),
              const SizedBox(height: 16),
              TextField(
                controller: input,
                autofocus: true,
                maxLength: 2000,
                minLines: 2,
                maxLines: 5,
                style: const TextStyle(fontSize: 22),
                decoration: const InputDecoration(
                  labelText: '想让小瑞帮您查什么？',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: () => Navigator.pop(context, input.text),
                child: const Text('发送'),
              ),
            ],
          ),
        ),
      ),
    );
    // Dispose after the bottom sheet has finished its exit animation.
    Future<void>.delayed(const Duration(milliseconds: 400), input.dispose);
    if (text != null && text.trim().isNotEmpty && mounted) {
      await session.submit(text);
    }
  }

  Future<void> _settings() async {
    session.interrupt();
    await _cancel();
    await audio.stopPlayback();
    if (!mounted) return;
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => StatefulBuilder(
        builder: (context, update) => SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text(
                  '小瑞的设置',
                  style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 20),
                const Text('讲话方式'),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(hold ? '按住说话' : '点击开始／结束'),
                  subtitle: const Text('不会因您停顿而自动结束'),
                  value: hold,
                  onChanged: (value) async {
                    setState(() => hold = value);
                    update(() {});
                    final p = await SharedPreferences.getInstance();
                    await p.setBool('hold', value);
                  },
                ),
                const SizedBox(height: 12),
                const Text('播报速度'),
                DropdownButtonFormField<String>(
                  initialValue: speed,
                  items: const [
                    DropdownMenuItem(value: 'slow', child: Text('慢速')),
                    DropdownMenuItem(value: 'normal', child: Text('正常')),
                  ],
                  onChanged: (value) async {
                    setState(() => speed = value!);
                    final p = await SharedPreferences.getInstance();
                    await p.setString('speed', speed);
                  },
                ),
                const SizedBox(height: 20),
                TextFormField(
                  initialValue: name,
                  maxLength: 30,
                  decoration: const InputDecoration(labelText: '怎么称呼您（仅保存在本机）'),
                  onChanged: (value) async {
                    name = value;
                    final p = await SharedPreferences.getInstance();
                    await p.setString('name', value);
                  },
                ),
                const Divider(height: 32),
                const Text(
                  '支付方式',
                  style: TextStyle(fontWeight: FontWeight.bold),
                ),
                const ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: Icon(Icons.payment),
                  title: Text('微信支付'),
                  subtitle: Text('尚未开通，仅展示'),
                ),
                const ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: Icon(Icons.account_balance_wallet_outlined),
                  title: Text('支付宝'),
                  subtitle: Text('尚未开通，仅展示'),
                ),
                const Text('不读取支付资料，不签约免密支付。'),
                const SizedBox(height: 20),
                OutlinedButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('返回小瑞'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _details(QueryTask task) async {
    session.interrupt();
    await _cancel();
    await audio.stopPlayback();
    if (!mounted) return;
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                task.status,
                style: const TextStyle(
                  fontSize: 28,
                  fontWeight: FontWeight.bold,
                ),
              ),
              Text(task.text),
              const Divider(height: 32),
              SelectableText(
                task.result.isEmpty ? '查询还在处理中，请稍等。' : task.result,
              ),
              ..._options(task),
              const SizedBox(height: 24),
              OutlinedButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('知道了'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _options(QueryTask task) {
    final events = task.response?['events'] as List? ?? [];
    final result = <Widget>[];
    for (final event in events) {
      if (event['type'] == 'query_result') {
        result.add(
          Padding(
            padding: const EdgeInsets.only(top: 20),
            child: SelectableText('来源：麦当劳官方 MCP\n${event['source'] ?? ''}'),
          ),
        );
        result.add(Text(event['success'] == true ? '查询返回成功' : '查询未成功，请核对错误信息'));
      }

      if (event['type'] == 'stores') {
        result.add(
          const Padding(
            padding: EdgeInsets.only(top: 20),
            child: Text('来源：麦当劳官方 MCP 实时查询'),
          ),
        );
        for (final store in event['stores'] as List? ?? []) {
          result.add(
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(store['name'] as String? ?? ''),
                    Text(store['address'] as String? ?? ''),
                    Text('门店编号：${store['code'] ?? ''}'),
                    OutlinedButton(
                      onPressed: () {
                        Navigator.pop(context);
                        unawaited(
                          session.submit(
                            '查询麦当劳门店 ${store['code']} ${store['name']} 的菜单',
                          ),
                        );
                      },
                      child: const Text('查看这家菜单'),
                    ),
                  ],
                ),
              ),
            ),
          );
        }
      }
      if (event['type'] == 'meals') {
        result.add(
          const Padding(
            padding: EdgeInsets.only(top: 20),
            child: Text('来源：麦当劳官方 MCP 实时查询；仅查询，不下单'),
          ),
        );
        for (final meal in event['meals'] as List? ?? []) {
          result.add(
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(meal['name'] as String? ?? ''),
                    if (meal['amount_cents'] is num)
                      Text(
                        '¥${((meal['amount_cents'] as num) / 100).toStringAsFixed(2)}',
                      ),
                    for (final choice in meal['choices'] as List? ?? [])
                      Text('$choice'),
                  ],
                ),
              ),
            ),
          );
        }
      }
      if (event['type'] == 'service_choices') {
        for (final choice in event['choices'] as List? ?? []) {
          result.add(
            OutlinedButton(
              onPressed: () {
                Navigator.pop(context);
                unawaited(
                  session.submit(
                    choice['prompt'] as String? ??
                        choice['label'] as String? ??
                        '',
                  ),
                );
              },
              child: Text(choice['label'] as String? ?? '查看选项'),
            ),
          );
        }
      }
    }
    return result;
  }

  Future<void> _tasks() async {
    session.interrupt();
    await _cancel();
    await audio.stopPlayback();
    if (!mounted) return;
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => AnimatedBuilder(
        animation: session,
        builder: (context, _) => SafeArea(
          child: SizedBox(
            height: MediaQuery.sizeOf(context).height * .65,
            child: ListView(
              padding: const EdgeInsets.all(24),
              children: [
                const Text(
                  '最近三件事',
                  style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
                ),
                if (session.tasks.isEmpty)
                  const Padding(
                    padding: EdgeInsets.only(top: 24),
                    child: Text('还没有查询。您说的话被接收后，会显示在这里。'),
                  ),
                for (final task in session.tasks.reversed.take(3))
                  Card(
                    child: ListTile(
                      minVerticalPadding: 20,
                      title: Text(
                        task.text,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                      subtitle: Text(task.status),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: () {
                        Navigator.pop(context);
                        _details(task);
                      },
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final canUse = session.ready && session.readOnly;
    final text = partial.isNotEmpty
        ? partial
        : recording
        ? '正在听，说完再点一下'
        : starting
        ? '正在打开麦克风'
        : finalizing
        ? '正在识别，请稍等'
        : session.summary;
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        leading: IconButton(
          tooltip: '头像与设置',
          icon: const Icon(Icons.account_circle_outlined, size: 32),
          onPressed: _settings,
        ),
        title: const Text('小瑞'),
        centerTitle: true,
        toolbarHeight: 72,
      ),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 760),
            child: Column(
              children: [
                Expanded(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.symmetric(horizontal: 24),
                    child: Column(
                      children: [
                        Text(
                          session.connected ? '本地服务已连接' : '本地服务未连接',
                          style: const TextStyle(fontSize: 18),
                        ),
                        if (!session.readOnly && session.ready)
                          const Text(
                            '请使用只读预览启动入口；当前不可提交查询。',
                            style: TextStyle(fontSize: 18),
                          ),
                        if (session.ready)
                          Text(
                            '语音${session.speechConfigured ? '已配置，远端待验证' : '未配置'} · AI${session.agentConfigured ? '已配置' : '未配置'} · 麦当劳${session.mcdConfigured ? '已配置' : '未配置'}',
                            textAlign: TextAlign.center,
                            style: const TextStyle(fontSize: 16),
                          ),
                        const SizedBox(height: 24),
                        Semantics(
                          label: '小瑞，微笑着陪伴您',
                          child: const ExcludeSemantics(
                            child: _CompanionFace(),
                          ),
                        ),
                        const SizedBox(height: 24),
                        if (name.isNotEmpty) Text('$name，您好'),
                        Semantics(
                          liveRegion: true,
                          child: Text(
                            text.length > 180
                                ? '${text.substring(0, 180)}…'
                                : text,
                            textAlign: TextAlign.center,
                          ),
                        ),
                        if (session.tasks.isNotEmpty && !recording && !starting)
                          TextButton(
                            onPressed: () => _details(session.tasks.last),
                            child: const Text('查看完整回复与选项'),
                          ),
                        const SizedBox(height: 24),
                        Semantics(
                          button: true,
                          label: recording
                              ? '结束讲话'
                              : hold
                              ? '按住开始讲话，松开结束；也可点击开始和结束'
                              : '点击开始讲话',
                          child: GestureDetector(
                            onLongPressStart:
                                hold && canUse && session.speechConfigured
                                ? (_) => _start()
                                : null,
                            onLongPressEnd: hold ? (_) => _finish() : null,
                            onLongPressCancel: hold ? () => _cancel() : null,
                            child: FilledButton(
                              style: FilledButton.styleFrom(
                                shape: const CircleBorder(),
                                fixedSize: const Size(140, 140),
                                backgroundColor: recording
                                    ? const Color(0xff9e503c)
                                    : null,
                              ),
                              onPressed: canUse && session.speechConfigured
                                  ? (recording ? _finish : _start)
                                  : null,
                              child: Icon(
                                recording
                                    ? Icons.stop_rounded
                                    : Icons.mic_rounded,
                                size: 64,
                              ),
                            ),
                          ),
                        ),
                        const SizedBox(height: 12),
                        Text(
                          hold
                              ? '按住说话，松开结束'
                              : recording
                              ? '正在听，说完再点一下'
                              : '点一下，慢慢说',
                          textAlign: TextAlign.center,
                        ),
                        if (recording || starting || finalizing)
                          TextButton(
                            onPressed: _cancel,
                            child: const Text('取消录音'),
                          ),
                        const SizedBox(height: 12),
                        Wrap(
                          alignment: WrapAlignment.center,
                          spacing: 12,
                          runSpacing: 8,
                          children: [
                            OutlinedButton.icon(
                              onPressed: canUse && !session.sending
                                  ? _typing
                                  : null,
                              icon: const Icon(Icons.keyboard_outlined),
                              label: const Text('打字'),
                            ),
                            OutlinedButton(
                              onPressed: () => audio.stopPlayback(),
                              child: const Text('停止播报'),
                            ),
                            OutlinedButton(
                              onPressed:
                                  session.summary.isNotEmpty &&
                                      session.speechConfigured
                                  ? () => audio.speak(
                                      session.summary.length > 1200
                                          ? session.summary.substring(0, 1200)
                                          : session.summary,
                                      speed: speed,
                                    )
                                  : null,
                              child: const Text('再说一遍'),
                            ),
                          ],
                        ),
                        if (session.sending)
                          const Padding(
                            padding: EdgeInsets.all(12),
                            child: Text('正在发送，请稍等'),
                          ),
                        if (voiceError.isNotEmpty || session.error.isNotEmpty)
                          Padding(
                            padding: const EdgeInsets.symmetric(vertical: 16),
                            child: Semantics(
                              liveRegion: true,
                              child: Text(
                                voiceError.isNotEmpty
                                    ? voiceError
                                    : session.error,
                                style: const TextStyle(
                                  color: Color(0xff963c2d),
                                ),
                              ),
                            ),
                          ),
                        if (session.retryText != null && !session.sending)
                          OutlinedButton(
                            onPressed: canUse
                                ? () => session.submit(
                                    session.retryText!,
                                    retry: true,
                                  )
                                : null,
                            child: const Text('重试这条消息'),
                          ),
                        if (!session.connected)
                          TextButton(
                            onPressed: session.connect,
                            child: const Text('重新连接'),
                          ),
                        const SizedBox(height: 16),
                        const Text(
                          '买药、买菜：暂未接入',
                          style: TextStyle(fontSize: 18),
                        ),
                        const Text(
                          '当前仅查询，不下单、不付款',
                          style: TextStyle(fontSize: 18),
                        ),
                        const SizedBox(height: 24),
                      ],
                    ),
                  ),
                ),
                GestureDetector(
                  onVerticalDragEnd: (details) {
                    if ((details.primaryVelocity ?? 0) < 0) _tasks();
                  },
                  child: Card(
                    margin: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                    child: ListTile(
                      minVerticalPadding: 18,
                      leading: const Icon(Icons.checklist_rounded),
                      title: const Text('任务板'),
                      subtitle: Text(
                        session.tasks.isEmpty
                            ? '还没有查询'
                            : session.tasks.last.status,
                      ),
                      trailing: const Icon(Icons.keyboard_arrow_up),
                      onTap: _tasks,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _CompanionFace extends StatelessWidget {
  const _CompanionFace();
  @override
  Widget build(BuildContext context) => Container(
    width: 160,
    height: 160,
    decoration: BoxDecoration(
      color: const Color(0xffe1e7d7),
      borderRadius: BorderRadius.circular(64),
      border: Border.all(color: const Color(0xff8b9b76), width: 3),
    ),
    child: const Stack(
      children: [
        Positioned(
          top: 55,
          left: 42,
          child: Icon(Icons.circle, size: 12, color: Color(0xff42543e)),
        ),
        Positioned(
          top: 55,
          right: 42,
          child: Icon(Icons.circle, size: 12, color: Color(0xff42543e)),
        ),
        Positioned(
          top: 65,
          left: 49,
          child: Text(
            '◡',
            style: TextStyle(fontSize: 64, height: 1, color: Color(0xff42543e)),
          ),
        ),
      ],
    ),
  );
}
