import numpy as np
import matplotlib.pyplot as plt

def f(x):
    return x**3 - x - 2 # A simple curve to show the stagnation

def regula_falsi_visualize(a, b, iterations=5):
    x_vals = [a, b]
    y_vals = [f(a), f(b)]
    
    plt.figure(figsize=(10, 6))
    x_range = np.linspace(a-1, b+1, 100)
    plt.plot(x_range, f(x_range), 'b-', label='f(x)')
    plt.axhline(0, color='black', lw=1)
    
    for i in range(iterations):
        # Calculate the intersection of the chord with x-axis
        c = (a*f(b) - b*f(a)) / (f(b) - f(a))
        
        plt.plot([a, b], [f(a), f(b)], 'orange', alpha=0.3) # The chord
        plt.plot(c, f(c), 'ro') # The new guess
        
        if f(a) * f(c) < 0:
            b = c # Right point moves
        else:
            a = c # Left point moves
            
    plt.title("Regula Falsi Stagnation Visualization")
    plt.legend()
    plt.grid(True)
    plt.show()

regula_falsi_visualize(-1, 2)
