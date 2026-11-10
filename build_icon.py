import os
import math
import subprocess
from PIL import Image, ImageDraw, ImageFilter

def create_pyvault_icon(size=1024):
    # Create base RGBA canvas
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    
    # Scale helper
    s = size / 1024.0
    
    # Draw drop shadow for squircle
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    margin = 100 * s
    shadow_rect = [margin, margin + 18 * s, size - margin, size - margin + 18 * s]
    shadow_draw.rounded_rectangle(shadow_rect, radius=int(185 * s), fill=(0, 0, 0, 110))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=25 * s))
    img.alpha_composite(shadow)
    
    # Main squircle layer
    squircle = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sq_draw = ImageDraw.Draw(squircle)
    rect = [margin, margin, size - margin, size - margin]
    
    # Background gradient for squircle
    # Top: #1E293B (30, 41, 59) -> Bottom: #0B1120 (11, 17, 32)
    # We can create a vertical gradient
    grad = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(grad)
    for y in range(int(margin), int(size - margin)):
        t = (y - margin) / (size - 2 * margin)
        # Deep blue-gray to deep dark obsidian
        r = int(30 * (1 - t) + 10 * t)
        g = int(45 * (1 - t) + 15 * t)
        b = int(70 * (1 - t) + 28 * t)
        g_draw.line([(margin, y), (size - margin, y)], fill=(r, g, b, 255))
        
    # Mask squircle
    mask = Image.new("L", (size, size), 0)
    m_draw = ImageDraw.Draw(mask)
    m_draw.rounded_rectangle(rect, radius=int(185 * s), fill=255)
    squircle.paste(grad, (0, 0), mask)
    
    # Draw border on squircle
    sq_draw.rounded_rectangle(rect, radius=int(185 * s), outline=(56, 189, 248, 70), width=int(4 * s))
    
    # Draw inner subtle accent line at top
    inner_rect = [margin + 6*s, margin + 6*s, size - margin - 6*s, size - margin - 6*s]
    sq_draw.rounded_rectangle(inner_rect, radius=int(180 * s), outline=(255, 255, 255, 25), width=int(2 * s))
    
    img.alpha_composite(squircle)
    
    # Draw central graphics: A sleek Shield + Vault Padlock
    center_x = size / 2
    center_y = size / 2
    
    # Draw glowing aura behind lock
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse([center_x - 220*s, center_y - 200*s, center_x + 220*s, center_y + 240*s], fill=(37, 99, 235, 65))
    glow_draw.ellipse([center_x - 140*s, center_y - 120*s, center_x + 140*s, center_y + 160*s], fill=(16, 185, 129, 60))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=45 * s))
    img.alpha_composite(glow)
    
    # Lock Shackle (top arch)
    # Outer shackle radius ~150s, stroke ~40s
    shackle_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shackle_draw = ImageDraw.Draw(shackle_layer)
    
    shackle_w = 125 * s
    shackle_top = 265 * s
    shackle_bottom = 460 * s
    shackle_thick = 36 * s
    
    # Draw arc and legs
    arc_box = [center_x - shackle_w, shackle_top, center_x + shackle_w, shackle_top + 2 * shackle_w]
    shackle_draw.arc(arc_box, start=180, end=0, fill=(226, 232, 240, 255), width=int(shackle_thick))
    # Shackle vertical legs
    shackle_draw.line([(center_x - shackle_w + shackle_thick/2 - 0.5, shackle_top + shackle_w), 
                       (center_x - shackle_w + shackle_thick/2 - 0.5, shackle_bottom)], fill=(203, 213, 225, 255), width=int(shackle_thick))
    shackle_draw.line([(center_x + shackle_w - shackle_thick/2 + 0.5, shackle_top + shackle_w), 
                       (center_x + shackle_w - shackle_thick/2 + 0.5, shackle_bottom)], fill=(203, 213, 225, 255), width=int(shackle_thick))
    
    img.alpha_composite(shackle_layer)
    
    # Lock Body
    body_w = 190 * s
    body_top = 430 * s
    body_h = 290 * s
    body_rect = [center_x - body_w, body_top, center_x + body_w, body_top + body_h]
    
    body_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    b_draw = ImageDraw.Draw(body_layer)
    
    # Body gradient fill (Gradient from Royal Blue #2563EB to Deep Sapphire #1D4ED8)
    body_grad = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(body_grad)
    for y in range(int(body_top), int(body_top + body_h)):
        t = (y - body_top) / body_h
        r = int(37 * (1 - t) + 15 * t)
        g = int(99 * (1 - t) + 40 * t)
        b = int(235 * (1 - t) + 140 * t)
        bg_draw.line([(center_x - body_w, y), (center_x + body_w, y)], fill=(r, g, b, 255))
        
    b_mask = Image.new("L", (size, size), 0)
    bm_draw = ImageDraw.Draw(b_mask)
    bm_draw.rounded_rectangle(body_rect, radius=int(45 * s), fill=255)
    body_layer.paste(body_grad, (0, 0), b_mask)
    
    # Body bevel / highlight
    b_draw.rounded_rectangle(body_rect, radius=int(45 * s), outline=(96, 165, 250, 180), width=int(3 * s))
    
    # Vault Dial / Core in the center of lock body
    dial_center_y = body_top + body_h * 0.44
    dial_r = 72 * s
    
    # Outer dial ring
    b_draw.ellipse([center_x - dial_r, dial_center_y - dial_r, center_x + dial_r, dial_center_y + dial_r], 
                   fill=(15, 23, 42, 230), outline=(56, 189, 248, 200), width=int(4 * s))
                   
    # Dial tick marks
    for angle_deg in range(0, 360, 30):
        rad = math.radians(angle_deg)
        r_inner = dial_r - 12 * s
        r_outer = dial_r - 4 * s
        x1 = center_x + r_inner * math.cos(rad)
        y1 = dial_center_y + r_inner * math.sin(rad)
        x2 = center_x + r_outer * math.cos(rad)
        y2 = dial_center_y + r_outer * math.sin(rad)
        b_draw.line([(x1, y1), (x2, y2)], fill=(148, 163, 184, 180), width=int(2.5 * s))
        
    # Inner emerald core / keyhole
    core_r = 38 * s
    b_draw.ellipse([center_x - core_r, dial_center_y - core_r, center_x + core_r, dial_center_y + core_r], 
                   fill=(16, 185, 129, 240), outline=(52, 211, 153, 255), width=int(3 * s))
    
    # Keyhole slot
    kh_top_r = 12 * s
    b_draw.ellipse([center_x - kh_top_r, dial_center_y - 12*s - kh_top_r, center_x + kh_top_r, dial_center_y - 12*s + kh_top_r], 
                   fill=(15, 23, 42, 255))
    kh_pts = [
        (center_x - 8 * s, dial_center_y - 8 * s),
        (center_x + 8 * s, dial_center_y - 8 * s),
        (center_x + 12 * s, dial_center_y + 18 * s),
        (center_x - 12 * s, dial_center_y + 18 * s)
    ]
    b_draw.polygon(kh_pts, fill=(15, 23, 42, 255))
    
    # Modern status indicator / horizontal sleek dash at bottom of body
    dash_y = body_top + body_h * 0.85
    b_draw.rounded_rectangle([center_x - 35 * s, dash_y - 3 * s, center_x + 35 * s, dash_y + 3 * s], 
                             radius=int(3 * s), fill=(56, 189, 248, 160))

    img.alpha_composite(body_layer)
    return img

def build_icns():
    base_img = create_pyvault_icon(1024)
    iconset_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "PyVault.iconset")
    os.makedirs(iconset_dir, exist_ok=True)
    
    # Save standard PNG for Qt and assets
    base_img.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_icon.png"))
    
    sizes = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png")
    ]
    
    for dim, name in sizes:
        resized = base_img.resize((dim, dim), Image.Resampling.LANCZOS)
        resized.save(os.path.join(iconset_dir, name))
        
    icns_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "AppIcon.icns")
    subprocess.run(["iconutil", "-c", "icns", iconset_dir, "-o", icns_path], check=True)
    print("Successfully built AppIcon.icns and app_icon.png")

if __name__ == "__main__":
    build_icns()
