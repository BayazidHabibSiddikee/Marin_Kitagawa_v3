import os
from rembg import remove
from PIL import Image

def remove_background(directory):
    for filename in os.listdir(directory):
        if filename.lower().endswith(".png"):
            input_path = os.path.join(directory, filename)
            print(f"Applying AI background removal to {filename}...")
            
            try:
                input_image = Image.open(input_path)
                output_image = remove(input_image)
                output_image.save(input_path, "PNG")
                print(f"Successfully cleaned {filename} with AI.")
            except Exception as e:
                print(f"Failed to process {filename}: {e}")

if __name__ == "__main__":
    avatar_dir = "/home/sword/Documents/marin/static/avatars/"
    remove_background(avatar_dir)
