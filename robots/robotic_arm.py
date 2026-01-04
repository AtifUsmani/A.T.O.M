import math
import json
import websocket
from core.config import cfg as config

L1 = 12.0
L2 = 12.0
last_pose = None

class WS_CONNECT:
    def __init__(self):
        self.ESP32_WS_URL = f"ws://{config['ROBOT-ARM']['IP_ADDRESS']}:81/"
        self.ws = None

        self.connect()

    def connect(self):
        print(f"Connecting to {self.ESP32_WS_URL} ...")

        self.ws = websocket.WebSocket()
        self.ws.connect(self.ESP32_WS_URL)

        print("✔ Connected to robot!")
    
    def send_command(self, data: dict):
        """
        Sends a JSON command to the ESP32.
        Data must be a Python dict that will be converted to JSON.
        """
        json_str = json.dumps(data)
        self.ws.send(json_str)
        print("→ Sent:", json_str)

    def set_joints(self, joint_dict: dict, speed=50, time_ms=None):
        """
        Example:
            set_joints({"shoulder": 120, "elbow": 140}, speed=40)
        """
        cmd = {
            "type": "set_joints",
            "preset": "custom",
            "joints": joint_dict,
            "speed": speed
        }

        if time_ms is not None:
            cmd["time_ms"] = time_ms

        self.send_command(cmd)

    def close_connection(self):
        self.ws.close()

class RoboticArm:
    def __init__(self):
        self.robot_control = WS_CONNECT()

    def IK(self, x, y, z):
        # Base rotation
        base = math.atan2(y, x)
        # Planar distance from base
        L = math.sqrt(x*x + y*y)
        r = math.sqrt(L*L + z*z)
        # Reach check
        if r > (L1 + L2) or r < abs(L1 - L2):
            raise ValueError("Target out of reach")
        # --- Elbow angle (law of cosines) ---
        cos_elbow = (r*r - L1*L1 - L2*L2) / (2 * L1 * L2)
        cos_elbow = max(-1.0, min(1.0, cos_elbow))
        elbow = math.acos(cos_elbow)          # radians
        # --- Shoulder angle ---
        phi = math.atan2(z, L)
        psi = math.acos((L1*L1 + r*r - L2*L2) / (2 * L1 * r))
        shoulder = phi + psi
        return {
            'base': math.degrees(base),
            'shoulder': math.degrees(shoulder),
            'elbow': math.degrees(elbow)
        }
    
    def apply_plane(self,cx, cy, cz, u, v, plane):
        """
        Maps (u, v) into (x, y, z) depending on plane
        """
        if plane == "XZ":
            return cx + u, cy, cz + v
        elif plane == "XY":
            return cx + u, cy + v, cz
        elif plane == "YZ":
            return cx, cy + u, cz + v
        else:
            raise ValueError("Invalid plane (use 'XY', 'XZ', or 'YZ')")

    def draw_circle(
        self,
        center=(6.0, 4.0, 12.0),   # (x, y, z)
        radius=6.0,
        plane="XZ",               # "XY", "XZ", "YZ"
        points=60,
        cycles=1,
        speed=60,
        delay=0.08
    ):
        import math
        import time

        cx, cy, cz = center

        print(f"⭕ Drawing circle at {center} in {plane} plane")

        # --- determine elbow configuration once ---
        try:
            if plane == "XZ":
                test = self.IK(cx + radius, cy, cz)
            elif plane == "XY":
                test = self.IK(cx + radius, cy, cz)
            elif plane == "YZ":
                test = self.IK(cx, cy + radius, cz)
            else:
                raise ValueError("Invalid plane")
        except ValueError:
            raise ValueError("Circle center/radius out of reach")

        elbow_sign = 1 if test['elbow'] >= 0 else -1

        for _ in range(cycles):
            for i in range(points + 1):
                theta = 2 * math.pi * i / points

                if plane == "XZ":
                    x = cx + radius * math.cos(theta)
                    y = cy
                    z = cz + radius * math.sin(theta)

                elif plane == "XY":
                    x = cx + radius * math.cos(theta)
                    y = cy + radius * math.sin(theta)
                    z = cz

                elif plane == "YZ":
                    x = cx
                    y = cy + radius * math.cos(theta)
                    z = cz + radius * math.sin(theta)

                try:
                    joints = self.IK(x, y, z)
                except ValueError:
                    continue   # skip unreachable point safely

                joints['elbow'] *= elbow_sign
                self.robot_control.set_joints(joints, speed=speed)
                time.sleep(delay)

            time.sleep(0.4)

        print("✅ Circle complete")

    def draw_line(
    self,
    start=(0.0, 0.0),
    end=(6.0, 0.0),
    center=(6.0, 4.0, 12.0),
    plane="XZ",
    points=40,
    speed=60,
    delay=0.08
):
        import numpy as np, time

        cx, cy, cz = center
        print(f"📏 Line | plane={plane}")

        us = np.linspace(start[0], end[0], points)
        vs = np.linspace(start[1], end[1], points)

        # elbow lock
        x0, y0, z0 = self.apply_plane(cx, cy, cz, us[0], vs[0], plane)
        first = self.IK(x0, y0, z0)
        elbow_sign = 1 if first['elbow'] >= 0 else -1

        for u, v in zip(us, vs):
            x, y, z = self.apply_plane(cx, cy, cz, u, v, plane)

            try:
                joints = self.IK(x, y, z)
            except ValueError:
                continue

            joints['elbow'] *= elbow_sign
            self.robot_control.set_joints(joints, speed=speed)
            time.sleep(delay)

        print("✅ Line complete")

    def draw_rectangle(
    self,
    center=(6.0, 4.0, 12.0),
    width=6.0,
    height=4.0,
    plane="XZ",
    points_per_edge=20,
    speed=60,
    delay=0.08
):
        cx, cy, cz = center
        w = width / 2
        h = height / 2

        print(f"▭ Rectangle | plane={plane}")

        corners_uv = [
            (-w, -h),
            ( w, -h),
            ( w,  h),
            (-w,  h),
            (-w, -h)
        ]

        for i in range(len(corners_uv) - 1):
            self.draw_line(
                start=corners_uv[i],
                end=corners_uv[i + 1],
                center=center,
                plane=plane,
                points=points_per_edge,
                speed=speed,
                delay=delay
            )

        print("✅ Rectangle complete")

    def move_to(self, x, y, z, speed=50):
        # Clamp the values
        x = max(0, min(20, x))
        y = max(0, min(20, y))
        z = max(0, min(24, z))
        
        joints = self.IK(x, y, z)
        self.robot_control.set_joints(joints, speed=speed)
        return 'Moved to ({:.2f}, {:.2f}, {:.2f})'.format(x, y, z)