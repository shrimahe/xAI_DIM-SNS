"""
Building Safety Management System v4.0 - Realtime Edition
==========================================================
Professional realtime building safety monitoring system with:
  - Automatic MQTT connection to local broker
  - Probability-based zone detection with distance averaging
  - Dynamic path planning with wrong-direction detection
  - Step-by-step evacuation guidance
  - Clean, professional light-themed interface

Features:
  - Auto-connects to localhost MQTT broker on startup
  - State changes automatically based on sensor inputs
  - Individual JSON files per tracked person
  - Turn-by-turn navigation with dynamic rerouting

Output: tracking_realtime/
"""
import sqlite3
import numpy as np
import networkx as nx
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib.animation import FuncAnimation
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from collections import deque, defaultdict
from enum import Enum, auto
import json
import threading
import time
import math
import os
from datetime import datetime


# =============================================================================
# CONFIGURATION
# =============================================================================

import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "path_information.db")

# MQTT Configuration
MQTT_BROKER = "localhost"
MQTT_PORT = 1883

# Apartment to zone mapping
NODE_MAP = {
    'Apt1A': 'NW', 'Apt1B': 'NE',
    'Apt2A': 'SW', 'Apt2B': 'SE',
    'A': 'NW', 'B': 'NE', 'C': 'SW', 'D': 'SE'
}
REVERSE_NODE_MAP = {'NW': 'Apt1A', 'NE': 'Apt1B', 'SW': 'Apt2A', 'SE': 'Apt2B'}

# Output folder
OUTPUT_FOLDER = "tracking_realtime"

# Hazard thresholds
GAS_DANGER = 1500
GAS_WARNING = 800
TEMP_DANGER = 45
TEMP_WARNING = 38

# Tracking parameters
BUILDING_SIZE_METERS = 10.0
DISTANCE_SCALE = 0.12
TRACK_ALL_DEVICES = True
TRACKED_DEVICES = []

# Probabilistic tracking
DISTANCE_AVG_WINDOW = 2  # Minimal averaging for fastest response
ZONE_DWELL_TIME = 0.3
ZONE_PROBABILITY_THRESHOLD = 0.15
POSITION_SMOOTHING = 0.0  # No smoothing = direct tracking of actual position
VELOCITY_DECAY = 0.9
MAX_VELOCITY = 2.0

# Dynamic path planning
PATH_REEVALUATION_INTERVAL = 1.0
OFF_PATH_THRESHOLD = 0.15
WRONG_DIRECTION_TOLERANCE = 2
FORCED_REROUTE_THRESHOLD = 4

# =============================================================================
# COLOR THEME - Professional Light Theme
# =============================================================================

COLORS = {
    # Backgrounds
    'bg_primary': '#f8f9fa',
    'bg_secondary': '#ffffff',
    'bg_card': '#ffffff',
    'bg_dark': '#e9ecef',

    # Text
    'text_primary': '#212529',
    'text_secondary': '#6c757d',
    'text_muted': '#adb5bd',

    # Status colors
    'safe': '#28a745',
    'warning': '#ffc107',
    'danger': '#dc3545',
    'info': '#17a2b8',
    'evacuating': '#fd7e14',

    # Accents
    'accent_blue': '#007bff',
    'accent_teal': '#20c997',
    'accent_purple': '#6f42c1',

    # Zones
    'zone_safe': '#d4edda',
    'zone_warning': '#fff3cd',
    'zone_danger': '#f8d7da',
    'zone_border_safe': '#28a745',
    'zone_border_warning': '#ffc107',
    'zone_border_danger': '#dc3545',

    # Paths
    'path_safe': '#28a745',
    'path_warning': '#fd7e14',
    'path_danger': '#dc3545',

    # UI Elements
    'grid': '#dee2e6',
    'shadow': '#00000015',
}


# =============================================================================
# ENUMS
# =============================================================================

class PersonStatus(Enum):
    SAFE = auto()
    WARNING = auto()
    EVACUATING = auto()
    ESCAPED = auto()


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class DistanceHistory:
    """Sliding window for distance averaging."""
    window_size: int = DISTANCE_AVG_WINDOW
    history: Dict[str, deque] = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=DISTANCE_AVG_WINDOW)))
    rssi_history: Dict[str, deque] = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=DISTANCE_AVG_WINDOW)))

    def add(self, anchor: str, distance: float, rssi: float):
        self.history[anchor].append(distance)
        self.rssi_history[anchor].append(rssi)

    def get_averaged(self, anchor: str) -> Optional[float]:
        if anchor not in self.history or len(self.history[anchor]) == 0:
            return None
        return sum(self.history[anchor]) / len(self.history[anchor])

    def get_averaged_rssi(self, anchor: str) -> Optional[float]:
        if anchor not in self.rssi_history or len(self.rssi_history[anchor]) == 0:
            return None
        return sum(self.rssi_history[anchor]) / len(self.rssi_history[anchor])

    def get_all_averaged(self) -> Dict[str, float]:
        return {
            anchor: self.get_averaged(anchor)
            for anchor in self.history
            if len(self.history[anchor]) >= 2
        }

    def get_sample_count(self, anchor: str) -> int:
        return len(self.history.get(anchor, []))


@dataclass
class ZoneTransition:
    """Zone transition with dwell time confirmation."""
    current_zone: str = ""
    candidate_zone: Optional[str] = None
    candidate_since: float = 0.0
    zone_probabilities: Dict[str, float] = field(default_factory=dict)

    def update(self, detected_zone: str, probabilities: Dict[str, float]) -> Tuple[str, bool]:
        self.zone_probabilities = probabilities

        if not self.current_zone:
            self.current_zone = detected_zone
            return self.current_zone, True

        if detected_zone == self.current_zone:
            self.candidate_zone = None
            return self.current_zone, False

        now = time.time()
        if detected_zone != self.candidate_zone:
            self.candidate_zone = detected_zone
            self.candidate_since = now
            return self.current_zone, False

        if now - self.candidate_since >= ZONE_DWELL_TIME:
            self.current_zone = detected_zone
            self.candidate_zone = None
            return self.current_zone, True

        return self.current_zone, False


@dataclass
class MovementState:
    """Velocity tracking for movement prediction."""
    velocity: Tuple[float, float] = (0.0, 0.0)
    last_position: Tuple[float, float] = (0.5, 0.5)
    last_update: float = field(default_factory=time.time)

    def update(self, new_position: Tuple[float, float]) -> Tuple[float, float]:
        now = time.time()
        dt = now - self.last_update

        if dt > 0.05 and dt < 5.0:
            dx = new_position[0] - self.last_position[0]
            dy = new_position[1] - self.last_position[1]

            inst_vx = dx / dt
            inst_vy = dy / dt

            speed = math.sqrt(inst_vx**2 + inst_vy**2)
            if speed > MAX_VELOCITY:
                scale = MAX_VELOCITY / speed
                inst_vx *= scale
                inst_vy *= scale

            self.velocity = (
                VELOCITY_DECAY * self.velocity[0] + (1 - VELOCITY_DECAY) * inst_vx,
                VELOCITY_DECAY * self.velocity[1] + (1 - VELOCITY_DECAY) * inst_vy
            )
        else:
            self.velocity = (self.velocity[0] * VELOCITY_DECAY, self.velocity[1] * VELOCITY_DECAY)

        self.last_position = new_position
        self.last_update = now
        return self.velocity

    def get_speed(self) -> float:
        return math.sqrt(self.velocity[0]**2 + self.velocity[1]**2)

    def get_direction(self) -> Optional[str]:
        speed = self.get_speed()
        if speed < 0.01:
            return None
        vx, vy = self.velocity
        if abs(vx) > abs(vy):
            return "EAST" if vx > 0 else "WEST"
        else:
            return "NORTH" if vy > 0 else "SOUTH"


