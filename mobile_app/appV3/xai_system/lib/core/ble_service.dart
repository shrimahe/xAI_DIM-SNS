import 'dart:typed_data';
import 'package:flutter_ble_peripheral/flutter_ble_peripheral.dart';
import 'package:permission_handler/permission_handler.dart';

class BleService {
  static final FlutterBlePeripheral _ble = FlutterBlePeripheral();
  
  // UUID to broadcast in Danger Mode
  static const String _uuid = "12345678-1234-1234-1234-1234567890ab";
  static const String _uuid2 = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
  static const String _uuid3 = "11111111-2222-3333-4444-555555555555";

  static int currentUserIndex = 0; // 0, 1, or 2

  static String get currentUuid {
    switch (currentUserIndex) {
      case 1: return _uuid2;
      case 2: return _uuid3;
      default: return _uuid;
    }
  }

  static Future<void> startAdvertising() async {
    try {
      if (!await _ble.isSupported) {
        print("BLE Advertising NOT supported on this device.");
        return;
      }

      // Check permissions first
      if (!await _checkPermissions()) {
        print("Bluetooth permissions denied. Cannot advertise.");
        return;
      }

      final AdvertiseData advertiseData = AdvertiseData(
        serviceUuid: currentUuid,
        includeDeviceName: false,
      );

      final AdvertiseSettings advertiseSettings = AdvertiseSettings(
        advertiseMode: AdvertiseMode.advertiseModeLowLatency,
        txPowerLevel: AdvertiseTxPower.advertiseTxPowerHigh,
        connectable: true,
        timeout: 0, 
      );

      await _ble.start(advertiseData: advertiseData, advertiseSettings: advertiseSettings);
      print("BLE Advertising Started: $currentUuid");
    } catch (e) {
      print("BLE Start Failed: $e");
    }
  }

  static Future<void> stopAdvertising() async {
    try {
      await _ble.stop();
      print("BLE Advertising Stopped");
    } catch (e) {
      print("BLE Stop Failed: $e");
    }
  }
  
  static Future<bool> isAdvertising() async {
    return await _ble.isAdvertising;
  }

  static Future<bool> _checkPermissions() async {
    // Request all potentially needed permissions
    Map<Permission, PermissionStatus> statuses = await [
      Permission.bluetooth,
      Permission.bluetoothAdvertise,
      Permission.bluetoothConnect,
      Permission.location,
    ].request();

    // Check key permissions based on what's granted
    // On Android 12+: Advertise + Connect
    // On Android <12: Location
    
    final advertiseGranted = statuses[Permission.bluetoothAdvertise] == PermissionStatus.granted;
    final connectGranted = statuses[Permission.bluetoothConnect] == PermissionStatus.granted;
    final locationGranted = statuses[Permission.location] == PermissionStatus.granted;

    // Logic: If Advertise is granted, we are good (likely Android 12+). 
    // If Location is granted and Advertise is not 'permanently denied' (likely Android <12), we are also good.
    
    if (advertiseGranted && connectGranted) return true;
    if (locationGranted) return true;
    
    print("Permissions debug: Adv=$advertiseGranted, Conn=$connectGranted, Loc=$locationGranted");
    return false;
  }
}
