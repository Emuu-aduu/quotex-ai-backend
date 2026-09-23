import 'package:flutter_tts/flutter_tts.dart';

class SoundService {
  final FlutterTts _flutterTts = FlutterTts();
  late final Future<void> _initFuture;

  SoundService() {
    _initFuture = _initTts();
  }

  Future<void> _initTts() async {
    await _flutterTts.setLanguage("en-US");
    await _flutterTts.setSpeechRate(0.5); // ভয়েস স্পিড
    await _flutterTts.setVolume(1.0); // সাউন্ড ভলিউম (0.0 থেকে 1.0)
    await _flutterTts.setPitch(1.0); // ভয়েস পিচ
  }

  // সিগন্যাল মেসেজ পড়ে শোনানোর ফাংশন
  Future<void> speakSignal(String text) async {
    await _initFuture; // নিশ্চিত করবে initialization শেষ হওয়ার পরেই কথা বলবে
    if (text.isNotEmpty) {
      await _flutterTts
          .stop(); // আগে কিছু বলতে থাকলে তা থামিয়ে নতুন সিগন্যাল বলবে
      await _flutterTts.speak(text);
    }
  }

  // সাউন্ড বন্ধ করার ফাংশন
  Future<void> stop() async {
    await _initFuture;
    await _flutterTts.stop();
  }
}
