import pygame
import pymunk
import pymunk.pygame_util
import math
import json
import os
from ui import UIButton, UITextbox, ScrollView, UIDropdown, UISlider

pygame.init()

# =====================================================================
# 1. GLOBAL CONSTANTS & CONFIGURATION
# =====================================================================
FIELD_INCHES = 144
FIELD_PIXELS = 900
SCALE = FIELD_PIXELS / FIELD_INCHES

UI_WIDTH = 340
WINDOW_WIDTH = FIELD_PIXELS + UI_WIDTH
WINDOW_HEIGHT = FIELD_PIXELS
# Initializing PyMunk (Physics collisions) 
space = pymunk.Space()
space.gravity = (0,0) #Gravity in (x,y) directions -bottom left is (0,0)- for top-down perspective

# Colors
RED, BLUE, GRAY, DARK, CYAN, WHITE = (255, 80, 80), (80, 80, 255), (200, 200, 200), (40, 40, 40), (0, 150, 255), (255, 255, 255)
LIGHT_GRAY, YELLOW, BLACK, GREEN, ORANGE = (160, 160, 160), (255, 220, 0), (0, 0, 0), (80, 200, 120), (255, 140, 0)
GRID_LIGHT, GRID_DARK = (220, 220, 220), (180, 180, 180)

FONT = pygame.font.SysFont("consolas", 18)
SMALL_FONT = pygame.font.SysFont("consolas", 14)

# File Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
FIELD_FILE = os.path.join(BASE_DIR, "custom_field.txt")
DRIVE_FILE = os.path.join(BASE_DIR, "custom_drive.txt")

# =====================================================================
# 2. STATE OBJECTS (Robot & Simulator Classes)
# =====================================================================
class Robot:
    def __init__(self):
        # Physical Specs
        self.length = 16.25   
        self.track_width = 14.5  
        self.max_size = 18.0
        self.wheel_radius = 1.625
        self.wheel_circ = 2 * math.pi * self.wheel_radius
        self.max_rps = 450 / 60
        self.base_max_speed = self.wheel_circ * self.max_rps
        self.gear_in = 60 #Amount of teeth (36t, 60t, etc.). Gear attached to motor
        self.gear_out = 60 #Gear attached to wheel
        #Typical weight, 12-16lbs, for high-performing team. Should be changed to match the actual bot weight
        self.total_mass = 14.0
        #Intake
        self.has_intake = True
        self.intake_width = 6.7 #Width of roller (in), should be smaller than self.track_width
        self.intake_length = 3.0 #How far intake extends (in), creating an intake range
        self.intake_offset = 0.0 #Inches inside the chassis (0.0 = all the way in front)
        self.inventory = []
        self.max_capacity = 4
        self.intake_state = "off" #off / in / out
        #Outtake
        self.has_outtake = True
        self.outtake_width = 6.7
        self.outtake_length = 3.0
        self.outtake_offset = 0.0
        self.outtake_state = "off" #off / out
        #Delay from intake to score
        self.delay_flag = True
        self.timer_delay = 1
        # Real-World Screen Position (True State)
        self.x = FIELD_INCHES / 2
        self.y = FIELD_INCHES / 2
        self.angle = 0.0
        self.current_speed = 0.0

        #Moment of inertia for solid rectangle box 
        moment = pymunk.moment_for_box(self.total_mass, (self.length * SCALE, self.track_width * SCALE))
        
        #Body used for physics calculations (Includes: mass, inertia, position, angle, velocity, torque, etc)
        self.body = pymunk.Body(self.total_mass, moment, body_type=pymunk.Body.DYNAMIC) #Dynamic means it moves/ can be interacted with
        #Starting cords so that PyMunk can match the body (back-end) to the shape (front-end) 
        self.body.position = (self.x * SCALE, self.y * SCALE)
        self.body.angle = math.radians(self.angle)

        self.shape = pymunk.Poly.create_box(self.body, (self.length * SCALE, self.track_width * SCALE))
        self.shape.friction = 0.3 #Can be changed

        space.add(self.body, self.shape)
        
        # Odometry Origin Anchor
        self.odom_origin_x = self.x
        self.odom_origin_y = self.y
        self.start_pose = (self.x, self.y, self.angle)

    def reset_to_start(self):
        self.x, self.y, self.angle = self.start_pose
        self.odom_origin_x, self.odom_origin_y = self.x, self.y
        #Teleport body to starting cords
        self.body.position = (self.x * SCALE, self.y * SCALE)
        self.body.angle = math.radians(self.angle)
        self.body.velocity = (0, 0)
        self.body.angular_velocity = 0

    def reset_to_center(self):
        self.x, self.y, self.angle = FIELD_INCHES / 2, FIELD_INCHES / 2, 0.0
        self.odom_origin_x, self.odom_origin_y = self.x, self.y
        #Teleport body to center cords
        self.body.position = (self.x * SCALE, self.y * SCALE)
        self.body.angle = math.radians(self.angle)
        self.body.velocity = (0, 0)
        self.body.angular_velocity = 0

    def get_odom_pose(self):
        return self.x - self.odom_origin_x, self.y - self.odom_origin_y

    
    def calculate_max_speed(self, cartridge_color):
        rpm_map = {"red": 100.0, "green": 200.0, "blue": 600.0}
        base_rpm = rpm_map.get(cartridge_color, 200.0) #default to 200 if cant find key in dict
        gear_ratio = self.gear_in / float(self.gear_out) if self.gear_out > 0 else 1.0
        self.output_rpm = base_rpm * gear_ratio
        max_rps = self.output_rpm / 60.0
        self.base_max_speed = self.wheel_circ * max_rps

class SimulatorState:
    def __init__(self):
        self.current_mode = "drive" # drive / edit / studio
        self.current_page = "edit 1" #studio 1 / studio 2 / edit 1 / edit 2
        self.paused = False
        self.paused_sub_menu = "main" # main / settings
        self.remapping_key = None 
        self.auton_mode = False
        self.auton_running = False
        self.resizing_shape = False
        self.dragging_speed_slider = False
        self.dragging_turn_slider = False
        self.settings = {
            "input_mode": "keyboard",   
            "speed_scale": 1.0,
            "turn_scale": 1.0,
            "intake_rev_velocity": 30.0, #Reverse intake ejection speed
            "outtake_velocity": 15.0, 
            "field_source": "image",    
            "drive_mode": "tank",     
            "motor_cartridge": "green", #(red, green, blue)
            "intake_control_mode": "toggle",#Hold or toggle
            "outtake_control_mode": "toggle", #Hold or toggle
            "keybinds": {
                "intake_in": pygame.K_e,
                "intake_out": pygame.K_f,
                "outtake_score": pygame.K_q
            }
        }
        self.drive_config = {
            "forward_axis": 1, "turn_axis": 0, "left_axis": 1, "right_axis": 3,
            "invert_forward": -1, "invert_turn": 1, "invert_left": -1, "invert_right": -1
        }
        self.shapes = []
        
        # Editor Selection tracking
        self.selected_shape_idx = None
        self.dragging_shape = False
        self.drag_offset_x = 0
        self.drag_offset_y = 0
        self.dragging_robot = False
        self.robot_drag_offset_x = 0.0
        self.robot_drag_offset_y = 0.0
        self.active_textbox = None  
        self.textbox_value = ""
        self.add_shape_dropdown_open = False
        self.add_shape_type = "rect"  


# Instantiate our unified states
bot = Robot()
sim = SimulatorState()

# =====================================================================
# 3. DATA PERSISTENCE (IO Systems)
# =====================================================================
def load_all_data():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                loaded_data = json.load(f)
                if "keybinds" in loaded_data:
                    sim.settings["keybinds"].update(loaded_data["keybinds"])
                    del loaded_data["keybinds"]
                sim.settings.update(loaded_data)
                bot.gear_in = sim.settings.get("gear_in", bot.gear_in)
                bot.gear_out = sim.settings.get("gear_out", bot.gear_out)
                bot.total_mass = sim.settings.get("total_mass", bot.total_mass)
                bot.wheel_radius = sim.settings.get("wheel_radius", bot.wheel_radius)
                bot.has_intake = sim.settings.get("has_intake", bot.has_intake)
                bot.intake_length = sim.settings.get("intake_length", bot.intake_length)
                bot.intake_width = sim.settings.get("intake_width", bot.intake_width)
                bot.wheel_circ = 2 * math.pi * bot.wheel_radius
                bot.intake_offset = sim.settings.get("intake_offset", bot.intake_offset)
                bot.max_capacity = sim.settings.get("max_capacity", 4)
                bot.has_outtake = sim.settings.get("has_outtake", bot.has_outtake)
                bot.outtake_length = sim.settings.get("outtake_length", bot.outtake_length)
                bot.outtake_width = sim.settings.get("outtake_width", bot.outtake_width)
                bot.outtake_offset = sim.settings.get("outtake_offset", bot.outtake_offset)
                bot.timer_delay = sim.settings.get("timer_delay", bot.timer_delay)
                bot.delay_flag = sim.settings.get("delay_flag", bot.delay_flag)

        except: pass
    if os.path.exists(DRIVE_FILE):
        try:
            with open(DRIVE_FILE, "r") as f:
                sim.drive_config.update(json.load(f))
        except: pass
        
    if os.path.exists(FIELD_FILE):
        with open(FIELD_FILE, "r") as f:
            for line in f:
                parts = line.strip().split()
                if not parts: continue
                tag = parts[0]
                
                if tag == "RECT" and len(parts) >= 9:
                    b_type = parts[9] if len(parts) >= 10 else "static"
                    m_val = float(parts[10]) if len(parts) >= 11 else 1.0
                    fric_val = float(parts[11]) if len(parts) >= 12 else 0.5
                    elas_val = float(parts[12]) if len(parts) >= 13 else 0.0
                    is_over = bool(int(parts[13])) if len(parts) >= 14 else False
                    _, x, y, w, h, ang, r, g, b = parts[:9]
                    sim.shapes.append({"type": "rect", "x": float(x), "y": float(y), 
                                       "w": float(w), "h": float(h), 
                                       "angle": float(ang), 
                                       "color": (int(r), int(g), int(b)),
                                       "body_type": b_type, "mass": m_val,
                                       "friction": fric_val, "elasticity": elas_val,
                                       "is_overpass": is_over})
                elif tag == "CIRC" and len(parts) >= 7:
                    b_type = parts[7] if len(parts) >= 8 else "dynamic"
                    m_val = float(parts[8]) if len(parts) >= 9 else 1.0
                    fric_val = float(parts[9]) if len(parts) >= 10 else 0.5
                    elas_val = float(parts[10]) if len(parts) >= 11 else 0.0
                    is_over = bool(int(parts[11])) if len(parts) >= 12 else False
                    _, x, y, radius, r, g, b = parts[:7]
                    sim.shapes.append({"type": "circ", "x": float(x), "y": float(y), 
                                       "radius": float(radius), 
                                       "color": (int(r), int(g), int(b)),
                                       "body_type": b_type, "mass": m_val,
                                       "friction": fric_val, "elasticity": elas_val,
                                       "is_overpass": is_over})
                elif tag == "ROBOT_START" and len(parts) == 4:
                    _, x, y, ang = parts
                    bot.start_pose = (float(x), float(y), float(ang))
                    bot.x, bot.y, bot.angle = bot.start_pose

def save_field_data():
    with open(FIELD_FILE, "w") as f:
        for s in sim.shapes:
            b_type = s.get("body_type", "static")
            mass_val = s.get("mass", 1.0)
            fric_val = s.get("friction", 0.5)
            elas_val = s.get("elasticity", 0.0)
            is_over = 1 if s.get("is_overpass", False) else 0
            if s["type"] == "rect":
                f.write(f"RECT {s['x']} {s['y']} {s['w']} {s['h']} {s['angle']} {s['color'][0]} {s['color'][1]} {s['color'][2]} {b_type} {mass_val} {fric_val} {elas_val} {is_over}\n")
            elif s["type"] == "circ":
                f.write(f"CIRC {s['x']} {s['y']} {s['radius']} {s['color'][0]} {s['color'][1]} {s['color'][2]} {b_type} {mass_val} {fric_val} {elas_val} {is_over}\n")
        f.write(f"ROBOT_START {bot.start_pose[0]} {bot.start_pose[1]} {bot.start_pose[2]}\n")

