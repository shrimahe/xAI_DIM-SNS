import 'package:animate_do/animate_do.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:xai_system/core/ble_service.dart';
import 'package:xai_system/pages/safe_page.dart';
import '../core/models.dart';

class DangerPage extends StatefulWidget {
  final SystemStatus status;
  const DangerPage({super.key, required this.status});

  @override
  State<DangerPage> createState() => _DangerPageState();
}

class _DangerPageState extends State<DangerPage> with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    BleService.startAdvertising();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 1),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    BleService.stopAdvertising();
    _pulseController.dispose();
    super.dispose();
  }

  PathInfo? get myPathInfo {
    final myUuid = BleService.currentUuid;
    try {
      // Find path info where filename contains the UUID
      return widget.status.pathData.firstWhere(
        (p) => p.fileName.contains(myUuid),
      );
    } catch (_) {
      return null;
    }
  }



  @override
  Widget build(BuildContext context) {
    final pathInfo = myPathInfo;
    final isSheltering = pathInfo?.isSheltering ?? false;
    final isEvacuating = pathInfo?.isEvacuating ?? false;

    // "Safe" condition: Sheltering is YES, Evacuating is NO
    if (isSheltering && !isEvacuating) {
      // Stop BLE immediately as we are "safe"
      BleService.stopAdvertising();
      return const SafePage();
    }
    
    // Ensure BLE is running if we are in Danger and NOT safe
    // (It might have been stopped if we flickered into Safe state previously)
    BleService.isAdvertising().then((isAdvertising) {
      if (!isAdvertising) BleService.startAdvertising();
    });

    return Scaffold(
      backgroundColor: const Color(0xFFD32F2F),
      body: SafeArea(
        child: Column(
          children: [
            _buildHeader(),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(24),
                child: Column(
                  children: [
                    _buildAlertBox(isSheltering),
                    const SizedBox(height: 24),
                    if (pathInfo != null) ...[
                       _buildMapVisualizer(pathInfo),
                       const SizedBox(height: 24),
                       _buildInstructionsList(pathInfo),
                    ] else ...[
                       // Fallback if no specific path found
                       Container(
                         padding: const EdgeInsets.all(20),
                         decoration: BoxDecoration(
                           color: Colors.white,
                           borderRadius: BorderRadius.circular(20),
                         ),
                         child: Text(
                           "Waiting for navigation... Follow building standard protocols.",
                           textAlign: TextAlign.center,
                           style: GoogleFonts.poppins(fontSize: 16),
                         ),
                       )
                    ],
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
               FadeTransition(
                opacity: _pulseController,
                child: const Icon(Icons.warning_amber_rounded,
                    color: Colors.white, size: 48),
              ),
              const SizedBox(width: 12),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    "EMERGENCY",
                    style: GoogleFonts.poppins(
                      fontSize: 28,
                      fontWeight: FontWeight.bold,
                      color: Colors.white,
                      letterSpacing: 2,
                    ),
                  ),
                   Text(
                    "Broadcasting Beacon...",
                    style: GoogleFonts.poppins(
                      fontSize: 14,
                      color: Colors.white70,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildAlertBox(bool isSheltering) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(24),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.2),
            blurRadius: 20,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Column(
          children: [
            Text(
              isSheltering ? "SHELTER IN PLACE" : "EVACUATE IMMEDIATELY",
              style: GoogleFonts.poppins(
                fontSize: 24,
                fontWeight: FontWeight.bold,
                color: const Color(0xFFD32F2F),
              ),
            ),
            const SizedBox(height: 8),
            Text(
              isSheltering 
                ? "Safe exit blocked. Stay calm and seal doors."
                : "Fire detected in your vicinity. Follow the path below.",
              textAlign: TextAlign.center,
              style: GoogleFonts.poppins(fontSize: 14, color: Colors.black87),
            ),
          ],
      ),
    );
  }

  Widget _buildMapVisualizer(PathInfo path) {
    // Fire States
    final Map<String, int> fireMap = widget.status.fireStates;
    bool isFire(String id) => (fireMap[id] ?? 0) == 1;

    // Derived Fire Logic (Propagation)
    final bool fNW = isFire("Apt1A");
    final bool fNE = isFire("Apt1B");
    final bool fSW = isFire("Apt2A");
    final bool fSE = isFire("Apt2B");
    
    final bool fNMid = fNW;
    final bool fEMid = fNE;
    final bool fSMid = fSE;
    final bool fWMid = fSW;
    final bool fCenter = false; // Usually safe unless pervasive

    // Cell Definitions
    Widget buildCell(String id, String title, String statusText, bool isDanger, {String? tag, String? exitLabel, bool isTriangle = false}) {
      final isAssignedExit = path.assignedExit.toLowerCase().contains(title.toLowerCase()) || 
                             (exitLabel != null && path.assignedExit.toLowerCase().contains(exitLabel.toLowerCase()));
      
      final color = isDanger ? const Color(0xFFFFEBEE) : (isAssignedExit ? const Color(0xFFE8F5E9).withOpacity(0.5) : const Color(0xFFE8F5E9));
      final borderColor = isDanger ? Colors.red : (isAssignedExit ? Colors.amber : const Color(0xFF4CAF50));
      final textColor = isDanger ? Colors.red : const Color(0xFF2E7D32);

      return Container(
        margin: const EdgeInsets.all(4),
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: borderColor, width: isAssignedExit ? 4 : 2),
          boxShadow: isAssignedExit ? [
            BoxShadow(color: Colors.amber.withOpacity(0.5), blurRadius: 10, spreadRadius: 2)
          ] : null,
        ),
        child: Stack(
          children: [
            // Exit Highlighting Background Glow
            if (isAssignedExit)
              Center(
                child: FadeTransition(
                  opacity: _pulseController,
                  child: Container(
                    width: 40,
                    height: 40,
                    decoration: BoxDecoration(
                      color: Colors.amber.withOpacity(0.2),
                      shape: BoxShape.circle,
                    ),
                  ),
                ),
              ),
            // Title
            Positioned(
              top: 8,
              left: 0,
              right: 0,
              child: Text(
                title,
                textAlign: TextAlign.center,
                style: GoogleFonts.poppins(
                  fontSize: 12,
                  fontWeight: FontWeight.bold,
                  color: isAssignedExit ? Colors.amber.shade900 : Colors.black87,
                ),
              ),
            ),
            // Status
            Positioned(
              bottom: 8,
              left: 0,
              right: 0,
              child: Text(
                isDanger ? "DANGER" : "SAFE",
                textAlign: TextAlign.center,
                style: GoogleFonts.poppins(
                  fontSize: 10,
                  fontWeight: FontWeight.bold,
                  color: textColor,
                ),
              ),
            ),
            // Apt Tag
            if (tag != null)
              Positioned(
                top: 8,
                left: tag == "Apt1A" || tag == "Apt2A" ? 8 : null,
                right: tag == "Apt1B" || tag == "Apt2B" ? 8 : null,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    border: Border.all(color: Colors.grey.shade300),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    tag,
                    style: GoogleFonts.poppins(fontSize: 8, color: Colors.grey.shade600),
                  ),
                ),
              ),
            // Exit Label
             if (exitLabel != null)
              Positioned(
                top: 2,
                left: exitLabel.contains("Emergency") ? 2 : null,
                right: exitLabel.contains("Main") || exitLabel.contains("Side") ? 2 : null,
                child: Text(
                  exitLabel,
                  style: GoogleFonts.poppins(
                    fontSize: 9, 
                    color: const Color(0xFF2E7D32),
                    fontWeight: FontWeight.w600
                  ),
                ),
              ),
            // Exit Triangle Icon
            if (isTriangle)
              Positioned(
                right: tag == "Apt1B" || tag == "Apt2B" ? 20 : null,
                left: tag == "Apt2A" ? 20 : null,
                bottom: 25,
                child: const Icon(Icons.change_history, color: Color(0xFF2E7D32), size: 16),
              ),
          ],
        ),
      );
    }

    return Container(
      height: 340,
      width: double.infinity,
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(24),
      ),
      child: Stack(
        children: [
          // The Grid of Cells
          Column(
            children: [
              Expanded(
                child: Row(
                  children: [
                    Expanded(child: buildCell("NW", "NW", "SAFE", fNW, tag: "Apt1A")),
                    Expanded(child: buildCell("N_Mid", "N_Mid", "SAFE", fNMid)),
                    Expanded(child: buildCell("NE", "NE", "SAFE", fNE, tag: "Apt1B", exitLabel: "Main Exit", isTriangle: true)),
                  ],
                ),
              ),
              Expanded(
                child: Row(
                  children: [
                    Expanded(child: buildCell("W_Mid", "W_Mid", "SAFE", fWMid)),
                    Expanded(child: buildCell("CENTER", "CENTER", "SAFE", fCenter)),
                    Expanded(child: buildCell("E_Mid", "E_Mid", "SAFE", fEMid)),
                  ],
                ),
              ),
              Expanded(
                child: Row(
                  children: [
                    Expanded(child: buildCell("SW", "SW", "SAFE", fSW, tag: "Apt2A", exitLabel: "Emergency Exit", isTriangle: true)),
                    Expanded(child: buildCell("S_Mid", "S_Mid", "SAFE", fSMid)),
                    Expanded(child: buildCell("SE", "SE", "SAFE", fSE, tag: "Apt2B", exitLabel: "Side Exit", isTriangle: true)),
                  ],
                ),
              ),
            ],
          ),

          // Path Painter (Dotted Line)
          Positioned.fill(
            child: CustomPaint(
              painter: PathPainter(
                pathNodes: path.pathNodes,
                assignedExit: path.assignedExit,
                posX: path.posX,
                posY: path.posY,
              ),
            ),
          ),

          // User Dot (Overlay)
          // The coordinates (0.0 to 1.0) need to map to the full container size
          // Container padding is 8, so we adjust slightly if needed, or just map 0-1 to width
          Positioned(
            left: path.posX * (MediaQuery.of(context).size.width - 48 - 16), // Approx width calculation
            top: (1 - path.posY) * 324, // Height without padding
            child: FractionalTranslation(
              translation: const Offset(-0.5, -0.5),
              child: Container(
                width: 24,
                height: 24,
                decoration: BoxDecoration(
                  color: Colors.amber,
                  shape: BoxShape.circle,
                  border: Border.all(color: Colors.white, width: 3),
                  boxShadow: [
                    BoxShadow(color: Colors.black.withOpacity(0.3), blurRadius: 8, spreadRadius: 2),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildInstructionsList(PathInfo path) {
    if (path.instructions.isEmpty) return const SizedBox.shrink();

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.9),
        borderRadius: BorderRadius.circular(24),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            "Instructions",
            style: GoogleFonts.poppins(
              fontSize: 18,
              fontWeight: FontWeight.bold,
              color: Colors.black87,
            ),
          ),
          const SizedBox(height: 12),
          ...path.instructions.map((instr) => Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.arrow_forward_rounded, color: Color(0xFFD32F2F), size: 20),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    instr,
                    style: GoogleFonts.poppins(fontSize: 15, fontWeight: FontWeight.w500),
                  ),
                ),
              ],
            ),
          )),
        ],
      ),
    );
  }
}

