"""
CNC Simulator using Tkinter
Realistic animated drawing with configurable speed
"""

import tkinter as tk
from math import cos, sin, pi, sqrt
import time

class CNC:
    def __init__(self, width=800, height=600, title="CNC Simulator", 
                 x_range=(-10, 10), y_range=(-10, 10), grid=True, 
                 speed=10.0, draw_delay=0.5):
        """
        Initialize CNC canvas
        
        Parameters:
        - width, height: Canvas size in pixels
        - title: Window title
        - x_range: (min, max) for x-axis in real coordinates
        - y_range: (min, max) for y-axis in real coordinates
        - grid: Show grid lines
        - speed: Drawing speed in units/second
        - draw_delay: Time to draw each segment in seconds (overrides speed if set)
        """
        # Create window
        self.root = tk.Tk()
        self.root.title(title)
        
        # Canvas setup
        self.width = width
        self.height = height
        self.canvas = tk.Canvas(self.root, width=width, height=height, bg='white')
        self.canvas.pack()
        
        # Coordinate system
        self.x_min, self.x_max = x_range
        self.y_min, self.y_max = y_range
        
        # Scaling factors
        self.x_scale = width / (self.x_max - self.x_min)
        self.y_scale = height / (self.y_max - self.y_min)
        
        # Drawing settings
        self.speed = speed  # units per second
        self.draw_delay = draw_delay  # fixed delay per segment
        
        # Tool position (red dot)
        self.current_x = 0
        self.current_y = 0
        self.tool_marker = None
        
        # Animation queue
        self.animation_queue = []
        self.is_animating = False
        
        # Draw grid and axes
        if grid:
            self._draw_grid()
        self._draw_axes()
        
        # Draw initial tool position
        self._update_tool_position()
    
    def _to_canvas_coords(self, x, y):
        """Convert real coordinates to canvas pixel coordinates"""
        canvas_x = (x - self.x_min) * self.x_scale
        canvas_y = self.height - (y - self.y_min) * self.y_scale
        return canvas_x, canvas_y
    
    def _draw_grid(self):
        """Draw grid lines"""
        # Vertical grid lines
        x_step = (self.x_max - self.x_min) / 10
        for i in range(11):
            x = self.x_min + i * x_step
            x1, y1 = self._to_canvas_coords(x, self.y_min)
            x2, y2 = self._to_canvas_coords(x, self.y_max)
            self.canvas.create_line(x1, y1, x2, y2, fill='lightgray', dash=(2, 4))
        
        # Horizontal grid lines
        y_step = (self.y_max - self.y_min) / 10
        for i in range(11):
            y = self.y_min + i * y_step
            x1, y1 = self._to_canvas_coords(self.x_min, y)
            x2, y2 = self._to_canvas_coords(self.x_max, y)
            self.canvas.create_line(x1, y1, x2, y2, fill='lightgray', dash=(2, 4))
    
    def _draw_axes(self):
        """Draw x and y axes"""
        # X-axis
        x1, y1 = self._to_canvas_coords(self.x_min, 0)
        x2, y2 = self._to_canvas_coords(self.x_max, 0)
        self.canvas.create_line(x1, y1, x2, y2, fill='black', width=2)
        
        # Y-axis
        x1, y1 = self._to_canvas_coords(0, self.y_min)
        x2, y2 = self._to_canvas_coords(0, self.y_max)
        self.canvas.create_line(x1, y1, x2, y2, fill='black', width=2)
        
        # Origin point
        cx, cy = self._to_canvas_coords(0, 0)
        self.canvas.create_oval(cx-3, cy-3, cx+3, cy+3, fill='black')
    
    def _update_tool_position(self):
        """Update the red tool marker position"""
        if self.tool_marker:
            self.canvas.delete(self.tool_marker)
        
        cx, cy = self._to_canvas_coords(self.current_x, self.current_y)
        self.tool_marker = self.canvas.create_oval(cx-5, cy-5, cx+5, cy+5, 
                                                   fill='red', outline='darkred', width=2)
    
    def _distance(self, x1, y1, x2, y2):
        """Calculate distance between two points"""
        return sqrt((x2 - x1)**2 + (y2 - y1)**2)
    
    def _animate_segment(self, x1, y1, x2, y2, color='blue', width=2):
        """Animate drawing a segment from (x1, y1) to (x2, y2)"""
        cx1, cy1 = self._to_canvas_coords(x1, y1)
        cx2, cy2 = self._to_canvas_coords(x2, y2)
        
        # Calculate number of steps based on delay or speed
        if self.draw_delay is not None:
            num_steps = max(int(self.draw_delay * 60), 10)  # 60 FPS target
        else:
            distance = self._distance(x1, y1, x2, y2)
            time_needed = distance / self.speed
            num_steps = max(int(time_needed * 60), 10)
        
        # Draw line progressively
        for i in range(num_steps + 1):
            t = i / num_steps
            
            # Current interpolated position
            curr_x = x1 + t * (x2 - x1)
            curr_y = y1 + t * (y2 - y1)
            
            # Update tool position
            self.current_x = curr_x
            self.current_y = curr_y
            self._update_tool_position()
            
            # Draw the line segment up to current position
            curr_cx = cx1 + t * (cx2 - cx1)
            curr_cy = cy1 + t * (cy2 - cy1)
            
            if i > 0:
                prev_cx = cx1 + (i-1)/num_steps * (cx2 - cx1)
                prev_cy = cy1 + (i-1)/num_steps * (cy2 - cy1)
                self.canvas.create_line(prev_cx, prev_cy, curr_cx, curr_cy, 
                                      fill=color, width=width)
            
            self.canvas.update()
            time.sleep(self.draw_delay / num_steps if self.draw_delay else 1.0 / 60)
        
        # Ensure final position is exact
        self.current_x = x2
        self.current_y = y2
        self._update_tool_position()
    
    def point(self, point_tuple, color='red', size=3):
        """
        Draw a point at coordinates
        
        Parameters:
        - point_tuple: (x, y) tuple
        - color: Point color
        - size: Point radius in pixels
        """
        x, y = point_tuple
        cx, cy = self._to_canvas_coords(x, y)
        self.canvas.create_oval(cx-size, cy-size, cx+size, cy+size, 
                               fill=color, outline=color)
        
        # Move tool to this position instantly
        self.current_x = x
        self.current_y = y
        self._update_tool_position()
        self.canvas.update()
        
        return self
    
    def segment(self, start, end, color='blue', width=2, animate=True):
        """
        Draw a line segment from start to end
        
        Parameters:
        - start: (x1, y1) tuple
        - end: (x2, y2) tuple
        - color: Line color
        - width: Line width in pixels
        - animate: If True, animate the drawing; if False, draw instantly
        """
        x1, y1 = start
        x2, y2 = end
        
        if animate:
            self._animate_segment(x1, y1, x2, y2, color, width)
        else:
            cx1, cy1 = self._to_canvas_coords(x1, y1)
            cx2, cy2 = self._to_canvas_coords(x2, y2)
            self.canvas.create_line(cx1, cy1, cx2, cy2, fill=color, width=width)
            
            # Update position
            self.current_x = x2
            self.current_y = y2
            self._update_tool_position()
            self.canvas.update()
        
        return self
    
    def move_to(self, point_tuple, animate=True):
        """
        Move to position without drawing
        
        Parameters:
        - point_tuple: (x, y) tuple
        - animate: If True, animate the movement
        """
        x, y = point_tuple
        
        if animate:
            # Move with visual feedback but no line
            cx, cy = self._to_canvas_coords(x, y)
            num_steps = 20
            
            for i in range(num_steps + 1):
                t = i / num_steps
                self.current_x = self.current_x + t * (x - self.current_x) / num_steps
                self.current_y = self.current_y + t * (y - self.current_y) / num_steps
                self._update_tool_position()
                self.canvas.update()
                time.sleep(0.01)
        
        self.current_x = x
        self.current_y = y
        self._update_tool_position()
        self.canvas.update()
        
        return self
    
    def line_to(self, point_tuple, color='blue', width=2):
        """Draw segment from current position to point"""
        return self.segment((self.current_x, self.current_y), point_tuple, color, width)
    
    def clear(self):
        """Clear all drawings (keep grid and axes)"""
        self.canvas.delete("all")
        self._draw_grid()
        self._draw_axes()
        self.current_x = 0
        self.current_y = 0
        self._update_tool_position()
        return self
    
    def set_speed(self, speed=None, delay=None):
        """
        Set drawing speed
        
        Parameters:
        - speed: Units per second (if delay is None)
        - delay: Fixed seconds per segment (overrides speed)
        """
        if delay is not None:
            self.draw_delay = delay
        if speed is not None:
            self.speed = speed
        return self
    
    def show(self):
        """Display the canvas (blocking)"""
        self.root.mainloop()
    
    def save(self, filename="cnc_output.ps"):
        """Save canvas to PostScript file"""
        self.canvas.postscript(file=filename)
        print(f"Saved to {filename}")
        return self