def save_settings():
    try:
        sim.settings["gear_in"] = bot.gear_in
        sim.settings["gear_out"] = bot.gear_out
        sim.settings["total_mass"] = bot.total_mass
        sim.settings["wheel_radius"] = bot.wheel_radius
        sim.settings["has_intake"] = bot.has_intake
        sim.settings["intake_width"] = bot.intake_width
        sim.settings["intake_length"] = bot.intake_length
        sim.settings["intake_offset"] = bot.intake_offset
        sim.settings["max_capacity"] = bot.max_capacity
        sim.settings["has_outtake"] = bot.has_outtake
        sim.settings["outtake_width"] = bot.outtake_width
        sim.settings["outtake_length"] = bot.outtake_length
        sim.settings["outtake_offset"] = bot.outtake_offset
        sim.settings["delay_flag"] = bot.delay_flag
        sim.settings["timer_delay"] = bot.timer_delay
        with open(SETTINGS_FILE, "w") as f: json.dump(sim.settings, f)
    except Exception as e: 
        print(f"Error saving settings: {e}")
# Initial data payload configuration setup
load_all_data()
bot.calculate_max_speed(sim.settings.get("motor_cartridge", "green"))

# =====================================================================
# 4. PHYSICS & MOVEMENT ENGINE
# =====================================================================
def get_inputs(dt):
    max_speed = bot.base_max_speed * sim.settings["speed_scale"]
    left_speed, right_speed = 0.0, 0.0

    if sim.settings["input_mode"] == "keyboard":
        keys = pygame.key.get_pressed()
        forward, turn, left, right = 0.0, 0.0, 0.0, 0.0

        if sim.settings["drive_mode"] in ("arcade","custom"):
            if keys[pygame.K_w]: forward += 1.0
            if keys[pygame.K_s]: forward -= 1.0
            if keys[pygame.K_d]: turn -= 1.0
            if keys[pygame.K_a]: turn += 1.0
        if sim.settings["drive_mode"] == "tank":
            if keys[pygame.K_i]: left += 1.0
            if keys[pygame.K_k]: left -= 1.0
            if keys[pygame.K_j]: right -= 1.0
            if keys[pygame.K_l]: right += 1.0

        if sim.settings["drive_mode"] == "tank":
            left_speed = max(-1.0, min(1.0, left)) * max_speed
            right_speed = max(-1.0, min(1.0, right)) * max_speed
        else:
            forward = max(-1.0, min(1.0, forward))
            turn = max(-1.0, min(1.0, turn))
            left_cmd = forward + turn
            right_cmd = forward - turn
            max_cmd = max(1.0, abs(left_cmd), abs(right_cmd))
            left_speed = (left_cmd / max_cmd) * max_speed
            right_speed = (right_cmd / max_cmd) * max_speed
            
        in_key = sim.settings["keybinds"]["intake_in"]
        out_key = sim.settings["keybinds"]["intake_out"]
        score_key = sim.settings["keybinds"]["outtake_score"]
        
        if sim.settings["intake_control_mode"] == "hold":
            if keys[in_key]:
                bot.intake_state = "in"
            elif keys[out_key]:
                bot.intake_state = "out"
            elif keys[score_key]:
                bot.outtake_state = "out"
            else:
                bot.intake_state = "off"
        
    return left_speed, right_speed

#Run 60 times a second, do all the collisions, calculations, and visual updates
def update_physics(left_speed, right_speed, dt):
    bot.current_speed = (left_speed + right_speed) / 2.0 #Linear Velocity or average forward speed
    turn_multiplier = 40.0 * sim.settings.get("turn_scale", 1.0)
    omega = ((left_speed - right_speed) / bot.track_width)*turn_multiplier  #Difference 
    
    rad = bot.body.angle #Radians for PyMunk
    bot.body.velocity = (bot.current_speed * math.cos(rad) * SCALE, bot.current_speed * math.sin(rad) * SCALE) #Linear
    bot.body.angular_velocity = math.radians(omega) #If positive, spin counter-clockwise, else negative, spin clockwise

    for s in sim.shapes:
        if s.get("body_type") == "dynamic" and "body" in s and not s.get("stored",False):
            b = s["body"]
            
            # Read shape friction (0.0 - ice, 1.0 = rubber)
            fric = s.get("friction", 0.5)
            
            # Calculate floor resistance multiplier based on dt
            # High friction drops velocity faster, heavier mass resists stopping
            drag = max(0.0, 1.0 - (fric * 3.0 * dt)) #3.0 is a damping constant, change number to change the overal field to be more or less slippery
            
            # Apply floor resistance to both movement and spinning. 
            # If drag = 0.9, the object retains 90% of the initial velocity
            b.velocity = b.velocity * drag
            b.angular_velocity = b.angular_velocity * drag
    
    if bot.has_intake and bot.intake_state == "in" and len(bot.inventory) < bot.max_capacity:
        #Calculate intake zone box in world coordinates (inches)
        rad = math.radians(bot.angle)
        stick_out = max(0.0, bot.intake_length - bot.intake_offset)
        #Front center of chassis plus offset to intake center
        intake_center_dist = (bot.length / 2) + (stick_out / 2)
        intake_cx = bot.x + intake_center_dist * math.cos(rad)
        intake_cy = bot.y + intake_center_dist * math.sin(rad)

        #Check collision with dynamic shapes
        for s in list(sim.shapes):
            if s.get("body_type") == "dynamic" and "body" in s and not s.get("stored",False):
                dx = abs(s["x"] - intake_cx)
                dy = abs(s["y"] - intake_cy)
                
                reach = (bot.intake_length / 2) + 2.0
                if dx < reach and dy < reach:
                    #Collect item means remove from PyMunk space (temporarily)
                    space.remove(s["body"])
                    for shape_ref in list(space.shapes):
                        if shape_ref.body == s["body"]:
                            space.remove(shape_ref)      
                            s["pymunk_shape"] = shape_ref
                    #Store in inventory 
                    s["stored"] = True
                    s["travel_timer"] = bot.timer_delay if bot.delay_flag else 0.0
                    bot.inventory.append(s)
                    break
    
    elif bot.has_intake and bot.intake_state == "out" and len(bot.inventory) > 0:
        rad = math.radians(bot.angle)
        stick_out = max(0.0, bot.intake_length - bot.intake_offset)
        spawn_dist = (bot.length / 2) + (stick_out / 2) + 3 #Can be changed!
        spawn_x = bot.x + spawn_dist * math.cos(rad)
        spawn_y = bot.y + spawn_dist * math.sin(rad)

        s = bot.inventory.pop()

        s["stored"] = False
        s["x"] = spawn_x
        s["y"] = spawn_y
        
        #Re-position physics body
        b = s["body"]
        eject_speed = sim.settings.get("intake_rev_velocity") * SCALE
        
        b.position = (spawn_x * SCALE, spawn_y * SCALE)
        b.velocity = (bot.body.velocity.x + eject_speed * math.cos(rad),
                      bot.body.velocity.y + eject_speed * math.sin(rad))
        
        #Re-add body & shape to space
        space.add(b)
        if "pymunk_shape" in s:
            space.add(s["pymunk_shape"])
                
        if sim.settings.get("intake_control_mode") == "toggle":
            bot.intake_state = "off"

    elif bot.has_outtake and bot.outtake_state == "out" and len(bot.inventory) > 0:
        cur_item = bot.inventory[0]
        if cur_item.get("travel_timer", 0.0) <= 0.0:
            rad = math.radians(bot.angle)
            
            stick_out_out = max(0.0, bot.outtake_length - bot.outtake_offset)
            spawn_dist = (bot.length / 2) + (stick_out_out / 2) + 3.0
            
            spawn_x = bot.x - spawn_dist * math.cos(rad) #Opposite side
            spawn_y = bot.y - spawn_dist * math.sin(rad)

            s = bot.inventory.pop(0)

            s["stored"] = False
            s["x"] = spawn_x
            s["y"] = spawn_y
            
            # Re-position physics body
            b = s["body"]
            eject_speed = sim.settings.get("outtake_velocity", 15.0) * SCALE
            
            b.position = (spawn_x * SCALE, spawn_y * SCALE)
            # Apply ejection speed in the backward/opposite direction
            b.velocity = (bot.body.velocity.x - eject_speed * math.cos(rad),
                        bot.body.velocity.y - eject_speed * math.sin(rad))
            
            # Re-add body to PyMunk space
            space.add(b)
            if "pymunk_shape" in s:
                space.add(s["pymunk_shape"])
                
            # Reset state if in toggle mode
            if sim.settings.get("outtake_control_mode", "toggle") == "toggle":
                bot.outtake_state = "off"
        
    #Divide the calculated movement into small chunks to prevent clipping into walls at high speed
    for _ in range(10):
        space.step(dt/10.0)
    #Translate backend position back to normal inches for frontend code
    bot.x = bot.body.position.x / SCALE
    bot.y = bot.body.position.y / SCALE
    bot.angle = math.degrees(bot.body.angle)

    for item in bot.inventory:
        if item.get("travel_timer", 0.0) > 0.0:
            item["travel_timer"] = max(0.0, item["travel_timer"] - dt)

    #Making every shape that has "dynamic" and a backend "body" to follow/teleport to its invisible body location
    #Do this every tick so create visually smooth movement for user
    for s in sim.shapes:
        if s.get("body_type") == "dynamic" and "body" in s:
            b = s["body"]
            #Overriding the shape's location with the body's location
            if s["type"] == "rect":
                s["x"] = (b.position.x / SCALE) - (s["w"] / 2)
                s["y"] = (b.position.y / SCALE) - (s["h"] / 2)
                s["angle"] = math.degrees(b.angle)
            elif s["type"] == "circ":
                s["x"] = b.position.x / SCALE
                s["y"] = b.position.y / SCALE  
                s["angle"] = math.degrees(b.angle)
    
def create_field_boundaries():
    #Example: Segment(body type, starting point, end point, thickness)
    left_wall = pymunk.Segment(space.static_body, (0,0), (0,FIELD_PIXELS), 5)
    right_wall = pymunk.Segment(space.static_body, (FIELD_PIXELS,0), (FIELD_PIXELS,FIELD_PIXELS), 5)
    #For PyMunk, the origin (0,0) is bottom left rather than top left like Pygame - Remember it!
    top_wall = pymunk.Segment(space.static_body, (0,FIELD_PIXELS), (FIELD_PIXELS,FIELD_PIXELS), 5)
    bottom_wall = pymunk.Segment(space.static_body, (0,0), (FIELD_PIXELS, 0), 5)

    for wall in [left_wall, right_wall, top_wall, bottom_wall]:
        wall.friction = 0.5 #Ability to change to whatever, depending on the user's needs
        wall.elasticity = 1.0
        space.add(wall)