class _MapLabel extends StatelessWidget {
  final String text;
  final Color? color;
  final double? fontSize;
  final FontWeight? fontWeight;

  const _MapLabel(this.text, {this.color, this.fontSize, this.fontWeight});

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      textAlign: TextAlign.center,
      style: GoogleFonts.poppins(
        color: color ?? const Color(0xFF00E676).withOpacity(0.7),
        fontWeight: fontWeight ?? FontWeight.bold,
        fontSize: fontSize ?? 11,
        height: 1.1,
      ),
    );
  }
}

class _PositionedOK extends StatelessWidget {
  final double leftRatio;
  final double topRatio;

  const _PositionedOK(this.leftRatio, this.topRatio);

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: leftRatio * 300 - 10, // approximate centering based on container size
      top: topRatio * 300,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
        decoration: BoxDecoration(
          border: Border.all(color: const Color(0xFF00E676), width: 1),
          borderRadius: BorderRadius.circular(4),
        ),
        child: Text(
          "OK",
          style: GoogleFonts.poppins(
            color: const Color(0xFF00E676),
            fontSize: 8,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
    );
  }
}

class GridPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = const Color(0xFF00E676).withOpacity(0.3) // Neon green grid
      ..strokeWidth = 2;

    // Draw 3x3 Grid (Vertical lines at 1/3 and 2/3)
    canvas.drawLine(Offset(size.width / 3, 0), Offset(size.width / 3, size.height), paint);
    canvas.drawLine(Offset(2 * size.width / 3, 0), Offset(2 * size.width / 3, size.height), paint);

    // Draw horizontal lines at 1/3 and 2/3
    canvas.drawLine(Offset(0, size.height / 3), Offset(size.width, size.height / 3), paint);
    canvas.drawLine(Offset(0, 2 * size.height / 3), Offset(size.width, 2 * size.height / 3), paint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class PathPainter extends CustomPainter {
  final List<String> pathNodes;
  final String assignedExit;
  final double posX;
  final double posY;

  PathPainter({
    required this.pathNodes,
    required this.assignedExit,
    required this.posX,
    required this.posY,
  });

  // Coordinates mapping for 3x3 grid (X: 0=West, 1=East; Y: 0=South, 1=North)
  static const Map<String, Offset> nodeCoords = {
    'NW': Offset(1 / 6, 5 / 6),
    'N_Mid': Offset(3 / 6, 5 / 6),
    'NE': Offset(5 / 6, 5 / 6),
    'W_Mid': Offset(1 / 6, 3 / 6),
    'CENTER': Offset(3 / 6, 3 / 6),
    'E_Mid': Offset(5 / 6, 3 / 6),
    'SW': Offset(1 / 6, 1 / 6),
    'S_Mid': Offset(3 / 6, 1 / 6),
    'SE': Offset(5 / 6, 1 / 6),
  };

  static const Map<String, String> exitToNode = {
    'Emergency Exit': 'SW',
    'Main Exit': 'NE',
    'Side Exit': 'SE',
    'EXIT_A': 'NE',
    'EXIT_B': 'SE',
  };

  @override
  void paint(Canvas canvas, Size size) {
    List<String> combinedNodes = List.from(pathNodes);
    
    // Ensure assigned exit is the last node if mapped
    final exitNode = exitToNode[assignedExit];
    if (exitNode != null && (combinedNodes.isEmpty || combinedNodes.last != exitNode)) {
      combinedNodes.add(exitNode);
    }

    if (combinedNodes.isEmpty) return;

    final paint = Paint()
      ..color = Colors.amber.withOpacity(0.9)
      ..strokeWidth = 4
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    final List<Offset> points = [];
    for (final node in combinedNodes) {
      final coord = nodeCoords[node];
      if (coord != null) {
        points.add(Offset(coord.dx * size.width, (1 - coord.dy) * size.height));
      }
    }

    if (points.isEmpty) return;

    final userPos = Offset(posX * size.width, (1 - posY) * size.height);
    
    // Find where the user is relative to the segments
    // We want to skip points the user has already passed.
    int startIndex = 0;
    double minTotalDist = double.infinity;

    for (int i = 0; i < points.length; i++) {
      final dist = (points[i] - userPos).distance;
      if (dist < minTotalDist) {
        minTotalDist = dist;
        startIndex = i;
      }
    }

    // If user is very close to the current point, we might want to start from the next points
    if (minTotalDist < 20 && startIndex < points.length - 1) {
      // Logic to decide if we should skip to next point
      // But for a smooth transition, we always start from userPos to the points[startIndex] or points[startIndex+1]
    }

    final path = Path();
    path.moveTo(userPos.dx, userPos.dy);
    
    // Start drawing from user to the next logical point in order
    // If user is closest to startIndex, draw to points[startIndex] then points[startIndex+1]...
    // unless user has already "passed" points[startIndex]...
    
    for (int i = startIndex; i < points.length; i++) {
      path.lineTo(points[i].dx, points[i].dy);
    }

    _drawDashedPath(canvas, path, paint);
  }

  void _drawDashedPath(Canvas canvas, Path path, Paint paint) {
    const dashWidth = 8.0;
    const dashSpace = 5.0;
    double distance = 0.0;
    
    for (final pathMetric in path.computeMetrics()) {
      while (distance < pathMetric.length) {
        canvas.drawPath(
          pathMetric.extractPath(distance, distance + dashWidth),
          paint,
        );
        distance += dashWidth + dashSpace;
      }
    }
  }

  @override
  bool shouldRepaint(covariant PathPainter oldDelegate) {
    return oldDelegate.posX != posX || 
           oldDelegate.posY != posY || 
           oldDelegate.pathNodes != pathNodes ||
           oldDelegate.assignedExit != assignedExit;
  }
}
