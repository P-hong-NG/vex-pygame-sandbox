import pygame
import pymunk
import pymunk.pygame_util
import math
import json
import os

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
SETTINGS_FILE = "settings.json"
FIELD_FILE = "custom_field.txt"
DRIVE_FILE = "custom_drive.txt"

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

        # Real-World Screen Position (True State)
        self.x = FIELD_INCHES / 2
        self.y = FIELD_INCHES / 2
        self.angle = 0.0

        #Typical weight, 12-16lbs, for high-performing team. Should be changed to match the actual bot weight
        mass = 14.0 
        #Moment of inertia for solid rectangle box 
        moment = pymunk.moment_for_box(mass, (self.length * SCALE, self.track_width * SCALE))
        
        #Body used for physics calculations (Includes: mass, inertia, position, angle, velocity, torque, etc)
        self.body = pymunk.Body(mass, moment, body_type=pymunk.Body.DYNAMIC) #Dynamic means it moves/ can be interacted with
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

class SimulatorState:
    def __init__(self):
        self.current_mode = "drive" # drive / edit
        self.paused = False
        self.auton_mode = False
        self.auton_running = False
        self.settings = {
            "input_mode": "keyboard",   
            "speed_scale": 1.0,
            "field_source": "image",    
            "drive_mode": "tank"        
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
                sim.settings.update(json.load(f))
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
                    _, x, y, w, h, ang, r, g, b = parts[:9]
                    sim.shapes.append({"type": "rect", "x": float(x), "y": float(y), 
                                       "w": float(w), "h": float(h), 
                                       "angle": float(ang), 
                                       "color": (int(r), int(g), int(b)),
                                       "body_type": b_type, "mass": m_val,
                                       "friction": fric_val, "elasticity": elas_val})
                elif tag == "CIRC" and len(parts) >= 7:
                    b_type = parts[7] if len(parts) >= 8 else "dynamic"
                    m_val = float(parts[8]) if len(parts) >= 9 else 1.0
                    fric_val = float(parts[9]) if len(parts) >= 10 else 0.5
                    elas_val = float(parts[10]) if len(parts) >= 11 else 0.0
                    _, x, y, radius, r, g, b = parts[:7]
                    sim.shapes.append({"type": "circ", "x": float(x), "y": float(y), 
                                       "radius": float(radius), 
                                       "color": (int(r), int(g), int(b)),
                                       "body_type": b_type, "mass": m_val,
                                       "friction": fric_val, "elasticity": elas_val})
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
            if s["type"] == "rect":
                f.write(f"RECT {s['x']} {s['y']} {s['w']} {s['h']} {s['angle']} {s['color'][0]} {s['color'][1]} {s['color'][2]} {b_type} {mass_val} {fric_val} {elas_val}\n")
            elif s["type"] == "circ":
                f.write(f"CIRC {s['x']} {s['y']} {s['radius']} {s['color'][0]} {s['color'][1]} {s['color'][2]} {b_type} {mass_val} {fric_val} {elas_val}\n")
        f.write(f"ROBOT_START {bot.start_pose[0]} {bot.start_pose[1]} {bot.start_pose[2]}\n")

def save_settings():
    try:
        with open(SETTINGS_FILE, "w") as f: json.dump(sim.settings, f)
    except: pass

# Initial data payload configuration setup
load_all_data()

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
    return left_speed, right_speed

#Run 60 times a second, do all the collisions, calculations, and visual updates
def update_physics(left_speed, right_speed, dt):
    v = (left_speed + right_speed) / 2.0 #Linear Velocity or average forward speed
    turn_multiplier = 40.0 #Can be changed! Increase for faster turning
    omega = ((left_speed - right_speed) / bot.track_width)*turn_multiplier  #Difference 
    
    rad = bot.body.angle #Radians for PyMunk
    bot.body.velocity = (v * math.cos(rad) * SCALE, v * math.sin(rad) * SCALE) #Linear
    bot.body.angular_velocity = math.radians(omega) #If positive, spin counter-clockwise, else negative, spin clockwise

    for s in sim.shapes:
        if s.get("body_type") == "dynamic" and "body" in s:
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
    
    #Divide the calculated movement into small chunks to prevent clipping into walls at high speed
    for _ in range(10):
        space.step(dt/10.0)
    #Translate backend position back to normal inches for frontend code
    bot.x = bot.body.position.x / SCALE
    bot.y = bot.body.position.y / SCALE
    bot.angle = math.degrees(bot.body.angle)

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
        if shape != bot.shape and shape not in space.shapes:
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
drive_mode_tank_rect = pygame.Rect(FIELD_PIXELS + 20, 70, 90, 26)
drive_mode_arcade_rect = pygame.Rect(FIELD_PIXELS + 120, 70, 90, 26)
drive_mode_custom_rect = pygame.Rect(FIELD_PIXELS + 220, 70, 90, 26)
keyboard_button_rect = pygame.Rect(FIELD_PIXELS + 20, 110, 100, 26)
controller_button_rect = pygame.Rect(FIELD_PIXELS + 140, 110, 100, 26)
slider_rect = pygame.Rect(FIELD_PIXELS + 20, 150, 200, 6)
reset_button_rect = pygame.Rect(FIELD_PIXELS + 20, 180, 130, 28)
reset_pose_button_rect = pygame.Rect(FIELD_PIXELS + 170, 180, 130, 28)
auton_button_rect = pygame.Rect(FIELD_PIXELS + 20, 215, 280, 28)
field_image_button_rect = pygame.Rect(FIELD_PIXELS + 20, 255, 120, 26)
field_custom_button_rect = pygame.Rect(FIELD_PIXELS + 160, 255, 120, 26)
add_shape_button_rect = pygame.Rect(FIELD_PIXELS + 20, 320, 140, 26)
delete_shape_button_rect = pygame.Rect(FIELD_PIXELS + 180, 320, 120, 26)
add_shape_dropdown_rect = pygame.Rect(FIELD_PIXELS + 20, 350, 140, 24)

# Property inputs panel definitions
shape_panel_y = 390
#Example .rect(x-cord,y-cord,width,height)
textbox_x_rect = pygame.Rect(FIELD_PIXELS + 20, shape_panel_y + 20, 80, 22)#X-cord
textbox_y_rect = pygame.Rect(FIELD_PIXELS + 120, shape_panel_y + 20, 80, 22)#Y-cord
textbox_w_rect = pygame.Rect(FIELD_PIXELS + 20, shape_panel_y + 55, 80, 22)#Weight
textbox_h_rect = pygame.Rect(FIELD_PIXELS + 120, shape_panel_y + 55, 80, 22)#Height
textbox_r_rect = pygame.Rect(FIELD_PIXELS + 20, shape_panel_y + 55, 80, 22)#Radius
textbox_a_rect = pygame.Rect(FIELD_PIXELS + 20, shape_panel_y + 90, 80, 22)#Angle
textbox_m_rect = pygame.Rect(FIELD_PIXELS + 120, shape_panel_y + 55, 80, 22)#Mass
textbox_f_rect = pygame.Rect(FIELD_PIXELS + 120, shape_panel_y + 90, 80, 22)#Friction
textbox_e_rect = pygame.Rect(FIELD_PIXELS + 220, shape_panel_y + 90, 80, 22)#Elasticity

COLOR_PALETTE = [(150,150,150), (255,80,80), (80,80,255), (255,220,0), (80,200,120)]
color_button_rects = [pygame.Rect(FIELD_PIXELS + 20 + i*36, shape_panel_y + 130, 30, 30) for i in range(len(COLOR_PALETTE))]

shape_type_toggle_rect = pygame.Rect(FIELD_PIXELS + 120, shape_panel_y + 130, 180, 22)

# Robot Config Input definitions
robot_start_y = shape_panel_y + 180
robot_x_rect = pygame.Rect(FIELD_PIXELS + 20, robot_start_y + 20, 80, 22)
robot_y_rect = pygame.Rect(FIELD_PIXELS + 120, robot_start_y + 20, 80, 22)
robot_a_rect = pygame.Rect(FIELD_PIXELS + 20, robot_start_y + 55, 80, 22)
robot_save_rect = pygame.Rect(FIELD_PIXELS + 120, robot_start_y + 55, 130, 26)
robot_len_rect = pygame.Rect(FIELD_PIXELS + 220, robot_start_y + 20, 80, 22)
robot_wid_rect = pygame.Rect(FIELD_PIXELS + 220, robot_start_y + 55, 80, 22)

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
    if sim.settings["field_source"] == "custom":
        for i, s in enumerate(sim.shapes):
            if s["type"] == "rect":
                surf = pygame.Surface((s["w"] * SCALE, s["h"] * SCALE), pygame.SRCALPHA)
            
                current_phys = s.get("body_type", "static") #Defualting to static, can be changed
                
                surf.fill(s["color"])
                rot = pygame.transform.rotate(surf, s["angle"])
                rect = rot.get_rect(center=((s["x"] + s["w"]/2) * SCALE, FIELD_PIXELS - (s["y"] + s["h"]/2) * SCALE))
                screen.blit(rot, rect)
                if i == sim.selected_shape_idx: 
                    pygame.draw.rect(screen, YELLOW, rect, 2)
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

    # Robot Layer
    robot_surf = pygame.Surface((bot.length * SCALE, bot.track_width * SCALE), pygame.SRCALPHA)
    robot_surf.fill(CYAN if sim.current_mode == "drive" else ORANGE)
    pygame.draw.line(robot_surf, WHITE, (bot.length * SCALE - 2, 0), (bot.length * SCALE - 2, bot.track_width * SCALE), 4)
    rot_bot = pygame.transform.rotate(robot_surf, bot.angle)
    bot_rect = rot_bot.get_rect(center=(bot.x * SCALE, FIELD_PIXELS - bot.y * SCALE))
    screen.blit(rot_bot, bot_rect)
    if sim.current_mode == "edit": pygame.draw.rect(screen, YELLOW, bot_rect, 2)

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

    # Dynamic settings selectors indicators map
    pygame.draw.rect(screen, GREEN if sim.settings["drive_mode"] == "tank" else LIGHT_GRAY, drive_mode_tank_rect, border_radius=4)
    pygame.draw.rect(screen, GREEN if sim.settings["drive_mode"] == "arcade" else LIGHT_GRAY, drive_mode_arcade_rect, border_radius=4)
    pygame.draw.rect(screen, GREEN if sim.settings["drive_mode"] == "custom" else LIGHT_GRAY, drive_mode_custom_rect, border_radius=4)
    draw_small("Tank", drive_mode_tank_rect.x + 20, drive_mode_tank_rect.y + 5, BLACK)
    draw_small("Arcade", drive_mode_arcade_rect.x + 15, drive_mode_arcade_rect.y + 5, BLACK)
    draw_small("Custom", drive_mode_custom_rect.x + 15, drive_mode_custom_rect.y + 5, BLACK)

    pygame.draw.rect(screen, YELLOW if sim.settings["input_mode"] == "keyboard" else LIGHT_GRAY, keyboard_button_rect, border_radius=4)
    pygame.draw.rect(screen, YELLOW if sim.settings["input_mode"] == "controller" else LIGHT_GRAY, controller_button_rect, border_radius=4)
    draw_small("Keyboard", keyboard_button_rect.x + 8, keyboard_button_rect.y + 5, BLACK)
    draw_small("Controller", controller_button_rect.x + 5, controller_button_rect.y + 5, BLACK)

    # Slider Rendering
    pygame.draw.rect(screen, LIGHT_GRAY, slider_rect)
    t = max(0.0, min(1.0, (sim.settings["speed_scale"] - 0.3) / 1.2))
    pygame.draw.circle(screen, YELLOW, (slider_rect.x + int(t * slider_rect.width), slider_rect.y + 3), 8)
    draw_small(f"{sim.settings['speed_scale']:.2f}x", FIELD_PIXELS + 230, 135, LIGHT_GRAY)

    # Action buttons execution
    pygame.draw.rect(screen, (180, 60, 60), reset_button_rect, border_radius=4)
    pygame.draw.rect(screen, (80, 80, 180), reset_pose_button_rect, border_radius=4)
    pygame.draw.rect(screen, GREEN if not sim.auton_running else LIGHT_GRAY, auton_button_rect, border_radius=4)
    draw_small("Reset Robot", reset_button_rect.x + 15, reset_button_rect.y + 6, BLACK)
    draw_small("Reset Center", reset_pose_button_rect.x + 10, reset_pose_button_rect.y + 6, BLACK)
    draw_small("Run Autonomous", auton_button_rect.x + 80, auton_button_rect.y + 6, BLACK)

    pygame.draw.rect(screen, GREEN if sim.settings["field_source"] == "image" else LIGHT_GRAY, field_image_button_rect, border_radius=4)
    pygame.draw.rect(screen, GREEN if sim.settings["field_source"] == "custom" else LIGHT_GRAY, field_custom_button_rect, border_radius=4)
    draw_small("Image", field_image_button_rect.x + 30, field_image_button_rect.y + 4, BLACK)
    draw_small("Custom", field_custom_button_rect.x + 25, field_custom_button_rect.y + 4, BLACK)

    # Shapes and list property fields configuration parsing loop drawing
    pygame.draw.rect(screen, LIGHT_GRAY, add_shape_button_rect, border_radius=4)
    pygame.draw.rect(screen, (180,60,60), delete_shape_button_rect, border_radius=4)
    draw_small("Add Shape", add_shape_button_rect.x + 20, add_shape_button_rect.y + 5, BLACK)
    draw_small("Delete Shape", delete_shape_button_rect.x + 15, delete_shape_button_rect.y + 5, BLACK)

    pygame.draw.rect(screen, WHITE, add_shape_dropdown_rect, border_radius=4)
    draw_small(f"{'Rectangle' if sim.add_shape_type=='rect' else 'Circle'} ▼", add_shape_dropdown_rect.x + 6, add_shape_dropdown_rect.y + 4, BLACK)
    
    if sim.add_shape_dropdown_open:
        r_o = pygame.Rect(add_shape_dropdown_rect.x, add_shape_dropdown_rect.y + 24, add_shape_dropdown_rect.width, 24)
        c_o = pygame.Rect(add_shape_dropdown_rect.x, add_shape_dropdown_rect.y + 48, add_shape_dropdown_rect.width, 24)
        pygame.draw.rect(screen, WHITE, r_o); pygame.draw.rect(screen, WHITE, c_o)
        draw_small("Rectangle", r_o.x + 4, r_o.y + 4, BLACK); draw_small("Circle", c_o.x + 4, c_o.y + 4, BLACK)

    # Inspector Panel selection layout loop context mapping logic
    if sim.selected_shape_idx is not None and 0 <= sim.selected_shape_idx < len(sim.shapes):
        s = sim.shapes[sim.selected_shape_idx]
        current_phys = s.get("body_type", "static")
        
        if s["type"] == "rect":
            draw_textbox(textbox_x_rect, "X", sim.textbox_value if sim.active_textbox == "x" else f"{s['x']:.1f}", sim.active_textbox == "x")
            draw_textbox(textbox_y_rect, "Y", sim.textbox_value if sim.active_textbox == "y" else f"{s['y']:.1f}", sim.active_textbox == "y")
            draw_textbox(textbox_w_rect, "W", sim.textbox_value if sim.active_textbox == "w" else f"{s['w']:.1f}", sim.active_textbox == "w")
            draw_textbox(textbox_h_rect, "H", sim.textbox_value if sim.active_textbox == "h" else f"{s['h']:.1f}", sim.active_textbox == "h")
            draw_textbox(textbox_a_rect, "Angle", sim.textbox_value if sim.active_textbox == "a" else f"{s['angle']:.1f}", sim.active_textbox == "a")
        elif s["type"] == "circ":
            draw_textbox(textbox_x_rect, "Center X", sim.textbox_value if sim.active_textbox == "x" else f"{s['x']:.1f}", sim.active_textbox == "x")
            draw_textbox(textbox_y_rect, "Center Y", sim.textbox_value if sim.active_textbox == "y" else f"{s['y']:.1f}", sim.active_textbox == "y")
            draw_textbox(textbox_r_rect, "Radius", sim.textbox_value if sim.active_textbox == "r" else f"{s['radius']:.1f}", sim.active_textbox == "r")
            
        #Draw mass input box, only if dynamic
        if current_phys == "dynamic":
            m_val = s.get("mass", 1.0)
            draw_textbox(textbox_m_rect, "Mass (lbs)", sim.textbox_value if sim.active_textbox == "m" else f"{m_val:.1f}", sim.active_textbox == "m")
        # Draw Friction & Elasticity textboxes for all selected shapes
        f_val = s.get("friction", 0.5) #Grabbing value from dictionary, default to 0.5
        e_val = s.get("elasticity", 0.0)
        draw_textbox(textbox_f_rect, "Friction", sim.textbox_value if sim.active_textbox == "f" else f"{f_val:.2f}", sim.active_textbox == "f")
        draw_textbox(textbox_e_rect, "Bounce", sim.textbox_value if sim.active_textbox == "e" else f"{e_val:.2f}", sim.active_textbox == "e")
        
        for i, col in enumerate(COLOR_PALETTE):
            pygame.draw.rect(screen, col, color_button_rects[i])
            if col == s["color"]: pygame.draw.rect(screen, YELLOW, color_button_rects[i], 2)
                
        button_color = RED if current_phys == "static" else GREEN
        text_label = "STATIC (WALL)" if current_phys == "static" else "DYNAMIC (BALL)"
        
        pygame.draw.rect(screen, button_color, shape_type_toggle_rect, border_radius=4)
        draw_small(text_label, shape_type_toggle_rect.x + 10, shape_type_toggle_rect.y + 4, BLACK)
        draw_small("Physics Mode", shape_type_toggle_rect.x, shape_type_toggle_rect.y - 16, LIGHT_GRAY)
    else:
        draw_small("No shape selected", FIELD_PIXELS + 20, shape_panel_y + 25, LIGHT_GRAY)

    # Global teleop diagnostics metrics dashboard tracking
    rx, ry, ra = bot.start_pose
    draw_textbox(robot_x_rect, "Start X", sim.textbox_value if sim.active_textbox == "rx" else f"{rx:.1f}", sim.active_textbox == "rx")
    draw_textbox(robot_y_rect, "Start Y", sim.textbox_value if sim.active_textbox == "ry" else f"{ry:.1f}", sim.active_textbox == "ry")
    draw_textbox(robot_a_rect, "Start θ", sim.textbox_value if sim.active_textbox == "ra" else f"{ra:.1f}", sim.active_textbox == "ra")
    pygame.draw.rect(screen, GREEN, robot_save_rect, border_radius=4)
    draw_small("Save Start", robot_save_rect.x + 20, robot_save_rect.y + 5, BLACK)
    draw_textbox(robot_len_rect, "Chassis L", sim.textbox_value if sim.active_textbox == "rlen" else f"{bot.length:.1f}", sim.active_textbox == "rlen")
    draw_textbox(robot_wid_rect, "Chassis W", sim.textbox_value if sim.active_textbox == "rwid" else f"{bot.track_width:.1f}", sim.active_textbox == "rwid")

    # Diagnostics state indicators footer section labels mapping configurations block
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
        
        # Temporary "PAUSED" text indicator
        draw_text("PAUSED", WINDOW_WIDTH // 2 - 40, WINDOW_HEIGHT // 2, WHITE)
    pygame.display.flip()

# =====================================================================
# 6. ACTION INTERACTION ROUTINES (UI Click & Inputs Handler)
# =====================================================================
def handle_ui_click(mx, my):
    if mode_drive_button_rect.collidepoint(mx, my): 
        sim.current_mode = "drive"
        sync_custom_obstacles_to_physics() #Calling the physics body build
        return
    if mode_edit_button_rect.collidepoint(mx, my): sim.current_mode = "edit"; return
    if drive_mode_tank_rect.collidepoint(mx, my): sim.settings["drive_mode"] = "tank"; save_settings(); return
    if drive_mode_arcade_rect.collidepoint(mx, my): sim.settings["drive_mode"] = "arcade"; save_settings(); return
    if drive_mode_custom_rect.collidepoint(mx, my): sim.settings["drive_mode"] = "custom"; save_settings(); return
    if keyboard_button_rect.collidepoint(mx, my): sim.settings["input_mode"] = "keyboard"; save_settings(); return
    if controller_button_rect.collidepoint(mx, my): sim.settings["input_mode"] = "controller"; save_settings(); return
    if field_image_button_rect.collidepoint(mx, my): sim.settings["field_source"] = "image"; save_settings(); return
    if field_custom_button_rect.collidepoint(mx, my): sim.settings["field_source"] = "custom"; save_settings(); return

    if slider_rect.collidepoint(mx, my):
        sim.settings["speed_scale"] = 0.3 + ((mx - slider_rect.x) / slider_rect.width) * 1.2
        save_settings(); return
    if reset_button_rect.collidepoint(mx, my): bot.reset_to_start(); return
    if reset_pose_button_rect.collidepoint(mx, my): bot.reset_to_center(); return
    if auton_button_rect.collidepoint(mx, my) and not sim.auton_running: sim.auton_mode = True; return

    if add_shape_button_rect.collidepoint(mx, my):
        cx, cy = FIELD_INCHES / 2, FIELD_INCHES / 2
        if sim.add_shape_type == "rect":
            sim.shapes.append({"type": "rect", 
                               "x": cx - 6, "y": cy - 6, 
                               "w": 12, "h": 12, "angle": 0.0, 
                               "color": (150,150,150), 
                               "body_type": "static"})
        else:
            sim.shapes.append({"type": "circ", "x": cx, "y": cy, 
                               "radius": 6, 
                               "color": (150,150,150),
                               "body_type": "dynamic"})
        sim.selected_shape_idx = len(sim.shapes) - 1; save_field_data(); return

    if delete_shape_button_rect.collidepoint(mx, my):
        if sim.selected_shape_idx is not None: sim.shapes.pop(sim.selected_shape_idx); sim.selected_shape_idx = None; save_field_data(); return
    if add_shape_dropdown_rect.collidepoint(mx, my): sim.add_shape_dropdown_open = not sim.add_shape_dropdown_open; return

    if sim.add_shape_dropdown_open:
        if pygame.Rect(add_shape_dropdown_rect.x, add_shape_dropdown_rect.y + 24, add_shape_dropdown_rect.width, 24).collidepoint(mx, my): sim.add_shape_type = "rect"; sim.add_shape_dropdown_open = False; return
        if pygame.Rect(add_shape_dropdown_rect.x, add_shape_dropdown_rect.y + 48, add_shape_dropdown_rect.width, 24).collidepoint(mx, my): sim.add_shape_type = "circ"; sim.add_shape_dropdown_open = False; return

    # Drop textboxes selection processing checks blocks
    if sim.selected_shape_idx is not None:
        s = sim.shapes[sim.selected_shape_idx]
        
        if shape_type_toggle_rect.collidepoint(mx, my):
            if s.get("body_type", "static") == "static":
                s["body_type"] = "dynamic"
            else:
                s["body_type"] = "static"
            save_field_data()
            return
        #Detects when user is typing in mass input box, default to 1.0 if received no inputs    
        if textbox_m_rect.collidepoint(mx, my) and s.get("body_type") == "dynamic":
            sim.active_textbox = "m"
            sim.textbox_value = f"{s.get('mass', 1.0):.1f}"
            return
        if textbox_f_rect.collidepoint(mx, my):
            sim.active_textbox = "f"
            sim.textbox_value = f"{s.get('friction', 0.5):.2f}"
            return
        if textbox_e_rect.collidepoint(mx, my):
            sim.active_textbox = "e"
            sim.textbox_value = f"{s.get('elasticity', 0.0):.2f}"
            return
        
        if s["type"] == "rect":
            if textbox_x_rect.collidepoint(mx, my): sim.active_textbox = "x"; sim.textbox_value = f"{s['x']:.1f}"; return
            if textbox_y_rect.collidepoint(mx, my): sim.active_textbox = "y"; sim.textbox_value = f"{s['y']:.1f}"; return
            if textbox_w_rect.collidepoint(mx, my): sim.active_textbox = "w"; sim.textbox_value = f"{s['w']:.1f}"; return
            if textbox_h_rect.collidepoint(mx, my): sim.active_textbox = "h"; sim.textbox_value = f"{s['h']:.1f}"; return
            if textbox_a_rect.collidepoint(mx, my): sim.active_textbox = "a"; sim.textbox_value = f"{s['angle']:.1f}"; return
        elif s["type"] == "circ":
            if textbox_x_rect.collidepoint(mx, my): sim.active_textbox = "x"; sim.textbox_value = f"{s['x']:.1f}"; return
            if textbox_y_rect.collidepoint(mx, my): sim.active_textbox = "y"; sim.textbox_value = f"{s['y']:.1f}"; return
            if textbox_r_rect.collidepoint(mx, my): sim.active_textbox = "r"; sim.textbox_value = f"{s['radius']:.1f}"; return
        for i, rect in enumerate(color_button_rects):
            if rect.collidepoint(mx, my): s["color"] = COLOR_PALETTE[i]; save_field_data(); return

    if robot_x_rect.collidepoint(mx, my): sim.active_textbox = "rx"; sim.textbox_value = f"{bot.start_pose[0]:.1f}"; return
    if robot_y_rect.collidepoint(mx, my): sim.active_textbox = "ry"; sim.textbox_value = f"{bot.start_pose[1]:.1f}"; return
    if robot_a_rect.collidepoint(mx, my): sim.active_textbox = "ra"; sim.textbox_value = f"{bot.start_pose[2]:.1f}"; return
    if robot_save_rect.collidepoint(mx, my): save_field_data(); return
    if robot_len_rect.collidepoint(mx, my): sim.active_textbox = "rlen"; sim.textbox_value = f"{bot.length:.1f}"; return
    if robot_wid_rect.collidepoint(mx, my): sim.active_textbox = "rwid"; sim.textbox_value = f"{bot.track_width:.1f}"; return

#Save typed values into the shape dictionary/file
def apply_textbox_value(): 
    if sim.active_textbox is None: return
    try: val = float(sim.textbox_value)
    except: sim.active_textbox = None; return

    if sim.active_textbox in ("x","y","w","h","r","a","m", "f", "e") and sim.selected_shape_idx is not None:
        s = sim.shapes[sim.selected_shape_idx]
        if sim.active_textbox == "x": s["x"] = val
        elif sim.active_textbox == "y": s["y"] = val
        elif sim.active_textbox == "w" and s["type"] == "rect": s["w"] = max(1.0, val)
        elif sim.active_textbox == "h" and s["type"] == "rect": s["h"] = max(1.0, val)
        elif sim.active_textbox == "r" and s["type"] == "circ": s["radius"] = max(1.0, val)
        elif sim.active_textbox == "a" and s["type"] == "rect": s["angle"] = val
        elif sim.active_textbox == "m": s["mass"] = max(0.1, val)  # Prevent zero or negative mass
        elif sim.active_textbox == "f": s["friction"] = max(0.0, min(1.0,val)) #Prevent negative and limit between 0 and 1 (rubber)
        elif sim.active_textbox == "e": s["elasticity"] = max(0.0, min(1.0,val)) #Prevent negative and limit between 0 and 1 (max bounce)
        save_field_data()
    elif sim.active_textbox in ("rx","ry","ra"):
        rx, ry, ra = bot.start_pose
        if sim.active_textbox == "rx": rx = val
        elif sim.active_textbox == "ry": ry = val
        elif sim.active_textbox == "ra": ra = val
        bot.start_pose = (rx, ry, ra)
        save_field_data()
    elif sim.active_textbox == "rlen": bot.length = max(6.0, min(bot.max_size, val))
    elif sim.active_textbox == "rwid": bot.track_width = max(6.0, min(bot.max_size, val))
    sim.active_textbox = None

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
            if mx >= FIELD_PIXELS: handle_ui_click(mx, my)
            elif sim.current_mode == "edit":
                # Check robot drag focus
                dx, dy = mx - bot.x * SCALE, my - (FIELD_PIXELS - bot.y * SCALE)
                r_radius = max(bot.length, bot.track_width) * SCALE / 2 + 10
                if dx*dx + dy*dy <= r_radius*r_radius:
                    sim.dragging_robot = True
                    sim.robot_drag_offset_x = (mx / SCALE) - bot.x
                    sim.robot_drag_offset_y = ((FIELD_PIXELS - my) / SCALE) - bot.y
                else:
                    m_fx, m_fy = mx / SCALE, (FIELD_PIXELS - my) / SCALE
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

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if sim.dragging_robot: sim.dragging_robot = False; bot.start_pose = (bot.x, bot.y, bot.angle); save_field_data()
            if sim.dragging_shape: sim.dragging_shape = False; save_field_data()

        elif event.type == pygame.MOUSEMOTION and sim.current_mode == "edit":
            mx, my = event.pos
            m_fx, m_fy = mx / SCALE, (FIELD_PIXELS - my) / SCALE
            if sim.dragging_robot:
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
            # Global Pause Toggle (ESC Key)
            if event.key == pygame.K_ESCAPE:
                sim.paused = not sim.paused
            #Only process typing if NOT paused
            elif sim.active_textbox is not None and not sim.paused:
                if event.key == pygame.K_RETURN: apply_textbox_value()
                elif event.key == pygame.K_BACKSPACE: sim.textbox_value = sim.textbox_value[:-1]
                elif event.unicode.isdigit() or event.unicode in ".-": sim.textbox_value += event.unicode
            elif sim.current_mode == "edit" and sim.selected_shape_idx is not None and event.key == pygame.K_BACKSPACE:
                sim.shapes.pop(sim.selected_shape_idx); sim.selected_shape_idx = None; save_field_data()

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
