import os
from PIL import Image, ImageDraw

def flood_fill_transparency(path, tolerance=30):
    img = Image.open(path).convert("RGBA")
    width, height = img.size
    
    # We'll flood fill from the 4 corners
    seeds = [(0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)]
    
    # Create a mask for the flood fill
    # We use a slightly more complex approach since PIL's floodfill is basic
    # We'll use the corner pixel colors
    for seed in seeds:
        color = img.getpixel(seed)
        # If it's already transparent, skip
        if color[3] == 0: continue
        
        # Simple flood fill from PIL
        ImageDraw.floodfill(img, seed, (255, 255, 255, 0), thresh=tolerance)
        
    img.save(path, "PNG")

def process_directory(directory):
    for filename in os.listdir(directory):
        if filename.lower().endswith(".png"):
            path = os.path.join(directory, filename)
            print(f"Applying flood-fill transparency to {filename}...")
            try:
                flood_fill_transparency(path)
                print(f"Successfully processed {filename}.")
            except Exception as e:
                print(f"Error processing {filename}: {e}")

if __name__ == "__main__":
    avatar_dir = "/home/sword/Documents/marin/static/avatars/"
    process_directory(avatar_dir)
