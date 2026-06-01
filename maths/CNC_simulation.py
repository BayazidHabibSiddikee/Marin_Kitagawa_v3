"""
CNC Simulator using Tkinter
Realistic animated drawing with configurable speed
"""

import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from math import sin, cos, pi, sqrt
import time

class CNC:
    def __init__(self, title="CNC Simulator", width=600, height=600,
                 x_range=(-10, 10), y_range=(-10, 10),
                 speed=5.0, draw_delay=None, grid=True):
        self.title = title
        self.width = width
        self.height = height
        self.x_min, self.x_max = x_range
        self.y_min, self.y_max = y_range
        
        self.fig, self.ax = plt.subplots(figsize=(width/100, height/100))
        self.ax.set_title(title)
        self.ax.set_xlim(self.x_min, self.x_max)
        self.ax.set_ylim(self.y_min, self.y_max)
        if grid:
            self.ax.grid(True)
        self.ax.axhline(0, color='black', linewidth=1)
        self.ax.axvline(0, color='black', linewidth=1)
        self.current_x = 0
        self.current_y = 0
    
    def point(self, point_tuple, color='red', size=3):
        x, y = point_tuple
        self.ax.plot(x, y, marker='o', markersize=size, color=color)
        self.current_x = x
        self.current_y = y
        return self
    
    def segment(self, start, end, color='blue', width=2, animate=True):
        x1, y1 = start
        x2, y2 = end
        self.ax.plot([x1, x2], [y1, y2], color=color, linewidth=width)
        self.current_x = x2
        self.current_y = y2
        return self
    
    def move_to(self, point_tuple, animate=True):
        self.current_x, self.current_y = point_tuple
        return self
    
    def clear(self):
        self.ax.clear()
        return self
        
    def set_speed(self, speed=None, delay=None):
        return self
    
    def show(self):
        os.makedirs("static/generated", exist_ok=True)
        filename = f"static/generated/mathplot_{int(time.time())}.png"
        self.fig.savefig(filename)
        plt.close(self.fig)
    
    def save(self, filename="cnc_output.png"):
        self.fig.savefig(filename)
        return self

def plot_path(cnc, points, color='blue', width=2, show_points=False, animate=True):
    if not points: return cnc
    cnc.move_to(points[0], animate=False)
    for i in range(len(points) - 1):
        cnc.segment(points[i], points[i + 1], color=color, width=width, animate=animate)
    return cnc

def plot_path_old(cnc, points, color='blue', width=2, show_points=False, animate=True):
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