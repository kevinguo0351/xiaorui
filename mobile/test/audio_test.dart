import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:just_audio/just_audio.dart';
import 'package:record/record.dart';
import 'package:xiaorui_mobile/audio.dart';

class TestPlayer extends Fake implements AudioPlayer {
  final sources = <AudioSource>[];
  Completer<void>? sourceGate;
  int plays = 0;
  @override
  Future<void> stop() async {}
  @override
  Future<Duration?> setAudioSource(
    AudioSource source, {
    bool preload = true,
    int? initialIndex,
    Duration? initialPosition,
  }) async {
    sources.add(source);
    await sourceGate?.future;
    return null;
  }

  @override
  Future<void> setSpeed(double speed) async {}
  @override
  Future<void> play() async {
    plays++;
  }

  @override
  Future<void> dispose() async {}
}

class PendingRecorder extends Fake implements AudioRecorder {
  final permission = Completer<bool>();
  bool released = false;
  @override
  Future<bool> hasPermission({bool request = true}) => permission.future;
  @override
  Future<String?> stop() async => null;
  @override
  Future<void> dispose() async {
    released = true;
  }
}

void main() {
  test('cancel during permission prompt releases late recorder', () async {
    final recorder = PendingRecorder();
    final audio = VoiceAudio(
      onPartial: (_) {},
      onFinal: (_) => fail('cancelled input submitted'),
      onError: (_) => fail('cancelled input reported error'),
      player: TestPlayer(),
      recorderFactory: () => recorder,
    );
    final starting = audio.start();
    await Future<void>.delayed(Duration.zero);
    await audio.cancel();
    recorder.permission.complete(true);
    await starting;
    expect(recorder.released, isTrue);
    expect(audio.recording, isFalse);
    await audio.dispose();
  });

  test('old TTS response cannot replace newer playback', () async {
    final oldResponse = Completer<http.Response>();
    final player = TestPlayer();
    final audio = VoiceAudio(
      baseUri: Uri.parse('http://localhost/flutter/'),
      onPartial: (_) {},
      onFinal: (_) {},
      onError: (_) {},
      player: player,
      client: MockClient((request) {
        final text = jsonDecode(request.body)['text'];
        return text == 'old'
            ? oldResponse.future
            : Future.value(http.Response('new', 200));
      }),
    );
    final old = audio.speak('old');
    await Future<void>.delayed(Duration.zero);
    await audio.speak('new');
    oldResponse.complete(http.Response('old', 200));
    await old;
    expect(player.sources.length, 1);
    expect(player.plays, 1);
    await audio.dispose();
  });

  test('source loads serialize and stopped source never plays', () async {
    final player = TestPlayer()..sourceGate = Completer<void>();
    final audio = VoiceAudio(
      baseUri: Uri.parse('http://localhost/flutter/'),
      onPartial: (_) {},
      onFinal: (_) {},
      onError: (_) {},
      player: player,
      client: MockClient((_) async => http.Response('audio', 200)),
    );
    final old = audio.speak('old');
    await Future<void>.delayed(Duration.zero);
    expect(player.sources.length, 1);
    final newer = audio.speak('new');
    player.sourceGate!.complete();
    await old;
    await newer;
    expect(player.sources.length, 2);
    expect(player.plays, 1);
    await audio.dispose();
  });
}
