import 'dart:async';
import 'package:flutter/material.dart';
import 'api_service.dart';
import 'models.dart';

class SystemStateManager extends ChangeNotifier {
  SystemStatus? currentStatus;
  String? error;
  Timer? _timer;

  void startPolling() {
    _timer = Timer.periodic(const Duration(seconds: 3), (_) async {
      try {
        final newStatus = await ApiService.fetchSystemStatus();
        currentStatus = newStatus;
        error = null; // Clear error on success
      } catch (e) {
        error = e.toString();
        // Keep old status if possible, or clear it if you want strict error view
      }
      notifyListeners();
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }
}