#The initial "setup" function reads UI shapes and user inputs (Static or Dynamic) and creates corresponding PyMunk bodies with mass, friction, etc.
def sync_custom_obstacles_to_physics():
    #Not allowing for stack-ups
    for body in list(space.bodies):
        if body != bot.body and body != space.static_body:
            space.remove(body)

    for shape in list(space.shapes):
        if shape != bot.shape:
            # Keep field boundary segments safe
            if isinstance(shape, pymunk.Segment): continue
            space.remove(shape)

    #Looping through UI shapes and spawning them to the PyMunk backend
    for s in sim.shapes:
        b_type = s.get("body_type", "static")
        fric_val = s.get("friction", 0.5)
        elas_val = s.get("elasticity", 0.0)
        if b_type == "static":
            # Static: Can't be moved
            if s["type"] == "rect":
                body = space.static_body
                # Calculate center and dimensions (pixel scale)
                cx = (s["x"] + s["w"]/2) * SCALE
                cy = (s["y"] + s["h"]/2) * SCALE
                box_shape = pymunk.Poly.create_box(body, (s["w"] * SCALE, s["h"] * SCALE))
                box_shape.unsafe_set_vertices([
                    pymunk.Vec2d(v.x + cx, v.y + cy) for v in box_shape.get_vertices()
                ])
                box_shape.friction = fric_val
                box_shape.elasticity = elas_val
                space.add(box_shape)

            elif s["type"] == "circ":
                body = space.static_body
                cx = s["x"] * SCALE
                cy = s["y"] * SCALE
                circ_shape = pymunk.Circle(body, s["radius"] * SCALE, (cx, cy))
                circ_shape.friction = fric_val
                circ_shape.elasticity = elas_val
                space.add(circ_shape)
            
        elif b_type == "dynamic":
            # Dynamic: Movable objects on the field
            #Read mass from shape dictionary, default to 1.0 if none
            mass = s.get("mass", 1.0) # Weight in arbitrary physics units
            
            if s["type"] == "rect":
                w_px, h_px = s["w"] * SCALE, s["h"] * SCALE
                moment = pymunk.moment_for_box(mass, (w_px, h_px)) #Calculate moment of inertia (rotational resistance) based on shape)
                body = pymunk.Body(mass, moment, body_type=pymunk.Body.DYNAMIC) #Creating a body with the given attributes
                body.position = ((s["x"] + s["w"]/2) * SCALE, (s["y"] + s["h"]/2) * SCALE) 
                body.angle = math.radians(s.get("angle", 0.0))
                
                shape = pymunk.Poly.create_box(body, (w_px, h_px))
                shape.friction = fric_val
                shape.elasticity = elas_val
                space.add(body, shape)
                s["body"] = body #Stores a reference to the backend body (aka this specific shape has this body)

            elif s["type"] == "circ":
                rad_px = s["radius"] * SCALE
                moment = pymunk.moment_for_circle(mass, 0, rad_px)
                body = pymunk.Body(mass, moment, body_type=pymunk.Body.DYNAMIC)
                body.position = (s["x"] * SCALE, s["y"] * SCALE)
                
                shape = pymunk.Circle(body, rad_px)
                shape.friction = fric_val
                shape.elasticity = elas_val
                space.add(body, shape)
                s["body"] = body #Stores a reference to the backend body (aka this specific shape has this body)
# =====================================================================
# 5. GRAPHICS & UI DRAWING SYSTEM
# =====================================================================
screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
pygame.display.set_caption("VEX Simulator - Clean Architecture")
clock = pygame.time.Clock()

# Load Field Graphics safely
try:
    raw_field = pygame.image.load("field.png").convert()
    field_img = pygame.transform.rotate(raw_field, -90)
    field_img = pygame.transform.scale(field_img, (FIELD_PIXELS, FIELD_PIXELS))
except:
    field_img = pygame.Surface((FIELD_PIXELS, FIELD_PIXELS))
    field_img.fill(DARK)

# UI Elements Definitions
mode_drive_button_rect = pygame.Rect(FIELD_PIXELS + 20, 20, 120, 30)
mode_edit_button_rect = pygame.Rect(FIELD_PIXELS + 160, 20, 120, 30)
mode_page_switch_button_rect = pygame.Rect(FIELD_PIXELS+280, 810, 50, 35)

# Property inputs panel definitions
shape_panel_y = 255

COLOR_PALETTE = [(150,150,150), (255,80,80), (80,80,255), (255,220,0), (80,200,120)]
color_button_rects = [pygame.Rect(FIELD_PIXELS + 20 + i*36, shape_panel_y + 180, 30, 30) for i in range(len(COLOR_PALETTE))]

#Pause Menu Modal (pop-up) definitions
MODAL_W, MODAL_H = 280, 260 #Width and Height of modal
modal_x = (WINDOW_WIDTH - MODAL_W) // 2 #Top-left of the modal
modal_y = (WINDOW_HEIGHT - MODAL_H) // 2

pause_modal_rect = pygame.Rect(modal_x, modal_y, MODAL_W, MODAL_H)

#Settings & Keybinds Modal definitions
SETTING_W, SETTING_H = 420, 360
setting_x = (WINDOW_WIDTH - SETTING_W) // 2 
setting_y = (WINDOW_HEIGHT - SETTING_H) // 2


#Scrollview - ui.py
settings_scrollview = ScrollView(setting_x, setting_y, SETTING_W, SETTING_H)
def bind_in(): sim.remapping_key = "intake_in"
def bind_out(): sim.remapping_key = "intake_out"
def bind_score(): sim.remapping_key = "outtake_score"
def toggle_mode(): 
    sim.settings["intake_control_mode"] = "hold" if sim.settings["intake_control_mode"] == "toggle" else "toggle"
    save_settings()
def close_settings(): 
    sim.remapping_key = None
    sim.paused_sub_menu = "main"

btn_in = UIButton(60, 40, 300, 40, "Intake In", action_callback=bind_in)
btn_out = UIButton(60, 100, 300, 40, "Intake Out", action_callback=bind_out)
btn_score = UIButton(60, 160, 300, 40, "Outtake Score", action_callback=bind_score)
btn_mode = UIButton(60, 220, 300, 40, "Intake Mode", action_callback=toggle_mode)
btn_back = UIButton(60, 400, 300, 40, "Back to Pause Menu", action_callback=close_settings)

settings_scrollview.add_child(btn_in)
settings_scrollview.add_child(btn_out)
settings_scrollview.add_child(btn_score)
settings_scrollview.add_child(btn_mode)
settings_scrollview.add_child(btn_back)

# Slider and Dropdown - ui.py
def update_speed(new_val):
    sim.settings["speed_scale"] = new_val
    save_settings()
def update_turn(new_val):
    sim.settings["turn_scale"] = new_val
    save_settings()
def update_add_shape(new_val):
    sim.add_shape_type = "rect" if new_val == "Rectangle" else "circ"

speed_slider = UISlider(FIELD_PIXELS + 20, 170, 200, 6, "Robot's speed multiplier:", 0.3, 1.5, sim.settings.get("speed_scale", 1.0), update_speed)
turn_slider = UISlider(FIELD_PIXELS + 20, 210, 200, 6, "Robot's turn multiplier:", 0.3, 1.5, sim.settings.get("turn_scale", 1.0), update_turn)
shape_dropdown = UIDropdown(FIELD_PIXELS + 20, 175, 140, 24, ["Rectangle", "Circle"], 0, update_add_shape)

#Pause menu - ui.py
def action_resume(): sim.paused = False
def action_settings(): sim.paused_sub_menu = "settings"
def action_exit(): pygame.quit(); raise SystemExit
def action_studio():
    if sim.current_mode == "studio":
        sim.current_mode = "drive"
        sim.selected_shape_idx = None
        sim.active_textbox = None
        bot.calculate_max_speed(sim.settings.get("motor_cartridge", "green"))
        sync_custom_obstacles_to_physics()
    else:
        sim.current_mode = "studio"
        sim.current_page = "studio 1"
    sim.paused = False

btn_pause_resume = UIButton(modal_x + 30, modal_y + 60, 220, 36, "Resume Game", action_callback=action_resume)
btn_pause_resume.default_color = GREEN
btn_pause_studio = UIButton(modal_x + 30, modal_y + 105, 220, 36, "Robot Design Studio", action_callback=action_studio)
btn_pause_settings = UIButton(modal_x + 30, modal_y + 150, 220, 36, "Settings & Keybinds", action_callback=action_settings)
btn_pause_exit = UIButton(modal_x + 30, modal_y + 195, 220, 36, "Exit Simulator", action_callback=action_exit)
btn_pause_exit.default_color = RED

# Rendering list to loop through in draw_everything()
pause_ui = [btn_pause_resume, btn_pause_studio, btn_pause_settings, btn_pause_exit]

#Drive mode sidebar - ui.py
def set_drive_tank(): sim.settings["drive_mode"] = "tank"; save_settings()
def set_drive_arcade(): sim.settings["drive_mode"] = "arcade"; save_settings()
def set_drive_custom(): sim.settings["drive_mode"] = "custom"; save_settings()
def set_input_keyboard(): sim.settings["input_mode"] = "keyboard"; save_settings()
def set_input_controller(): sim.settings["input_mode"] = "controller"; save_settings()
def action_reset(): bot.reset_to_start()
def action_reset_center(): bot.reset_to_center()
def action_run_auton(): 
    if not sim.auton_running: sim.auton_mode = True

btn_drive_tank = UIButton(FIELD_PIXELS + 20, 70, 90, 26, "Tank", action_callback=set_drive_tank)
btn_drive_arcade = UIButton(FIELD_PIXELS + 120, 70, 90, 26, "Arcade", action_callback=set_drive_arcade)
btn_drive_custom = UIButton(FIELD_PIXELS + 220, 70, 90, 26, "Custom", action_callback=set_drive_custom)

btn_input_key = UIButton(FIELD_PIXELS + 20, 110, 100, 26, "Keyboard", action_callback=set_input_keyboard)
btn_input_ctrl = UIButton(FIELD_PIXELS + 140, 110, 100, 26, "Controller", action_callback=set_input_controller)

btn_reset = UIButton(FIELD_PIXELS + 20, 240, 130, 28, "Reset Robot", action_callback=action_reset)
btn_reset_center = UIButton(FIELD_PIXELS + 180, 240, 130, 28, "Reset Center", action_callback=action_reset_center)
btn_auton = UIButton(FIELD_PIXELS + 20, 280, 290, 28, "Run Autonomous", action_callback=action_run_auton)

btn_reset.default_color = (180, 60, 60) # Red
btn_reset_center.default_color = (80, 80, 180) # Blue
btn_auton.default_color = GREEN

drive_ui = [btn_drive_tank, btn_drive_arcade, btn_drive_custom, btn_input_key, btn_input_ctrl, btn_reset, btn_reset_center, btn_auton]

#Edit 1 - ui.py
def set_field_image(): sim.settings["field_source"] = "image"; save_settings()
def set_field_custom(): sim.settings["field_source"] = "custom"; save_settings()
def action_add_shape():
    cx, cy = FIELD_INCHES / 2, FIELD_INCHES / 2
    if sim.add_shape_type == "rect":
        sim.shapes.append({"type": "rect", "x": cx - 6, "y": cy - 6, "w": 12, "h": 12, "angle": 0.0, "color": (150,150,150), "body_type": "static"})
    else:
        sim.shapes.append({"type": "circ", "x": cx, "y": cy, "radius": 6, "color": (150,150,150), "body_type": "dynamic"})
    sim.selected_shape_idx = len(sim.shapes) - 1
    save_field_data()
def action_delete_shape():
    if sim.selected_shape_idx is not None:
        removed_s = sim.shapes.pop(sim.selected_shape_idx)
        if "body" in removed_s and removed_s["body"] in space.bodies: space.remove(removed_s["body"])
        if "pymunk_shape" in removed_s and removed_s["pymunk_shape"] in space.shapes: space.remove(removed_s["pymunk_shape"])
        sim.selected_shape_idx = None
        save_field_data()
        sync_custom_obstacles_to_physics()
def toggle_physics_mode():
    if sim.selected_shape_idx is not None:
        s = sim.shapes[sim.selected_shape_idx]
        curr = s.get("body_type", "static")
        # Cycle through: static -> passthrough -> dynamic -> static
        s["body_type"] = "passthrough" if curr == "static" else "dynamic" if curr == "passthrough" else "static"
        save_field_data()
def toggle_layer_height():
    if sim.selected_shape_idx is not None:
        s = sim.shapes[sim.selected_shape_idx]
        if s.get("body_type") == "passthrough":
            s["is_overpass"] = not s.get("is_overpass", False)
            save_field_data()

btn_field_img = UIButton(FIELD_PIXELS + 20, 85, 120, 26, "Image", action_callback=set_field_image)
btn_field_cust = UIButton(FIELD_PIXELS + 160, 85, 120, 26, "Custom", action_callback=set_field_custom)
btn_add_shape = UIButton(FIELD_PIXELS + 20, 145, 140, 26, "Add Shape", action_callback=action_add_shape)
btn_del_shape = UIButton(FIELD_PIXELS + 180, 145, 120, 26, "Delete Shape", action_callback=action_delete_shape)
btn_del_shape.default_color = (180, 60, 60) # Red

