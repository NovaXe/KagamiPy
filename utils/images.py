import sys
import os
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont


def color_image(color):
    image = Image.new("RGB", (100, 100), color)
    name = f"{color}.png"


def color_role_help(_color_roles):
    file_exists = os.path.exists("utils/images_temp/colors.png")
    if file_exists:
        img = Image.open("utils/images_temp/colors.png")
        num_colors = int(img.height / 40)
        img.close()
        if num_colors >= len(_color_roles):
            return

    color_roles = list(reversed(_color_roles))

    image = Image.new("RGB", (512, len(color_roles) * 40))
    active_draw = ImageDraw.Draw(image, "RGB")
    for i in range(len(color_roles)):
        color = "#%02x%02x%02x" % color_roles[i].color.to_rgb()
        name = color_roles[i].name[+3:]
        active_draw.rectangle(((0, i * 40), (512, i * 40 + 40)), fill=color)
        font = ImageFont.truetype("arialbd.ttf", 30)
        try:
            active_draw.text((255, i * 40 + 20), f"{name}- {color}", anchor="mm", fill="black", font=font)
        except Exception as e:
            print(e)

    try:
        image.save(f"utils/images_temp/colors.png", format="PNG")
        print("[Images] saved")
    except OSError as e:
        print(f"[util images] OSError, file contains partial data")
        print(e)
    except ValueError:
        print(f"[util images] ValueError, output format could not be determined")

