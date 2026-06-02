import os
from PIL import Image

def process_avatars(directory):
    for filename in os.listdir(directory):
        if filename.endswith(".png") and filename != "README.md":
            path = os.path.join(directory, filename)
            print(f"Processing {filename}...")
            
            try:
                img = Image.open(path)
                img = img.convert("RGBA")
                datas = img.getdata()

                new_data = []
                for item in datas:
                    # Target white background (RGB > 240)
                    # We use a threshold to handle slight off-whites
                    if item[0] > 245 and item[1] > 245 and item[2] > 245:
                        new_data.append((255, 255, 255, 0))
                    else:
                        new_data.append(item)

                img.putdata(new_data)
                img.save(path, "PNG")
                print(f"Successfully made {filename} transparent.")
            except Exception as e:
                print(f"Failed to process {filename}: {e}")

if __name__ == "__main__":
    avatar_dir = "/home/sword/Documents/marin/static/avatars/"
    process_avatars(avatar_dir)
