import 'dart:convert';
import 'package:http/http.dart' as http;
import 'models.dart';

class ApiService {
  // Updated to match the real backend IP provided by user
  static const String baseUrl = "http://10.128.181.157:5000"; 

  // Choose node here: 1A, 1B, 2A, 2B
  static const String node = "1A";

  static Future<SystemStatus> fetchSystemStatus() async {
    try {
      final response = await http
          .get(
            Uri.parse("$baseUrl/api/nodes/$node"),
          )
          .timeout(const Duration(seconds: 5));

      if (response.statusCode != 200) {
        throw Exception("Failed to fetch node data: ${response.statusCode}");
      }

      final json = jsonDecode(response.body);
      return SystemStatus.fromJson(json);
    } catch (e) {
      throw Exception("API Error: $e");
    }
  }
}
