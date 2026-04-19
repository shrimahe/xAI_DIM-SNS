import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import '../lib/core/models.dart';

void main() {
  test('SystemStatus.fromJson parses backend response correctly', () {
    // JSON response matching new flat structure
    final jsonResponse = {
      "fire_state": 0,
      "gas_level": 332.0,
      "humidity": 62.0,
      "node_id": "Apt1A",
      "pressure": 1009.3,
      "sound_level": 45.0,
      "temperature": 28.5,
      "timestamp": "2026-01-16 11:35:52"
    };

    final status = SystemStatus.fromJson(jsonResponse);

    expect(status.state, "NORMAL");
    expect(status.gas, 332.0);
    expect(status.sound, 45.0);
    expect(status.temperature, 28.5);
    expect(status.humidity, 62.0);
    // Calculated score: 332/1000 = 0.332
    expect(status.xaiScore, closeTo(0.332, 0.001));
    expect(status.path, null);
  });
}
