"""Movement model and route interpolator for realistic cold-chain asset tracking."""

import math
from typing import Dict, List, Tuple


class RouteModel:
    """Simulates realistic vehicle motion along a sequence of GPS waypoints."""

    # Pre-defined realistic logistics corridors across Indian regions
    PREDEFINED_ROUTES: Dict[str, List[Tuple[float, float]]] = {
        # Route 1: Maharashtra Corridor (Mumbai to Pune Distribution Highway)
        "mumbai_pune": [
            (19.0760, 72.8777),  # Mumbai Central Hub
            (19.0330, 73.0297),  # Navi Mumbai Industrial Gateway
            (18.9894, 73.1175),  # Panvel Pharma Transit
            (18.8950, 73.2350),  # Khalapur Interchange
            (18.7557, 73.4091),  # Lonavala Cold Storage
            (18.7180, 73.5350),  # Talegaon Logistics Park
            (18.6275, 73.7997),  # Pimpri-Chinchwad Biotech Park
            (18.5204, 73.8567),  # Pune Central Distribution Terminal
        ],
        # Route 1B: Thane / Navi Mumbai Cold Corridor (Thane West to Belapur via Airoli & Vashi)
        "thane_navi_mumbai": [
            (19.2183, 72.9781),  # Thane Majiwada Distribution Center (~20km North of Mumbai)
            (19.1860, 72.9756),  # Thane Wagle Industrial Estate
            (19.1550, 72.9960),  # Airoli Knowledge Park
            (19.1120, 73.0110),  # Mahape Millenium Business Park
            (19.0657, 73.0034),  # Vashi APMC Cold Storage
            (19.0330, 73.0297),  # Nerul Logistics Gateway
            (19.0180, 73.0390),  # Belapur Pharma Complex
        ],
        # Route 1C: Panvel / Pune Expressway Corridor (Panvel to Pune Express Nodes)
        "panvel_pune": [
            (18.9894, 73.1175),  # Panvel Cold Transit Hub (~27km East/SE of Mumbai)
            (18.9450, 73.1720),  # Shedung Expressway Plaza
            (18.8950, 73.2350),  # Khalapur Toll Plaza
            (18.7830, 73.3420),  # Khopoli Industrial Transit
            (18.7557, 73.4091),  # Lonavala Cold Storage
            (18.6740, 73.6980),  # Dehu Road Pharma Depot
            (18.5204, 73.8567),  # Pune Central Distribution Terminal
        ],
        # Route 2: Gujarat Pharma Corridor (Ahmedabad to Surat via Vadodara)
        "gujarat_corridor": [
            (23.0225, 72.5714),  # Ahmedabad Pharma Zone
            (22.6916, 72.8634),  # Nadiad Junction
            (22.5645, 72.9289),  # Anand Dairy & Cold Hub
            (22.3072, 73.1812),  # Vadodara Chemical/Bio Complex
            (21.7051, 72.9959),  # Bharuch Logistics Gate
            (21.6264, 73.0033),  # Ankleshwar Pharma Estate
            (21.1702, 72.8311),  # Surat Distribution Hub
        ],
        # Route 3: Madhya Pradesh Central Corridor (Indore to Bhopal)
        "mp_corridor": [
            (22.7196, 75.8577),  # Indore Pithampur SEZ
            (22.9676, 76.0534),  # Dewas Industrial Depot
            (22.9772, 76.3688),  # Sonkatch Transit
            (23.0195, 76.7214),  # Ashta Cold Node
            (23.2032, 77.0844),  # Sehore Junction
            (23.2599, 77.4126),  # Bhopal Central Medical Depot
        ],
        # Route 4: Rajasthan Cold-Chain Corridor (Jaipur to Ajmer)
        "rajasthan_corridor": [
            (26.9124, 75.7873),  # Jaipur Sitapura Pharma Area
            (26.8152, 75.5458),  # Bagru Industrial Area
            (26.6806, 75.2346),  # Dudu Logistics Checkpoint
            (26.5744, 74.8643),  # Kishangarh Hub
            (26.4499, 74.6399),  # Ajmer Cold Storage Terminal
            (26.1013, 74.3197),  # Beawar Distribution Depot
        ],
        # Backward compatibility aliases
        "coastal_north": [
            (23.0225, 72.5714),
            (22.6916, 72.8634),
            (22.3072, 73.1812),
            (21.7051, 72.9959),
            (21.1702, 72.8311),
        ],
        "inland_nashik": [
            (22.7196, 75.8577),
            (22.9676, 76.0534),
            (23.0195, 76.7214),
            (23.2599, 77.4126),
        ],
        "city_depot": [
            (26.9124, 75.7873),
            (26.8152, 75.5458),
            (26.6806, 75.2346),
            (26.4499, 74.6399),
        ],
    }

    def __init__(
        self,
        route_name: str,
        step_distance_deg: float = 0.0015,
        start_index: int = 0,
    ) -> None:
        self.route_name = route_name
        self.waypoints = self.PREDEFINED_ROUTES.get(
            route_name,
            self.PREDEFINED_ROUTES["city_depot"],
        )
        self.step_distance_deg = step_distance_deg
        self.current_waypoint_idx = min(start_index, len(self.waypoints) - 1)
        self.forward = True

        # Current vehicle position
        initial_pt = self.waypoints[self.current_waypoint_idx]
        self.current_lat = initial_pt[0]
        self.current_lon = initial_pt[1]

    def advance(self) -> Tuple[float, float]:
        """Move the simulated vehicle one incremental step towards the next waypoint."""
        if len(self.waypoints) < 2:
            return self.current_lat, self.current_lon

        # Determine target waypoint
        if self.forward:
            target_idx = self.current_waypoint_idx + 1
            if target_idx >= len(self.waypoints):
                self.forward = False
                target_idx = len(self.waypoints) - 2
        else:
            target_idx = self.current_waypoint_idx - 1
            if target_idx < 0:
                self.forward = True
                target_idx = 1

        target_lat, target_lon = self.waypoints[target_idx]

        # Calculate vector towards target
        d_lat = target_lat - self.current_lat
        d_lon = target_lon - self.current_lon
        distance = math.hypot(d_lat, d_lon)

        if distance <= self.step_distance_deg or distance == 0:
            # Reached waypoint
            self.current_lat = target_lat
            self.current_lon = target_lon
            self.current_waypoint_idx = target_idx
        else:
            # Advance along vector
            ratio = self.step_distance_deg / distance
            self.current_lat += d_lat * ratio
            self.current_lon += d_lon * ratio

        return round(self.current_lat, 5), round(self.current_lon, 5)

    def get_position(self) -> Tuple[float, float]:
        """Return the current [latitude, longitude]."""
        return round(self.current_lat, 5), round(self.current_lon, 5)
