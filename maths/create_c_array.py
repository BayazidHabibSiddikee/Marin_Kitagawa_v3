import numpy as np

t = np.linspace(0, 8*np.pi, 800)
x = t * np.cos(t)
y = t * np.sin(t)
z = t

# Convert to Python lists
x_list = x.tolist()
y_list = y.tolist()
z_list = z.tolist()

# Write C header file
def export_to_c_array(x, y, z, filename=None):
    with open(filename, 'w') as f:
        #f.write("#ifndef SPIRAL_PATH_H\n")
        #f.write("#define SPIRAL_PATH_H\n\n")
        f.write(f"#define NUM_POINTS {len(x)}\n\n")
        
        # X array
        f.write("float path_x[] = {\n    ")
        f.write(",\n    ".join([f"{val:.6f}f" for val in x]))
        f.write("\n};\n\n")
        
        # Y array
        f.write("float path_y[] = {\n    ")
        f.write(",\n    ".join([f"{val:.6f}f" for val in y]))
        f.write("\n};\n\n")
        
        # Z array
        f.write("float path_z[] = {\n    ")
        f.write(",\n    ".join([f"{val:.6f}f" for val in z]))
        f.write("\n};\n\n")
        
        #f.write("#endif // SPIRAL_PATH_H\n")
    
    print(f"C header file exported to {filename}")

#export_to_c_array(x_list, y_list, z_list,"Car.h")