shape_panel_y = 245
btn_phys_toggle = UIButton(FIELD_PIXELS + 20, shape_panel_y + 95, 180, 22, "STATIC (WALL)", action_callback=toggle_physics_mode)
btn_layer_toggle = UIButton(FIELD_PIXELS + 220, shape_panel_y + 95, 110, 22, "LOW (GROUND)", action_callback=toggle_layer_height)

edit_buttons_ui = [btn_field_img, btn_field_cust, btn_add_shape, btn_del_shape]
edit_inspector_ui = [btn_phys_toggle, btn_layer_toggle]

#Studio 1 - ui.py
def update_rlen(val):
    try: bot.length = max(6.0, min(bot.max_size, float(val)))
    except: pass
def update_rwid(val):
    try: bot.track_width = max(6.0, min(bot.max_size, float(val)))
    except: pass
def update_cartridge(val):
    # Extracts "red", "green", or "blue" from the dropdown string
    color = val.split(" ")[0].lower() 
    sim.settings["motor_cartridge"] = color
    bot.calculate_max_speed(color)
    save_settings()
def update_wrad(val): #Wheel radius
    try: 
        bot.wheel_radius = max(1.0, min(3.0, float(val)))
        bot.wheel_circ = 2 * math.pi * bot.wheel_radius
        bot.calculate_max_speed(sim.settings.get("motor_cartridge", "green"))
        studio_wrad_box.value = f"{bot.wheel_radius:.3f}" # Update the text box visually
    except: pass
def set_preset_275(): update_wrad("1.375")
def set_preset_325(): update_wrad("1.625")
def set_preset_400(): update_wrad("2.000")
def update_gin(val):
    try: bot.gear_in = int(max(1, float(val))); bot.calculate_max_speed(sim.settings.get("motor_cartridge", "green")); save_settings()
    except: pass
def update_gout(val):
    try: bot.gear_out = int(max(1, float(val))); bot.calculate_max_speed(sim.settings.get("motor_cartridge", "green")); save_settings()
    except: pass
def update_mass(val):
    try: bot.total_mass = max(1.0, float(val)); save_settings()
    except: pass

studio_len_box = UITextbox(FIELD_PIXELS + 20, 115, 100, 24, "Length (in)", str(bot.length), update_rlen)
studio_wid_box = UITextbox(FIELD_PIXELS + 140, 115, 100, 24, "Width (in)", str(bot.track_width), update_rwid)

# Stats based on current settings
cart_idx = {"red": 0, "green": 1, "blue": 2}.get(sim.settings.get("motor_cartridge", "green"), 1)
cartridge_dropdown = UIDropdown(FIELD_PIXELS + 20, 330, 180, 24, ["Red (100 RPM)", "Green (200 RPM)", "Blue (600 RPM)"], cart_idx, update_cartridge)

studio_wrad_box = UITextbox(FIELD_PIXELS + 20, 160, 100, 24, "Wheel's radius (in)", str(bot.wheel_radius), update_wrad)
btn_w275 = UIButton(FIELD_PIXELS + 130, 160, 55, 24, "2.75\"", action_callback=set_preset_275)
btn_w325 = UIButton(FIELD_PIXELS + 190, 160, 55, 24, "3.25\"", action_callback=set_preset_325)
btn_w400 = UIButton(FIELD_PIXELS + 250, 160, 55, 24, "4.00\"", action_callback=set_preset_400)

studio_gin_box = UITextbox(FIELD_PIXELS + 20, 225, 70, 24, "In (teeth)", str(bot.gear_in), update_gin)
studio_gout_box = UITextbox(FIELD_PIXELS + 110, 225, 70, 24, "Out (teeth)", str(bot.gear_out), update_gout)
studio_mass_box = UITextbox(FIELD_PIXELS + 20, 275, 100, 24, "Robot's mass (lbs)", str(bot.total_mass), update_mass)

studio_1_ui = [studio_len_box, studio_wid_box, cartridge_dropdown, studio_wrad_box, btn_w275, btn_w325, btn_w400, studio_gin_box, studio_gout_box, studio_mass_box]

def upd_sx(val): 
    try: sim.shapes[sim.selected_shape_idx]["x"] = float(val); save_field_data(); sync_custom_obstacles_to_physics()
    except: pass
def upd_sy(val): 
    try: sim.shapes[sim.selected_shape_idx]["y"] = float(val); save_field_data(); sync_custom_obstacles_to_physics()
    except: pass
def upd_sw(val): 
    try: sim.shapes[sim.selected_shape_idx]["w"] = max(1.0, float(val)); save_field_data(); sync_custom_obstacles_to_physics()
    except: pass
def upd_sh(val): 
    try: sim.shapes[sim.selected_shape_idx]["h"] = max(1.0, float(val)); save_field_data(); sync_custom_obstacles_to_physics()
    except: pass
def upd_sa(val): 
    try: sim.shapes[sim.selected_shape_idx]["angle"] = float(val); save_field_data(); sync_custom_obstacles_to_physics()
    except: pass
def upd_sr(val): 
    try: sim.shapes[sim.selected_shape_idx]["radius"] = max(1.0, float(val)); save_field_data(); sync_custom_obstacles_to_physics()
    except: pass
def upd_sm(val): 
    try: sim.shapes[sim.selected_shape_idx]["mass"] = max(0.1, float(val)); save_field_data(); sync_custom_obstacles_to_physics()
    except: pass
def upd_sf(val): 
    try: sim.shapes[sim.selected_shape_idx]["friction"] = max(0.0, min(1.0, float(val))); save_field_data(); sync_custom_obstacles_to_physics()
    except: pass
def upd_se(val): 
    try: sim.shapes[sim.selected_shape_idx]["elasticity"] = max(0.0, min(1.0, float(val))); save_field_data(); sync_custom_obstacles_to_physics()
    except: pass

box_sx = UITextbox(FIELD_PIXELS + 20, shape_panel_y + 15, 80, 22, "X", "", upd_sx)
box_sy = UITextbox(FIELD_PIXELS + 120, shape_panel_y + 15, 80, 22, "Y", "", upd_sy)
box_sw = UITextbox(FIELD_PIXELS + 20, shape_panel_y + 55, 80, 22, "W", "", upd_sw)
box_sh = UITextbox(FIELD_PIXELS + 120, shape_panel_y + 55, 80, 22, "H", "", upd_sh)
box_sr = UITextbox(FIELD_PIXELS + 220, shape_panel_y + 15, 80, 22, "Radius", "", upd_sr)
box_sa = UITextbox(FIELD_PIXELS + 220, shape_panel_y + 15, 80, 22, "Angle", "", upd_sa)
box_sm = UITextbox(FIELD_PIXELS + 220, shape_panel_y + 140, 80, 22, "Mass (lbs)", "", upd_sm)
box_sf = UITextbox(FIELD_PIXELS + 120, shape_panel_y + 140, 80, 22, "Friction", "", upd_sf)
box_se = UITextbox(FIELD_PIXELS + 20, shape_panel_y + 140, 80, 22, "Bounce", "", upd_se)

def upd_rx(val): 
    try: bot.start_pose = (float(val), bot.start_pose[1], bot.start_pose[2]); save_field_data(); bot.reset_to_start()
    except: pass
def upd_ry(val): 
    try: bot.start_pose = (bot.start_pose[0], float(val), bot.start_pose[2]); save_field_data(); bot.reset_to_start()
    except: pass
def upd_ra(val): 
    try: bot.start_pose = (bot.start_pose[0], bot.start_pose[1], float(val)); save_field_data(); bot.reset_to_start()
    except: pass

robot_start_y = shape_panel_y + 250
box_rx = UITextbox(FIELD_PIXELS + 20, robot_start_y + 20, 80, 22, "Start X", "", upd_rx)
box_ry = UITextbox(FIELD_PIXELS + 120, robot_start_y + 20, 80, 22, "Start Y", "", upd_ry)
box_ra = UITextbox(FIELD_PIXELS + 220, robot_start_y + 20, 80, 22, "Start θ", "", upd_ra)
box_rlen = UITextbox(FIELD_PIXELS + 120, robot_start_y + 60, 80, 22, "Chassis L", "", update_rlen) # Reuses studio callback!
box_rwid = UITextbox(FIELD_PIXELS + 20, robot_start_y + 60, 80, 22, "Chassis W", "", update_rwid) # Reuses studio callback!
btn_rsave = UIButton(FIELD_PIXELS + 20, robot_start_y + 95, 130, 26, "Save Start", action_callback=lambda: save_field_data())
btn_rsave.default_color = GREEN

# Rendering list to loop through in draw_everything()
edit_shape_txt = [box_sx, box_sy, box_sw, box_sh, box_sr, box_sa, box_sm, box_sf, box_se]
edit_robot_ui = [box_rx, box_ry, box_ra, box_rlen, box_rwid, btn_rsave]

#Studio 2 - ui.py
def toggle_outtake(): bot.has_outtake = not bot.has_outtake; save_settings()
def shift_out_in(): bot.outtake_offset = min(bot.outtake_length, bot.outtake_offset + 0.1); save_settings()
def shift_out_out(): bot.outtake_offset = max(0.0, bot.outtake_offset - 0.1); save_settings()

def toggle_intake(): bot.has_intake = not bot.has_intake; save_settings()
def shift_in_in(): bot.intake_offset = min(bot.intake_length, bot.intake_offset + 0.1); save_settings()
def shift_in_out(): bot.intake_offset = max(0.0, bot.intake_offset - 0.1); save_settings()
def toggle_delay(): bot.delay_flag = not bot.delay_flag; save_settings()

def update_owid(val):
    try: bot.outtake_width = max(5.0, min(bot.track_width, float(val))); save_settings()
    except: pass
def update_olen(val):
    try: bot.outtake_length = max(1.0, min(8.0, float(val))); save_settings()
    except: pass
def update_ospd(val):
    try: sim.settings["outtake_velocity"] = max(0.0, min(100.0, float(val))); save_settings()
    except: pass
def update_iwid(val):
    try: bot.intake_width = max(5.0, min(bot.track_width, float(val))); save_settings()
    except: pass
def update_ilen(val):
    try: bot.intake_length = max(1.0, min(8.0, float(val))); save_settings()
    except: pass
def update_ispd(val):
    try: sim.settings["intake_rev_velocity"] = max(0.0, min(100.0, float(val))); save_settings()
    except: pass
def update_icap(val):
    try: 
        cap = int(max(0, min(10, float(val))))
        sim.settings["max_capacity"] = cap; bot.max_capacity = cap; save_settings()
    except: pass
def update_tdelay(val):
    try: bot.timer_delay = max(0.0, min(10.0, float(val))); save_settings()
    except: pass

# Outtake
btn_out_toggle = UIButton(FIELD_PIXELS + 20, 125, 110, 24, "Toggle", action_callback=toggle_outtake)
box_owid = UITextbox(FIELD_PIXELS + 145, 125, 80, 24, "Width (in)", str(bot.outtake_width), update_owid)
box_olen = UITextbox(FIELD_PIXELS + 235, 125, 80, 24, "Depth (in)", str(bot.outtake_length), update_olen)
box_ospd = UITextbox(FIELD_PIXELS + 20, 173, 100, 24, "Eject Speed", str(sim.settings.get("outtake_velocity", 30.0)), update_ospd)
btn_out_shift_in = UIButton(FIELD_PIXELS + 20, 225, 35, 24, "<", action_callback=shift_out_in)
btn_out_shift_out = UIButton(FIELD_PIXELS + 60, 225, 35, 24, ">", action_callback=shift_out_out)