# =============================================
# HELPER FUNCTIONS
# =============================================

def plot_path(cnc, points, color='blue', width=2, show_points=False, animate=True):
    """
    Plot a path through multiple points
    
    Parameters:
    - cnc: CNC instance
    - points: List of (x, y) tuples
    - color: Line color
    - width: Line width
    - show_points: Also draw points at vertices
    - animate: Animate the drawing
    """
    if not points:
        return cnc
    
    # Move to first point
    cnc.move_to(points[0], animate=False)
    
    for i in range(len(points) - 1):
        cnc.segment(points[i], points[i + 1], color=color, width=width, animate=animate)
        
        if show_points:
            cnc.point(points[i], color=color)
    
    if show_points and points:
        cnc.point(points[-1], color=color)
    
    return cnc


# =============================================
# EXAMPLE USAGE
# =============================================

if __name__ == "__main__":
    # Example 1: Draw a square with 0.5 second per segment
    print("Example 1: Animated Square (0.5s per segment)")
    cnc = CNC(title="Animated Square", x_range=(-5, 5), y_range=(-5, 5), 
              draw_delay=0.5)
    
    square = [(2, 2), (-2, 2), (-2, -2), (2, -2), (2, 2)]
    
    for i in range(len(square) - 1):
        cnc.segment(square[i], square[i+1], color='purple', width=3)
    
    cnc.show()
    
    # Example 2: Triangle with different speeds
    print("\nExample 2: Triangle with speed control")
    cnc2 = CNC(title="Triangle", x_range=(-5, 5), y_range=(-5, 5), 
               draw_delay=0.3)
    
    triangle = [(0, 3), (-3, -2), (3, -2), (0, 3)]
    plot_path(cnc2, triangle, color='green', width=3)
    
    cnc2.show()
    
    # Example 3: Spiral with fast drawing
    print("\nExample 3: Fast Spiral")
    cnc3 = CNC(title="Spiral", width=800, height=800, 
               x_range=(-30, 30), y_range=(-30, 30),
               draw_delay=0.01)  # Fast drawing
    
    import numpy as np
    t = np.linspace(0, 8*pi, 200)  # Fewer points for faster demo
    x = (t * np.cos(t)).tolist()
    y = (t * np.sin(t)).tolist()
    spiral_points = list(zip(x, y))
    
    plot_path(cnc3, spiral_points, color='blue', width=2)
    
    cnc3.show()
    
    # Example 4: Star with point markers
    print("\nExample 4: Star (0.5s per segment)")
    cnc4 = CNC(title="Star", x_range=(-6, 6), y_range=(-6, 6),
               draw_delay=0.5)
    
    # 5-pointed star
    star_points = []
    for i in range(5):
        angle = i * 2 * pi / 5 - pi/2
        star_points.append((5 * cos(angle), 5 * sin(angle)))
        
        # Inner point
        angle_inner = (i + 0.5) * 2 * pi / 5 - pi/2
        star_points.append((2 * cos(angle_inner), 2 * sin(angle_inner)))
    
    star_points.append(star_points[0])  # Close the star
    
    plot_path(cnc4, star_points, color='gold', width=3, show_points=True)
    
    cnc4.show()