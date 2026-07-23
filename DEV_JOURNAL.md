This Dev's journal documents my ideas and initial designs/thoughts for the VEX driving simulator I'm working on in "main.py".
For instructions on how to use and improve the simulator, go to "TUNING_GUIDE.md"

Engineering Log: Architectural Design Decisions

[July 18, 2026] - Shifting to PyMunk Rigid-Body Physics (This is transferred from the "README.md" to clean up the README space)

===The Problem=== In the legacy version of the simulator, the robot chassis boundaries were locked using manual coordinate clamping (bot.x = max(...)). This created a major bug where the corners of the chassis would clip straight into the walls. When driving into a barrier at an angle, the corner would get stuck and slide upward instead of showing realistic physics behavior—like taking the impact force at that specific angle and swinging the robot around to face the wall flatly.

===Brainstorming & Solutions=== I looked into two different ways to use PyMunk to handle these corner collisions and bring in realistic mechanics:
_ 1. Raw Force Model (Independent Left/Right Drivetrain Forces): Pushing the robot by applying raw forces to the left and right sides individually. While this sounds highly realistic, a top-down simulation view can create the impression that the robot drifts endlessly because no tire-friction forces are calculated. Fixing this would require massive custom math equations every single frame to keep track of directions and counter-forces.
_ 2. Velocity-Controlled Two-Wheel Bridge (Chosen Strategy): Instead of raw forces, we compute the robot's linear and angular velocities from the controller inputs and feed these vectors directly into a dynamic PyMunk body every frame.

===Why Option 2 Wins=== After digging into PyMunk's documentation and seeing what the library can do, I naturally landed on Option 2. It lets PyMunk handle the heavy math under the hood rather than forcing me to track independent directional forces every frame for Option 1 manually:
_Natural Rotational Torque: When hitting a wall at a 45-degree angle, PyMunk's internal collision solver calculates an instant impulse force right on the hitting corner. Because this force acts away from the center of mass, it naturally counteracts the chassis' speed and pivots the robot flat against the wall, mimicking how a real VEX drivetrain would interact with the field's walls. 
_No Drifting: It completely bypasses the drifting bug. The moment the driver releases the joysticks to zero, the velocity drops to zero, giving the robot snappy, realistic traction on the field tiles, rather than Option 1, where individual calculations try to adjust forces and create more room for error.

[July 23, 2026] - Planning and sketching for the next steps of the simulator

===Personal Comments and an Unexpected Problem=== Now that the simulator has gotten the basic physics, like ball collisions, non-movable walls, realistic friction and energy loss upon impact, objects having mass and momentum (how hard to accelerate), it can be used as a practice simulator for driving and maneuvering around the current year's game layout. But a new problem came: this simulator would be great for last year's game when the idea for the simulator started -"Push-Back" requires a lot of defending and movement for de-scores, along with a "perfect" auton-run to ensure control - but this year (according to my personal judgment) requires a lot more tactics and robot percision which depends more on the actual robot design. The current simulator doesn't have many abilities to create a "mock" practice run, like picking and dropping pins, rolling bars, and having other bots compete for the middle spot; I realized that the simulator would need to be more customizable to match the yearly game changes. Thus, I brainstormed sketches for a better (more control and options) simulator that would feel like an actual game so that a new team, which doesn't have someone to understand the code, can still use the sim to its full potential.

===Sketches for future simulator (that would be turned into a "game" rather than "sim")===
![image_alt](https://github.com/P-hong-NG/vex-pygame-sandbox/blob/afd79e4021666a3b664198f5896ab660910e8dd5/IMG_0195.jpg)

