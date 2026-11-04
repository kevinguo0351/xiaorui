import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:just_audio/just_audio.dart';
import 'package:record/record.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

/// Platform boundary: raw PCM16 little endian, mono, 16 kHz only.
/// record_web's AudioWorklet resamples the actual AudioContext rate, then
/// writes little-endian Int16 samples. Never use MediaRecorder/WebM here.
class VoiceAudio {
  VoiceAudio({
    required this.onPartial,
    required this.onFinal,
    required this.onError,
    this.onRecording,
    Uri? baseUri,
    AudioPlayer? player,
    http.Client? client,
    AudioRecorder Function()? recorderFactory,
  }) : baseUri = baseUri ?? Uri.base,
       _player = player ?? AudioPlayer(),
       _http = client ?? http.Client(),
       _recorderFactory = recorderFactory ?? AudioRecorder.new;

  final void Function(String) onPartial;
  final void Function(String) onFinal;
  final void Function(String) onError;
  final void Function(bool)? onRecording;
  final Uri baseUri;
  final AudioPlayer _player;
  final http.Client _http;
  final AudioRecorder Function() _recorderFactory;
  _Capture? _capture;
  int _playbackGeneration = 0;
  int _captureGeneration = 0;
  Future<void> _playerQueue = Future<void>.value();
  bool _disposed = false;
  bool get recording => _capture?.recording ?? false;
  bool get starting => _capture != null && !recording;

  bool _current(_Capture capture) => !_disposed && identical(_capture, capture);

  Future<void> start() async {
    if (_disposed || _capture != null) return;
    final capture = _Capture(_recorderFactory());
    _captureGeneration++;
    _capture = capture;
    await stopPlayback();
    try {
      final allowed = await capture.recorder.hasPermission();
      if (!_current(capture)) return;
      if (!allowed) throw StateError('麦克风权限未开启，请在浏览器设置中允许。');
      if (!await capture.recorder.isEncoderSupported(AudioEncoder.pcm16bits)) {
        throw StateError('此浏览器不支持 PCM 录音，请使用新版 Chrome。');
      }
      if (!_current(capture)) return;
      final endpoint = baseUri.resolve('/api/voice/asr');
      final channel = WebSocketChannel.connect(
        endpoint.replace(scheme: endpoint.scheme == 'https' ? 'wss' : 'ws'),
      );
      capture.channel = channel;
      capture.socketSubscription = channel.stream.listen(
        (raw) {
          if (!_current(capture)) return;
          try {
            final event = jsonDecode(raw as String) as Map<String, dynamic>;
            switch (event['type']) {
              case 'ready':
                if (!capture.ready.isCompleted) capture.ready.complete(true);
              case 'partial':
                onPartial(event['text'] as String? ?? '');
              case 'final':
                capture.finalText = event['text'] as String? ?? '';
                if (!capture.finishing) {
                  _fail(capture, '语音服务提前结束，请重新录音或打字。');
                  return;
                }
                if (capture.finished) unawaited(_deliver(capture));
              case 'error':
                _fail(capture, event['message'] as String? ?? '语音服务暂时不可用。');
            }
          } catch (_) {
            _fail(capture, '语音服务返回了无法识别的数据。');
          }
        },
        onError: (Object error) {
          _fail(capture, '语音连接中断，请检查网络后重试。');
        },
        onDone: () {
          if (!_current(capture)) return;
          if (capture.finalText != null) {
            if (capture.finished) unawaited(_deliver(capture));
          } else {
            _fail(capture, '语音连接已结束，请重试。');
          }
        },
      );
      final ready = await capture.ready.future.timeout(
        const Duration(seconds: 15),
        onTimeout: () => false,
      );
      if (!_current(capture)) return;
      if (!ready) throw StateError('语音服务连接超时，请重试。');
      final stream = await capture.recorder.startStream(
        const RecordConfig(
          encoder: AudioEncoder.pcm16bits,
          sampleRate: 16000,
          numChannels: 1,
          echoCancel: true,
          noiseSuppress: true,
        ),
      );
      if (!_current(capture)) return;
      capture.recording = true;
      onRecording?.call(true);
      capture.microphoneSubscription = stream.listen(
        (bytes) {
          if (!_current(capture) || capture.finishing) return;
          if (bytes.length.isOdd) {
            _fail(capture, '录音格式异常，请重试。');
            return;
          }
          capture.bytes += bytes.length;
          if (capture.bytes > 60 * 16000 * 2) {
            unawaited(finish());
            return;
          }
          // Gateway imposes a per-frame limit and Int16 alignment.
          for (var offset = 0; offset < bytes.length; offset += 32000) {
            final end = offset + 32000 < bytes.length
                ? offset + 32000
                : bytes.length;
            channel.sink.add(Uint8List.sublistView(bytes, offset, end));
          }
        },
        onError: (Object error) {
          _fail(capture, '录音未完成，请检查麦克风后重试。');
        },
      );
      capture.timer = Timer(const Duration(seconds: 59), () {
        if (_current(capture)) unawaited(finish());
      });
    } catch (error) {
      _fail(
        capture,
        error is StateError ? error.message : '无法开始录音，请检查麦克风权限及语音服务。',
      );
    } finally {
      capture.startEnded.complete();
      // A permission dialog or startStream may resolve after cancellation.
      // Each attempt owns its recorder, so cleanup never stops a newer turn.
      if (!_current(capture)) await capture.release();
    }
  }