@dataclass
class Person:
    uuid: str
    distances: Dict[str, float] = field(default_factory=dict)
    rssi_values: Dict[str, float] = field(default_factory=dict)
    distance_history: DistanceHistory = field(default_factory=DistanceHistory)
    zone_transition: ZoneTransition = field(default_factory=ZoneTransition)
    movement_state: MovementState = field(default_factory=MovementState)
    position: Tuple[float, float] = (0.5, 0.5)
    smoothed_position: Tuple[float, float] = (0.5, 0.5)
    last_seen: float = field(default_factory=time.time)
    current_zone: str = ""
    zone_probabilities: Dict[str, float] = field(default_factory=dict)
    status: PersonStatus = PersonStatus.SAFE
    message: str = ""
    assigned_exit: str = ""
    path: List[str] = field(default_factory=list)
    path_index: int = 0
    directions: str = ""
    turn_by_turn: List[str] = field(default_factory=list)
    last_path_update: float = 0.0
    wrong_direction_count: int = 0
    current_guidance: str = ""
    guidance_urgency: str = "normal"
    previous_distance_to_target: float = float('inf')
    reroute_count: int = 0
    path_history: List[str] = field(default_factory=list)
    priority: bool = False
    near_exit_since: Optional[float] = None

    def add_distance(self, anchor: str, distance: float, rssi: float):
        self.distances[anchor] = distance
        self.rssi_values[anchor] = rssi
        self.last_seen = time.time()
        self.distance_history.add(anchor, distance, rssi)
        self.update_position()

    def update_position(self):
        anchors = {
            'A': (0.15, 0.85), 'B': (0.85, 0.85),
            'C': (0.15, 0.15), 'D': (0.85, 0.15),
            'Apt1A': (0.15, 0.85), 'Apt1B': (0.85, 0.85),
            'Apt2A': (0.15, 0.15), 'Apt2B': (0.85, 0.15),
        }

        averaged_distances = self.distance_history.get_all_averaged()
        active = [(a, d * DISTANCE_SCALE) for a, d in averaged_distances.items()
                  if d is not None and d > 0 and a in anchors]

        if len(active) == 0:
            return

        raw_position = self._compute_position(active, anchors)

        if self.smoothed_position:
            self.smoothed_position = (
                self.smoothed_position[0] * POSITION_SMOOTHING + raw_position[0] * (1 - POSITION_SMOOTHING),
                self.smoothed_position[1] * POSITION_SMOOTHING + raw_position[1] * (1 - POSITION_SMOOTHING)
            )
        else:
            self.smoothed_position = raw_position

        self.position = self.smoothed_position
        self.movement_state.update(self.position)
        self.zone_probabilities = self._calculate_zone_probabilities(active, anchors)

        detected_zone = self._get_most_likely_zone()
        self.current_zone, _ = self.zone_transition.update(detected_zone, self.zone_probabilities)

    def _compute_position(self, active: List[Tuple[str, float]], anchors: Dict) -> Tuple[float, float]:
        if len(active) == 1:
            anchor, dist_norm = active[0]
            ax, ay = anchors[anchor]
            # Position is near the anchor, scaled by distance
            # Small distance = close to anchor, large distance = further away
            cx, cy = 0.5, 0.5
            dx, dy = cx - ax, cy - ay
            length = math.sqrt(dx*dx + dy*dy)
            if length > 0:
                # Use actual distance without cap for better accuracy
                return (
                    float(np.clip(ax + dist_norm * dx / length, 0.0, 1.0)),
                    float(np.clip(ay + dist_norm * dy / length, 0.0, 1.0))
                )
            return (ax, ay)  # Stay at anchor position if no direction

        if len(active) == 2:
            (a1, d1), (a2, d2) = active
            p1, p2 = np.array(anchors[a1]), np.array(anchors[a2])
            total = d1 + d2
            if total > 0:
                w1, w2 = d2 / total, d1 / total
                pos = p1 * w1 + p2 * w2
                return (float(np.clip(pos[0], 0.0, 1.0)), float(np.clip(pos[1], 0.0, 1.0)))
            return (0.5, 0.5)

        positions, dists, weights = [], [], []
        for anchor, dist_norm in active:
            if anchor in anchors:
                positions.append(anchors[anchor])
                dists.append(dist_norm)
                rssi = self.distance_history.get_averaged_rssi(anchor) or -70
                rssi_weight = max(0.1, (rssi + 100) / 60)
                weights.append(rssi_weight)

        positions = np.array(positions)
        dists = np.array(dists)
        weights = np.array(weights)
        weights = weights / weights.sum()

        estimate = np.average(positions, axis=0, weights=weights)

        # Gradient descent for multilateration - more iterations for better accuracy
        for _ in range(30):
            current = np.sqrt(np.sum((positions - estimate) ** 2, axis=1))
            errors = current - dists
            gradient = np.zeros(2)
            for i, (pos, err, w) in enumerate(zip(positions, errors, weights)):
                direction = estimate - pos
                norm = np.linalg.norm(direction)
                if norm > 0.001:
                    gradient += w * err * direction / norm
            estimate = estimate - 0.15 * gradient  # Smaller step for finer convergence

        return (float(np.clip(estimate[0], 0.0, 1.0)), float(np.clip(estimate[1], 0.0, 1.0)))

    def _calculate_zone_probabilities(self, active, anchors) -> Dict[str, float]:
        zones = {
            'NW': (0.15, 0.85), 'N_Mid': (0.50, 0.85), 'NE': (0.85, 0.85),
            'W_Mid': (0.15, 0.50), 'CENTER': (0.50, 0.50), 'E_Mid': (0.85, 0.50),
            'SW': (0.15, 0.15), 'S_Mid': (0.50, 0.15), 'SE': (0.85, 0.15),
        }

        pos = self.position
        zone_distances = {}
        for zone, zpos in zones.items():
            d = math.sqrt((pos[0] - zpos[0])**2 + (pos[1] - zpos[1])**2)
            zone_distances[zone] = d

        sigma = 0.15
        raw_probs = {}
        for zone, d in zone_distances.items():
            raw_probs[zone] = math.exp(-(d**2) / (2 * sigma**2))

        total = sum(raw_probs.values())
        if total > 0:
            return {z: p / total for z, p in raw_probs.items()}
        return {z: 1.0/9 for z in zones}

    def _get_most_likely_zone(self) -> str:
        if not self.zone_probabilities:
            return "CENTER"
        return max(self.zone_probabilities, key=self.zone_probabilities.get)

    def get_zone_confidence(self) -> float:
        if not self.zone_probabilities or not self.current_zone:
            return 0.0
        return self.zone_probabilities.get(self.current_zone, 0.0)


# =============================================================================
# SENSOR
# =============================================================================

@dataclass
class Sensor:
    fire: bool = False
    gas: int = 0
    temp: float = 25.0
    sound: int = 0

    def is_dangerous(self) -> bool:
        return self.fire or self.gas > GAS_DANGER or self.temp > TEMP_DANGER

    def has_warning(self) -> bool:
        return self.gas > GAS_WARNING or self.temp > TEMP_WARNING

    def get_status_text(self) -> str:
        if self.fire:
            return "FIRE"
        if self.gas > GAS_DANGER or self.temp > TEMP_DANGER:
            return "DANGER"
        if self.gas > GAS_WARNING or self.temp > TEMP_WARNING:
            return "WARNING"
        return "SAFE"

    def get_color(self) -> str:
        if self.is_dangerous():
            return COLORS['danger']
        if self.has_warning():
            return COLORS['warning']
        return COLORS['safe']


# =============================================================================
# BUILDING
# =============================================================================

