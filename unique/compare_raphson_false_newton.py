import numpy as np
import matplotlib.pyplot as plt

class RK4Solver:
    """
    MARIN'S HIGH-PRECISION RK4 SOLVER
    Based on the logic from TeaTimeNumericalAnalysis.pdf
    """
    def __init__(self, f):
        self.f = f  # The derivative function dy/dx = f(x, y)

    def solve(self, x0, y0, h, steps):
        x = np.zeros(steps + 1)
        y = np.zeros(steps + 1)
        
        x[0], y[0] = x0, y0
        
        for i in range(steps):
            # The 4-Stage Runge-Kutta Magic
            # Logic mapped directly from the Octave snippet provided
            k1 = self.f(x[i], y[i])
            k2 = self.f(x[i] + h/2, y[i] + h/2 * k1)
            k3 = self.f(x[i] + h/2, y[i] + h/2 * k2)
            k4 = self.f(x[i] + h, y[i] + h * k3)
            
            # The Weighted Average (The Truth)
            y[i+1] = y[i] + (h/6) * (k1 + 2*k2 + 2*k3 + k4)
            x[i+1] = x[i] + h
            
        return x, y

# =============================================================================
# TESTING GROUND: Let's solve a common ODE
# Example: dy/dx = x + y | Initial Condition: y(0) = 1
# =============================================================================

def my_ode(x, y):
    return x + y

# Parameters
x_start = 0
y_start = 1
step_size = 0.1
total_steps = 20

# Execution
solver = RK4Solver(my_ode)
x_res, y_res = solver.solve(x_start, y_start, step_size, total_steps)

# Visualizing the result
plt.figure(figsize=(10, 6))
plt.plot(x_res, y_res, 'b-o', label='RK4 Solution', markersize=4)
plt.title("Numerical Solution using RK4 (The Gold Standard)", fontsize=14)
plt.xlabel("x")
plt.ylabel("y")
plt.grid(True, alpha=0.3)
plt.legend()
plt.show()

print("RK4 Execution Complete. Results saved to memory.")