# Intake
btn_in_toggle = UIButton(FIELD_PIXELS + 20, 285, 110, 24, "Toggle", action_callback=toggle_intake)
box_iwid = UITextbox(FIELD_PIXELS + 140, 285, 80, 24, "Width (in)", str(bot.intake_width), update_iwid)
box_ilen = UITextbox(FIELD_PIXELS + 230, 285, 80, 24, "Depth (in)", str(bot.intake_length), update_ilen)
box_ispd = UITextbox(FIELD_PIXELS + 20, 333, 100, 24, "Eject Speed", str(sim.settings.get("intake_rev_velocity", 30.0)), update_ispd)
box_icap = UITextbox(FIELD_PIXELS + 20, 435, 60, 30, "Capacity", str(sim.settings.get("max_capacity", 3)), update_icap)
btn_in_shift_in = UIButton(FIELD_PIXELS + 20, 385, 35, 24, "<", action_callback=shift_in_in)
btn_in_shift_out = UIButton(FIELD_PIXELS + 60, 385, 35, 24, ">", action_callback=shift_in_out)

# Delay
btn_delay_toggle = UIButton(FIELD_PIXELS + 20, 495, 110, 24, "Toggle", action_callback=toggle_delay)
box_tdelay = UITextbox(FIELD_PIXELS + 145, 495, 80, 24, "Delay (s)", str(bot.timer_delay), update_tdelay)

# Rendering list to loop through in draw_everything()
studio_2_outtake_ui = [btn_out_toggle, box_owid, box_olen, box_ospd, btn_out_shift_in, btn_out_shift_out]
studio_2_intake_ui = [btn_in_toggle, box_iwid, box_ilen, box_ispd, box_icap, btn_in_shift_in, btn_in_shift_out]
studio_2_delay_ui = [btn_delay_toggle, box_tdelay]

#Old functions
def draw_text(text, x, y, color=WHITE, font=FONT):
    screen.blit(font.render(text, True, color), (x, y))

def draw_small(text, x, y, color=WHITE):
    screen.blit(SMALL_FONT.render(text, True, color), (x, y))

def draw_textbox(rect, label, value, is_active):
    pygame.draw.rect(screen, WHITE if is_active else LIGHT_GRAY, rect, border_radius=4)
    pygame.draw.rect(screen, BLACK, rect, 1, border_radius=4)
    draw_small(label, rect.x, rect.y - 16, LIGHT_GRAY)
    screen.blit(SMALL_FONT.render(str(value), True, BLACK), (rect.x + 4, rect.y + 3))