class Building:
    NODES = {
        'NW': (0.15, 0.85), 'N_Mid': (0.50, 0.85), 'NE': (0.85, 0.85),
        'W_Mid': (0.15, 0.50), 'CENTER': (0.50, 0.50), 'E_Mid': (0.85, 0.50),
        'SW': (0.15, 0.15), 'S_Mid': (0.50, 0.15), 'SE': (0.85, 0.15),
    }

    EDGES = [
        ('NW', 'N_Mid'), ('N_Mid', 'NE'),
        ('W_Mid', 'CENTER'), ('CENTER', 'E_Mid'),
        ('SW', 'S_Mid'), ('S_Mid', 'SE'),
        ('NW', 'W_Mid'), ('W_Mid', 'SW'),
        ('N_Mid', 'CENTER'), ('CENTER', 'S_Mid'),
        ('NE', 'E_Mid'), ('E_Mid', 'SE'),
    ]

    EXITS = {'NE': 'Main Exit', 'SW': 'Emergency Exit', 'SE': 'Side Exit'}

    def __init__(self):
        self.graph = nx.Graph()
        self.graph.add_nodes_from(self.NODES.keys())
        self.graph.add_edges_from(self.EDGES)
        self.sensors = {zone: Sensor() for zone in ['NW', 'NE', 'SW', 'SE', 'CENTER']}

    def update_sensor(self, zone: str, **kwargs):
        if zone in self.sensors:
            for key, value in kwargs.items():
                setattr(self.sensors[zone], key, value)

    def get_zone_sensor(self, zone_id: str) -> Sensor:
        corner_map = {
            'NW': 'NW', 'N_Mid': 'NW', 'NE': 'NE',
             'W_Mid': 'SW', 'CENTER': 'CENTER', 'E_Mid': 'NE',
            'SW': 'SW', 'S_Mid': 'SE', 'SE': 'SE'
        }
        return self.sensors.get(corner_map.get(zone_id, 'NW'), Sensor())

    def has_any_danger(self) -> Tuple[bool, str]:
        for zone, sensor in self.sensors.items():
            if sensor.fire:
                return True, f"FIRE in {zone}"
            if sensor.gas > GAS_DANGER:
                return True, f"GAS LEAK in {zone}"
            if sensor.temp > TEMP_DANGER:
                return True, f"HIGH TEMP in {zone}"
        return False, ""

    def find_path(self, start: str, end: str, allow_through_danger: bool = False) -> Tuple[List[str], float]:
        if start not in self.graph or end not in self.graph:
            return [], float('inf')
        try:
            # Update edge weights based on current danger levels
            for u, v in self.graph.edges():
                sensor_u = self.get_zone_sensor(u)
                sensor_v = self.get_zone_sensor(v)
                # High weight for dangerous zones to avoid them
                weight_u = 1000 if sensor_u.is_dangerous() else (5 if sensor_u.has_warning() else 1)
                weight_v = 1000 if sensor_v.is_dangerous() else (5 if sensor_v.has_warning() else 1)
                self.graph[u][v]['weight'] = max(weight_u, weight_v)

            # Use dijkstra_path which respects edge weights
            path = nx.dijkstra_path(self.graph, start, end, weight='weight')
            cost = sum(self.graph[path[i]][path[i+1]]['weight'] for i in range(len(path) - 1))

            # Check if path goes through any dangerous zone (except start if person is already there)
            if not allow_through_danger:
                for i, node in enumerate(path):
                    if i == 0:
                        continue  # Skip start node - person might already be in danger
                    sensor = self.get_zone_sensor(node)
                    if sensor.is_dangerous():
                        return [], float('inf')  # Reject path that goes through fire

            return path, cost
        except nx.NetworkXNoPath:
            return [], float('inf')

    def find_nearest_node(self, pos: Tuple[float, float]) -> str:
        min_dist = float('inf')
        nearest = 'CENTER'
        for node, npos in self.NODES.items():
            dist = math.sqrt((pos[0] - npos[0])**2 + (pos[1] - npos[1])**2)
            if dist < min_dist:
                min_dist = dist
                nearest = node
        return nearest

    def find_best_exit(self, start: str, exit_counts: Dict[str, int]) -> Tuple[Optional[str], List[str]]:
        best_exit = None
        best_path = []
        best_score = float('inf')

        # Check if person is currently in a danger zone
        start_sensor = self.get_zone_sensor(start)
        person_in_danger = start_sensor.is_dangerous()

        # If person is in danger zone, first priority is getting them OUT
        if person_in_danger:
            # Find nearest safe zone to escape to
            safest_neighbor = None
            min_danger = float('inf')
            for neighbor in self.graph.neighbors(start):
                sensor = self.get_zone_sensor(neighbor)
                if not sensor.is_dangerous():
                    danger_level = 10 if sensor.has_warning() else 0
                    if danger_level < min_danger:
                        min_danger = danger_level
                        safest_neighbor = neighbor

            if safest_neighbor:
                # First get out of danger, then find exit from safe zone
                escape_path = [start, safest_neighbor]
                # Now find best exit from the safe zone
                for exit_node in self.EXITS:
                    exit_sensor = self.get_zone_sensor(exit_node)
                    if exit_sensor.is_dangerous():
                        continue
                    path, cost = self.find_path(safest_neighbor, exit_node)
                    if path:
                        congestion = exit_counts.get(exit_node, 0) * 0.5
                        score = cost + congestion
                        if score < best_score:
                            best_score = score
                            best_exit = exit_node
                            best_path = escape_path + path[1:]  # Combine paths
                return best_exit, best_path

        # Normal case: person not in danger zone
        for exit_node in self.EXITS:
            # Skip exits that are in dangerous zones (fire/gas leak)
            exit_sensor = self.get_zone_sensor(exit_node)
            if exit_sensor.is_dangerous():
                continue  # This exit is blocked due to fire/danger

            path, cost = self.find_path(start, exit_node)
            if path:
                congestion = exit_counts.get(exit_node, 0) * 0.5
                score = cost + congestion
                if score < best_score:
                    best_score = score
                    best_exit = exit_node
                    best_path = path

        # If all exits are blocked, find path to safest zone first (shelter in place)
        if best_exit is None:
            safest_zone = None
            min_danger = float('inf')
            for neighbor in self.graph.neighbors(start):
                sensor = self.get_zone_sensor(neighbor)
                danger_level = 100 if sensor.is_dangerous() else (10 if sensor.has_warning() else 0)
                if danger_level < min_danger:
                    min_danger = danger_level
                    safest_zone = neighbor
            if safest_zone and safest_zone != start:
                return None, [start, safest_zone]  # Path to safer zone

        return best_exit, best_path

    def get_turn_by_turn(self, path: List[str], exit_name: str) -> Tuple[str, List[str]]:
        if not path:
            return "", []

        directions = []
        instructions = []

        for i in range(len(path) - 1):
            curr = self.NODES[path[i]]
            next_node = self.NODES[path[i + 1]]
            dx, dy = next_node[0] - curr[0], next_node[1] - curr[1]

            if abs(dx) > abs(dy):
                direction = "East" if dx > 0 else "West"
            else:
                direction = "North" if dy > 0 else "South"

            directions.append(direction)
            instructions.append(f"{i+1}. Go {direction} to {path[i+1]}")

        instructions.append(f"{len(path)}. EXIT via {exit_name}")
        return " -> ".join(directions), instructions


# =============================================================================
# TRACKER
# =============================================================================

class Tracker:
    def __init__(self):
        self.people: Dict[str, Person] = {}
        self._lock = threading.Lock()

    def update(self, uuid: str, anchor: str, distance: float, rssi: float):
        with self._lock:
            if uuid not in self.people:
                self.people[uuid] = Person(uuid=uuid)
            self.people[uuid].add_distance(anchor, distance, rssi)

    def get_all(self) -> List[Person]:
        with self._lock:
            return list(self.people.values())

    def get_active(self, max_age: float = 30.0) -> List[Person]:
        with self._lock:
            now = time.time()
            return [p for p in self.people.values() if (now - p.last_seen) < max_age]

    def count(self) -> int:
        return len(self.get_active())

    def get_zone_stats(self) -> Dict[str, int]:
        stats = {}
        for person in self.get_active():
            zone = person.current_zone or "CENTER"
            stats[zone] = stats.get(zone, 0) + 1
        return stats

    def reset_status(self):
        with self._lock:
            for person in self.people.values():
                if person.status != PersonStatus.ESCAPED:
                    person.status = PersonStatus.SAFE
                    person.message = ""
                    person.path = []
                    person.path_index = 0


