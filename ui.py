import pygame

# Initialize font module independently for the ui system
pygame.font.init()

# Define core ui colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
LIGHT_GRAY = (160, 160, 160)

# Define a dedicated font for ui elements
UI_FONT = pygame.font.SysFont("consolas", 14)

class UIElement:
    def __init__(self, x, y, w, h):
        # Local relative position inside the container
        self.local_rect = pygame.Rect(x, y, w, h)
        
        # Absolute screen position calculated every frame based on scrolling
        self.screen_rect = pygame.Rect(x, y, w, h)
        
        # Keep track of visibility and hover states
        self.is_hovered = False
        self.is_visible = True

    def update_position(self, offset_x, offset_y):
        # Calculate the actual screen coordinates when scrolled
        self.screen_rect.x = self.local_rect.x + offset_x
        self.screen_rect.y = self.local_rect.y + offset_y

    def handle_event(self, event, mx, my):
        # Blueprint method for child classes to handle clicks
        pass

    def draw(self, surface):
        # Blueprint method for child classes to draw themselves
        pass

class UIButton(UIElement):
    def __init__(self, x, y, w, h, text, default_color=LIGHT_GRAY, hover_color=WHITE, text_color=BLACK, action_callback=None):
        super().__init__(x, y, w, h)
        self.text = text
        self.default_color = default_color
        self.hover_color = hover_color
        self.text_color = text_color
        # The function to run when clicked
        self.action_callback = action_callback  
        
    def handle_event(self, event, mx, my):
        # Check if the mouse is hovering over the button
        self.is_hovered = self.screen_rect.collidepoint(mx, my)

        # Check if the left mouse button was clicked
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Trigger the action if hovered and a function exists
            if self.is_hovered and self.action_callback:
                self.action_callback()
                # Tell the system the click was handled successfully
                return True 
        return False

    def draw(self, surface):
        # Do not draw anything if the button is hidden
        if not self.is_visible: return
        
        # Draw the button background and border
        pygame.draw.rect(surface, self.default_color, self.screen_rect, border_radius=4)
        pygame.draw.rect(surface, BLACK, self.screen_rect, 1, border_radius=4)

        # Center the text exactly in the middle of the button
        text_surf = UI_FONT.render(self.text, True, self.text_color)
        text_rect = text_surf.get_rect(center=self.screen_rect.center)
        surface.blit(text_surf, text_rect)

class UITextbox(UIElement):
    def __init__(self, x, y, w, h, label, initial_value="", on_change_callback=None):
        super().__init__(x, y, w, h)
        self.label = label
        self.value = str(initial_value)
        self.is_active = False
        # Runs when the user hits the enter key
        self.on_change_callback = on_change_callback 

    def handle_event(self, event, mx, my):
        # Handle clicks to activate or deactivate the typing box
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.screen_rect.collidepoint(mx, my):
                self.is_active = True
                return True
            else:
                # Clicked outside so stop typing
                self.is_active = False 

        # Handle keyboard typing only if the box is currently active
        elif event.type == pygame.KEYDOWN and self.is_active:
            if event.key == pygame.K_RETURN:
                self.is_active = False
                # Save the new value when enter is pressed
                if self.on_change_callback:
                    self.on_change_callback(self.value) 
            elif event.key == pygame.K_BACKSPACE:
                self.value = self.value[:-1]
            elif event.unicode.isdigit() or event.unicode in ".-":
                self.value += event.unicode
            return True
        return False

    def draw(self, surface):
        # Do not draw anything if the textbox is hidden
        if not self.is_visible: return

        # Make the background white if typing or gray if idle
        bg_color = WHITE if self.is_active else LIGHT_GRAY
        pygame.draw.rect(surface, bg_color, self.screen_rect, border_radius=4)
        pygame.draw.rect(surface, BLACK, self.screen_rect, 1, border_radius=4)

        # Draw the title label slightly above the white box
        label_surf = UI_FONT.render(self.label, True, LIGHT_GRAY)
        surface.blit(label_surf, (self.screen_rect.x, self.screen_rect.y - 16))

        # Draw the actual typed letters inside the box
        value_surf = UI_FONT.render(self.value, True, BLACK)
        surface.blit(value_surf, (self.screen_rect.x + 4, self.screen_rect.y + 3))