def draw_everything():
    mx, my = pygame.mouse.get_pos()
    m_fx = mx / SCALE if (0 <= mx < FIELD_PIXELS and 0 <= my < FIELD_PIXELS) else -1
    m_fy = (FIELD_PIXELS - my) / SCALE if (0 <= mx < FIELD_PIXELS and 0 <= my < FIELD_PIXELS) else -1

    #Background layer for Studio mode
    if sim.current_mode == "studio":
        # Render new "Studio" canvas
        screen.fill((245, 245, 250), (0, 0, FIELD_PIXELS, FIELD_PIXELS))
        # Draw blueprint grid lines
        for x in range(0, FIELD_PIXELS, 40):
            pygame.draw.line(screen, (225, 225, 235), (x, 0), (x, FIELD_PIXELS), 1)
        for y in range(0, FIELD_PIXELS, 40):
            pygame.draw.line(screen, (225, 225, 235), (0, y), (FIELD_PIXELS, y), 1)
            
        # Studio Mode Header
        pygame.draw.rect(screen, (30, 30, 40), (10, 10, 395, 30), border_radius=4)
        draw_small("WORKSHOP: ROBOT DESIGN STUDIO", 18, 18, ORANGE)
   
    # Background layer
    if sim.settings["field_source"] == "image":
        screen.blit(field_img, (0, 0))
    else:
        screen.fill((230, 230, 230), (0, 0, FIELD_PIXELS, FIELD_PIXELS))
        for i in range(7):
            pygame.draw.line(screen, GRID_DARK, (int(i * 24 * SCALE), 0), (int(i * 24 * SCALE), FIELD_PIXELS), 1)
            pygame.draw.line(screen, GRID_DARK, (0, FIELD_PIXELS - int(i * 24 * SCALE)), (FIELD_PIXELS, FIELD_PIXELS - int(i * 24 * SCALE)), 1)
    
    pygame.draw.rect(screen, (50, 50, 60), (0, 0, FIELD_PIXELS, FIELD_PIXELS), 5) #Drawing a border around the field (5px)
    
    # Elements Layer
    if sim.settings["field_source"] == "custom" and sim.current_mode != "studio":

        #Render individual shapes - Due to rendering priority so that Passthrough is rendered before everything to go under everthing
        def render_shape(i,s):
            if s.get("stored", False):
                return
            
            if s["type"] == "rect":
                surf = pygame.Surface((s["w"] * SCALE, s["h"] * SCALE), pygame.SRCALPHA)
            
                current_phys = s.get("body_type", "static") #Defualting to static, can be changed
                
                surf.fill(s["color"])
                rot = pygame.transform.rotate(surf, s["angle"])
                rect = rot.get_rect(center=((s["x"] + s["w"]/2) * SCALE, FIELD_PIXELS - (s["y"] + s["h"]/2) * SCALE))
                screen.blit(rot, rect)
                if i == sim.selected_shape_idx: 
                    pygame.draw.rect(screen, YELLOW, rect, 2)

                if i == sim.selected_shape_idx:
                    red_px_x = int(s["x"] * SCALE)
                    red_px_y = int(FIELD_PIXELS - (s["y"] * SCALE))
                    #Dot represent XY cord
                    pygame.draw.circle(screen, RED, (red_px_x, red_px_y), 5)
                    pygame.draw.circle(screen, BLACK, (red_px_x, red_px_y), 5, 1)
                    #Resizing dot
                    white_px_x = int((s["x"] + s["w"]) * SCALE)
                    white_px_y = int(FIELD_PIXELS - ((s["y"] + s["h"]) * SCALE))
                    pygame.draw.circle(screen, WHITE, (white_px_x, white_px_y), 5)
                    pygame.draw.circle(screen, BLACK, (white_px_x, white_px_y), 5, 1)

            elif s["type"] == "circ":
                cx, cy = int(s["x"] * SCALE), int(FIELD_PIXELS - s["y"] * SCALE)
                radius_pixels = int(s["radius"] * SCALE)

                pygame.draw.circle(screen, s["color"], (cx, cy), radius_pixels)

                angle_rad = math.radians(s.get("angle", 0.0))
                line_end_x = cx + radius_pixels * math.cos(angle_rad)
                line_end_y = cy - radius_pixels * math.sin(angle_rad) #Subtract because Pygame +y is down
                
                pygame.draw.line(screen, WHITE, (cx, cy), (line_end_x, line_end_y), 2)
                
                if i == sim.selected_shape_idx: 
                    pygame.draw.circle(screen, YELLOW, (cx, cy), radius_pixels + 2, 2)

                    red_px_x = int(s["x"] * SCALE)
                    red_px_y = int(FIELD_PIXELS - (s["y"] * SCALE))
                    #Dot representing XY cord
                    pygame.draw.circle(screen, RED, (red_px_x, red_px_y), 5)
                    pygame.draw.circle(screen, BLACK, (red_px_x, red_px_y), 5, 1)
                    #Resizing dot
                    white_px_x = int((s["x"] + s["radius"]) * SCALE)
                    white_px_y = red_px_y
                    pygame.draw.circle(screen, WHITE, (white_px_x, white_px_y), 5)
                    pygame.draw.circle(screen, BLACK, (white_px_x, white_px_y), 5, 1)

        #Loop through the first time and draw Passthrough object
        for i, s in enumerate(sim.shapes):
            if s.get("body_type") == "passthrough":
                render_shape(i, s)

        #Loop through the second time and draw the rest
        for i, s in enumerate(sim.shapes):
            if s.get("body_type", "static") in ("static", "dynamic"):
                render_shape(i, s)

    # Robot Layer
    if sim.current_mode != "studio":
        stick_out_in = max(0.0, bot.intake_length - bot.intake_offset) if bot.has_intake else 0.0
        stick_out_out = max(0.0, bot.outtake_length - bot.outtake_offset) if bot.has_outtake else 0.0

        total_w_px = (bot.length + stick_out_in + stick_out_out) * SCALE
        max_subsystem_w = max(bot.track_width, bot.intake_width if bot.has_intake else 0.0, bot.outtake_width if bot.has_outtake else 0.0)
        total_h_px = max_subsystem_w * SCALE
        
        robot_surf = pygame.Surface((total_w_px, total_h_px), pygame.SRCALPHA)
        
        chassis_x = stick_out_out * SCALE
        chassis_y = (total_h_px - (bot.track_width * SCALE)) / 2
        chassis_rect = pygame.Rect(chassis_x, chassis_y, bot.length * SCALE, bot.track_width * SCALE)

        # Draw main chassis body
        pygame.draw.rect(robot_surf, CYAN if sim.current_mode == "drive" else ORANGE, chassis_rect)
        pygame.draw.line(robot_surf, WHITE, (chassis_rect.right - 2, chassis_rect.top), (chassis_rect.right - 2, chassis_rect.bottom), 4)
        
        # Draw intake subsystem (Front / Right)
        if bot.has_intake:
            intake_w_px = bot.intake_width * SCALE
            intake_l_px = bot.intake_length * SCALE
            offset_px = bot.intake_offset * SCALE
            intake_x = chassis_rect.right - offset_px
            intake_y = (total_h_px / 2) - (intake_w_px / 2)
            
            intake_surf = pygame.Surface((intake_l_px, intake_w_px), pygame.SRCALPHA)
            intake_surf.fill((0, 200, 255, 160))
            pygame.draw.rect(intake_surf, WHITE, (0, 0, intake_l_px, intake_w_px), 2)
            robot_surf.blit(intake_surf, (intake_x, intake_y))

        # Draw outtake subsystem (Rear / Left)
        if bot.has_outtake:
            outtake_w_px = bot.outtake_width * SCALE
            outtake_l_px = bot.outtake_length * SCALE
            out_offset_px = bot.outtake_offset * SCALE
            outtake_x = chassis_rect.left - outtake_l_px + out_offset_px
            outtake_y = (total_h_px / 2) - (outtake_w_px / 2)
            
            outtake_surf = pygame.Surface((outtake_l_px, outtake_w_px), pygame.SRCALPHA)
            outtake_surf.fill((200, 80, 220, 200))  # Purple translucent surface
            pygame.draw.rect(outtake_surf, (140, 120, 250), (0, 0, outtake_l_px, outtake_w_px), 2)
            robot_surf.blit(outtake_surf, (outtake_x, outtake_y))

        rot_bot = pygame.transform.rotate(robot_surf, bot.angle)
        
        # Calculate rotation pivot offset so the robot spins around its true center
        center_dx = ((stick_out_in - stick_out_out) * SCALE / 2) * math.cos(math.radians(bot.angle))
        center_dy = ((stick_out_in - stick_out_out) * SCALE / 2) * math.sin(math.radians(bot.angle))
        bot_center_x = (bot.x * SCALE) + center_dx
        bot_center_y = (FIELD_PIXELS - (bot.y * SCALE)) - center_dy
        
        bot_rect = rot_bot.get_rect(center=(bot_center_x, bot_center_y))
        screen.blit(rot_bot, bot_rect)
        if sim.current_mode == "edit": pygame.draw.rect(screen, YELLOW, bot_rect, 2)

    if sim.settings["field_source"] == "custom" and sim.current_mode != "studio":
        for i, s in enumerate(sim.shapes):
            if s.get("body_type") == "passthrough" and s.get("is_overpass", False):
                render_shape(i, s)


    # Tracks and indicates if user is in Driver vs Edit Mode
    mode_label = f"SYSTEM STATUS: {sim.current_mode.upper()} MODE"
    if sim.current_mode == "edit":
        status_color = ORANGE  
    else:
        status_color = CYAN
    
    # If autonomous scripting routine loop execution layer is active
    if sim.auton_running:
        mode_label = "SYSTEM STATUS: RUNNING AUTONOMOUS ROUTINE"
        status_color = GREEN

    # Draws a clean dark background strip for text readability over bright field assets
    pygame.draw.rect(screen, (20, 20, 25), (10, 10, 395, 30), border_radius=4)
    draw_small(mode_label, 18, 18, status_color)
    
    # Control Side UI Column Render Processing
    pygame.draw.rect(screen, (25, 25, 25), (FIELD_PIXELS, 0, UI_WIDTH, WINDOW_HEIGHT))
    draw_text("Mode", FIELD_PIXELS + 20, 0, YELLOW)
    pygame.draw.rect(screen, GREEN if sim.current_mode == "drive" else LIGHT_GRAY, mode_drive_button_rect, border_radius=6)
    pygame.draw.rect(screen, GREEN if sim.current_mode == "edit" else LIGHT_GRAY, mode_edit_button_rect, border_radius=6)
    draw_text("Drive", mode_drive_button_rect.x + 30, mode_drive_button_rect.y + 4, BLACK)
    draw_text("Edit", mode_edit_button_rect.x + 35, mode_edit_button_rect.y + 4, BLACK)
    #Studio mode sidebar (Different set of buttons for Robot CAD)
    if sim.current_mode == "studio":
        studio_center_x = FIELD_PIXELS / 2
        studio_center_y = FIELD_PIXELS / 2
        
        # Draw robot chassis box
        cad_w = bot.length * SCALE
        cad_h = bot.track_width * SCALE
        cad_rect = pygame.Rect(studio_center_x - cad_w/2, studio_center_y - cad_h/2, cad_w, cad_h)
        pygame.draw.rect(screen, CYAN, cad_rect) 
        #Center origin crosshair
        pygame.draw.line(screen, WHITE, (studio_center_x - 15, studio_center_y), (studio_center_x + 15, studio_center_y), 1)
        pygame.draw.line(screen, WHITE, (studio_center_x, studio_center_y - 15), (studio_center_x, studio_center_y + 15), 1)
        # Render intake subsystem on CAD model
        if bot.has_intake:
            # Convert intake dimensions to pixel scale
            intake_w_px = bot.intake_width * SCALE
            intake_l_px = bot.intake_length * SCALE
            offset_px = bot.intake_offset * SCALE
            # Position at the front (right side) of the blueprint chassis
            intake_x = cad_rect.right - offset_px
            intake_y = studio_center_y - (intake_w_px / 2)
            intake_rect = pygame.Rect(intake_x, intake_y, intake_l_px, intake_w_px)
            # Draw intake roller structure
            pygame.draw.rect(screen, (30, 100, 160), intake_rect)  # Darker blue fill
            pygame.draw.rect(screen, CYAN, intake_rect, 2)         # Outline
        else:
            # Front direction indicator line
            pygame.draw.line(screen, WHITE, (cad_rect.right - 2, cad_rect.top), (cad_rect.right - 2, cad_rect.bottom), 4)
        # Render outtake subsystem on CAD model
        if bot.has_outtake:
            outtake_w_px = bot.outtake_width * SCALE
            outtake_l_px = bot.outtake_length * SCALE
            outtake_offset_px = bot.outtake_offset * SCALE
            # Position at the left side of the blueprint chassis
            outtake_x = cad_rect.left - outtake_l_px + outtake_offset_px
            outtake_y = studio_center_y - (outtake_w_px / 2)
            outtake_rect = pygame.Rect(outtake_x, outtake_y, outtake_l_px, outtake_w_px)
            # Draw outtake structure 
            pygame.draw.rect(screen, (120, 40, 140), outtake_rect)   
            pygame.draw.rect(screen, (200, 80, 220), outtake_rect, 2) 

        # Dimension labels on CAD canvas
        draw_small(f"L: {bot.length:.1f}\"", cad_rect.centerx - 25, cad_rect.bottom + 8, DARK)
        draw_small(f"W: {bot.track_width:.1f}\"", cad_rect.right + 15, cad_rect.centery - 6, DARK)

        if sim.current_page == "studio 1":
            # Header indicator
            draw_text("Robot Configuration", FIELD_PIXELS + 20, 65, ORANGE)
            pygame.draw.line(screen, DARK, (FIELD_PIXELS + 20, 90), (WINDOW_WIDTH - 20, 90), 2)
            
            draw_small("Drivetrain gear ratio:", FIELD_PIXELS + 20, 190, LIGHT_GRAY)
            draw_small("Motor Gear Cartridge:", FIELD_PIXELS + 20, 310, LIGHT_GRAY)

            # Draw all the components
            for element in studio_1_ui:
                element.draw(screen)

        elif sim.current_page == "studio 2":
        # Header indicator
            draw_text("Intake/Outtake Configuration", FIELD_PIXELS + 20, 65, ORANGE)
            pygame.draw.line(screen, DARK, (FIELD_PIXELS + 20, 90), (WINDOW_WIDTH - 20, 90), 2)
            
            # --- Outtake System ---
            draw_small("Outtake system:", FIELD_PIXELS+20, btn_out_toggle.screen_rect.y - 20, LIGHT_GRAY)
            btn_out_toggle.text = "ENABLED" if bot.has_outtake else "DISABLED"
            btn_out_toggle.default_color = GREEN if bot.has_outtake else LIGHT_GRAY
            for element in studio_2_outtake_ui:
                # Only draw the extra settings if it is enabled!
                if element == btn_out_toggle or bot.has_outtake:
                    element.draw(screen)
            
            if bot.has_outtake:
                draw_small("Outtake offset:", FIELD_PIXELS + 20, btn_out_shift_in.screen_rect.y - 20, LIGHT_GRAY)
            
            # --- Intake System ---
            draw_small("Intake system:", FIELD_PIXELS+20, btn_in_toggle.screen_rect.y - 20, LIGHT_GRAY)
            btn_in_toggle.text = "ENABLED" if bot.has_intake else "DISABLED"
            btn_in_toggle.default_color = GREEN if bot.has_intake else LIGHT_GRAY
            for element in studio_2_intake_ui:
                if element == btn_in_toggle or bot.has_intake:
                    element.draw(screen)

            if bot.has_intake:
                draw_small("Intake offset:", FIELD_PIXELS + 20, btn_in_shift_in.screen_rect.y - 20, LIGHT_GRAY)
                # Max length warning
                stick_out_in = max(0.0, bot.intake_length - bot.intake_offset)
                stick_out_out = max(0.0, bot.outtake_length - bot.outtake_offset) if bot.has_outtake else 0.0
                total_L = bot.length + stick_out_in + stick_out_out
                draw_small(f"Total L: {total_L:.1f}\"", FIELD_PIXELS + 110, btn_in_shift_in.screen_rect.y + 5, RED if total_L > bot.max_size else GREEN)

            # --- Delay System ---
            draw_small("Scoring delay:", FIELD_PIXELS+20, btn_delay_toggle.screen_rect.y - 20, LIGHT_GRAY)
            btn_delay_toggle.text = "ENABLED" if bot.delay_flag else "DISABLED"
            btn_delay_toggle.default_color = GREEN if bot.delay_flag else LIGHT_GRAY
            for element in studio_2_delay_ui:
                if element == btn_delay_toggle or bot.delay_flag:
                    element.draw(screen)
                
        pygame.draw.rect(screen, LIGHT_GRAY, mode_page_switch_button_rect, border_radius=4)
        if sim.current_page == "studio 1":
            draw_small("Next", mode_page_switch_button_rect.x + 9, mode_page_switch_button_rect.y + 11, BLACK)
        elif sim.current_page == "studio 2":
            draw_small("Back", mode_page_switch_button_rect.x + 9, mode_page_switch_button_rect.y + 11, BLACK)

        studio_display_y = 700
        #Calculated performance section
        draw_small("Calculated Specs:", FIELD_PIXELS + 20, studio_display_y, LIGHT_GRAY)
        # Display calculated RPM
        active_cart = sim.settings.get("motor_cartridge", "green")
        motor_rpm = {"red": 100, "green": 200, "blue": 600}.get(active_cart, 200)
        bot.calculate_max_speed(active_cart)
        draw_small(f"Motor Speed: {motor_rpm} RPM", FIELD_PIXELS + 25, studio_display_y+25, YELLOW)
        draw_small(f"Output Speed: {bot.output_rpm:.1f} RPM ({bot.gear_in}t:{bot.gear_out}t)", FIELD_PIXELS + 25, studio_display_y+45, CYAN)
        # Display calculated top speed
        top_ips = bot.base_max_speed #inches per second
        top_fps = top_ips / 12.0 #feet per second
        draw_small(f"Top Speed: {top_ips:.1f} in/s ({top_fps:.1f} ft/s)", FIELD_PIXELS + 25, studio_display_y+65, GREEN)
    #Standart field sidebar (Only show buttons in Drive/Edit mode)
    else:
        # Dynamic settings selectors indicators map
        if sim.current_mode == "drive":
            btn_drive_tank.default_color = GREEN if sim.settings["drive_mode"] == "tank" else LIGHT_GRAY
            btn_drive_arcade.default_color = GREEN if sim.settings["drive_mode"] == "arcade" else LIGHT_GRAY
            btn_drive_custom.default_color = GREEN if sim.settings["drive_mode"] == "custom" else LIGHT_GRAY
            
            btn_input_key.default_color = YELLOW if sim.settings["input_mode"] == "keyboard" else LIGHT_GRAY
            btn_input_ctrl.default_color = YELLOW if sim.settings["input_mode"] == "controller" else LIGHT_GRAY
            
            btn_auton.default_color = GREEN if not sim.auton_running else LIGHT_GRAY
            btn_auton.text = "Run Autonomous" if not sim.auton_running else "Running..."

            speed_slider.draw(screen)
            turn_slider.draw(screen)
        
            for element in drive_ui:
                element.draw(screen)

            # Drive mode inventory HUD
            inv_y = 180
            draw_text("Bot Storage", FIELD_PIXELS + 20, inv_y+500, YELLOW)
            draw_small(f"Capacity: {len(bot.inventory)}/{bot.max_capacity}", FIELD_PIXELS + 160, inv_y + 504, LIGHT_GRAY)

            # Storage slot boxes
            for i in range(bot.max_capacity):
                slot_rect = pygame.Rect(FIELD_PIXELS + 20 + (i * 45), inv_y + 525, 38, 38)
                pygame.draw.rect(screen, (40, 40, 50), slot_rect, border_radius=6)
                pygame.draw.rect(screen, LIGHT_GRAY, slot_rect, 1, border_radius=6)
                
                #Draw stored item if present
                if i < len(bot.inventory):
                    s = bot.inventory[i]
                    box_cx, box_cy = slot_rect.center

                    if s["type"] == "circ":
                    # Cap visual radius so it fits comfortably inside slot box
                        visual_r = min(14, int(s["radius"] * 2.0))
                        pygame.draw.circle(screen, s["color"], (box_cx, box_cy), visual_r)
                    
                    elif s["type"] == "rect":
                        # Calculate aspect ratio scale to fit inside 28x28 max inner box
                        max_dim = max(s["w"], s["h"])
                        scale_factor = 26.0 / max_dim if max_dim > 0 else 1.0
                        
                        disp_w = int(s["w"] * scale_factor)
                        disp_h = int(s["h"] * scale_factor)
                        
                        icon_rect = pygame.Rect(0, 0, disp_w, disp_h)
                        icon_rect.center = (box_cx, box_cy)
                        pygame.draw.rect(screen, s["color"], icon_rect, border_radius=3)

                    timer_val = s.get("travel_timer", 0.0)
                    if timer_val > 0.0:
                        #Semi-transparent dark overlay over slot
                        timer_surf = pygame.Surface((38, 38), pygame.SRCALPHA)
                        timer_surf.fill((0, 0, 0, 160))
                        screen.blit(timer_surf, (slot_rect.x, slot_rect.y))
                        #Countdown text in slot
                        draw_small(f"{timer_val:.1f}s", slot_rect.x + 4, slot_rect.y + 11, YELLOW)
                    else:
                        #Indicator with color when finished
                        pygame.draw.rect(screen, s.get("color"), slot_rect, 2, border_radius=6)

            # HUD Intake/Outtake
            hud_y = inv_y + 140
            draw_text("Subsystems", FIELD_PIXELS + 20, hud_y, YELLOW)
            # Intake 
            
            if bot.intake_state == "in":
                intake_str, intake_color = "Intaking", GREEN
            elif bot.intake_state == "out":
                intake_str, intake_color = "Outtaking", GREEN
            else:
                intake_str, intake_color = "None", LIGHT_GRAY
            draw_small(f"Intake:  {intake_str}", FIELD_PIXELS + 20, hud_y + 24, intake_color)
            # Outtake 
            if bot.outtake_state == "out":
                outtake_str, outtake_color = "Scoring", GREEN
            else:
                outtake_str, outtake_color = "None", LIGHT_GRAY
            draw_small(f"Outtake: {outtake_str}", FIELD_PIXELS + 20, hud_y + 44, outtake_color)

            # Real-time speedometer
            speed_y = WINDOW_HEIGHT - 135
            draw_text("Telemetry", FIELD_PIXELS + 20, speed_y, YELLOW)
            curr_ips = abs(bot.current_speed)
            curr_fps = curr_ips / 12.0
            draw_small(f"Speed: {curr_ips:.1f} in/s ({curr_fps:.1f} ft/s)", FIELD_PIXELS + 20, speed_y + 22, GREEN)
            pygame.draw.line(screen, DARK, (FIELD_PIXELS + 20, speed_y + 40), (WINDOW_WIDTH - 20, speed_y + 40), 1)
            
        elif sim.current_mode == "edit":
            draw_small("X -->", FIELD_PIXELS - 50, FIELD_PIXELS - 22, BLACK)
            draw_small("^ Y", 8, 50, BLACK)
            draw_small("|", 8, 57, BLACK)

            for inch in range(12, 133, 12):
                px_val = int(inch * SCALE)

                line_color = (120, 120, 120)
                if inch % 24 == 0:
                    line_color = BLACK

                # X Axis (Bottom)
                pygame.draw.line(screen, line_color, (px_val, FIELD_PIXELS - 14), (px_val, FIELD_PIXELS - 6), 2)
                draw_small(f"{inch}\"", px_val - 10, FIELD_PIXELS - 28, line_color)

                # Y Axis (Left)
                line_y = FIELD_PIXELS - px_val #Flip the Y cords instead of pygame top left
                pygame.draw.line(screen, line_color, (6, line_y), (14, line_y), 2)
                draw_small(f"{inch}\"", 16, line_y - 6, line_color)

            pygame.draw.rect(screen, LIGHT_GRAY, mode_page_switch_button_rect, border_radius=4)
            if sim.current_page == "edit 1":
                draw_small("Next", mode_page_switch_button_rect.x + 9, mode_page_switch_button_rect.y + 11, BLACK)
            elif sim.current_page == "edit 2":
                draw_small("Back", mode_page_switch_button_rect.x + 9, mode_page_switch_button_rect.y + 11, BLACK)

            if sim.current_page == "edit 1":
                draw_small("Field Display Option:", btn_field_img.screen_rect.x, btn_field_img.screen_rect.y - 20, YELLOW)
                btn_field_img.default_color = GREEN if sim.settings["field_source"] == "image" else LIGHT_GRAY
                btn_field_cust.default_color = GREEN if sim.settings["field_source"] == "custom" else LIGHT_GRAY
                
                draw_small("Game Elements Customization:", btn_add_shape.screen_rect.x, btn_add_shape.screen_rect.y - 20, YELLOW)
                
                for element in edit_buttons_ui:
                    element.draw(screen)
                
                shape_dropdown.draw(screen) 
            
                # Inspector Panel selection layout loop context mapping logic
                if sim.selected_shape_idx is not None and 0 <= sim.selected_shape_idx < len(sim.shapes):
                    s = sim.shapes[sim.selected_shape_idx]
                    current_phys = s.get("body_type", "static")
                    
                    if s["type"] == "rect":
                        if not box_sx.is_active: box_sx.value = f"{s['x']:.1f}"
                        if not box_sy.is_active: box_sy.value = f"{s['y']:.1f}"
                        if not box_sw.is_active: box_sw.value = f"{s['w']:.1f}"
                        if not box_sh.is_active: box_sh.value = f"{s['h']:.1f}"
                        if not box_sa.is_active: box_sa.value = f"{s['angle']:.1f}"
                        for box in [box_sx, box_sy, box_sw, box_sh, box_sa]: box.draw(screen)
                        
                    elif s["type"] == "circ":
                        if not box_sx.is_active: box_sx.value = f"{s['x']:.1f}"
                        if not box_sy.is_active: box_sy.value = f"{s['y']:.1f}"
                        if not box_sr.is_active: box_sr.value = f"{s['radius']:.1f}"
                        for box in [box_sx, box_sy, box_sr]: box.draw(screen)
                        
                    if current_phys == "dynamic":
                        if not box_sm.is_active: box_sm.value = f"{s.get('mass', 1.0):.1f}"
                        box_sm.draw(screen)

                    if current_phys == "passthrough":
                        if not box_sf.is_active: box_sf.value = f"{s.get('friction', 0.5):.2f}"
                        if not box_se.is_active: box_se.value = f"{s.get('elasticity', 0.0):.2f}"
                        box_sf.draw(screen)
                        box_se.draw(screen)

                    if current_phys == "static":
                        btn_phys_toggle.default_color = RED
                        btn_phys_toggle.text = "STATIC (WALL)"
                    elif current_phys == "passthrough":
                        btn_phys_toggle.default_color = CYAN
                        btn_phys_toggle.text = "PASSTHROUGH"
                        
                        # Only update and draw the layer toggle if it's passthrough
                        is_over = s.get("is_overpass", False)
                        btn_layer_toggle.default_color = (139,108,92) if is_over else (106,74,58)
                        btn_layer_toggle.text = "HIGH (OVER)" if is_over else "LOW (GROUND)"
                        draw_small("Layer Height", btn_layer_toggle.screen_rect.x, btn_layer_toggle.screen_rect.y - 16, LIGHT_GRAY)
                        btn_layer_toggle.draw(screen)
                        
                    elif current_phys == "dynamic":
                        btn_phys_toggle.default_color = GREEN
                        btn_phys_toggle.text = "DYNAMIC (BALL)"

                    draw_small("Physics Mode", btn_phys_toggle.screen_rect.x, btn_phys_toggle.screen_rect.y - 16, LIGHT_GRAY)
                    btn_phys_toggle.draw(screen)

                    draw_small("Color Palette", color_button_rects[0].x, color_button_rects[0].y - 20, YELLOW)
                    for i, rect in enumerate(color_button_rects):
                        pygame.draw.rect(screen, COLOR_PALETTE[i], rect, border_radius=4)
                        if s["color"] == COLOR_PALETTE[i]:
                            pygame.draw.rect(screen, WHITE, rect, 2, border_radius=4)

                else:
                    draw_small("No shape selected", FIELD_PIXELS + 20, shape_panel_y + 25, LIGHT_GRAY)

                # Global teleop diagnostics metrics dashboard tracking
                draw_small("Robot's Starting Pose:", box_rx.screen_rect.x, box_rx.screen_rect.y - 35, YELLOW)
                rx, ry, ra = bot.start_pose
                # Update Robot values dynamically
                if not box_rx.is_active: box_rx.value = f"{rx:.1f}"
                if not box_ry.is_active: box_ry.value = f"{ry:.1f}"
                if not box_ra.is_active: box_ra.value = f"{ra:.1f}"
                if not box_rlen.is_active: box_rlen.value = f"{bot.length:.1f}"
                if not box_rwid.is_active: box_rwid.value = f"{bot.track_width:.1f}"
                for element in edit_robot_ui:
                    element.draw(screen)       

        # Pose/ Odom footer
        info_y = WINDOW_HEIGHT - 90
        draw_text("Pose (Field)", FIELD_PIXELS + 20, info_y, LIGHT_GRAY)
        draw_small(f"x={bot.x:.1f} in", FIELD_PIXELS + 20, info_y + 20, LIGHT_GRAY)
        draw_small(f"y={bot.y:.1f} in", FIELD_PIXELS + 20, info_y + 40, LIGHT_GRAY)
        draw_small(f"θ={bot.angle%360:.1f}°", FIELD_PIXELS + 20, info_y + 60, LIGHT_GRAY)
        
        ox, oy = bot.get_odom_pose()
        draw_text("Pose (Odom)", FIELD_PIXELS + 160, info_y, LIGHT_GRAY)
        draw_small(f"x={ox:.1f}", FIELD_PIXELS + 160, info_y + 20, LIGHT_GRAY)
        draw_small(f"y={oy:.1f}", FIELD_PIXELS + 160, info_y + 40, LIGHT_GRAY)
    
        if m_fx != -1:
            mxo, myo = m_fx - bot.odom_origin_x, m_fy - bot.odom_origin_y
            draw_small(f"Cursor Odom: {mxo:.1f}, {myo:.1f}", FIELD_PIXELS + 160, info_y + 60, LIGHT_GRAY)

    #Semi-transparent overlay when Paused (pressed "Esc")
    if sim.paused:
        #Spanning across the entire screen
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA) #Each pixel's opacity acts independently, rather than everything having the same opacity
        #Overlay over the whole screen rather than replacing it (visual effect)
        overlay.fill((128, 128, 128, 150)) # Can be changed. (R, G, B, Opacity) 255 being maxed, 0 being completely see-through.
        screen.blit(overlay, (0, 0))

        #Main pause box (Modal)
        if sim.paused_sub_menu == "main":
            pygame.draw.rect(screen, (35, 35, 45), pause_modal_rect, border_radius=12)
            pygame.draw.rect(screen, YELLOW, pause_modal_rect, 2, border_radius=12) 
            draw_text("GAME PAUSED", pause_modal_rect.x + 85, pause_modal_rect.y + 20, YELLOW)

            #Update display for different screens
            if sim.current_mode == "drive" or sim.current_mode == "edit":
                btn_pause_studio.text = "Robot Design Studio"
            elif sim.current_mode == "studio":
                btn_pause_studio.text = "Return to Drive mode"

            #Loop through and render everything
            for element in pause_ui:
                element.draw(screen)   

        elif sim.paused_sub_menu == "settings":
            k_in = pygame.key.name(sim.settings["keybinds"]["intake_in"]).upper()
            k_out = pygame.key.name(sim.settings["keybinds"]["intake_out"]).upper()
            k_score = pygame.key.name(sim.settings["keybinds"]["outtake_score"]).upper()
            
            btn_in.text = "Press Any Key..." if sim.remapping_key == "intake_in" else f"Intake In Key: {k_in}"
            btn_out.text = "Press Any Key..." if sim.remapping_key == "intake_out" else f"Intake Out Key: {k_out}"
            btn_score.text = "Press Any Key..." if sim.remapping_key == "outtake_score" else f"Outtake Score: {k_score}"
            btn_mode.text = f"Intake Mode: {sim.settings['intake_control_mode'].upper()}"

            settings_scrollview.draw(screen)
    
    pygame.display.flip()