# =============================================================================
# MQTT INTERFACE
# =============================================================================

class MQTTInterface:
    def __init__(self, building: Building, tracker: Tracker):
        self.building = building
        self.tracker = tracker
        self.broker = MQTT_BROKER
        self.port = MQTT_PORT
        self.client = None
        self.connected = False
        self.callbacks = []
        self.node_status = {'Apt1A': False, 'Apt1B': False, 'Apt2A': False, 'Apt2B': False}
        self.anchor_data = {
            'Apt1A': {'distance': None, 'rssi': None, 'last_update': 0, 'device': None},
            'Apt1B': {'distance': None, 'rssi': None, 'last_update': 0, 'device': None},
            'Apt2A': {'distance': None, 'rssi': None, 'last_update': 0, 'device': None},
            'Apt2B': {'distance': None, 'rssi': None, 'last_update': 0, 'device': None},
        }

    def connect(self) -> bool:
        try:
            import paho.mqtt.client as mqtt

            def on_connect(client, userdata, flags, rc):
                if rc == 0:
                    print(f"[MQTT] Connected to {self.broker}:{self.port}")
                    client.subscribe("building/#")
                    client.subscribe("sensorData/nodes/#")
                    client.subscribe("ips/nodes/#")
                    client.subscribe("ips/anchors/#")

                    if TRACKED_DEVICES:
                        for device_uuid in TRACKED_DEVICES:
                            for apt in ['Apt1A', 'Apt1B', 'Apt2A', 'Apt2B']:
                                client.subscribe(f"building/{apt}/{device_uuid}")

                    self.connected = True
                    for cb in self.callbacks:
                        cb('connected', None)

            def on_disconnect(client, userdata, rc):
                self.connected = False
                self.node_status = {k: False for k in self.node_status}
                for cb in self.callbacks:
                    cb('disconnected', None)

            def on_message(client, userdata, msg):
                try:
                    topic = msg.topic
                    payload_str = msg.payload.decode()
                    data = json.loads(payload_str)

                    if topic.startswith("building/") and topic.endswith("/sensors"):
                        parts = topic.split('/')
                        if len(parts) >= 2:
                            apt_id = parts[1]
                            data['node_id'] = apt_id
                            self._handle_sensor(data)
                    elif topic.startswith("building/"):
                        parts = topic.split('/')
                        if len(parts) == 3:
                            apt_id = parts[1]
                            device_uuid = parts[2]
                            if device_uuid == "sensors":
                                return
                            if TRACK_ALL_DEVICES or device_uuid in TRACKED_DEVICES:
                                self._handle_tracking(device_uuid, apt_id, data)
                    elif topic.startswith("sensorData/nodes/"):
                        self._handle_sensor(data)
                    elif topic.startswith("ips/nodes/") or topic.startswith("ips/anchors/"):
                        parts = topic.split('/')
                        if len(parts) >= 4:
                            self._handle_ips(parts[2], parts[3], data)
                except Exception as e:
                    print(f"[MQTT] Error: {e}")

            self.client = mqtt.Client()
            self.client.on_connect = on_connect
            self.client.on_disconnect = on_disconnect
            self.client.on_message = on_message
            self.client.connect(self.broker, self.port)
            self.client.loop_start()
            return True

        except ImportError:
            print("[MQTT] paho-mqtt not installed. Install with: pip install paho-mqtt")
            return False
        except Exception as e:
            print(f"[MQTT] Connection error: {e}")
            return False

    def _handle_sensor(self, data: dict):
        node_id = data.get('node_id', '') or data.get('anchor', '') or data.get('apartment', '')
        mapped = NODE_MAP.get(node_id, node_id)

        if mapped in ['NW', 'NE', 'SW', 'SE']:
            fire = data.get('fire_state') or data.get('fire') or data.get('fire_detected') or False
            if isinstance(fire, str):
                fire = fire.lower() in ('true', '1', 'yes')

            gas = int(float(data.get('gas_level') or data.get('gas') or data.get('gas_ppm') or 0))
            temp = float(data.get('temperature') or data.get('temp') or data.get('temperature_c') or 25)
            sound = int(float(data.get('sound_level') or data.get('sound') or data.get('sound_db') or 0))

            self.building.update_sensor(mapped, fire=fire, gas=gas, temp=temp, sound=sound)

            if node_id in self.node_status:
                self.node_status[node_id] = True

            for cb in self.callbacks:
                cb('sensor', mapped)

    def _handle_ips(self, anchor: str, uuid: str, data: dict):
        if data.get('tracking', False):
            distance = data.get('distance')
            rssi = data.get('rssi', -70)
            if distance is not None:
                self.tracker.update(uuid, anchor, distance, rssi)

    def _handle_tracking(self, device_uuid: str, topic_anchor: str, data: dict):
        tracking = data.get('tracking', False)
        payload_anchor = data.get('anchor', '')

        anchor_map = {
            'apt1a': 'Apt1A', 'apt1b': 'Apt1B', 'apt2a': 'Apt2A', 'apt2b': 'Apt2B',
            'a': 'Apt1A', 'b': 'Apt1B', 'c': 'Apt2A', 'd': 'Apt2B',
            'nw': 'Apt1A', 'ne': 'Apt1B', 'sw': 'Apt2A', 'se': 'Apt2B',
        }

        anchor = anchor_map.get(topic_anchor.lower(), topic_anchor)
        if not anchor or anchor not in ['Apt1A', 'Apt1B', 'Apt2A', 'Apt2B']:
            anchor = anchor_map.get(payload_anchor.lower(), payload_anchor) if payload_anchor else topic_anchor

        if tracking:
            distance = data.get('distance')
            rssi = data.get('rssi', -70)

            if distance is not None and anchor:
                if anchor in self.anchor_data:
                    self.anchor_data[anchor] = {
                        'distance': distance,
                        'rssi': rssi,
                        'last_update': time.time(),
                        'device': device_uuid[:8]
                    }

                self.tracker.update(device_uuid, anchor, distance, rssi)

                if anchor in self.node_status:
                    self.node_status[anchor] = True

    def disconnect(self):
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
        self.connected = False


# =============================================================================
# JSON EXPORTER
# =============================================================================

