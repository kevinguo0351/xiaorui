// Validate the exact locked record_web worklet, without a microphone or keys.
// Usage: node tool/verify_record_pcm.cjs [record_web/assets/js/record.worklet.js]
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
let worklet = process.argv[2];
if (!worklet) {
  const configPath = path.resolve(__dirname, '../.dart_tool/package_config.json');
  if (!fs.existsSync(configPath)) throw new Error('Run flutter pub get in mobile/ first.');
  const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
  const recordWeb = config.packages.find(pkg => pkg.name === 'record_web');
  if (!recordWeb) throw new Error('record_web is missing: run flutter pub get.');
  worklet = new URL('assets/js/record.worklet.js', new URL(recordWeb.rootUri.replace(/[/]?$/, '/'), `file://${configPath}`));
}
const source = fs.readFileSync(worklet, 'utf8');
for (const inputRate of [16000, 44100, 48000]) {
  let Processor;
  const chunks = [];
  const context = vm.createContext({
    sampleRate: inputRate,
    AudioWorkletProcessor: class {
      constructor() { this.port = { postMessage: value => chunks.push(value) }; }
    },
    registerProcessor: (_, value) => { Processor = value; },
  });
  vm.runInContext(source, context);
  const recorder = new Processor({parameterData: {
    numChannels: 1, sampleRate: 16000, streamBufferSize: 2048,
  }});
  for (let frame = 0; frame < inputRate; frame += 128) {
    const input = new Float32Array(Math.min(128, inputRate - frame));
    for (let i = 0; i < input.length; i++) {
      input[i] = .5 * Math.sin(2 * Math.PI * 440 * (frame + i) / inputRate);
    }
    recorder.process([[input]]);
  }
  recorder.flush();
  const bytes = Buffer.concat(chunks.map(chunk => Buffer.from(chunk.buffer)));
  assert.ok(Math.abs(bytes.length / 2 - 16000) <= 32,
    // Allow at most 2 ms of resampler boundary rounding over one second.
    // A compressed stream or a hardware-rate PCM stream fails this check.
    `${inputRate}: expected one second of 16 kHz mono samples, got ${bytes.length / 2}`);
  assert.equal(bytes.length % 2, 0);
  let energy = 0;
  for (let i = 0; i < bytes.length; i += 2) {
    const sample = bytes.readInt16LE(i);
    assert.ok(Math.abs(sample) <= 16400, 'PCM amplitude or endian mismatch');
    energy += sample * sample;
  }
  const rms = Math.sqrt(energy / (bytes.length / 2));
  assert.ok(rms > 11000 && rms < 12000, `unexpected PCM16LE RMS ${rms}`);
  console.log(`${inputRate} Hz → ${bytes.length / 2} mono PCM16LE samples; RMS ${Math.round(rms)}: PASS`);
}
