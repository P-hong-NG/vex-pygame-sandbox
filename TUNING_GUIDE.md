# Tuning Guide

How to change how the robot, field, Blocker, and match feel. Most robot settings no longer need any code: open **Studio mode** and change them there. The numbers below are for things Studio doesn’t cover.

Tips before starting:
- Change one number at a time, then drive. If two things change together, you won’t know which one did it
- Search for the name (like `GRID_CELL_SIZE_IN`) instead of a line number, because line numbers move whenever the code changes
- Write down the old value before changing it, so it’s easy to go back

## 1. The robot

**Use Studio mode for these** (no code needed): size, wheel size, gear ratio, mass, motor cartridge (100, 200, or 600 rpm), and the intake and outtake settings. The sim recalculates the top speed when the gears or cartridge change.

**In `main.py`:**
- `self.length = 16.25` and `self.track_width = 14.5`: the starting chassis size in inches. Studio can change them while the sim runs. Real VEX robots must fit inside 18 inches, so keeping the length between 6 and 18 inches stays realistic
- `self.shape.friction = 0.3` (in the robot class): how much the chassis grips what it touches. It only matters during collisions, not normal driving. Raise it, and the robot sticks to walls and pieces. Lower it, and it slides along them
- `turn_multiplier = 40.0` (in the drive code): how quickly the robot turns. Higher values give snappier turns, and lower values give more careful ones. In-game, the “turn multiplier” slider in the Drive sidebar scales this number, so try the slider before editing code

## 2. The field and the floor

- **Floor grip (`3.0` in the line that makes `drag`):** how fast loose pieces and blocks slow down. Raise it and the field feels grippy, so pieces stop quickly. Lower it, and the field feels slippery, so pieces slide far. Example: at 3.0, a piece pushed once stops in a few inches, and at 1.0 it glides much further
- **`wall.friction = 0.5`:** how much walls drag on whatever scrapes along them
- **`wall.elasticity = 1.0`:** how bouncy the walls are. 1.0 bounces things back at full speed. Try 0.5 to 0.8 if you want walls to soak up some of the hit
- **Physics steps (`for _ in range(10): space.step(dt/10.0)`):** each frame is split into 10 small physics steps. Change both 10s together. If heavy objects slip through walls at high speed, try 15 or 20. If the sim lags on a slow computer, try 5. More steps mean better collisions but more work for the computer

## 3. The Blocker (`blocking_bot.py`)

### Difficulty (`DIFFICULTY_PRESETS`)
Each difficulty is a group of five numbers:
- `max_speed_in_per_s`: top speed. Easy 30, Medium 45, Hard 60
- `turn_gain`: how eagerly it turns toward you. Easy 2, Medium 3, Hard 4
- `lead_time`: how many seconds ahead it guesses where you’re going. Easy 0.15, Medium 0.30, Hard 0.50
- `stop_distance`: how close it stays, in inches. Easy 10, Medium 3, Hard -3. A negative number means it tries to drive into you
- `max_turn_rate_deg_per_s`: its fastest turn. Easy 140, Medium 180, Hard 220

Example: to make Medium a little meaner, raise its `lead_time` from 0.30 to 0.40, so it cuts you off sooner.

### Making it feel less like a script
- `DDA_OFFSET_RANGE = (0.9, 1.1)`: each life, the Blocker’s speed is set to your own average speed times a random number in this range. Widening it to `(0.8, 1.2)` makes it less predictable
- `MIN_BLOCKER_SPEED = 15.0` and `MIN_BLOCKER_TURN_RATE = 60.0`: floors, so a Blocker never gets too slow if you spent a while sitting still

### When it gets stuck
- `STUCK_CHECK_WINDOW_SECONDS = 2.0`: how far back it looks to see if it has made progress
- `STUCK_PROGRESS_THRESHOLD_IN = 6.0`: it decides it’s stuck if it moved less than this
- `STUCK_EXIT_PROGRESS_THRESHOLD_IN = 12.0`: it only decides it’s free again after moving this much. Keep this number bigger than the one above, or it will flip between stuck and not stuck over and over
- `STUCK_ESCAPE_BIAS_DEG = 15.0`: the small nudge it uses to turn away from a wall

### Following your trail (breadcrumbs)
- `BREADCRUMB_ARRIVAL_RADIUS_IN = 8.0`: how close it must get to a point on your trail before that point is counted as reached
- `BREADCRUMB_SWITCH_MARGIN_IN = 12.0`: a new point has to be at least this much closer before it switches targets. Raise it if the Blocker keeps changing its mind

### Planning (grid and A*)
- `GRID_CELL_SIZE_IN = 6.0`: size of one grid cell. Smaller cells find tighter gaps but take more computer work
- `GRID_REBUILD_INTERVAL_SECONDS = 0.5`: how often the grid is redrawn from the field. Lower is more up to date; higher runs faster
- `ASTAR_LOOKAHEAD_CELLS = 3`: how many cells ahead on the route it aims at. A bigger number gives smoother turns but cuts corners more

### Attacking and defending
- `RUSH_CLOSING_SPEED_IN_PER_S = 50.0`, `RUSH_TRIGGER_DIST_IN = 8.0`, `RUSH_BACKOFF_SPEED_FACTOR = 0.6`: if you drive at it fast and get close, it backs away at this fraction of its top speed instead of getting rammed
- `REVERSE_SPEED_FACTOR = 0.5`: how fast it drives backward, compared to forward
- `DEFEND_ENGAGE_RADIUS_IN = 40.0`: in Defend style, it only leaves its home spot when you come this close
- `MIX_PREDICT_SECONDS = 1.0`: in Mix style, how far ahead it guesses your movement

## 4. Match and scoring (`main.py`)

- `MATCH_AUTO_S = 15.0`, `MATCH_DRIVER_S = 105.0`, `MATCH_ENDGAME_S = 10.0`: the match is 15 seconds of auto, then 105 of driver, and the last 10 show as endgame. Change them for a game with different timing
- `POINTS_PER_PIECE = 5`, `POINTS_PER_YELLOW = 10`, `POINTS_PER_MIDFIELD_ROBOT = 8`: the score values for the Override game
- `MIDFIELD_HALF_IN = 24`: how far each point of the center diamond reaches from the middle of the field. 24 matches the official drawing, where the points sit on the tile line crossings. A bigger number makes the zone bigger
- `LOADER_REACH_IN = 36`: how close the robot has to park to a loader before **G** works
- `DESCORE_INTERVAL_S = 0.5`: how many seconds between each piece the intake takes back out of a goal