class Exporter:
    @staticmethod
    def ensure_folders():
        if not os.path.exists(OUTPUT_FOLDER):
            os.makedirs(OUTPUT_FOLDER)

    @staticmethod
    def export_all(tracker: Tracker, building: Building):
        Exporter.ensure_folders()
        people = tracker.get_active()

        for person in people:
            zone = person.current_zone or building.find_nearest_node(person.position)
            zone_sensor = building.get_zone_sensor(zone)
            avg_distances = person.distance_history.get_all_averaged()

            person_data = {
                "device_id": person.uuid,
                "last_updated": datetime.now().isoformat(),
                "location": {
                    "position_x": round(person.position[0], 4),
                    "position_y": round(person.position[1], 4),
                    "zone": zone,
                    "zone_confidence": round(person.get_zone_confidence(), 3),
                    "zone_status": zone_sensor.get_status_text(),
                    "is_danger_zone": zone_sensor.is_dangerous()
                },
                "zone_probabilities": {
                    z: round(p, 3) for z, p in person.zone_probabilities.items()
                    if p >= ZONE_PROBABILITY_THRESHOLD
                },
                "movement": {
                    "velocity_x": round(person.movement_state.velocity[0], 4),
                    "velocity_y": round(person.movement_state.velocity[1], 4),
                    "speed": round(person.movement_state.get_speed(), 4),
                    "direction": person.movement_state.get_direction()
                },
                "anchor_data": {},
                "status": person.status.name,
                "priority": person.priority,
                "message": person.message,
                "evacuation": {
                    "is_evacuating": person.status == PersonStatus.EVACUATING,
                    "is_sheltering": person.status == PersonStatus.ESCAPED,
                    "assigned_exit": person.assigned_exit,
                    "path_nodes": person.path,
                    "current_step": person.path_index,
                    "total_steps": len(person.path),
                    "progress_percent": round((person.path_index / len(person.path)) * 100, 1) if person.path else 100,
                    "direction_summary": person.directions,
                    "turn_by_turn_instructions": person.turn_by_turn
                },
                "dynamic_guidance": {
                    "current_instruction": person.current_guidance,
                    "urgency_level": person.guidance_urgency,
                    "wrong_direction_count": person.wrong_direction_count,
                    "reroute_count": person.reroute_count,
                    "path_history": person.path_history
                }
            }

            # Add anchor data with averaging info
            anchor_mapping = {
                'NW': ['A', 'Apt1A'], 'NE': ['B', 'Apt1B'],
                'SW': ['C', 'Apt2A'], 'SE': ['D', 'Apt2B']
            }
            for zone_name, anchors in anchor_mapping.items():
                for anchor in anchors:
                    if anchor in avg_distances:
                        raw_dist = person.distances.get(anchor)
                        avg_dist = avg_distances.get(anchor)
                        avg_rssi = person.distance_history.get_averaged_rssi(anchor)
                        samples = person.distance_history.get_sample_count(anchor)
                        person_data["anchor_data"][zone_name] = {
                            "distance_m_raw": round(raw_dist, 3) if raw_dist else None,
                            "distance_m_avg": round(avg_dist, 3) if avg_dist else None,
                            "rssi_dBm_avg": round(avg_rssi, 1) if avg_rssi else None,
                            "sample_count": samples
                        }
                        break

            safe_uuid = person.uuid.replace('/', '_').replace('\\', '_')[:50]
            filepath = os.path.join(OUTPUT_FOLDER, f"{safe_uuid}.json")
            try:
                with open(filepath, 'w') as f:
                    json.dump(person_data, f, indent=2)
            except Exception as e:
                print(f"[JSON] Error: {e}")
            
            # -------------------------------------------------
            # WRITE TO path_information DATABASE (UPSERT)
            # -------------------------------------------------
            try:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()

                evac = person_data.get("evacuation", {})
                loc = person_data.get("location", {})

                c.execute("""
                    INSERT INTO path_information (
                        file_name,
                        position_x,
                        position_y,
                        is_evacuating,
                        is_sheltering,
                        assigned_exit,
                        path_nodes,
                        current_step,
                        total_steps,
                        progress_percent,
                        direction_summary,
                        turn_by_turn_instructions,
                        last_updated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(file_name)
                    DO UPDATE SET
                        position_x = excluded.position_x,
                        position_y = excluded.position_y,
                        is_evacuating = excluded.is_evacuating,
                        is_sheltering = excluded.is_sheltering,
                        assigned_exit = excluded.assigned_exit,
                        path_nodes = excluded.path_nodes,
                        current_step = excluded.current_step,
                        total_steps = excluded.total_steps,
                        progress_percent = excluded.progress_percent,
                        direction_summary = excluded.direction_summary,
                        turn_by_turn_instructions = excluded.turn_by_turn_instructions,
                        last_updated = excluded.last_updated
                """, (
                    f"{safe_uuid}.json",
                    loc.get("position_x"),
                    loc.get("position_y"),
                    int(evac.get("is_evacuating", False)),
                    int(evac.get("is_sheltering", False)),
                    evac.get("assigned_exit"),
                    json.dumps(evac.get("path_nodes", [])),
                    evac.get("current_step", 0),
                    evac.get("total_steps", 0),
                    evac.get("progress_percent", 0),
                    evac.get("direction_summary", ""),
                    json.dumps(evac.get("turn_by_turn_instructions", [])),
                    person_data.get("last_updated")
                ))

                conn.commit()
                conn.close()

            except Exception as e:
                print(f"[DB] Error updating path_information for {safe_uuid}: {e}")


# =============================================================================
# MAIN DISPLAY
# =============================================================================

