# vex-pygame-sandbox
A 2D driving simulator built in Python using Pygame and PyMunk to test movement physics and practice driving or matches.

Engineering Log: Architectural Design Decisions

[July 18, 2026] - Shifting to PyMunk Rigid-Body Physics

---The Problem---
In the legacy version of the simulator, the robot chassis boundaries were locked using manual coordinate clamping (`bot.x = max(...)`). This created a major bug where the corners of the chassis would clip straight into the walls. When driving into a barrier at an angle, the corner would get stuck and slide upward instead of showing realistic physics behavior—like taking the impact force at that specific angle and swinging the robot around to face the wall flatly.

---Brainstorming & Solutions---
I looked into two different ways to use PyMunk to handle these corner collisions and bring in realistic mechanics:

_ 1. Raw Force Model (Independent Left/Right Drivetrain Forces): Pushing the robot by applying raw forces to the left and right sides individually. While this sounds highly realistic, a top-down simulation view can create the impression that the robot drifts endlessly because no tire-friction forces are calculated. Fixing this would require massive custom math equations every single frame just to keep track of directions and counter-forces.
_ 2. Velocity-Controlled Two-Wheel Bridge (Chosen Strategy): Instead of raw forces, we compute the robot's linear and angular velocities from the controller inputs and feed these vectors directly into a dynamic PyMunk body every frame. 

---Why Option 2 Wins---
After digging into PyMunk’s documentation and seeing what the library can do, I naturally landed on Option 2. It lets PyMunk handle the heavy math under the hood rather than forcing me to manually track independent directional forces every frame for Option 1. 

_Natural Rotational Torque: When hitting a wall at a 45-degree angle, PyMunk's internal collision solver calculates an instant impulse force right on the hitting corner. Because this force acts away from the center of mass, it naturally counteracts the chassis' speed and pivots the robot flat against the wall, mimicking how a real VEX drivetrain would interact with the field’s walls.
_No Drifting: It completely bypasses the drifting bug. The moment the driver releases the joysticks to zero, the velocity drops to zero, giving the robot snappy, realistic traction on the field tiles, rather than Option 1, where individual calculations try to adjust forces and create more room for error.