class ScrollView(UIElement):
    def __init__(self, x, y, w, h):
        super().__init__(x, y, w, h)
        # List to hold all the buttons, textboxes, etc. inside this container
        self.children = []
        
        # Scrolling math variables
        self.scroll_y = 0
        self.scroll_speed = 20
        self.max_scroll = 0

    def add_child(self, element):
        """Adds a UI component to this container."""
        self.children.append(element)
        self._calculate_max_scroll()

    def _calculate_max_scroll(self):
        """Figures out how far down we are allowed to scroll based on the lowest item."""
        if not self.children:
            self.max_scroll = 0
            return
            
        # Find the bottom edge of the very last element in the list
        lowest_bottom = max([child.local_rect.bottom for child in self.children])
        
        # If the items don't fill the box, no scrolling needed.
        # If they overflow, the max scroll is the overflow amount.
        self.max_scroll = max(0, lowest_bottom - self.local_rect.height)

    def handle_event(self, event, mx, my):
        if not self.is_visible: return False

        # 1. Handle mouse wheel scrolling (only if the mouse is hovering over the menu)
        if self.screen_rect.collidepoint(mx, my):
            if event.type == pygame.MOUSEWHEEL:
                # event.y is 1 (scroll up) or -1 (scroll down)
                self.scroll_y += event.y * self.scroll_speed
                
                # Clamp the scrolling so we don't scroll into the void
                self.scroll_y = max(-self.max_scroll, min(0, self.scroll_y))
                return True

        # 2. Pass the event down to the children (buttons, textboxes)
        for child in self.children:
            # If a child handles the click, stop checking the others
            if child.handle_event(event, mx, my):
                return True
                
        return False

    def draw(self, surface):
        if not self.is_visible: return

        # Draw the main background for the menu panel
        pygame.draw.rect(surface, (35, 35, 45), self.screen_rect, border_radius=12)
        pygame.draw.rect(surface, (255, 220, 0), self.screen_rect, 2, border_radius=12) # Yellow border

        # Tell Pygame to ONLY draw things inside this specific rectangle
        old_clip = surface.get_clip()
        surface.set_clip(self.screen_rect)

        # Draw all the children, passing them their dynamic offset position
        for child in self.children:
            child.update_position(self.screen_rect.x, self.screen_rect.y + self.scroll_y)
            child.draw(surface)

        # Restore the original clipping boundaries so the rest of the game draws normally
        surface.set_clip(old_clip)