  Future<void> finish() async {
    final capture = _capture;
    if (capture == null || capture.finishing) return;
    if (!capture.recording) {
      await cancel();
      return;
    }
    capture.finishing = true;
    capture.timer?.cancel();
    try {
      await capture.recorder.stop();
      await capture.microphoneSubscription?.cancel();
    } catch (_) {
      _fail(capture, '结束录音时发生错误，请重新录音。');
      return;
    }
    if (!_current(capture)) return;
    capture.recording = false;
    onRecording?.call(false);
    if (capture.bytes == 0) {
      await cancel();
      onError('没有录到声音，请再试一次。');
      return;
    }
    capture.finished = true;
    if (capture.finalText != null) {
      await _deliver(capture);
    } else {
      capture.channel?.sink.add(jsonEncode({'type': 'finish'}));
      capture.timer = Timer(const Duration(seconds: 18), () {
        _fail(capture, '识别等待超时，请再试一次。');
      });
    }
  }

  Future<void> _deliver(_Capture capture) async {
    if (!_current(capture)) return;
    final text = (capture.finalText ?? '').trim();
    final cleanup = cancel();
    final generation = _captureGeneration;
    await cleanup;
    if (_disposed || generation != _captureGeneration) return;
    if (text.isEmpty) {
      onError('没有听清楚，请再说一次。');
    } else {
      onFinal(text);
    }
  }

  void _fail(_Capture capture, String message) {
    if (!_current(capture)) return;
    onError(message);
    unawaited(cancel());
  }

  Future<void> cancel() async {
    final capture = _capture;
    _captureGeneration++;
    _capture = null;
    if (capture == null) return;
    if (!capture.ready.isCompleted) capture.ready.complete(false);
    capture.timer?.cancel();
    onRecording?.call(false);
    try {
      capture.channel?.sink.add(jsonEncode({'type': 'cancel'}));
    } catch (_) {
      /* socket already closed */
    }
    await capture.socketSubscription?.cancel();
    try {
      await capture.channel?.sink.close().timeout(const Duration(seconds: 2));
    } catch (_) {
      /* closed or disconnected */
    }
    await capture.microphoneSubscription?.cancel();
    // Do not wait for a pending browser permission dialog; start's finally
    // releases this attempt when it resolves.
    if (capture.startEnded.isCompleted) await capture.release();
  }

  /// Speed is a local playback multiplier. The service's existing
  /// speech_rate is unchanged; no unverified provider parameter is sent.
  Future<void> speak(String text, {String speed = 'slow'}) async {
    final generation = ++_playbackGeneration;
    await _withPlayer(() => _player.stop());
    if (_disposed || generation != _playbackGeneration) return;
    try {
      final response = await _http
          .post(
            baseUri.resolve('/api/voice/tts'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'text': text.length > 1200 ? text.substring(0, 1200) : text,
            }),
          )
          .timeout(const Duration(seconds: 50));
      if (_disposed || generation != _playbackGeneration) return;
      if (response.statusCode != 200) {
        final data = jsonDecode(utf8.decode(response.bodyBytes));
        throw StateError(data['detail'] ?? '语音播报暂时不可用。');
      }
      await _withPlayer(() async {
        if (_disposed || generation != _playbackGeneration) return;
        await _player.setAudioSource(
          AudioSource.uri(
            Uri.dataFromBytes(response.bodyBytes, mimeType: 'audio/mpeg'),
          ),
        );
        if (_disposed || generation != _playbackGeneration) return;
        await _player.setSpeed(
          speed == 'normal'
              ? 1
              : speed == 'slower'
              ? .75
              : .9,
        );
        if (_disposed || generation != _playbackGeneration) return;
        unawaited(
          _player.play().catchError((Object error) {
            if (!_disposed && generation == _playbackGeneration) {
              onError('暂时不能播放，请点“再说一遍”重试。');
            }
          }),
        );
      });
    } catch (error) {
      if (!_disposed && generation == _playbackGeneration) {
        onError(error is StateError ? error.message : '暂时不能播放，请点“再说一遍”重试。');
      }
    }
  }

  Future<void> _withPlayer(Future<void> Function() action) {
    final operation = _playerQueue.then((_) => action());
    _playerQueue = operation.catchError((Object _) {});
    return operation;
  }

  Future<void> stopPlayback() async {
    _playbackGeneration++;
    await _withPlayer(() => _player.stop());
  }

  Future<void> dispose() async {
    if (_disposed) return;
    _disposed = true;
    await cancel();
    await stopPlayback();
    _http.close();
    await _player.dispose();
  }
}

class _Capture {
  _Capture(this.recorder);
  final AudioRecorder recorder;
  final Completer<bool> ready = Completer<bool>();
  final Completer<void> startEnded = Completer<void>();
  WebSocketChannel? channel;
  StreamSubscription<dynamic>? socketSubscription;
  StreamSubscription<Uint8List>? microphoneSubscription;
  Timer? timer;
  bool recording = false;
  bool finishing = false;
  bool finished = false;
  bool released = false;
  int bytes = 0;
  String? finalText;

  Future<void> release() async {
    if (released) return;
    released = true;
    try {
      await recorder.stop();
    } catch (_) {
      /* not started */
    }
    try {
      await recorder.dispose();
    } catch (_) {
      /* platform already released */
    }
  }
}
