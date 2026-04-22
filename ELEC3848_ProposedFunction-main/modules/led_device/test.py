import piomatter
import numpy as np
import time

width = 64
height = 64
n_addr_lines = 5

geometry = piomatter.Geometry(
    width=width, 
    height=height, 
    n_addr_lines=n_addr_lines,
    rotation=piomatter.Orientation.Normal
)

matrix_framebuffer = np.zeros(shape=(geometry.height, geometry.width, 3), dtype=np.uint8)

matrix = piomatter.PioMatter(
    colorspace=piomatter.Colorspace.RGB888Packed,
    pinout=piomatter.Pinout.AdafruitMatrixBonnet,
    framebuffer=matrix_framebuffer,
    geometry=geometry
)

for y in range(height):
    for x in range(width):
        r = int((x / width) * 255)
        g = int((y / height) * 255)
        b = int(((x + y) / (width + height)) * 255)
        matrix_framebuffer[y, x] = [r, g, b]

matrix.refresh()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass