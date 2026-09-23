import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'sound_service.dart'; // SoundService Import

// ==========================================
// 1. CONFIGURATION & URL HANDLER
// ==========================================
class AppConfig {
  static String get baseUrl {
    if (kIsWeb) {
      return 'http://localhost:8000';
    }
    return 'http://10.0.2.2:8000'; // Android Emulator
  }
}

// ==========================================
// 2. DATA MODEL LAYER
// ==========================================
class SignalModel {
  final String pair;
  final String signal; // CALL, PUT, HOLD
  final double confidence;
  final String timeframe;
  final DateTime timestamp;

  SignalModel({
    required this.pair,
    required this.signal,
    required this.confidence,
    required this.timeframe,
    required this.timestamp,
  });

  factory SignalModel.fromJson(Map<String, dynamic> json) {
    final rawSignal =
        (json['action'] ?? json['signal'] ?? json['direction'] ?? 'HOLD')
            .toString()
            .toUpperCase();

    double parsedConfidence =
        double.tryParse(
          (json['confidence'] ?? json['percentage'] ?? '0')
              .toString()
              .replaceAll('%', ''),
        ) ??
        0.0;
    if (parsedConfidence > 0 && parsedConfidence <= 1.0) {
      parsedConfidence *= 100;
    }

    return SignalModel(
      pair: json['pair']?.toString() ?? json['asset']?.toString() ?? 'EUR/USD',
      signal: (rawSignal == 'CALL' || rawSignal == 'PUT' || rawSignal == 'UP')
          ? (rawSignal == 'UP' ? 'CALL' : rawSignal)
          : 'HOLD',
      confidence: parsedConfidence,
      timeframe: json['timeframe']?.toString() ?? '1m',
      timestamp:
          DateTime.tryParse(json['timestamp']?.toString() ?? '') ??
          DateTime.now(),
    );
  }

  bool get isCall => signal == 'CALL';
  bool get isPut => signal == 'PUT';
}

// ==========================================
// 3. API SERVICE LAYER
// ==========================================
class SignalApiService {
  static Future<SignalModel> fetchLiveSignal(String timeframe) async {
    try {
      final response = await http
          .get(
            Uri.parse(
              '${AppConfig.baseUrl}/api/v1/get-signal?timeframe=$timeframe',
            ),
          )
          .timeout(const Duration(seconds: 8));

      if (response.statusCode == 200) {
        final Map<String, dynamic> data = jsonDecode(response.body);
        return SignalModel.fromJson(data);
      } else {
        throw HttpException('Server Error: Status Code ${response.statusCode}');
      }
    } on TimeoutException {
      throw const SocketException(
        'Connection Timeout. Server did not respond.',
      );
    } on FormatException {
      throw const FormatException('Bad Response Format from Server');
    }
  }

  // DuckDB History API Fetcher
  static Future<Map<String, dynamic>> fetchSignalHistory() async {
    try {
      final response = await http
          .get(Uri.parse('${AppConfig.baseUrl}/api/v1/history'))
          .timeout(const Duration(seconds: 8));

      if (response.statusCode == 200) {
        return jsonDecode(response.body);
      }
    } catch (e) {
      debugPrint("Error fetching history: $e");
    }
    return {"win_rate": 0.0, "total_trades": 0, "history": []};
  }
}

// ==========================================
// 4. MAIN ENTRY POINT & THEME
// ==========================================
void main() {
  runApp(const QuotexSignalApp());
}

class QuotexSignalApp extends StatelessWidget {
  const QuotexSignalApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Quotex AI Signals',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark().copyWith(
        scaffoldBackgroundColor: const Color(0xFF0B0F19),
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFF111827),
          elevation: 0,
        ),
      ),
      home: const SignalDashboardScreen(),
    );
  }
}

// ==========================================
// 5. UI DASHBOARD SCREEN
// ==========================================
class SignalDashboardScreen extends StatefulWidget {
  const SignalDashboardScreen({super.key});

  @override
  State<SignalDashboardScreen> createState() => _SignalDashboardScreenState();
}

class _SignalDashboardScreenState extends State<SignalDashboardScreen> {
  SignalModel? _currentSignal;
  bool _isLoading = false;
  String? _errorMessage;

  bool _isAutoRefreshEnabled = false;
  Timer? _autoRefreshTimer;

  // Timeframe Selection State
  String _selectedTimeframe = '1m';
  final List<String> _timeframes = ['1m', '5m', '10m', '15m', '30m', '1hr'];

  // History & Win-Rate States
  double _winRate = 0.0;
  int _totalTrades = 0;
  List<dynamic> _signalHistory = [];

  // SoundService Instance
  final SoundService _soundService = SoundService();

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  @override
  void dispose() {
    _autoRefreshTimer?.cancel();
    _soundService.stop();
    super.dispose();
  }

  Future<void> _loadData() async {
    await Future.wait([_loadSignal(), _loadHistory()]);
  }

  Future<void> _loadSignal() async {
    if (_isLoading) return;

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final result = await SignalApiService.fetchLiveSignal(_selectedTimeframe);
      if (!mounted) return;
      setState(() {
        _currentSignal = result;
        _isLoading = false;
      });

      if (result.isCall || result.isPut) {
        final alertMessage =
            "${result.pair}, ${result.signal} signal for $_selectedTimeframe with ${result.confidence.toStringAsFixed(0)} percent accuracy";
        _soundService.speakSignal(alertMessage);
      }

      // Refresh history after new signal
      _loadHistory();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorMessage = e.toString().replaceAll('Exception: ', '');
        _isLoading = false;
      });
    }
  }

  Future<void> _loadHistory() async {
    final historyData = await SignalApiService.fetchSignalHistory();
    if (!mounted) return;
    setState(() {
      _winRate = (historyData['win_rate'] ?? 0.0).toDouble();
      _totalTrades = historyData['total_trades'] ?? 0;
      _signalHistory = historyData['history'] ?? [];
    });
  }

  void _toggleAutoRefresh(bool value) {
    setState(() {
      _isAutoRefreshEnabled = value;
    });

    if (value) {
      _autoRefreshTimer = Timer.periodic(const Duration(seconds: 15), (_) {
        _loadData();
      });
    } else {
      _autoRefreshTimer?.cancel();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'QUOTEX AI SIGNAL CENTER',
          style: TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.bold,
            letterSpacing: 1.2,
          ),
        ),
        centerTitle: true,
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 20.0, vertical: 16.0),
          child: Column(
            children: [
              // Auto-Sync Bar & Win Rate Summary Card
              Row(
                children: [
                  Expanded(
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 14,
                        vertical: 12,
                      ),
                      decoration: BoxDecoration(
                        color: const Color(0xFF111827),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: Colors.white12),
                      ),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text(
                            'Auto-Sync (15s)',
                            style: TextStyle(
                              fontSize: 13,
                              color: Colors.white70,
                            ),
                          ),
                          Switch(
                            value: _isAutoRefreshEnabled,
                            onChanged: _toggleAutoRefresh,
                            activeTrackColor: Colors.greenAccent,
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 14,
                        vertical: 14,
                      ),
                      decoration: BoxDecoration(
                        color: const Color(0xFF111827),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(
                          color: Colors.blueAccent.withValues(alpha: 0.3),
                        ),
                      ),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text(
                            'Win Rate',
                            style: TextStyle(
                              fontSize: 13,
                              color: Colors.white70,
                            ),
                          ),
                          Text(
                            '$_winRate% ($_totalTrades)',
                            style: const TextStyle(
                              fontSize: 14,
                              fontWeight: FontWeight.bold,
                              color: Colors.greenAccent,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),

              // Timeframe Selector Dropdown Bar
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 4,
                ),
                decoration: BoxDecoration(
                  color: const Color(0xFF111827),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: Colors.white12),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text(
                      'Select Timeframe:',
                      style: TextStyle(fontSize: 14, color: Colors.white70),
                    ),
                    DropdownButton<String>(
                      value: _selectedTimeframe,
                      dropdownColor: const Color(0xFF111827),
                      underline: const SizedBox(),
                      icon: const Icon(
                        Icons.arrow_drop_down,
                        color: Colors.blueAccent,
                      ),
                      style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.bold,
                      ),
                      items: _timeframes.map((String tf) {
                        return DropdownMenuItem<String>(
                          value: tf,
                          child: Text(tf.toUpperCase()),
                        );
                      }).toList(),
                      onChanged: (String? newValue) {
                        if (newValue != null) {
                          setState(() {
                            _selectedTimeframe = newValue;
                          });
                          _loadSignal(); // নতুন টাইমফ্রেম সিলেক্ট করলেই সিগন্যাল লোড হবে
                        }
                      },
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 20),

              if (_isLoading && _currentSignal == null)
                const Padding(
                  padding: EdgeInsets.all(40.0),
                  child: CircularProgressIndicator(color: Colors.blueAccent),
                )
              else if (_errorMessage != null)
                _buildErrorCard()
              else if (_currentSignal != null)
                _buildSignalCard(_currentSignal!),

              const SizedBox(height: 24),

              SizedBox(
                width: double.infinity,
                height: 52,
                child: ElevatedButton.icon(
                  onPressed: _isLoading ? null : _loadData,
                  icon: _isLoading
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Icon(Icons.refresh_rounded),
                  label: Text(
                    _isLoading ? 'FETCHING...' : 'GET INSTANT SIGNAL',
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 1,
                    ),
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.blueAccent,
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                ),
              ),

              const SizedBox(height: 30),

              // History Section Header
              const Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  'RECENT SIGNALS HISTORY (Last 10)',
                  style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.bold,
                    color: Colors.white70,
                    letterSpacing: 1,
                  ),
                ),
              ),
              const SizedBox(height: 12),

              // Signal History Table/List
              _buildHistoryTable(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSignalCard(SignalModel signal) {
    final themeColor = signal.isCall
        ? Colors.greenAccent
        : signal.isPut
        ? Colors.redAccent
        : Colors.orangeAccent;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(24.0),
      decoration: BoxDecoration(
        color: const Color(0xFF111827),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(
          color: themeColor.withValues(alpha: 0.5),
          width: 1.5,
        ),
        boxShadow: [
          BoxShadow(
            color: themeColor.withValues(alpha: 0.15),
            blurRadius: 25,
            spreadRadius: 2,
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                signal.pair,
                style: const TextStyle(
                  fontSize: 28,
                  fontWeight: FontWeight.w900,
                  color: Colors.white,
                  letterSpacing: 1.5,
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 4,
                ),
                decoration: BoxDecoration(
                  color: Colors.white10,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.white24),
                ),
                child: Text(
                  signal.timeframe.toUpperCase(),
                  style: const TextStyle(
                    color: Colors.white70,
                    fontWeight: FontWeight.bold,
                    fontSize: 12,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),

          Container(
            padding: const EdgeInsets.symmetric(horizontal: 40, vertical: 12),
            decoration: BoxDecoration(
              color: themeColor.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(40),
              border: Border.all(color: themeColor, width: 2),
            ),
            child: Text(
              signal.signal,
              style: TextStyle(
                fontSize: 26,
                fontWeight: FontWeight.w800,
                color: themeColor,
                letterSpacing: 2,
              ),
            ),
          ),
          const SizedBox(height: 20),

          Column(
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text(
                    'AI Accuracy:',
                    style: TextStyle(color: Colors.white60, fontSize: 14),
                  ),
                  Text(
                    '${signal.confidence.toStringAsFixed(1)}%',
                    style: TextStyle(
                      color: themeColor,
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: LinearProgressIndicator(
                  value: signal.confidence / 100,
                  minHeight: 8,
                  backgroundColor: Colors.white10,
                  valueColor: AlwaysStoppedAnimation<Color>(themeColor),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildHistoryTable() {
    if (_signalHistory.isEmpty) {
      return Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: const Color(0xFF111827),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: Colors.white10),
        ),
        child: const Center(
          child: Text(
            'No signal history found in DuckDB.',
            style: TextStyle(color: Colors.white54, fontSize: 13),
          ),
        ),
      );
    }

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF111827),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white12),
      ),
      child: ListView.separated(
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        itemCount: _signalHistory.length,
        separatorBuilder: (context, index) =>
            const Divider(color: Colors.white10, height: 1),
        itemBuilder: (context, index) {
          final item = _signalHistory[index];
          final asset = item['asset'] ?? 'EUR/USD';
          final direction = (item['direction'] ?? 'HOLD')
              .toString()
              .toUpperCase();
          final score = item['score'] ?? '0/4';
          final timeframe = (item['timeframe'] ?? '1m')
              .toString()
              .toUpperCase();
          final timestamp = item['timestamp'] ?? '';

          final isCall = direction == 'CALL' || direction == 'UP';
          final badgeColor = isCall ? Colors.greenAccent : Colors.redAccent;

          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(
                          asset,
                          style: const TextStyle(
                            fontWeight: FontWeight.bold,
                            fontSize: 15,
                            color: Colors.white,
                          ),
                        ),
                        const SizedBox(width: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 6,
                            vertical: 2,
                          ),
                          decoration: BoxDecoration(
                            color: Colors.white10,
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(
                            timeframe,
                            style: const TextStyle(
                              fontSize: 10,
                              color: Colors.white70,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      timestamp,
                      style: const TextStyle(
                        fontSize: 11,
                        color: Colors.white54,
                      ),
                    ),
                  ],
                ),
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 4,
                      ),
                      decoration: BoxDecoration(
                        color: Colors.white10,
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text(
                        'Score: $score',
                        style: const TextStyle(
                          fontSize: 12,
                          color: Colors.white70,
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 6,
                      ),
                      decoration: BoxDecoration(
                        color: badgeColor.withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: badgeColor),
                      ),
                      child: Text(
                        isCall ? 'CALL' : 'PUT',
                        style: TextStyle(
                          color: badgeColor,
                          fontWeight: FontWeight.bold,
                          fontSize: 12,
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildErrorCard() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.red.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.redAccent.withValues(alpha: 0.4)),
      ),
      child: Column(
        children: [
          const Icon(
            Icons.error_outline_rounded,
            color: Colors.redAccent,
            size: 40,
          ),
          const SizedBox(height: 12),
          Text(
            _errorMessage ?? 'Unknown Error Occurred',
            textAlign: TextAlign.center,
            style: const TextStyle(color: Colors.redAccent, fontSize: 14),
          ),
        ],
      ),
    );
  }
}
