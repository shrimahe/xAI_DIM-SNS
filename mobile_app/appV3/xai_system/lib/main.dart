import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:google_fonts/google_fonts.dart';

import 'core/models.dart';
import 'core/system_state_manager.dart';
import 'pages/normal_page.dart';
import 'pages/danger_page.dart';

void main() {
  runApp(const XAISystemApp());
}

class XAISystemApp extends StatelessWidget {
  const XAISystemApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => SystemStateManager()..startPolling(),
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        title: 'XAI System',
        theme: ThemeData(
          textTheme: GoogleFonts.poppinsTextTheme(),
          useMaterial3: true,
        ),
        home: const HomeRouter(),
      ),
    );
  }
}

class HomeRouter extends StatelessWidget {
  const HomeRouter({super.key});

  @override
  Widget build(BuildContext context) {
    final manager = context.watch<SystemStateManager>();
    final status = manager.currentStatus;
    final error = manager.error;

    if (error != null && status == null) {
      return Scaffold(
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(20.0),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                 const Icon(Icons.error_outline, color: Colors.red, size: 48),
                 const SizedBox(height: 16),
                 Text(
                   "Connection Error",
                   style: Theme.of(context).textTheme.headlineSmall,
                 ),
                 const SizedBox(height: 8),
                 Text(
                   error,
                   textAlign: TextAlign.center,
                   style: const TextStyle(color: Colors.grey),
                 ),
                 const SizedBox(height: 24),
                 const CircularProgressIndicator(),
                 const SizedBox(height: 8),
                 const Text("Retrying...", style: TextStyle(fontSize: 12)),
              ],
            ),
          ),
        ),
      );
    }

    if (status == null) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }

    // Check if GLOBAL status is danger OR ANY individual apartment is on fire
    final bool anyFire = status.state == "DANGER" || status.fireStates.containsValue(1);

    if (anyFire) {
      return DangerPage(status: status);
    }

    return NormalPage(status: status);
  }
}
