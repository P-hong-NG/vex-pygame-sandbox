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

        # Choose the right color based on if the mouse is hovering
        current_color = self.hover_color if self.is_hovered else self.default_color
        
        # Draw the button background and border
        pygame.draw.rect(surface, current_color, self.screen_rect, border_radius=4)
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
