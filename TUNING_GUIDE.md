Tuning and Configuration guide for VEX driving simulator

The simulator lets you customize robot specs, physics properties, driving behavior, and top-down floor dynamics directly in 'main.py'.

===Robot Physical Specs and Weights (~Lines 40-60)===
"self.length = 16.25": Set the robot chassis length, in inches. The legal range for VEX is 6.0 to 18.0 inches
"self.track_width = 14.5": Set the distance between the left and right wheels, in inches. Affects turn radius and arcade driving
"mass = 14.0": Set the total robot weight, in pounds (lbs). Heavier robots push obstacles easily (Higher moment) but take longer to accelerate
"self.shape.friction = 0.3": The wheels' grip friction against field obstacles during collision. Doesn't affect driving normally, only during collisions

===Driver/Robot Controls (~Lines 240)===
"turn_multiplier = 40.0": Scales turning responsiveness when driving. Increase (50, 60) for faster but snappy turns; decrease (25) for slower but more precise turns

===Top-down Field and Floor Settings (~Lines 250-300)===
"drag = max(0.0, 1.0 - (fric * 3.0 * dt))": Controls floor resistance for dynamic (movable) game pieces across tile surfaces.
(conti.) Increase the '3.0' constant to make field tiles grippy (objects stop quickly); decrease the constant to make the field slippery like ice (objects glide far)
"wall.friction = 0.5": Wall surface friction when robots or game pieces scrape along the field's walls
"wall.elasticity = 1.0": Bounciness multiplier for boundary walls. Keeping it at '1.0' allows dynamic game pieces to retain their custom bounce settings upon impact. 
(conti.) Lower it (0.5-0.8) if perimeter walls should absorb some energy. Bounce response = Bounce of incoming obstacles * Bounce of wall (1 being the bounciest)

===Physics Sub-stepping or Game Ticks for Lag Control(~Lines 260)===
"for _ in range(10):
     space.step(dt/10.0)": Divides frame physics calculations (Moving from point A to B when user drives) into 10 smaller micro-steps (like ticks and refresh rate).)
(conti.) Change BOTH numbers (10 and 10.0), increase to 15 or 20 if heavy objects are pushing through walls at high speed, reduce to 5 to reduce CPU usage
