import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:xiaorui_mobile/session.dart';

void main() {
  SessionController make({
    Future<http.Response> Function(http.Request)? handler,
  }) => SessionController(
    client: MockClient(handler ?? (request) async => http.Response('{}', 200)),
    base: Uri.parse('http://localhost:8000/flutter/'),
  );
  void accept(SessionController s, String id, {String? clientId}) => s.receive({
    'type': 'accepted',
    'message_id': id,
    'client_id': clientId ?? id,
    'text': '查询$id',
  });
  test('persistent event replay restores real result without autoplay', () {
    final s = make();
    addTearDown(s.dispose);
    var spoken = 0;
    s.onReply = (_) => spoken++;
    s.receive({
      'type': 'accepted',
      'message_id': '1',
      'text': '查门店',
      'cursor': 1,
    }, replay: true);
    s.receive({
      'type': 'completed',
      'message_id': '1',
      'cursor': 2,
      'response': {
        'text': '找到门店',
        'events': [
          {'type': 'stores', 'stores': []},
        ],
      },
    }, replay: true);
    expect(s.tasks.single.status, '等您选择');
    expect(s.summary, '找到门店');
    expect(spoken, 0);
  });
  test(
    'old completion after a new interaction never changes summary',
    () async {
      final s = make(
        handler: (r) async =>
            http.Response(jsonEncode({'message_id': 'old'}), 202),
      );
      addTearDown(s.dispose);
      s.ready = true;
      s.readOnly = true;
      await s.submit('查询旧门店');
      s.interrupt();
      s.receive({
        'type': 'completed',
        'message_id': 'old',
        'response': {'text': '旧回复', 'events': []},
      });
      expect(s.summary, isNot('旧回复'));
      expect(s.tasks.single.result, '旧回复');
    },
  );
  test(
    'duplicate taps while sending enqueue one message; retry keeps id',
    () async {
      final response = Completer<http.Response>();
      final bodies = <Map<String, dynamic>>[];
      final s = make(
        handler: (r) {
          bodies.add(jsonDecode(r.body));
          return response.future;
        },
      );
      addTearDown(s.dispose);
      s.ready = true;
      s.readOnly = true;
      final first = s.submit('查菜单');
      await s.submit('查菜单');
      await Future<void>.delayed(Duration.zero);
      expect(bodies.length, 1);
      response.complete(http.Response('{"detail":"unavailable"}', 503));
      await first;
      final id = s.retryId;
      await s.submit('查菜单', retry: true);
      expect(bodies.last['client_id'], id);
    },
  );
  test('controller refuses query without read only host', () async {
    var requests = 0;
    final s = make(
      handler: (r) async {
        requests++;
        return http.Response('{}', 200);
      },
    );
    addTearDown(s.dispose);
    s.ready = true;
    await s.submit('确认下单');
    expect(requests, 0);
  });
  test(
    'progress and failures use honest status; no tool result asks for information',
    () {
      final s = make();
      addTearDown(s.dispose);
      accept(s, '1');
      s.receive({'type': 'started', 'message_id': '1'});
      expect(s.tasks.single.status, '正在查询');
      s.receive({
        'type': 'completed',
        'message_id': '1',
        'response': {'text': '请告诉我您的位置', 'events': []},
      });
      expect(s.tasks.single.status, '需要补充');
      accept(s, '2');
      s.receive({'type': 'failed', 'message_id': '2', 'text': '服务已重启，已中断'});
      expect(s.tasks.last.status, '中断');
    },
  );
  test('authoritative query result determines success and failure', () {
    final s = make();
    addTearDown(s.dispose);
    accept(s, '1');
    s.receive({
      'type': 'completed',
      'message_id': '1',
      'response': {
        'text': '结果',
        'events': [
          {
            'type': 'query_result',
            'success': true,
            'source': 'https://open.mcd.cn/mcp',
            'data': {},
          },
        ],
      },
    });
    expect(s.tasks.single.status, '查询完成');
    s.receive({
      'type': 'completed',
      'message_id': '1',
      'response': {
        'text': '失败',
        'events': [
          {
            'type': 'query_result',
            'success': false,
            'data': {'error': 'timeout'},
          },
        ],
      },
    });
    expect(s.tasks.single.status, '查询失败');
  });
  test('SSE replay cursor suppresses duplicate accepted events', () {
    final s = make();
    addTearDown(s.dispose);
    s.receive({
      'type': 'accepted',
      'message_id': '1',
      'text': '查门店',
      'cursor': 3,
    });
    s.receive({
      'type': 'accepted',
      'message_id': '1',
      'text': '查门店',
      'cursor': 3,
    });
    expect(s.tasks.length, 1);
  });
}
