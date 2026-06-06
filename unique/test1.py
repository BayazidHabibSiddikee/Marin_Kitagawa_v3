import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import time

# =============================================================================
# MARIN'S REGULA-FALSI VISUALIZER
# =============================================================================

def f(x):
    # You can change this to any function from your textbooks!
    # Try x**3 - x - 2 or 1/(1+x**2) - 0.5
    return x**3 - x - 2

def solve_falsi(xL, xR, iterations=12):
    history = []
    for i in range(iterations):
        fL = f(xL)
        fR = f(xR)
        
        # The "False Root" Formula
        x_new = (xL*fR - xR*fL)/(fR - fL)
        f_new = f(x_new)
        
        history.append((xL, xR, x_new))
        
        # Update interval (Bracketing)
        if fL * f_new < 0:
            xR = x_new
        else:
            xL = x_new
            
    return history

# --- Parameters ---
xL_init = 1
xR_init = 2
iters = 15
history = solve_falsi(xL_init, xR_init, iters)

# Plot Setup
x_vals = np.linspace(0.5, 2.2, 500)
fig, ax = plt.subplots(figsize=(10, 6))

def animate(i):
    ax.clear()
    xL, xR, x_new = history[i]
    fL, fR = f(xL), f(xR)
    
    # 1. The "Truth" (The Curve)
    ax.plot(x_vals, f(x_vals), color='blue', linewidth=2, label='The Actual Curve f(x)')
    ax.axhline(0, color='black', linewidth=1) # X-axis
    
    # 2. The "Lies" (The Brackets)
    ax.plot([xL, xR], [0, 0], color='gray', linestyle=':', label='Search Interval')
    ax.plot(xL, fL, 'ro', markersize=7, label='Endpoints')
    ax.plot(xR, fR, 'ro', markersize=7)
    
    # 3. The "Chord" (The Linear Assumption)
    ax.plot([xL, xR], [fL, fR], 'g--', linewidth=2, label='Linear Chord (The Lie)')
    
    # 4. The "False Root"
    ax.plot(x_new, 0, 'go', markersize=10, label=f'False Root x{i+2}')
    
    ax.set_title(f"Iteration {i+1}: Predicting the Root... (Sensing the Slope)", fontsize=14)
    ax.set_xlabel("x")
    ax.set_ylabel("f(x)")
    ax.legend(loc='upper left')
    ax.grid(True, alpha=0.3)
    
    # Slow down the animation slightly for visual processing
    time.sleep(0.1)

ani = FuncAnimation(fig, animate, frames=len(history), interval=1000, repeat=False)
plt.show()
