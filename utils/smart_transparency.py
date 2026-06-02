import os
from PIL import Image, ImageChops

def make_transparent(img, threshold=240):
    img = img.convert("RGBA")
    datas = img.getdata()
    
    # Smarter: take the corner pixels to guess background color
    corners = [datas[0], datas[img.width - 1], datas[len(datas) - img.width], datas[len(datas) - 1]]
    bg_r = sum(c[0] for c in corners) / 4
    bg_g = sum(c[1] for c in corners) / 4
    bg_b = sum(c[2] for c in corners) / 4
    
    new_data = []
    for item in datas:
        # Distance formula to background color
        dist = ((item[0] - bg_r)**2 + (item[1] - bg_g)**2 + (item[2] - bg_b)**2)**0.5
        
        # If very close to background color OR very bright (white)
        if dist < 40 or (item[0] > threshold and item[1] > threshold and item[2] > threshold):
            new_data.append((255, 255, 255, 0))
        else:
            new_data.append(item)
            
    img.putdata(new_data)
    return img

def process_directory(directory):
    for filename in os.listdir(directory):
        if filename.lower().endswith((".png", ".jpg", ".jpeg")):
            name, ext = os.path.splitext(filename)
            input_path = os.path.join(directory, filename)
            output_path = os.path.join(directory, name + ".png")
            
            print(f"Processing {filename}...")
            try:
                with Image.open(input_path) as img:
                    transparent_img = make_transparent(img)
                    transparent_img.save(output_path, "PNG")
                
                # If we converted from JPG, remove the old one
                if ext.lower() in [".jpg", ".jpeg"]:
                    os.remove(input_path)
                    print(f"Converted {filename} to {name}.png and removed original.")
                else:
                    print(f"Updated {filename} with better transparency.")
            except Exception as e:
                print(f"Error processing {filename}: {e}")

if __name__ == "__main__":
    avatar_dir = "/home/sword/Documents/marin/static/avatars/"
    process_directory(avatar_dir)
