import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

class QueryTask {
  QueryTask(this.id, this.text, {this.clientId = ''});
  final String id;
  final String text;
  final String clientId;
  String status = '已收到';
  String result = '';
  Map<String, dynamic>? response;
}

class SessionController extends ChangeNotifier {
  SessionController({http.Client? client, Uri? base})
    : _client = client ?? http.Client(),
      _base = base ?? Uri.base;
  final http.Client _client;
  final Uri _base;
  final List<QueryTask> tasks = [];
  bool connected = false, ready = false, sending = false, disposed = false;
  bool speechConfigured = false, agentConfigured = false, mcdConfigured = false;
  bool readOnly = false;
  String error = '', summary = '您好，我是小瑞。今天想让我帮您查点什么？';
  String? retryText, retryId;
  int _cursor = 0, _generation = 0;
  final Map<String, int> _generations = {};
  StreamSubscription<String>? _events;
  Timer? _reconnect;
  void Function(String)? onReply;
  Uri uri(String path) => _base.resolve(path);
  void changed() {
    if (!disposed) notifyListeners();
  }

  Future<Map<String, dynamic>> _json(
    String path, [
    Map<String, dynamic>? body,
  ]) async {
    final response =
        await (body == null
                ? _client.get(uri(path))
                : _client.post(
                    uri(path),
                    headers: {'Content-Type': 'application/json'},
                    body: jsonEncode(body),
                  ))
            .timeout(const Duration(seconds: 20));
    final decoded = jsonDecode(utf8.decode(response.bodyBytes));
    if (response.statusCode >= 400) {
      throw Exception(
        decoded is Map && decoded['detail'] is String
            ? decoded['detail']
            : '服务暂时不可用',
      );
    }
    return Map<String, dynamic>.from(decoded as Map);
  }

  Future<void> connect() async {
    try {
      final health = await _json('/api/health');
      final voice = await _json('/api/voice/status');
      final state = await _json('/api/contact/state');
      if (disposed) return;
      agentConfigured = health['agent_configured'] == true;
      mcdConfigured = health['mcd_configured'] == true;
      readOnly =
          health['read_only'] == true || health['read_only_mode'] == true;
      speechConfigured = voice['configured'] == true;
      for (final raw in state['events'] as List? ?? []) {
        receive(Map<String, dynamic>.from(raw), replay: true);
      }
      _cursor = state['cursor'] as int? ?? 0;
      connected = true;
      ready = true;
      error = '';
      changed();
      await _listen();
    } catch (_) {
      if (disposed) return;
      connected = false;
      error = '连接未完成，请检查本地服务后重连。';
      changed();
    }
  }

  Future<void> _listen() async {
    if (disposed) return;
    await _events?.cancel();
    try {
      final response = await _client
          .send(http.Request('GET', uri('/api/contact/events?after=$_cursor')))
          .timeout(const Duration(seconds: 20));
      if (response.statusCode != 200) throw Exception('连接中断');
      connected = true;
      error = '';
      changed();
      _events = response.stream
          .transform(utf8.decoder)
          .transform(const LineSplitter())
          .listen(
            (line) {
              if (!line.startsWith('data:')) return;
              try {
                receive(
                  Map<String, dynamic>.from(jsonDecode(line.substring(5))),
                );
              } catch (_) {
                error = '消息显示异常，请重新连接恢复记录。';
                changed();
              }
            },
            onError: (_) => _lost(),
            onDone: _lost,
            cancelOnError: true,
          );
    } catch (_) {
      _lost();
    }
  }

  void _lost() {
    if (disposed) return;
    connected = false;
    error = '消息连接中断，正在恢复；已接收的查询不会重复发送。';
    changed();
    _reconnect?.cancel();
    _reconnect = Timer(const Duration(seconds: 3), _listen);
  }

  void interrupt() {
    _generation++;
  }

  Future<void> submit(String text, {bool retry = false}) async {
    text = text.trim();
    if (sending || !ready || !readOnly || text.isEmpty || text.length > 2000) {
      return;
    }
    sending = true;
    error = '';
    _generation++;
    final id = retry && retryId != null
        ? retryId!
        : 'flutter_${DateTime.now().microsecondsSinceEpoch}_${Random.secure().nextInt(1 << 30)}';
    retryId = id;
    retryText = text;
    _generations[id] = _generation;
    changed();
    try {
      final data = await _json('/api/contact/messages', {
        'text': text,
        'client_id': id,
      });
      if (disposed) return;
      receive({
        'type': 'accepted',
        'message_id': data['message_id'],
        'client_id': id,
        'text': text,
      });
      retryId = null;
      retryText = null;
    } catch (e) {
      error =
          '${e.toString().replaceFirst('Exception: ', '')}。可重试同一条消息，不会重复建任务。';
    } finally {
      sending = false;
      changed();
    }
  }

  QueryTask? _task(String id) {
    for (final t in tasks) {
      if (t.id == id) return t;
    }
    return null;
  }

  void receive(Map<String, dynamic> event, {bool replay = false}) {
    final cursor = event['cursor'] as int?;
    if (cursor != null) {
      if (!replay && cursor <= _cursor) return;
      _cursor = max(_cursor, cursor);
    }
    final id = event['message_id'] as String? ?? '';
    final type = event['type'];
    if (type == 'accepted' && _task(id) == null) {
      tasks.add(
        QueryTask(
          id,
          event['text'] as String? ?? '',
          clientId: event['client_id'] as String? ?? '',
        ),
      );
    }
    final ids = (event['message_ids'] as List? ?? [id]).cast<String>();
    for (final taskId in ids) {
      final task = _task(taskId);
      if (task == null) continue;
      if (type == 'started' || type == 'progress') task.status = '正在查询';
      if (type == 'failed') {
        task.status =
            (event['text'] as String? ?? '').contains('中断') ||
                (event['text'] as String? ?? '').contains('重启')
            ? '中断'
            : '查询失败';
        task.result = event['text'] as String? ?? '这次查询未完成';
      }
      if (type == 'completed') {
        final response = Map<String, dynamic>.from(
          event['response'] as Map? ?? {},
        );
        task.response = response;
        task.result = response['text'] as String? ?? '';
        final details = response['events'] as List? ?? [];
        final failed = details.any(
          (e) =>
              (e['type'] == 'query_result' && e['success'] == false) ||
              (e['type'] == 'service_result' &&
                  e['data'] is Map &&
                  (e['data']['error'] != null ||
                      e['data']['success'] == false)),
        );
        task.status = failed
            ? '查询失败'
            : details.any(
                (e) =>
                    ['stores', 'meals', 'service_choices'].contains(e['type']),
              )
            ? '等您选择'
            : details.any(
                (e) =>
                    e['type'] == 'service_result' ||
                    (e['type'] == 'query_result' && e['success'] == true),
              )
            ? '查询完成'
            : '需要补充';
      }
      if (type == 'completed' || type == 'failed') {
        final current =
            (replay && _generation == 0) ||
            (!replay && _generations[task.clientId] == _generation);
        if (current && event['superseded'] != true) {
          summary = task.result;
          if (!replay && type == 'completed') {
            onReply?.call(
              task.response?['speech_text'] as String? ?? task.result,
            );
          }
        }
      }
    }
    changed();
  }

  @override
  void dispose() {
    disposed = true;
    _reconnect?.cancel();
    _events?.cancel();
    _client.close();
    super.dispose();
  }
}
