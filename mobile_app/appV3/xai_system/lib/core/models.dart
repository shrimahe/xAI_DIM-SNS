class SystemStatus {
  final String state;
  final String nodeId;
  final String timestamp; // New field
  final Map<String, int> fireStates;
  final String xaiExplanation;
  final double xaiScore;

  // BME280
  final double temperature;
  final double humidity;
  final double pressure;

  // MQ-2
  final double gas;

  // MAX4466
  final double sound;

  // Path Navigation Data
  final List<PathInfo> pathData;

  SystemStatus({
    required this.state,
    required this.nodeId,
    required this.timestamp,
    required this.fireStates,
    required this.xaiExplanation,
    required this.xaiScore,
    required this.temperature,
    required this.humidity,
    required this.pressure,
    required this.gas,
    required this.sound,
    required this.pathData,
  });

  factory SystemStatus.fromJson(Map<String, dynamic> json) {
    // 1. Extract Node Data
    final nodeData = json['node_data'] as Map<String, dynamic>? ?? {};
    
    final String nodeId = nodeData['node_id'] as String? ?? "Unknown";
    final String timestamp = nodeData['timestamp'] as String? ?? "";

    // Determine state from fire_state (0 = NORMAL, 1 = DANGER)
    final int fireState = nodeData['fire_state'] is int ? nodeData['fire_state'] : 0;
    final String computedState = fireState == 1 ? "DANGER" : "NORMAL";

    // Parse global fire states
    final Map<String, dynamic> fireStatesRaw = json['fire_states'] as Map<String, dynamic>? ?? {};
    final Map<String, int> parsedFireStates = fireStatesRaw.map((k, v) => MapEntry(k, v as int? ?? 0));

    // Parse sensors from node_data
    final double temp = (nodeData['temperature'] as num?)?.toDouble() ?? 0.0;
    final double hum = (nodeData['humidity'] as num?)?.toDouble() ?? 0.0;
    final double pres = (nodeData['pressure'] as num?)?.toDouble() ?? 0.0;
    final double gasVal = (nodeData['gas_level'] as num?)?.toDouble() ?? 0.0;
    final double soundVal = (nodeData['sound_level'] as num?)?.toDouble() ?? 0.0;

    // 2. Extract Anomaly/XAI Data
    final anomalyData = json['anomaly'] as Map<String, dynamic>? ?? {};
    
    // Explanation from backend
    String explanation = anomalyData['explanation'] as String? ?? 
        "System operating normally. No anomalies detected.";

    // 3. Extract Safety Score
    double computedScore = 0.0;
    if (json['safety_score'] != null) {
       computedScore = (json['safety_score'] as num).toDouble() / 100.0;
    } else if (anomalyData['value'] != null) {
       computedScore = (anomalyData['value'] as num).toDouble();
    } else {
       computedScore = (gasVal / 1000).clamp(0.0, 1.0);
    }

    // 4. Extract Path Information
    final List<dynamic> pathList = json['path_information'] as List<dynamic>? ?? [];
    final List<PathInfo> parsedPaths = pathList.map((e) => PathInfo.fromJson(e)).toList();

    // Adjust Explanation if it's empty but system is DANGER
    if (explanation.isEmpty && computedState == "DANGER") {
      explanation = "Warning: High sensor readings detected!";
    }

    return SystemStatus(
      state: computedState,
      nodeId: nodeId,
      timestamp: timestamp,
      fireStates: parsedFireStates,
      xaiExplanation: explanation,
      xaiScore: computedScore,
      temperature: temp,
      humidity: hum,
      pressure: pres,
      gas: gasVal,
      sound: soundVal,
      pathData: parsedPaths,
    );
  }
}

class PathInfo {
  final String fileName;
  final double posX;
  final double posY;
  final bool isEvacuating;
  final bool isSheltering;
  final String assignedExit;
  final List<String> instructions;
  final List<String> pathNodes;

  PathInfo({
    required this.fileName,
    required this.posX,
    required this.posY,
    required this.isEvacuating,
    required this.isSheltering,
    required this.assignedExit,
    required this.instructions,
    required this.pathNodes,
  });

  factory PathInfo.fromJson(Map<String, dynamic> json) {
    // Helper to safely parse string list from JSON string or list
    List<String> parseInstructions(dynamic input) {
      if (input is List) return input.map((e) => e.toString()).toList();
      if (input is String) {
        // Simple cleanup for stringified list like '["a", "b"]'
        return input.replaceAll('[', '').replaceAll(']', '').replaceAll('"', '').split(',').where((e) => e.trim().isNotEmpty).map((e) => e.trim()).toList();
      }
      return [];
    }

    return PathInfo(
      fileName: json['file_name'] ?? "",
      posX: (json['position_x'] as num?)?.toDouble() ?? 0.0,
      posY: (json['position_y'] as num?)?.toDouble() ?? 0.0,
      isEvacuating: (json['is_evacuating'] as num?) == 1,
      isSheltering: (json['is_sheltering'] as num?) == 1,
      assignedExit: json['assigned_exit'] ?? "",
      instructions: parseInstructions(json['turn_by_turn_instructions']),
      pathNodes: parseInstructions(json['path_nodes']),
    );
  }
}