class UISlider(UIElement):
    def __init__(self, x, y, w, h, label, min_val, max_val, start_val, on_change_callback=None):
        super().__init__(x, y, w, h)
        self.label = label
        self.min_val = min_val
        self.max_val = max_val
        self.value = start_val #Current value
        # The function to run when the slider is dragged + released
        self.on_change_callback = on_change_callback
        self.is_dragging = False

    def handle_event(self, event, mx, my):
        # Updates the slider value on where user clicked with the left mouse button
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.screen_rect.collidepoint(mx, my):
                self.is_dragging = True
                self._update_value_from_mouse(mx)
                return True
                
        # Continuously updating the dot value so it follows the user's drag
        elif event.type == pygame.MOUSEMOTION:
            if self.is_dragging:
                self._update_value_from_mouse(mx)
                return True
                
        # Check if mouse button was released
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.is_dragging:
                self.is_dragging = False
                # Save the new setting when they let go
                if self.on_change_callback:
                    self.on_change_callback(self.value)
                return True
                
        return False

    def _update_value_from_mouse(self, mx):
        # Relative x-cords. rel_x = 50 means the mouse's location is 50 px right of the left side of slider
        rel_x = mx - self.screen_rect.x 
        # Force the percentage to stay between 0.0 and 1.0
        percentage = max(0.0, min(1.0, rel_x / self.screen_rect.width))
        # Convert that percentage into specific range (self.min_value and self.max_val)
        raw_value = self.min_val + (percentage * (self.max_val - self.min_val))
        self.value = round(raw_value, 2) # Keeping it clean
        # Update live while dragging
        if self.on_change_callback:
            self.on_change_callback(self.value)

    def draw(self, surface):
        if not self.is_visible: return
        
        # Draw the title label above the slider
        label_surf = UI_FONT.render(self.label, True, LIGHT_GRAY)
        surface.blit(label_surf, (self.screen_rect.x, self.screen_rect.y - 20))
        
        # Draw the gray track background
        pygame.draw.rect(surface, LIGHT_GRAY, self.screen_rect, border_radius=4)
        
        # Calculate exactly where the yellow handle dot should be
        percentage = (self.value - self.min_val) / (self.max_val - self.min_val)
        handle_x = self.screen_rect.x + int(percentage * self.screen_rect.width)
        
        # Draw the yellow handle circle
        pygame.draw.circle(surface, (255, 220, 0), (handle_x, self.screen_rect.centery), 8)
        
        # Draw the current number value to the right of the slider
        val_surf = UI_FONT.render(f"{self.value}x", True, LIGHT_GRAY)
        surface.blit(val_surf, (self.screen_rect.right + 10, self.screen_rect.y - 5))

class UIDropdown(UIElement):
    def __init__(self, x, y, w, h, options_list, start_index=0, on_change_callback=None):
        super().__init__(x, y, w, h)
        self.options = options_list
        self.selected_index = start_index
        # The function to run when a new option is picked
        self.on_change_callback = on_change_callback
        self.is_open = False
        # How tall each individual option box is, can be change
        self.option_height = 24

    def handle_event(self, event, mx, my):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # If the dropdown is currently open check if they clicked an option
            if self.is_open:
                # Loop through the options to see which one got clicked
                for i in range(len(self.options)):
                    # Create fake rectangle for the current option box in the loop for cords check
                    opt_rect = pygame.Rect(self.screen_rect.x, self.screen_rect.bottom + (i * self.option_height), self.screen_rect.width, self.option_height)
                    
                    if opt_rect.collidepoint(mx, my):
                        self.selected_index = i
                        self.is_open = False
                        # Save the new choice back to the main game
                        if self.on_change_callback:
                            self.on_change_callback(self.options[i])
                        return True
                        
                # If none of the options is clicked, means they clicked outside so close it
                self.is_open = False
                
                # Check if they actually clicked the main box again to close it
                if self.screen_rect.collidepoint(mx, my):
                    return True
                    
            else:
                if self.screen_rect.collidepoint(mx, my):
                    self.is_open = True
                    return True
                    
        return False

    def draw(self, surface):
        if not self.is_visible: return
        
        # Draw the main top box
        pygame.draw.rect(surface, WHITE, self.screen_rect, border_radius=4)
        pygame.draw.rect(surface, BLACK, self.screen_rect, 1, border_radius=4)
        
        # Draw the currently selected text and a down arrow
        current_text = self.options[self.selected_index]
        text_surf = UI_FONT.render(f"{current_text} ▼", True, BLACK)
        surface.blit(text_surf, (self.screen_rect.x + 6, self.screen_rect.y + 4))
        
        # If the menu is open draw all the options stacked below it
        if self.is_open:
            for i, option in enumerate(self.options):
                # Calculate where this specific box goes below the main box
                opt_y = self.screen_rect.bottom + (i * self.option_height)
                opt_rect = pygame.Rect(self.screen_rect.x, opt_y, self.screen_rect.width, self.option_height)
                
                # Draw the white background and black border for the option
                pygame.draw.rect(surface, WHITE, opt_rect)
                pygame.draw.rect(surface, BLACK, opt_rect, 1)
                
                # Draw the text inside the option box
                opt_surf = UI_FONT.render(option, True, BLACK)
                surface.blit(opt_surf, (opt_rect.x + 6, opt_rect.y + 4))