class SafetyDisplay:
    def __init__(self, building: Building, tracker: Tracker, mqtt: MQTTInterface):
        self.building = building
        self.tracker = tracker
        self.mqtt = mqtt
        self.exit_counts = {}
        self.last_export = 0

        # Create figure with professional light theme
        plt.style.use('seaborn-v0_8-whitegrid')
        self.fig = plt.figure(figsize=(16, 9), facecolor=COLORS['bg_primary'])
        self.fig.canvas.manager.set_window_title('Building Safety Management System v4.0')

        # Main map area
        self.ax_map = self.fig.add_axes([0.02, 0.08, 0.6, 0.88])
        self.ax_map.set_facecolor(COLORS['bg_secondary'])

        # Status panel (larger - includes BLE data)
        self.ax_status = self.fig.add_axes([0.64, 0.35, 0.34, 0.61])
        self.ax_status.set_facecolor(COLORS['bg_card'])

        # Guidance panel (shorter)
        self.ax_guidance = self.fig.add_axes([0.64, 0.08, 0.34, 0.24])
        self.ax_guidance.set_facecolor(COLORS['bg_card'])

        self.mqtt.callbacks.append(self._on_mqtt_event)

    def _on_mqtt_event(self, event_type: str, data):
        if event_type == 'sensor':
            self._check_and_update_status()

    def draw_map(self):
        self.ax_map.clear()
        self.ax_map.set_xlim(-0.05, 1.05)
        self.ax_map.set_ylim(-0.05, 1.05)
        self.ax_map.set_aspect('equal')
        self.ax_map.axis('off')
        self.ax_map.set_facecolor(COLORS['bg_secondary'])

        # Title
        has_danger, reason = self.building.has_any_danger()
        people_count = self.tracker.count()
        evacuating = sum(1 for p in self.tracker.get_all() if p.status == PersonStatus.EVACUATING)

        if has_danger:
            title_color = COLORS['danger']
            status = f"EMERGENCY - {reason}"
        elif any(s.has_warning() for s in self.building.sensors.values()):
            title_color = COLORS['warning']
            status = "WARNING"
        else:
            title_color = COLORS['safe']
            status = "NORMAL"

        self.ax_map.text(0.5, 1.02, f"BUILDING STATUS: {status}", ha='center', va='bottom',
                        color=title_color, fontsize=14, fontweight='bold', transform=self.ax_map.transAxes)
        self.ax_map.text(0.5, 0.97, f"Tracking: {people_count} | Evacuating: {evacuating}",
                        ha='center', va='bottom', color=COLORS['text_secondary'], fontsize=10,
                        transform=self.ax_map.transAxes)

        # Draw zones
        zone_size = 0.28
        zones = [
            ('NW', 0.04, 0.68), ('N_Mid', 0.36, 0.68), ('NE', 0.68, 0.68),
            ('W_Mid', 0.04, 0.36), ('CENTER', 0.36, 0.36), ('E_Mid', 0.68, 0.36),
            ('SW', 0.04, 0.04), ('S_Mid', 0.36, 0.04), ('SE', 0.68, 0.04),
        ]

        zone_stats = self.tracker.get_zone_stats()

        for zone_id, x, y in zones:
            sensor = self.building.get_zone_sensor(zone_id)

            if sensor.is_dangerous():
                face_color = COLORS['zone_danger']
                edge_color = COLORS['zone_border_danger']
                edge_width = 4
            elif sensor.has_warning():
                face_color = COLORS['zone_warning']
                edge_color = COLORS['zone_border_warning']
                edge_width = 3
            else:
                face_color = COLORS['zone_safe']
                edge_color = COLORS['zone_border_safe']
                edge_width = 2

            rect = FancyBboxPatch((x, y), zone_size, zone_size,
                                   boxstyle="round,pad=0.01,rounding_size=0.02",
                                   facecolor=face_color, edgecolor=edge_color,
                                   linewidth=edge_width)
            self.ax_map.add_patch(rect)

            # Zone label
            self.ax_map.text(x + zone_size/2, y + zone_size - 0.03, zone_id,
                           ha='center', va='top', color=COLORS['text_primary'],
                           fontsize=11, fontweight='bold')

            # Status label
            status_text = sensor.get_status_text()
            self.ax_map.text(x + zone_size/2, y + 0.04, status_text,
                           ha='center', va='bottom', color=sensor.get_color(),
                           fontsize=9, fontweight='bold')

            # Occupancy count
            count = zone_stats.get(zone_id, 0)
            if count > 0:
                self.ax_map.scatter(x + zone_size - 0.03, y + zone_size - 0.03,
                                  s=200, c=COLORS['accent_blue'], marker='o', zorder=10,
                                  edgecolors='white', linewidths=2)
                self.ax_map.text(x + zone_size - 0.03, y + zone_size - 0.03, str(count),
                               ha='center', va='center', color='white',
                               fontsize=10, fontweight='bold', zorder=11)

        # Draw paths
        for u, v in self.building.EDGES:
            p1, p2 = self.building.NODES[u], self.building.NODES[v]
            u_sensor, v_sensor = self.building.get_zone_sensor(u), self.building.get_zone_sensor(v)

            if u_sensor.is_dangerous() or v_sensor.is_dangerous():
                color, alpha = COLORS['danger'], 0.3
            else:
                color, alpha = COLORS['safe'], 0.5

            self.ax_map.plot([p1[0], p2[0]], [p1[1], p2[1]], color=color, linewidth=3, alpha=alpha)

        # Draw exits
        exit_offsets = {'NE': (0, 0.08), 'SW': (-0.08, 0), 'SE': (0.08, 0), 'NW': (-0.08, 0)}
        exit_align = {'NE': ('center', 'bottom'), 'SW': ('right', 'center'), 'SE': ('left', 'center'), 'NW': ('right', 'center')}

        for node, name in self.building.EXITS.items():
            pos = self.building.NODES[node]
            self.ax_map.scatter(pos[0], pos[1], s=250, c=COLORS['safe'],
                              marker='^', edgecolors='white', linewidths=2, zorder=10)

            ox, oy = exit_offsets.get(node, (0, 0.08))
            ha, va = exit_align.get(node, ('center', 'bottom'))
            self.ax_map.text(pos[0] + ox, pos[1] + oy, name.replace('_', ' '),
                           ha=ha, va=va, color=COLORS['safe'], fontsize=9, fontweight='bold')

        # Draw anchor nodes with labels
        anchor_positions = {
            'Apt1A': (0.15, 0.85), 'Apt1B': (0.85, 0.85),
            'Apt2A': (0.15, 0.15), 'Apt2B': (0.85, 0.15),
        }
        anchor_offsets = {
            'Apt1A': (-0.06, 0.04), 'Apt1B': (0.06, 0.04),
            'Apt2A': (-0.06, -0.04), 'Apt2B': (0.06, -0.04),
        }
        anchor_align = {
            'Apt1A': ('right', 'bottom'), 'Apt1B': ('left', 'bottom'),
            'Apt2A': ('right', 'top'), 'Apt2B': ('left', 'top'),
        }

        now = time.time()
        for anchor_name, (ax, ay) in anchor_positions.items():
            # Check if anchor has recent data
            ble_data = self.mqtt.anchor_data.get(anchor_name, {})
            is_active = (now - ble_data.get('last_update', 0)) < 5

            # Anchor marker
            marker_color = COLORS['accent_teal'] if is_active else COLORS['text_muted']
            self.ax_map.scatter(ax, ay, s=80, c=marker_color, marker='s',
                              edgecolors='white', linewidths=1.5, zorder=8)

            # Anchor label with distance
            ox, oy = anchor_offsets[anchor_name]
            ha, va = anchor_align[anchor_name]

            distance = ble_data.get('distance')
            if distance is not None and is_active:
                label = f"{anchor_name}\n{distance:.1f}m"
                label_color = COLORS['accent_teal']
            else:
                label = anchor_name
                label_color = COLORS['text_muted']

            self.ax_map.text(ax + ox, ay + oy, label, ha=ha, va=va,
                           color=label_color, fontsize=8, fontweight='bold',
                           bbox=dict(boxstyle='round,pad=0.2', facecolor='white',
                                    edgecolor=label_color, alpha=0.9, linewidth=1))

        # Draw people
        for person in self.tracker.get_all():
            if person.status == PersonStatus.ESCAPED:
                continue

            x, y = person.position

            # Determine appearance
            if person.status == PersonStatus.EVACUATING:
                if person.guidance_urgency == "critical":
                    color, size, marker = COLORS['danger'], 180, '*'
                elif person.guidance_urgency == "warning" or person.priority:
                    color, size, marker = COLORS['evacuating'], 150, '*'
                else:
                    color, size, marker = COLORS['evacuating'], 120, 'o'
            elif person.status == PersonStatus.WARNING:
                color, size, marker = COLORS['warning'], 100, 'o'
            else:
                color, size, marker = COLORS['info'], 80, 'o'

            # Draw person
            self.ax_map.scatter(x, y, s=size, c=color, marker=marker,
                              edgecolors='white', linewidths=2, zorder=15)

            # Velocity arrow
            vx, vy = person.movement_state.velocity
            speed = person.movement_state.get_speed()
            if speed > 0.02:
                arrow_color = COLORS['danger'] if person.wrong_direction_count >= WRONG_DIRECTION_TOLERANCE else COLORS['accent_blue']
                self.ax_map.arrow(x, y, vx * 0.2, vy * 0.2, head_width=0.02,
                                head_length=0.01, fc=arrow_color, ec='white', linewidth=0.5, zorder=16)

            # Evacuation path
            if person.status == PersonStatus.EVACUATING and person.path:
                path_pts = [person.position] + [self.building.NODES[n] for n in person.path[person.path_index:]]
                if len(path_pts) > 1:
                    xs, ys = [p[0] for p in path_pts], [p[1] for p in path_pts]
                    path_color = COLORS['danger'] if person.guidance_urgency == "critical" else COLORS['evacuating']
                    self.ax_map.plot(xs, ys, '--', color=path_color, linewidth=2, alpha=0.7, zorder=5)

    def draw_status(self):
        self.ax_status.clear()
        self.ax_status.set_xlim(0, 1)
        self.ax_status.set_ylim(0, 1)
        self.ax_status.set_xticks([])
        self.ax_status.set_yticks([])
        self.ax_status.set_facecolor(COLORS['bg_card'])

        for spine in self.ax_status.spines.values():
            spine.set_color(COLORS['grid'])
            spine.set_linewidth(1)

        now = time.time()

        # Connection status
        if self.mqtt.connected:
            status_txt = "● CONNECTED"
            status_color = COLORS['safe']
        else:
            status_txt = "○ DISCONNECTED"
            status_color = COLORS['danger']

        self.ax_status.text(0.5, 0.96, status_txt, ha='center', color=status_color, fontsize=8, fontweight='bold')

        # ===== BLE ANCHOR DATA =====
        self.ax_status.text(0.5, 0.89, 'BLE DATA', ha='center',
                          color=COLORS['accent_blue'], fontsize=9, fontweight='bold')
        self.ax_status.axhline(y=0.86, color=COLORS['grid'], linewidth=0.5, xmin=0.05, xmax=0.95)

        # Column positions - compact layout within bounds
        c0 = 0.05   # Indicator
        c1 = 0.12   # Node name
        c2 = 0.40   # Distance
        c3 = 0.58   # RSSI
        c4 = 0.75   # Device (right-aligned)

        # Headers
        self.ax_status.text(c1, 0.82, 'Node', color=COLORS['text_muted'], fontsize=6)
        self.ax_status.text(c2, 0.82, 'Dist', color=COLORS['text_muted'], fontsize=6)
        self.ax_status.text(c3, 0.82, 'RSSI', color=COLORS['text_muted'], fontsize=6)
        self.ax_status.text(c4, 0.82, 'Dev', color=COLORS['text_muted'], fontsize=6)

        y = 0.75
        for apt_id in ['Apt1A', 'Apt1B', 'Apt2A', 'Apt2B']:
            ble_data = self.mqtt.anchor_data.get(apt_id, {})
            distance = ble_data.get('distance')
            rssi = ble_data.get('rssi')
            device = ble_data.get('device', '')
            last_update = ble_data.get('last_update', 0)
            is_fresh = (now - last_update) < 5

            ind_color = COLORS['safe'] if is_fresh else COLORS['text_muted']
            self.ax_status.text(c0, y, "●" if is_fresh else "○", color=ind_color, fontsize=7)
            self.ax_status.text(c1, y, apt_id, color=COLORS['text_primary'], fontsize=7, fontweight='bold')

            if distance is not None and is_fresh:
                self.ax_status.text(c2, y, f'{distance:.1f}m', color=COLORS['info'], fontsize=7)
                self.ax_status.text(c3, y, f'{rssi:.0f}', color=COLORS['text_secondary'], fontsize=7)
                dev_str = device[:5] if device else '--'
                self.ax_status.text(c4, y, dev_str, color=COLORS['text_muted'], fontsize=6)
            else:
                self.ax_status.text(c2, y, '--', color=COLORS['text_muted'], fontsize=7)
                self.ax_status.text(c3, y, '--', color=COLORS['text_muted'], fontsize=7)

            y -= 0.08

        # ===== SENSOR DATA =====
        self.ax_status.text(0.5, 0.42, 'SENSORS', ha='center',
                          color=COLORS['evacuating'], fontsize=9, fontweight='bold')
        self.ax_status.axhline(y=0.39, color=COLORS['grid'], linewidth=0.5, xmin=0.05, xmax=0.95)

        # Column positions for sensors - compact
        s0 = 0.05   # Indicator
        s1 = 0.12   # Node
        s2 = 0.35   # Fire
        s3 = 0.50   # Temp
        s4 = 0.67   # Gas
        s5 = 0.84   # Sound (right-aligned)

        # Headers
        self.ax_status.text(s1, 0.35, 'Zone', color=COLORS['text_muted'], fontsize=6)
        self.ax_status.text(s2, 0.35, 'Fire', color=COLORS['text_muted'], fontsize=6)
        self.ax_status.text(s3, 0.35, 'Temp', color=COLORS['text_muted'], fontsize=6)
        self.ax_status.text(s4, 0.35, 'Gas', color=COLORS['text_muted'], fontsize=6)
        self.ax_status.text(s5, 0.35, 'Snd', ha='left', color=COLORS['text_muted'], fontsize=6)

        y = 0.28
        for apt_id in ['Apt1A', 'Apt1B', 'Apt2A', 'Apt2B']:
            zone = NODE_MAP[apt_id]
            sensor = self.building.sensors.get(zone)
            is_online = self.mqtt.node_status.get(apt_id, False)

            ind_color = COLORS['safe'] if is_online else COLORS['text_muted']
            self.ax_status.text(s0, y, "●" if is_online else "○", color=ind_color, fontsize=7)
            self.ax_status.text(s1, y, apt_id, color=COLORS['text_primary'], fontsize=7, fontweight='bold')

            if sensor:
                fire_color = COLORS['danger'] if sensor.fire else COLORS['safe']
                self.ax_status.text(s2, y, 'Y' if sensor.fire else 'N', color=fire_color, fontsize=7,
                                   fontweight='bold' if sensor.fire else 'normal')

                temp_color = COLORS['danger'] if sensor.temp > TEMP_DANGER else (
                    COLORS['warning'] if sensor.temp > TEMP_WARNING else COLORS['text_secondary'])
                self.ax_status.text(s3, y, f'{sensor.temp:.0f}°', color=temp_color, fontsize=7)

                gas_color = COLORS['danger'] if sensor.gas > GAS_DANGER else (
                    COLORS['warning'] if sensor.gas > GAS_WARNING else COLORS['text_secondary'])
                self.ax_status.text(s4, y, f'{sensor.gas}', color=gas_color, fontsize=7)

                self.ax_status.text(s5, y, f'{sensor.sound}', color=COLORS['text_muted'], fontsize=6)
            else:
                self.ax_status.text(s2, y, '--', color=COLORS['text_muted'], fontsize=7)

            y -= 0.09

    def draw_guidance(self):
        self.ax_guidance.clear()
        self.ax_guidance.set_xlim(0, 1)
        self.ax_guidance.set_ylim(0, 1)
        self.ax_guidance.set_xticks([])
        self.ax_guidance.set_yticks([])
        self.ax_guidance.set_facecolor(COLORS['bg_card'])

        for spine in self.ax_guidance.spines.values():
            spine.set_color(COLORS['grid'])
            spine.set_linewidth(1)

        # Get evacuating people
        evacuating = [p for p in self.tracker.get_all() if p.status == PersonStatus.EVACUATING]
        evac_count = len(evacuating)

        title = f'GUIDANCE ({evac_count} evacuating)' if evac_count > 0 else 'GUIDANCE'
        title_color = COLORS['danger'] if evac_count > 0 else COLORS['text_primary']
        self.ax_guidance.text(0.5, 0.85, title, ha='center', color=title_color, fontsize=9, fontweight='bold')

        if not evacuating:
            self.ax_guidance.text(0.5, 0.4, 'All clear - No evacuations', ha='center', va='center',
                                color=COLORS['safe'], fontsize=9)
            return

        y = 0.62
        for person in evacuating[:2]:  # Show max 2 (compact)
            # Urgency indicator
            if person.guidance_urgency == "critical":
                ind, ind_color = "▲", COLORS['danger']
            elif person.guidance_urgency == "warning":
                ind, ind_color = "●", COLORS['warning']
            else:
                ind, ind_color = "●", COLORS['safe']

            self.ax_guidance.text(0.05, y, ind, color=ind_color, fontsize=10)
            self.ax_guidance.text(0.12, y, person.uuid[:6], color=COLORS['text_secondary'], fontsize=8)

            # Guidance (short)
            guidance = person.current_guidance or person.message or "Evacuating..."
            if len(guidance) > 35:
                guidance = guidance[:32] + "..."
            self.ax_guidance.text(0.30, y, guidance, color=ind_color, fontsize=8)

            # Progress
            if person.path:
                prog = int((person.path_index / len(person.path)) * 100)
                self.ax_guidance.text(0.95, y, f'{prog}%', ha='right', color=COLORS['text_muted'], fontsize=8)

            y -= 0.30

    def _check_and_update_status(self):
        """Automatic status updates based on sensor data."""
        has_danger, reason = self.building.has_any_danger()

        if not has_danger:                                                                                                                                                                                      
            # Only reset if people were evacuating                                                                                                                                                              
            any_evacuating = any(p.status == PersonStatus.EVACUATING for p in self.tracker.get_all())                                                                                                           
            if any_evacuating:                                                                                                                                                                                  
                for person in self.tracker.get_all():                                                                                                                                                           
                    if person.status != PersonStatus.ESCAPED:                                                                                                                                                   
                        person.status = PersonStatus.SAFE                                                                                                                                                       
                        person.message = "All clear"                                                                                                                                                            
                        person.path = []                                                                                                                                                                        
                        person.current_guidance = ""                                                                                                                                                            
                self.exit_counts = {}                                                                                                                                                                           
            return

        # Identify danger zones
        danger_zones = set()
        for node, sensor in self.building.sensors.items():
            if sensor.is_dangerous():
                danger_zones.add(node)
                adjacent = {'NW': ['N_Mid', 'W_Mid'], 'NE': ['N_Mid', 'E_Mid'],
                           'SW': ['S_Mid', 'W_Mid'], 'SE': ['S_Mid', 'E_Mid']}
                if node in adjacent:
                    danger_zones.update(adjacent[node])

        # Find safe exits
        safe_exits = [e for e in self.building.EXITS if e not in danger_zones]
        self.exit_counts = {e: 0 for e in self.building.EXITS}

        # Assign evacuation paths
        for person in self.tracker.get_all():
            if person.status == PersonStatus.ESCAPED:
                continue

            zone = person.current_zone or self.building.find_nearest_node(person.position)
            in_danger = zone in danger_zones

            if safe_exits:
                exit_node, path = self.building.find_best_exit(zone, self.exit_counts)

                if exit_node and path:
                    person.status = PersonStatus.EVACUATING
                    person.assigned_exit = self.building.EXITS[exit_node]
                    person.path = path
                    person.path_index = 0
                    person.directions, person.turn_by_turn = self.building.get_turn_by_turn(path, person.assigned_exit)
                    person.priority = in_danger

                    if in_danger:
                        person.message = f"DANGER! Evacuate via {person.assigned_exit}"
                        person.current_guidance = f"MOVE NOW toward {path[0] if path else 'exit'}"
                    else:
                        person.message = f"Evacuate via {person.assigned_exit}"
                        person.current_guidance = f"Proceed to {path[0] if path else 'exit'}"

                    self.exit_counts[exit_node] += 1

    def _update_dynamic_paths(self):
        """Update paths based on person movement."""
        now = time.time()

        for person in self.tracker.get_all():
            if person.status != PersonStatus.EVACUATING or not person.path:
                continue

            if now - person.last_path_update < PATH_REEVALUATION_INTERVAL:
                continue

            person.last_path_update = now

            if person.path_index >= len(person.path):
                continue

            target_node = person.path[person.path_index]
            target_pos = self.building.NODES.get(target_node)
            if not target_pos:
                continue

            dx = target_pos[0] - person.position[0]
            dy = target_pos[1] - person.position[1]
            current_distance = math.sqrt(dx*dx + dy*dy)

            # Check if reached waypoint
            if current_distance < 0.12:
                person.path_index += 1
                person.wrong_direction_count = 0

                if person.path_index < len(person.path):
                    next_node = person.path[person.path_index]
                    remaining = len(person.path) - person.path_index
                    person.current_guidance = f"Move toward {next_node} ({remaining} steps left)"
                    person.guidance_urgency = "normal"
                else:
                    person.current_guidance = f"You've reached {person.assigned_exit}!"
                continue

            # Check direction
            expected_dir = "EAST" if dx > 0 else "WEST" if abs(dx) > abs(dy) else "NORTH" if dy > 0 else "SOUTH"
            actual_dir = person.movement_state.get_direction()

            opposites = {"NORTH": "SOUTH", "SOUTH": "NORTH", "EAST": "WEST", "WEST": "EAST"}
            is_wrong = actual_dir and opposites.get(expected_dir) == actual_dir

            if is_wrong or current_distance > person.previous_distance_to_target + 0.02:
                person.wrong_direction_count += 1

                if person.wrong_direction_count >= FORCED_REROUTE_THRESHOLD:
                    self._reroute_person(person)
                elif person.wrong_direction_count >= WRONG_DIRECTION_TOLERANCE:
                    person.guidance_urgency = "warning"
                    person.current_guidance = f"WRONG WAY! Turn around, go {expected_dir}"
            else:
                person.wrong_direction_count = max(0, person.wrong_direction_count - 1)
                person.guidance_urgency = "normal"
                remaining = len(person.path) - person.path_index
                person.current_guidance = f"Continue {expected_dir} to {target_node} ({remaining} steps)"

            person.previous_distance_to_target = current_distance

    def _reroute_person(self, person):
        """Find alternative route."""
        danger_zones = {n for n, s in self.building.sensors.items() if s.is_dangerous()}
        current_zone = person.current_zone or self.building.find_nearest_node(person.position)

        best_exit, best_path, best_cost = None, None, float('inf')

        for exit_node, exit_name in self.building.EXITS.items():
            if exit_node in danger_zones:
                continue
            path, cost = self.building.find_path(current_zone, exit_node)
            if path and cost < best_cost:
                best_cost, best_exit, best_path = cost, exit_node, path

        if best_exit and best_path:
            person.reroute_count += 1
            person.assigned_exit = self.building.EXITS[best_exit]
            person.path = best_path
            person.path_index = 0
            person.wrong_direction_count = 0
            person.directions, person.turn_by_turn = self.building.get_turn_by_turn(best_path, person.assigned_exit)
            person.guidance_urgency = "critical"
            person.current_guidance = f"REROUTING to {person.assigned_exit}"
            person.message = f"New route: {person.assigned_exit}"

    def _update_movement(self):
        """Update path progress for people."""
        for person in self.tracker.get_all():
            if person.status == PersonStatus.ESCAPED:
                continue

            # Check if person is near any SAFE exit for 3 seconds
            pos = person.position
            near_safe_exit = False
            near_dangerous_exit = False
            exit_threshold = 0.18
            for exit_node in self.building.EXITS:
                exit_pos = self.building.NODES[exit_node]
                dist_to_exit = math.sqrt((pos[0] - exit_pos[0])**2 + (pos[1] - exit_pos[1])**2)
                if dist_to_exit < exit_threshold:
                    # Check if this exit zone has fire/danger
                    exit_sensor = self.building.get_zone_sensor(exit_node)
                    if exit_sensor.is_dangerous():
                        near_dangerous_exit = True
                    else:
                        near_safe_exit = True
                    break

            # If near a dangerous exit, reroute to another exit
            if near_dangerous_exit and person.status == PersonStatus.EVACUATING:
                person.near_exit_since = None
                self._reroute_person(person)
                person.message = "EXIT BLOCKED BY FIRE! Rerouting..."
                person.guidance_urgency = "critical"
                continue

            if near_safe_exit and person.status == PersonStatus.EVACUATING:
                if person.near_exit_since is None:
                    person.near_exit_since = time.time()
                elif time.time() - person.near_exit_since >= 3.0:
                    person.status = PersonStatus.ESCAPED
                    person.message = "Safe and evacuated"
                    person.path = []
                    person.near_exit_since = None
                    continue
            else:
                person.near_exit_since = None

            if person.status != PersonStatus.EVACUATING or not person.path:
                continue

            if person.path_index >= len(person.path):
                if person.assigned_exit.startswith("SHELTER"):
                    person.message = "AT SHELTER - Wait for rescue"
                else:
                    person.status = PersonStatus.ESCAPED
                    person.message = "Safe and evacuated"
                continue

            target = self.building.NODES[person.path[person.path_index]]
            dist = math.sqrt((target[0] - person.position[0])**2 + (target[1] - person.position[1])**2)

            # Larger threshold (0.2) to account for BLE tracking accuracy
            if dist < 0.2:
                person.path_index += 1

    def animate(self, frame):
        self._update_movement()
        self._update_dynamic_paths()
        self._check_and_update_status()

        now = time.time()
        if now - self.last_export > 0.5:
            Exporter.export_all(self.tracker, self.building)
            self.last_export = now

        self.draw_map()
        self.draw_status()
        self.draw_guidance()

        return []

    def run(self):
        print("=" * 60)
        print("  BUILDING SAFETY MANAGEMENT SYSTEM v4.0 - REALTIME")
        print("=" * 60)
        print(f"\n  Auto-connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}...")
        print(f"  Output folder: {OUTPUT_FOLDER}/")
        print("\n  Close the window to exit.")
        print("=" * 60)

        # Auto-connect to MQTT
        if self.mqtt.connect():
            print("[MQTT] Connection initiated...")
        else:
            print("[MQTT] Failed to connect. Will retry...")

        Exporter.ensure_folders()

        # Start animation
        self.animation = FuncAnimation(self.fig, self.animate, interval=100, blit=False, cache_frame_data=False)

        plt.show()

        # Cleanup
        self.mqtt.disconnect()
        print("\n[SYSTEM] Shutdown complete.")


# =============================================================================
# MAIN
# =============================================================================

def main():
    building = Building()
    tracker = Tracker()
    mqtt = MQTTInterface(building, tracker)

    display = SafetyDisplay(building, tracker, mqtt)
    display.run()


if __name__ == "__main__":
    main()