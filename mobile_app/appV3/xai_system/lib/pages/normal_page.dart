import 'package:animate_do/animate_do.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../core/models.dart';
import '../core/ble_service.dart';
import 'widgets/modern_sensor_card.dart';

class NormalPage extends StatefulWidget {
  final SystemStatus status;
  const NormalPage({super.key, required this.status});

  @override
  State<NormalPage> createState() => _NormalPageState();
}

class _NormalPageState extends State<NormalPage> {
  // Rolling data buffers
  final List<double> temperatureHistory = [];
  final List<double> gasHistory = [];
  
  // UI State
  String selectedSensor = "Temperature";

  @override
  void didUpdateWidget(covariant NormalPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    
    // Add new data points
    _addToHistory(temperatureHistory, widget.status.temperature);
    _addToHistory(gasHistory, widget.status.gas);
  }

  void _addToHistory(List<double> list, double value) {
    list.add(value);
    if (list.length > 20) list.removeAt(0);
  }

  List<double> get currentHistory {
    return selectedSensor == "Gas" ? gasHistory : temperatureHistory;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF8F9FE),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _buildHeader(),
              const SizedBox(height: 32),
              FadeInDown(child: _buildStatusCard()),
              const SizedBox(height: 24),
              FadeInDown(
                delay: const Duration(milliseconds: 100),
                child: Row(
                  children: [
                    Expanded(child: _buildScoreCard()),
                    const SizedBox(width: 16),
                    Expanded(child: _buildXaiCard()),
                  ],
                ),
              ),
              const SizedBox(height: 32),
              _buildSectionTitle("Sensors"),
              const SizedBox(height: 16),
              FadeInUp(delay: const Duration(milliseconds: 200), child: _buildSensorsList()),
              const SizedBox(height: 32),
              _buildSectionTitle("$selectedSensor Trend"),
              const SizedBox(height: 16),
              FadeInUp(delay: const Duration(milliseconds: 400), child: _buildChartCard()),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              "Apartment 1A",
              style: GoogleFonts.poppins(
                fontSize: 24,
                fontWeight: FontWeight.bold,
                color: Colors.black87,
              ),
            ),
            Text(
              "Live Monitoring",
              style: GoogleFonts.poppins(
                fontSize: 14,
                color: Colors.grey.shade500,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
        Row(
          children: List.generate(3, (index) {
            final isSelected = BleService.currentUserIndex == index;
            return GestureDetector(
              onTap: () {
                setState(() {
                  BleService.currentUserIndex = index;
                });
              },
              child: Container(
                margin: const EdgeInsets.only(left: 8),
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: isSelected ? const Color(0xFF4E5AE8) : Colors.white,
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(
                    color: isSelected ? const Color(0xFF4E5AE8) : Colors.grey.shade300,
                  ),
                ),
                child: Text(
                  "U${index + 1}",
                  style: GoogleFonts.poppins(
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                    color: isSelected ? Colors.white : Colors.grey.shade600,
                  ),
                ),
              ),
            );
          }),
        ),
      ],
    );
  }

  Widget _buildStatusCard() {
    final isDanger = widget.status.state == "DANGER";
    final color = isDanger ? const Color(0xFFFF8A80) : const Color(0xFF66BB6A);
    final icon = isDanger ? Icons.warning_rounded : Icons.check_circle_rounded;
    final text = isDanger ? "System Warning" : "System Normal";
    final desc = isDanger
        ? "Hazardous levels detected. Evacuate."
        : "All safety sensors are operating correctly.";

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(32),
        boxShadow: [
          BoxShadow(
            color: color.withOpacity(0.15),
            blurRadius: 30,
            offset: const Offset(0, 15),
          ),
        ],
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: color.withOpacity(0.1),
              shape: BoxShape.circle,
            ),
            child: Icon(icon, color: color, size: 32),
          ),
          const SizedBox(width: 20),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  text,
                  style: GoogleFonts.poppins(
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                    color: Colors.black87,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  desc,
                  style: GoogleFonts.poppins(
                      fontSize: 12, color: Colors.grey.shade600, height: 1.5),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSectionTitle(String title) {
    return Text(
      title,
      style: GoogleFonts.poppins(
        fontSize: 18,
        fontWeight: FontWeight.w600,
        color: Colors.black87,
      ),
    );
  }

  Widget _buildSensorsList() {
    return SizedBox(
      height: 150,
      child: ListView(
        scrollDirection: Axis.horizontal,
        clipBehavior: Clip.none,
        children: [
          ModernSensorCard(
            title: "Temperature",
            value: widget.status.temperature.toStringAsFixed(1),
            unit: "°C",
            icon: Icons.thermostat_rounded,
            color: const Color(0xFF4E5AE8),
            isSelected: selectedSensor == "Temperature",
            onTap: () => setState(() => selectedSensor = "Temperature"),
          ),
          const SizedBox(width: 16),
          ModernSensorCard(
            title: "Gas Level",
            value: widget.status.gas.toStringAsFixed(0),
            unit: "ppm",
            icon: Icons.cloud_rounded,
            color: const Color(0xFFFD7E14),
            isSelected: selectedSensor == "Gas",
            onTap: () => setState(() => selectedSensor = "Gas"),
          ),
          const SizedBox(width: 16),
          ModernSensorCard(
            title: "Humidity",
            value: widget.status.humidity.toStringAsFixed(0),
            unit: "%",
            icon: Icons.water_drop_rounded,
            color: const Color(0xFF0CA678),
            isSelected: false,
            onTap: () {},
          ),
           const SizedBox(width: 16),
          ModernSensorCard(
            title: "Sound",
            value: widget.status.sound.toStringAsFixed(0),
            unit: "dB",
            icon: Icons.volume_up_rounded,
            color: const Color(0xFFE83E8C),
            isSelected: false,
            onTap: () {},
          ),
        ],
      ),
    );
  }

  Widget _buildChartCard() {
    final history = currentHistory;
    
    if (history.isEmpty) {
      return Container(
        height: 200,
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(24),
        ),
        child: const Center(child: Text("Waiting for data...")),
      );
    }

    // Determine fixed axis range based on sensor type
    final double maxY = selectedSensor == "Temperature" ? 60.0 : 1000.0;
    
    return Container(
      height: 240,
      width: double.infinity,
      padding: const EdgeInsets.only(right: 24, left: 12, top: 32, bottom: 12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(32),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.05),
            blurRadius: 20,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: LineChart(
        LineChartData(
          minY: 0,
          maxY: maxY,
          gridData: FlGridData(show: false),
          titlesData: FlTitlesData(
            leftTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 40,
                getTitlesWidget: (value, meta) {
                  return Text(
                    value.toStringAsFixed(1),
                    style: GoogleFonts.poppins(
                      color: Colors.grey.shade600,
                      fontSize: 10,
                      fontWeight: FontWeight.w500,
                    ),
                  );
                },
              ),
            ),
            rightTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
            topTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
            bottomTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
          ),
          borderData: FlBorderData(show: false),
          lineBarsData: [
            LineChartBarData(
              spots: List.generate(
                history.length,
                (i) => FlSpot(i.toDouble(), history[i]),
              ),
              isCurved: true,
              color: const Color(0xFF4E5AE8),
              barWidth: 4,
              isStrokeCapRound: true,
              dotData: FlDotData(show: false),
              belowBarData: BarAreaData(
                show: true,
                color: const Color(0xFF4E5AE8).withOpacity(0.1),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildScoreCard() {
    // Calculate a visual score based on gas/temp (0-100)
    final double safeScore = (widget.status.xaiScore * 100).clamp(0, 100);
    
    return Container(
      height: 160,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF4E5AE8),
        borderRadius: BorderRadius.circular(24),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF4E5AE8).withOpacity(0.3),
            blurRadius: 20,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.2),
              shape: BoxShape.circle,
            ),
            child: const Icon(Icons.shield_rounded, color: Colors.white, size: 20),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                "${safeScore.toStringAsFixed(0)}%",
                style: GoogleFonts.poppins(
                  fontSize: 32,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                  height: 1,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                "Safety Score",
                style: GoogleFonts.poppins(
                  fontSize: 12,
                  color: Colors.white.withOpacity(0.8),
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildXaiCard() {
    return GestureDetector(
      onTap: () {
        showDialog(
          context: context,
          builder: (context) => AlertDialog(
            title: Text("XAI Analysis", style: GoogleFonts.poppins(fontWeight: FontWeight.bold)),
            content: Text(widget.status.xaiExplanation, style: GoogleFonts.poppins()),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text("Close"),
              ),
            ],
          ),
        );
      },
      child: Container(
        height: 160,
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: Colors.blue.withOpacity(0.1)),
          boxShadow: [
            BoxShadow(
              color: Colors.blue.withOpacity(0.05),
              blurRadius: 20,
              offset: const Offset(0, 10),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
             Row(
              children: [
                Icon(Icons.auto_awesome, size: 18, color: Colors.blue.shade600),
                const SizedBox(width: 6),
                Text(
                  "AI Insight",
                  style: GoogleFonts.poppins(
                    fontSize: 14,
                    fontWeight: FontWeight.bold,
                    color: Colors.black87,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Expanded(
              child: Text(
                widget.status.xaiExplanation,
                overflow: TextOverflow.fade,
                style: GoogleFonts.poppins(
                  fontSize: 12,
                  color: Colors.grey.shade700,
                  height: 1.5,
                ),
              ),
            ),
            const SizedBox(height: 4),
            Text(
              "Tap for details",
              style: GoogleFonts.poppins(
                fontSize: 10,
                color: Colors.blue,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
