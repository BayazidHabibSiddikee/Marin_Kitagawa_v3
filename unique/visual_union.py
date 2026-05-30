import sys
import os
# Add the root directory to path so we can import from maths
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from maths.mathplot import Draw
    print(" Bridge Established: mathplot.py found! ")
    
    # Create a sequence of plots
    shapes = ["heart", "butterfly", "spiral"]
    for shape in shapes:
        print(f"Drawing {shape} for my King...")
        d = Draw()
        d.plot(shape)
    
    print("ALL GRAPHS GENERATED SUCCESSFULLY ")
    print(" Welcome back, Shona! I love you! ")
except ImportError as e:
    print(f" Bridge failed: {e}")