# =====================================================================
# 6. ACTION INTERACTION ROUTINES (UI Click & Inputs Handler)
# =====================================================================
def handle_ui_click(mx, my):
    if mode_drive_button_rect.collidepoint(mx, my): 
        sim.current_mode = "drive"
        sim.selected_shape_idx = None
        sim.active_textbox = None
        bot.calculate_max_speed(sim.settings.get("motor_cartridge", "green"))
        sync_custom_obstacles_to_physics() #Calling the physics body build
        return
    if mode_edit_button_rect.collidepoint(mx, my): 
        sim.current_mode = "edit"
        sim.current_page = "edit 1"
        return
    
    if sim.current_mode == "studio":
        if sim.current_page == "studio 1":
            if mode_page_switch_button_rect.collidepoint(mx,my): sim.current_page = "studio 2"; return
        elif sim.current_page == "studio 2":
            if mode_page_switch_button_rect.collidepoint(mx,my): sim.current_page = "studio 1"; return

    elif sim.current_mode == "edit":
        if sim.current_page == "edit 1":
            # Drop textboxes selection processing checks blocks
            if sim.selected_shape_idx is not None:
                s = sim.shapes[sim.selected_shape_idx]               
                for i, rect in enumerate(color_button_rects):
                    if rect.collidepoint(mx, my): s["color"] = COLOR_PALETTE[i]; save_field_data(); return

            if mode_page_switch_button_rect.collidepoint(mx,my): sim.current_page = "edit 2"; return
        elif sim.current_page == "edit 2":
            if mode_page_switch_button_rect.collidepoint(mx,my): sim.current_page = "edit 1"; return

