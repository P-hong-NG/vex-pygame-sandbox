import math
import time
import json

import pymunk


# Two dedicated collision tags so we can tell "player-blocker collision"
# apart from every other collision already happening in the sim
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

    COLLISION_TYPE_PLAYER = COLLISION_TYPE_PLAYER
    COLLISION_TYPE_BLOCKER = COLLISION_TYPE_BLOCKER

    # Difficulty presets: how aggressively the blocker pursues
    #Bot's speed/ how quicking blocker turns to bot/ how far into the future it predict user's movement
    DIFFICULTY_PRESETS = {
        "easy":   {"max_speed_in_per_s": 30.0, "turn_gain": 2.0, "lead_time": 0.15}, 
        "medium": {"max_speed_in_per_s": 45.0, "turn_gain": 3.0, "lead_time": 0.30},
        "hard":   {"max_speed_in_per_s": 60.0, "turn_gain": 4.0, "lead_time": 0.45},
    }

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

    def enable(self):
        if not self._added_to_space:
            self.space.add(self.body, self.shape)
            self._added_to_space = True
        self.enabled = True
        self._match_start_time = time.time()
        self.impacts.clear()
        self.mistakes.clear()
        self._recent_speed_history.clear()

    def disable(self):
        self.enabled = False
        if self._added_to_space:
            self.space.remove(self.body, self.shape)
            self._added_to_space = False

    def register_collision_handler(self):

        # Call once, after main.py's create_field_boundaries()/space setup.
        # Logs an "impact" every time the blocker and the player robot touch
        # Currently using PyMunk 7 version - change format if using a different version
        self.space.on_collision(
            COLLISION_TYPE_PLAYER, 
            COLLISION_TYPE_BLOCKER, 
            post_solve=self._on_impact
        )

    def _on_impact(self, arbiter, space, data):
        if not self.enabled:
            return
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

        self._track_player_speed(player_bot)

        # --- Predict where the player is heading (lead-point pursuit) ---
        rad = math.radians(player_bot.angle)
        # player_bot.current_speed is in in/s along its own heading
        lead_x = player_bot.x + math.cos(rad) * player_bot.current_speed * self.lead_time
        lead_y = player_bot.y + math.sin(rad) * player_bot.current_speed * self.lead_time

        dx = lead_x - self.x
        dy = lead_y - self.y
        dist = math.hypot(dx, dy)
        target_angle = math.degrees(math.atan2(dy, dx))

        # Shortest signed angle difference in [-180, 180]
        angle_diff = (target_angle - self.angle + 180) % 360 - 180

        # Proportional steering: turn hard when misaligned, drive straight when lined up
        omega = max(-180.0, min(180.0, angle_diff * self.turn_gain))

        # Slow down while turning sharply (mirrors how a real tank drive behaves),
        # and stop closing distance once basically on top of the player so it
        # "blocks" instead of just ramming through.
        alignment = max(0.0, 1.0 - abs(angle_diff) / 90.0)
        distance_factor = min(1.0, dist / 12.0)  # ease off inside ~1 ft
        forward_speed = self.max_speed * alignment * distance_factor

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

    def _track_player_speed(self, player_bot):
        now = self._elapsed()
        self._recent_speed_history.append((now, player_bot.current_speed))
        # Trim anything older than the rolling window
        cutoff = now - self._speed_history_window
        self._recent_speed_history = [(t, s) for (t, s) in self._recent_speed_history if t >= cutoff]

        # "Mistake" definition: speed was decent, then collapsed hard within
        # the rolling window, and there was a logged impact in that window.
        # This is intentionally simple -- it's meant to flag review-worthy
        # moments for the driver, not to be a precise physics judgement.
        if len(self._recent_speed_history) < 2:
            return
        peak_speed = max(s for (_, s) in self._recent_speed_history)
        if peak_speed < 5.0:
            return
        current = player_bot.current_speed
        if current < peak_speed * 0.3:
            recent_impact = any(now - imp["t"] < self._speed_history_window for imp in self.impacts)
            if recent_impact and not self._already_logged_recently(now):
                self.mistakes.append({
                    "t": round(now, 2),
                    "x": round(player_bot.x, 2),
                    "y": round(player_bot.y, 2),
                    "speed_before": round(peak_speed, 2),
                    "speed_after": round(current, 2),
                })

    def _already_logged_recently(self, now, window=1.0):
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
            gaps = [t2 - t1 for t1, t2 in zip(times, times[1:])]#?
            avg_gap = sum(gaps) / len(gaps)
        return {
            "elapsed_seconds": round(elapsed, 1),
            "impacts": n_impacts,
            "mistakes": n_mistakes,
            "avg_seconds_between_impacts": round(avg_gap, 2) if avg_gap else None,
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
