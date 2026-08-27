import math
import time
import json
import random

import pymunk


# Two dedicated collision tags so we can tell "player-blocker collision"
# apart from every other collision already happening in the sim
# Defined once here (outside the class, globally) so the numbers are easy to
# see and won't collide with new (global) tags as the file grows.
COLLISION_TYPE_PLAYER = 10
COLLISION_TYPE_BLOCKER = 11


class BlockingBot:
    """
    A second robot-like PyMunk body that chases/blocks the player.

    Usage from main.py:

        from blocking_bot import BlockingBot

        blocking_bot = BlockingBot(space, SCALE, FIELD_INCHES)
        bot.shape.collision_type = blocking_bot.COLLISION_TYPE_PLAYER  # tag the player shape once

        # inside update_physics(), only when enabled + drive mode + not paused:
        blocking_bot.update(bot, dt)

        # inside draw_everything(), after the player bot is drawn:
        blocking_bot.draw(screen, SCALE, FIELD_PIXELS)
    """


    # Aliasing: re-introduce constants above as class attributes, 
    # so main.py can reach/call them as BlockingBot.COLLISION_TYPE_PLAYER
    # without a separate import
    COLLISION_TYPE_PLAYER = COLLISION_TYPE_PLAYER
    COLLISION_TYPE_BLOCKER = COLLISION_TYPE_BLOCKER

    # Difficulty presets: how aggressively the blocker pursues
    #Bot's speed/ how quicking blocker turns to bot/ how far into the future it predict user's movement
    DIFFICULTY_PRESETS = {
        "easy":   {"max_speed_in_per_s": 30.0, "turn_gain": 2.0, "lead_time": 0.15, "stop_distance": 10.0}, 
        "medium": {"max_speed_in_per_s": 45.0, "turn_gain": 3.0, "lead_time": 0.30, "stop_distance": 3.0},
        "hard":   {"max_speed_in_per_s": 60.0, "turn_gain": 4.0, "lead_time": 0.50, "stop_distance": -3.0},
    }

    # --- DDA (Dynamic Difficulty Adjustment) constants ---
    # Roguelike-style variance, re-rolled each blocker "life": instead of a
    # fixed max_speed, scale off the PLAYER's own measured average speed
    # (main.py's Robot.update_performance_stats) so the blocker feels like
    # "roughly as fast as you've been driving, give or take" rather than a
    # flat number. See DEV_JOURNAL for the fuller reasoning (Crash Bandicoot/
    # Mario Kart DDA comparison, why randomized offset over strict rubber-banding).
    DDA_OFFSET_RANGE = (0.9, 1.1)  # random +/-10% variance around the baseline
    MIN_BLOCKER_SPEED = 15.0       # in/s floor -- guards against a near-stationary
                                   # blocker if the player's own sampled avg_speed
                                   # happened to be very low (e.g. mostly idle)

    # --- "Fully boxed in" escape constants ---
    BOXED_IN_CLEARANCE_THRESHOLD = 0.15  # below this even the "best" ray is
                                          # basically point-blank (~3.6in at a
                                          # 24in look_dist)
    STUCK_ESCAPE_BIAS_DEG = 15.0  # fixed, always-the-same-direction nudge off
                                  # dead-180 for a true last-resort reverse

    def __init__(self, space, scale, field_inches, difficulty="medium",
                 length=16.25, track_width=14.5, mass=14.0):
        self.space = space
        self.scale = scale
        self.field_inches = field_inches

        self.length = length
        self.track_width = track_width
        self.mass = mass

        self.enabled = False
        self.set_difficulty(difficulty)

        # Blocker will spawn in the left bottom quarter of the 144in by 144in field (36in out and 36in up from bottom left)
        # Can be changed to simulate where the opponent would be at the start of match (changing every year)
        self.x = field_inches * 0.25
        self.y = field_inches * 0.25
        self.angle = 0.0

        moment = pymunk.moment_for_box(self.mass, (length * scale, track_width * scale))
        self.body = pymunk.Body(self.mass, moment, body_type=pymunk.Body.DYNAMIC)
        self.body.position = (self.x * scale, self.y * scale)
        self.body.angle = math.radians(self.angle)

        self.shape = pymunk.Poly.create_box(self.body, (length * scale, track_width * scale))
        self.shape.friction = 0.3
        self.shape.collision_type = COLLISION_TYPE_BLOCKER

        # Bot starts OUT of the space until enabled
        self._added_to_space = False

        # --- data collection state ---
        self.impacts = []          # [{t, x, y, impulse}, ...]
        self.mistakes = []         # [{t, x, y, speed_before, speed_after}, ...]
        self._match_start_time = None
        self._recent_speed_history = []   # [(sim_time, player_speed), ...] short rolling window
        self._speed_history_window = 0.5  # seconds

    # ------------------------------------------------------------------
    # Setup / teardown
    # ------------------------------------------------------------------
    def set_difficulty(self, difficulty):
        preset = self.DIFFICULTY_PRESETS.get(difficulty, self.DIFFICULTY_PRESETS["medium"])
        self.difficulty = difficulty
        self.max_speed = preset["max_speed_in_per_s"]
        self.turn_gain = preset["turn_gain"]
        self.lead_time = preset["lead_time"]
        self.stop_distance = preset["stop_distance"]

    def enable(self, player_bot=None):
        if not self._added_to_space:
            self.space.add(self.body, self.shape)
            self._added_to_space = True
        self.enabled = True
        self._match_start_time = time.time()
        self.impacts.clear()
        self.mistakes.clear()
        self._recent_speed_history.clear()
        self._roll_dda_stats(player_bot)

    def _roll_dda_stats(self, player_bot):
        """
        Called once per "life" (each time enable() runs). Re-rolls this
        life's max_speed off the PLAYER's own measured average speed, plus
        a randomized +/-10% offset -- so the blocker isn't a fixed number,
        it's "roughly as fast as you've been driving lately, give or take."

        Falls back to the difficulty preset's max_speed if we don't have
        trustworthy player data yet (player_bot is None, or main.py's
        has_enough_stats is still False early in a session) -- this is the
        "cold start" case.

        turn_gain/lead_time/stop_distance are left at their difficulty-preset
        values for now. turn_gain in particular isn't a direct unit match to
        the player's avg_turn_rate (deg/s vs. a steering-gain constant), so
        scaling it needs its own normalization decision -- doing that as a
        separate, later step rather than guessing at a conversion here.
        """
        if player_bot is not None and getattr(player_bot, "has_enough_stats", False):
            baseline_speed = player_bot.avg_speed
        else:
            baseline_speed = self.DIFFICULTY_PRESETS[self.difficulty]["max_speed_in_per_s"]

        offset = random.uniform(*self.DDA_OFFSET_RANGE)
        self.max_speed = max(self.MIN_BLOCKER_SPEED, baseline_speed * offset)

        # Kept around for the end-of-session report/debug HUD -- lets a
        # reader see what this life's blocker was actually scaled to, and
        # off of what baseline, instead of just a final number with no context.
        self.dda_baseline_speed = baseline_speed
        self.dda_offset = offset

    def disable(self):
        self.enabled = False
        if self._added_to_space:
            self.space.remove(self.body, self.shape)
            self._added_to_space = False

    def register_collision_handler(self):

        # Call once, after main.py's create_field_boundaries()/space setup.
        # Logs an "impact" every time the blocker and the player robot touch
        # Currently using PyMunk 7 version - change format if using a different version
        # post_solve=: run _on_impact() right after PyMunk resolves a collision
        # between these two tags, so we always have final, saved contact data 
        # (not a collision that got cancelled/ignored earlier)
        self.space.on_collision(
            COLLISION_TYPE_PLAYER, 
            COLLISION_TYPE_BLOCKER, 
            post_solve=self._on_impact
        )

    def _on_impact(self, arbiter, space, data):
        if not self.enabled:
            return
        # arbiter = PyMunk's data object for this specific collision.
        # .total_impulse = a vector; .length turns it into one number 
        # ()"how hard" the hit was, regardless of direction) for logging
        impulse = arbiter.total_impulse.length
        sim_time = self._elapsed()
        self.impacts.append({
            "t": round(sim_time, 2),
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "impulse": round(impulse, 2),
        })

    def _elapsed(self):
        if self._match_start_time is None:
            return 0.0
        return time.time() - self._match_start_time

    # ------------------------------------------------------------------
    # Per-frame update
    # ------------------------------------------------------------------
    def update(self, player_bot, dt):
        # player_bot: the existing Robot instance from main.py (needs
        # .x, .y, .angle (degrees), .current_speed, .body.velocity)
        
        if not self.enabled:
            return

        if not hasattr(self, '_prev_player_x'):
            self._prev_player_x = player_bot.x
            self._prev_player_y = player_bot.y

        # Calculate real inches moved per sec based on physical changes
        if dt > 0:
            true_vx = (player_bot.x - self._prev_player_x) / dt
            true_vy = (player_bot.y - self._prev_player_y) / dt
        else:
            true_vx, true_vy = 0.0, 0.0

        true_speed = math.hypot(true_vx, true_vy)

        # Save current position to use in the next tick
        self._prev_player_x = player_bot.x
        self._prev_player_y = player_bot.y

        self._track_player_speed(player_bot, true_speed)

        # Predict based entirely on actual physical (in-field) values
        self.lead_x = player_bot.x + (true_vx * self.lead_time)
        self.lead_y = player_bot.y + (true_vy * self.lead_time)

        #=========================Rays & LiDAR section=================================
        num_rays = 7 # number of rays casted

        spread_deg = 15.0 # degrees between each laser
        look_dist = 24.0 * self.scale

        # Calculate the starting angle offset so the rays are centered
        start_offset = -((num_rays - 1) / 2) * spread_deg 
        
        vision_array = []
        clearance_array = []  # per-ray "how much room" (0=touching, 1=clear to look_dist) --
                               # kept even for blocked rays (prototype - not consumed yet)
        self.ray_lines = [] # Save the lines/bring up the scope
        
        for i in range(num_rays):
            # Calculate the specific angle for current ray
            offset_rad = math.radians(start_offset + (i * spread_deg))
            ray_angle = math.radians(self.angle) + offset_rad
            
            direction = pymunk.Vec2d(math.cos(ray_angle), math.sin(ray_angle))
            
            # Start right at the robot's own rectangular edge for THIS ray's
            # angle, not one fixed circle radius for every ray. The old
            # version used the diagonal-to-corner distance for every ray,
            # which is correct for the angled rays but leaves a real gap
            # (~2.76in for this chassis) in front of the straight-ahead ray,
            # since it's not actually a corner - a thin obstacle sitting in
            # that gap would never get seen, since a ray can't detect
            # anything behind where it starts.
            half_length = self.length / 2
            half_width = self.track_width / 2
            cos_a = abs(math.cos(offset_rad))
            sin_a = abs(math.sin(offset_rad))
            edge_candidates = []
            if cos_a > 1e-9:
                edge_candidates.append(half_length / cos_a)
            if sin_a > 1e-9: #Make sure not divide by 0
                edge_candidates.append(half_width / sin_a)
            box_edge_dist = min(edge_candidates) if edge_candidates else half_length
            bumper_offset = (box_edge_dist + 0.5) * self.scale
            
            start_pt = self.body.position + (direction * bumper_offset)
            end_pt = start_pt + (direction * look_dist)
            hit_info = self.space.segment_query_first(start_pt, end_pt, 1.0, pymunk.ShapeFilter())
            
            hit_status = 0 # Default to 0 (0 - clear path; 1 - obstructed path)
            clearance = 1.0  # 1.0 = fully clear to look_dist, same default as "no hit"
            
            if hit_info:
                hit_shape = hit_info.shape
                # Ignore the driving bodies (blocker + user)
                if hit_shape != self.shape and hit_shape.collision_type != self.COLLISION_TYPE_PLAYER:
                    hit_status = 1 # (Obstacle detected)
                    clearance = hit_info.alpha  # 0 (touching) to 1 (hit right at look_dist)
            
            vision_array.append(hit_status)
            clearance_array.append(clearance)
            self.ray_lines.append((start_pt, end_pt, hit_status)) # Save for drawing
            
        #print(vision_array) 

        center_ray_index = num_rays // 2 #Floor division so always int
        middle_hits = vision_array[center_ray_index-1] + vision_array[center_ray_index] + vision_array[center_ray_index+1]

        # Slowing the blocker down to 30% speed when the front rays detect an obstacle
        if middle_hits == 3:
            obstacle_brake = 0.3    # Down 70%
        elif middle_hits == 2:
            obstacle_brake = 0.55   # Down 45%
        elif middle_hits == 1:
            obstacle_brake = 0.80   # Down 20%
        else:
            obstacle_brake = 1.0    

        # math.hypot and not sqrt(dx**2 + dy**2): same returned distance, but more
        # numerically stable at very small values (plus cleaner format)
        dx = self.lead_x - self.x
        dy = self.lead_y - self.y
        dist = math.hypot(dx, dy)

        # Normalizing (from 0 to 1 - meaning 1 is max speed and 0 is none)
        if dist > 0: 
            dx /= dist
            dy /= dist

        user_angle = math.degrees(math.atan2(dy, dx)) # Return -180 to 180
        relative_player_angle = (user_angle - self.angle + 180) % 360 - 180

        safe_dx = 0.0
        safe_dy = 0.0
        clear_paths = 0

        # Loop through the array and add up the directions of all the safe "0" rays
        for i, status in enumerate(vision_array):
            if status == 0:  
                ray_offset_deg = start_offset + (i * spread_deg)
                ray_angle = math.radians(self.angle + ray_offset_deg)

                weight = 1.0
                # If the ray is on the same side as the player, increase weight to 1.5
                # Priorities turning toward the side of user
                if (ray_offset_deg > 0 and relative_player_angle > 0) or (ray_offset_deg < 0 and relative_player_angle < 0):
                    weight = 1.5

                safe_dx += math.cos(ray_angle) * weight
                safe_dy += math.sin(ray_angle) * weight
                clear_paths += 1

        if 1 in vision_array and clear_paths > 0:
            escape_mag = math.hypot(safe_dx, safe_dy)
            # Normalizing (0-to-1 scale)

            safe_dx /= escape_mag
            safe_dy /= escape_mag

            final_dx = (dx * 0.3) + (safe_dx * 0.7)
            final_dy = (dy * 0.3) + (safe_dy * 0.7)

        elif clear_paths == 0:
            # Every ray reads "blocked" within look_dist -- but "blocked"
            # isn't the same as "equally blocked." Uses the clearance data
            # from the ray loop above to head toward whichever ray has the
            # most room, instead of always reversing.
            best_idx = clearance_array.index(max(clearance_array))
            best_clearance = clearance_array[best_idx]

            if best_clearance < self.BOXED_IN_CLEARANCE_THRESHOLD:
                # Even the best direction is basically point-blank (every
                # way is genuinely boxed in) -- true last resort: reverse.
                # Reversing exactly 180deg from self.angle is numerically
                # unstable (floating-point noise in the cos/sin/atan2
                # round-trip can land at just-under +180 one frame and
                # just-under -180 the next, flipping the turn direction
                # every tick and never actually completing it -- this was
                # the "won't turn around" bug). A small, ALWAYS-the-same-
                # direction bias breaks that tie deterministically instead
                # of leaving it to floating-point chance.
                escape_angle = math.radians(self.angle + 180 + self.STUCK_ESCAPE_BIAS_DEG)
            else:
                best_offset_deg = start_offset + (best_idx * spread_deg)
                escape_angle = math.radians(self.angle + best_offset_deg)

            final_dx = math.cos(escape_angle)
            final_dy = math.sin(escape_angle)

        else:
            final_dx = dx
            final_dy = dy
            
        # Convert the final blended vector back into an angle for the steering wheel
        target_angle = math.degrees(math.atan2(final_dy, final_dx))

        # Shortest signed angle difference in [-180, 180]
        # displacement = target_angle - self.angle: the heading the blocker
        # WANT minus the heading it currently HAS (angles, not positions)
        # "Wrapping" it into [-180, 180] stops the bot from ever turning the "wrong way"
        angle_diff = (target_angle - self.angle + 180) % 360 - 180
        # Proportional steering: turn hard when misaligned, drive straight when lined up
        omega = max(-180.0, min(180.0, angle_diff * self.turn_gain))

        # Slow down while turning sharply (mirrors how a real tank drive behaves),
        # and stop closing distance once basically on top of the player so it
        # "blocks" instead of just ramming through.
        alignment = max(0.0, 1.0 - abs(angle_diff) / 90.0)
        # Measure from bumper to bumper (not .x and .y that is in the bot or blocker)
        bumper_dist = max(0.0, dist - (player_bot.length / 2 + self.length / 2) - self.stop_distance)
        distance_factor = min(1.0, bumper_dist / 12.0) 

        forward_speed = self.max_speed * alignment * distance_factor * obstacle_brake

        self.body.angular_velocity = math.radians(omega)
        heading = math.radians(self.angle)
        self.body.velocity = (
            forward_speed * math.cos(heading) * self.scale,
            forward_speed * math.sin(heading) * self.scale,
        )

        # Note: self.x/self.y/self.angle are NOT updated here. Call
        # sync_from_physics() AFTER space.step() runs (same ordering
        # main.py already uses for the player robot), otherwise this
        # bot's steering next frame would be based on stale position.

    def sync_from_physics(self):
        """Call once per frame, right after space.step(), mirroring how
        main.py pulls bot.x/bot.y/bot.angle back from bot.body."""
        if not self.enabled:
            return
        self.x = self.body.position.x / self.scale
        self.y = self.body.position.y / self.scale
        self.angle = math.degrees(self.body.angle)

    def _track_player_speed(self, player_bot, true_speed):
        now = self._elapsed()

        #Log physical speed (not inputed) in inches/sec
        self._recent_speed_history.append((now, true_speed))

        # Trim anything older than the rolling window. Without it, 
        # the list would grow every tick for the whole session. Keeping only
        # the last 0.5s of (time, speed) pairs keeps it small and fast
        # to scan for the "significant speed change" check below
        cutoff = now - self._speed_history_window
        self._recent_speed_history = [(t, s) for (t, s) in self._recent_speed_history if t >= cutoff]

        # "Mistake" definition: speed was decent, then collapsed hard within
        # the rolling window, and there was a logged impact in that window.
        # This is intentionally simple, it's meant to flag review-worthy
        # moments for the driver, not to be a precise physics judgement
        if len(self._recent_speed_history) < 2:
            return
        peak_speed = max(s for (_, s) in self._recent_speed_history)
        if peak_speed < 5.0:
            return
        
        if true_speed < peak_speed * 0.3:
            recent_impact = any(now - imp["t"] < self._speed_history_window for imp in self.impacts)
            if recent_impact and not self._already_logged_recently(now):
                self.mistakes.append({
                    "t": round(now, 2),
                    "x": round(player_bot.x, 2),
                    "y": round(player_bot.y, 2),
                    "speed_before": round(peak_speed, 2),
                    "speed_after": round(true_speed, 2),
                })

    def _already_logged_recently(self, now, window=1.0):
        # any(...) returns True the moment ONE mistake in the list is recent
        # enough. Stopping the same collision from getting logged as a
        # separate "mistake" on every tick for 60 ticks/sec while the
        # player is still slowed down from it.
        return any(now - m["t"] < window for m in self.mistakes)

    # ------------------------------------------------------------------
    # Feedback / reporting
    # ------------------------------------------------------------------
    def get_summary(self):
        n_impacts = len(self.impacts)
        n_mistakes = len(self.mistakes)
        elapsed = self._elapsed()
        avg_gap = None
        if n_impacts >= 2:
            times = [imp["t"] for imp in self.impacts]
            # Pairwise trick: zip(times, times[1:]) lines up each impact
            # time with the one right after it -[(6,17),(17,25),(25,31)]-
            # so the gap between consecutive hits is one subtraction each,
            # no manual indexing (aka for loops).
            gaps = [t2 - t1 for t1, t2 in zip(times, times[1:])]#?
            avg_gap = sum(gaps) / len(gaps)
        return {
            "elapsed_seconds": round(elapsed, 1),
            "impacts": n_impacts,
            "mistakes": n_mistakes,
            "avg_seconds_between_impacts": round(avg_gap, 2) if avg_gap else None,
            "dda_baseline_speed": round(getattr(self, "dda_baseline_speed", 0.0), 1),
            "dda_offset": round(getattr(self, "dda_offset", 1.0), 2),
            "max_speed": round(self.max_speed, 1),
        }

    def save_report(self, path):
        report = {
            "difficulty": self.difficulty,
            "summary": self.get_summary(),
            "impacts": self.impacts,
            "mistakes": self.mistakes,
        }
        with open(path, "w") as f:
            json.dump(report, f, indent=2)#?
        return report

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def draw(self, screen, scale, field_pixels):
        if not self.enabled:
            return
        import pygame

        w_px = self.length * scale
        h_px = self.track_width * scale
        surf = pygame.Surface((w_px, h_px), pygame.SRCALPHA)
        surf.fill((255, 60, 60, 200))
        pygame.draw.rect(surf, (120, 0, 0), (0, 0, w_px, h_px), 2)

        rot = pygame.transform.rotate(surf, self.angle)
        center_x = self.x * scale
        center_y = field_pixels - (self.y * scale)
        rect = rot.get_rect(center=(center_x, center_y))
        screen.blit(rot, rect)

        if hasattr(self, 'lead_x') and hasattr(self, 'lead_y'):
            start_pos = (center_x, center_y)
            target_px_x = self.lead_x * scale
            target_px_y = field_pixels - (self.lead_y * scale)
            end_pos = (target_px_x, target_px_y)
            
            # Red Line of Sight and Blue Target Circle
            pygame.draw.line(screen, (255, 100, 100), start_pos, end_pos, 2)
            pygame.draw.circle(screen, (100, 200, 255), end_pos, 8, 2)

        if hasattr(self, 'ray_lines'):
            for start_pt, end_pt, hit_status in self.ray_lines:
                # Convert PyMunk coordinates to Pygame pixels (and flip the Y-axis)
                sx = start_pt.x
                sy = field_pixels - start_pt.y
                ex = end_pt.x
                ey = field_pixels - end_pt.y
                
                # Draw Red if it hit something (1), Yellow if clear (0)
                color = (255, 60, 60) if hit_status == 1 else (255, 255, 0)
                pygame.draw.line(screen, color, (sx, sy), (ex, ey), 2)