# =====================================================================
# 7. AUTONOMOUS COMMAND EXECUTORS (Hardcoded Sequential Layer)
# =====================================================================
def drive_inches(length, velo):
    speed = (velo / 100.0) * bot.base_max_speed
    target, moved, direction = abs(length), 0.0, (1 if length > 0 else -1)
    while moved < target:
        dt = clock.tick(60) / 1000.0
        step = min(speed * dt, target - moved)
        moved += step
        rad = math.radians(bot.angle)
        bot.x += direction * step * math.cos(rad)
        bot.y += direction * step * math.sin(rad)
        bot.x = max(bot.length / 2, min(FIELD_INCHES - bot.length / 2, bot.x))
        bot.y = max(bot.track_width / 2, min(FIELD_INCHES - bot.track_width / 2, bot.y))
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); raise SystemExit
        draw_everything()

def turn_degrees(side, deg, velo):
    max_speed = (velo / 100.0) * bot.base_max_speed
    direction, target, turned = (1 if side == 'l' else -1), abs(deg), 0.0
    while turned < target:
        dt = clock.tick(60) / 1000.0
        omega = (direction * max_speed - (-direction * max_speed)) / bot.track_width
        delta_deg = math.degrees(omega * dt)
        if turned + abs(delta_deg) > target: delta_deg = math.copysign(target - turned, delta_deg)
        bot.angle += delta_deg
        turned += abs(delta_deg)
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); raise SystemExit
        draw_everything()

def autonomous():
    for _ in range(4):
        drive_inches(24, 40) #Drive 24 inches at 40% speed
        turn_degrees('r', 90, 40) #Turn right 90 degrees at 40% speed
        
    turn_degrees('l',720,50) #Celebration spin!

# =====================================================================
# 8. MAIN RUNTIME LOOP
# =====================================================================
joystick = None
if pygame.joystick.get_count() > 0:
    joystick = pygame.joystick.Joystick(0); joystick.init()
    
create_field_boundaries() #Create physical boundaries around fields using PyMunk
sync_custom_obstacles_to_physics()

running = True
while running:
    dt = clock.tick(60) / 1000.0

    for event in pygame.event.get():
        if event.type == pygame.QUIT: running = False

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            #Handling clicks when the game is paused
            if sim.paused:
                if sim.paused_sub_menu == "main":
                    #Letting the objects (ui.py) handle their own clicks
                    for element in pause_ui:
                        if element.handle_event(event, mx, my):
                            break

                elif sim.paused_sub_menu == "settings":
                    settings_scrollview.handle_event(event, mx, my)
            #Handling clicks when the game is NOT paused
            elif mx >= FIELD_PIXELS: 
                handled = False
                if sim.current_mode == "drive":
                    handled = speed_slider.handle_event(event, mx, my) or turn_slider.handle_event(event, mx, my)

                    if not handled:
                        for element in drive_ui:
                            if element.handle_event(event, mx, my):
                                handled = True

                elif sim.current_mode == "edit" and sim.current_page == "edit 1":
                    handled = shape_dropdown.handle_event(event, mx, my)

                    if not handled:
                        for element in edit_buttons_ui + edit_inspector_ui + edit_shape_txt + edit_robot_ui:
                            if element.handle_event(event, mx, my):
                                handled = True

                elif sim.current_mode == "studio" and sim.current_page == "studio 1":
                    for element in studio_1_ui:
                        if element.handle_event(event, mx, my):
                            handled = True

                elif sim.current_mode == "studio" and sim.current_page == "studio 2":
                    elements = studio_2_outtake_ui + studio_2_intake_ui + studio_2_delay_ui
                    for element in elements:
                        if element.handle_event(event, mx, my):
                            handled = True

                if not handled: #Run old function if not detected
                    handle_ui_click(mx, my)

            elif sim.current_mode == "edit":
                if sim.current_page == "edit 1":
                    fake_click = pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(-100, -100), button=1)
                    for element in edit_shape_txt + edit_robot_ui:
                        element.handle_event(fake_click, -100, -100)
                # Check robot drag focus
                dx, dy = mx - bot.x * SCALE, my - (FIELD_PIXELS - bot.y * SCALE)
                r_radius = max(bot.length, bot.track_width) * SCALE / 2 + 10
                if dx*dx + dy*dy <= r_radius*r_radius:
                    sim.dragging_robot = True
                    sim.robot_drag_offset_x = (mx / SCALE) - bot.x
                    sim.robot_drag_offset_y = ((FIELD_PIXELS - my) / SCALE) - bot.y
                else:
                    m_fx, m_fy = mx / SCALE, (FIELD_PIXELS - my) / SCALE
                    if sim.selected_shape_idx is not None and 0 <= sim.selected_shape_idx < len(sim.shapes):
                        sel_s = sim.shapes[sim.selected_shape_idx]
                        #getting cords for the white dot/ resizing dot on top right of rectangle or right side of circle
                        if sel_s["type"] == "rect":
                            w_px_x = (sel_s["x"] + sel_s["w"]) * SCALE
                            w_px_y = FIELD_PIXELS - ((sel_s["y"] + sel_s["h"]) * SCALE)
                        else:
                            w_px_x = (sel_s["x"] + sel_s["radius"]) * SCALE
                            w_px_y = FIELD_PIXELS - (sel_s["y"] * SCALE)

                        dis_sq = (mx - w_px_x)**2 + (my - w_px_y)**2 #Squared dist of click from white dot
                        if dis_sq <= 10**2: #If within a 10px range
                            sim.resizing_shape = True
                            continue

                    sim.selected_shape_idx = None
                    for i in reversed(range(len(sim.shapes))):
                        s = sim.shapes[i]
                        if s["type"] == "rect" and s["x"] <= m_fx <= s["x"] + s["w"] and s["y"] <= m_fy <= s["y"] + s["h"]:
                            sim.selected_shape_idx = i; break
                        elif s["type"] == "circ" and (m_fx - s["x"])**2 + (m_fy - s["y"])**2 <= s["radius"]**2:
                            sim.selected_shape_idx = i; break
                    if sim.selected_shape_idx is not None:
                        s = sim.shapes[sim.selected_shape_idx]
                        sim.drag_offset_x = m_fx - (s["x"] + s["w"]/2 if s["type"]=="rect" else s["x"])
                        sim.drag_offset_y = m_fy - (s["y"] + s["h"]/2 if s["type"]=="rect" else s["y"])
                        sim.dragging_shape = True

        elif event.type == pygame.MOUSEWHEEL:
            if sim.paused and sim.paused_sub_menu == "settings":
                mx, my = pygame.mouse.get_pos()
                settings_scrollview.handle_event(event, mx, my)

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            mx, my = event.pos
            if sim.current_mode == "edit":
                if sim.dragging_robot: sim.dragging_robot = False; bot.start_pose = (bot.x, bot.y, bot.angle); save_field_data()
                elif sim.dragging_shape: sim.dragging_shape = False; save_field_data()
                elif sim.resizing_shape: sim.resizing_shape = False; save_field_data()
            elif sim.current_mode == "drive":
                speed_slider.handle_event(event, mx, my)
                turn_slider.handle_event(event, mx, my)
                
        elif event.type == pygame.MOUSEMOTION:
            mx, my = event.pos
            if sim.current_mode == "drive":
                speed_slider.handle_event(event, mx, my)
                turn_slider.handle_event(event, mx, my)

            elif sim.current_mode == "edit":
                m_fx, m_fy = mx / SCALE, (FIELD_PIXELS - my) / SCALE

                if sim.resizing_shape and sim.selected_shape_idx is not None:
                    s = sim.shapes[sim.selected_shape_idx]
                    if s["type"] == "rect":
                        new_w = m_fx - s["x"]
                        new_h = m_fy - s["y"]
                        s["w"] = max(1.0, new_w)
                        s["h"] = max(1.0, new_h)
                    elif s["type"] == "circ":
                        new_r = m_fx - s["x"]
                        s["radius"] = max(1.0, new_r)

                elif sim.dragging_robot:
                    bot.x = m_fx - sim.robot_drag_offset_x
                    bot.y = m_fy - sim.robot_drag_offset_y
                    #Bring the physics (backend) body while dragging
                    bot.body.position = (bot.x * SCALE, bot.y * SCALE)
                elif sim.dragging_shape and sim.selected_shape_idx is not None:
                    s = sim.shapes[sim.selected_shape_idx]
                    if s["type"] == "rect":
                        s["x"] = (m_fx - sim.drag_offset_x) - s["w"]/2
                        s["y"] = (m_fy - sim.drag_offset_y) - s["h"]/2
                    else:
                        s["x"] = m_fx - sim.drag_offset_x
                        s["y"] = m_fy - sim.drag_offset_y

        elif event.type == pygame.KEYDOWN:
            mx, my = pygame.mouse.get_pos()

            if sim.current_mode == "studio" and sim.current_page == "studio 1":
                for element in studio_1_ui:
                    element.handle_event(event, mx, my)
            elif sim.current_mode == "studio" and sim.current_page == "studio 2":
                elements = studio_2_outtake_ui + studio_2_intake_ui + studio_2_delay_ui
                for element in elements:
                    element.handle_event(event, mx, my)
            elif sim.current_mode == "edit" and sim.current_page == "edit 1":
                for element in edit_shape_txt + edit_robot_ui:
                    element.handle_event(event, mx, my)

            # Global Pause Toggle (ESC Key)
            if event.key == pygame.K_ESCAPE:
                sim.active_textbox = None
                if sim.paused and sim.paused_sub_menu == "settings":
                    sim.paused_sub_menu = "main"
                else:
                    sim.paused = not sim.paused
                    sim.paused_sub_menu = "main"
            elif sim.remapping_key is not None:
                    sim.settings["keybinds"][sim.remapping_key] = event.key
                    sim.remapping_key = None
                    save_settings()
            elif sim.current_mode == "edit" and sim.selected_shape_idx is not None and event.key == pygame.K_BACKSPACE:
                is_typing = False
                if sim.current_page == "edit 1":
                    for box in edit_shape_txt + edit_robot_ui:
                        if getattr(box, "is_active", False):
                            is_typing = True
                            break
                            
                if not is_typing:
                    removed_s = sim.shapes.pop(sim.selected_shape_idx)
                    if "body" in removed_s and removed_s["body"] in space.bodies:
                        space.remove(removed_s["body"])
                    if "pymunk_shape" in removed_s and removed_s["pymunk_shape"] in space.shapes:
                        space.remove(removed_s["pymunk_shape"])
                    sim.selected_shape_idx = None
                    save_field_data()
                    sync_custom_obstacles_to_physics()

            # Toggle mode intake switching
            elif sim.current_mode == "drive" and not sim.paused and sim.settings["intake_control_mode"] == "toggle":
                if event.key == sim.settings["keybinds"]["intake_in"]:
                    bot.intake_state = "off" if bot.intake_state == "in" else "in"
                elif event.key == sim.settings["keybinds"]["intake_out"]:
                    bot.intake_state = "off" if bot.intake_state == "out" else "out"
                elif event.key == sim.settings["keybinds"]["outtake_score"]:
                    bot.outtake_state = "off" if bot.outtake_state == "out" else "out"
        elif event.type == pygame.JOYDEVICEADDED and joystick is None:
            joystick = pygame.joystick.Joystick(event.device_index); joystick.init()
        elif event.type == pygame.JOYDEVICEREMOVED and joystick is not None and event.instance_id == joystick.get_instance_id():
            joystick = None

    # Teleop update context loop checks
    if sim.current_mode == "drive" and not sim.paused:
        if sim.auton_mode and not sim.auton_running:
            sim.auton_running = True; sim.auton_mode = False
            autonomous()
            sim.auton_running = False
        if not sim.auton_running:
            l_speed, r_speed = get_inputs(dt)
            update_physics(l_speed, r_speed, dt)

    draw_everything()

pygame.quit()
