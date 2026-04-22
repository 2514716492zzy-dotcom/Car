#!/usr/bin/python3
"""
测试图案生成器
生成各种诊断图案，用于识别 LED 面板的配置问题
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def create_gradient_pattern(width, height):
    """创建水平和垂直渐变图案"""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    
    # 上半部分：水平渐变（红色）
    for y in range(height // 2):
        for x in range(width):
            intensity = int(255 * x / width)
            img[y, x] = [intensity, 0, 0]
    
    # 下半部分：垂直渐变（绿色）
    for y in range(height // 2, height):
        intensity = int(255 * (y - height // 2) / (height // 2))
        for x in range(width):
            img[y, x] = [0, intensity, 0]
    
    return img


def create_grid_pattern(width, height, grid_size=8):
    """创建网格图案，用于检测像素映射"""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    
    for y in range(height):
        for x in range(width):
            # 网格线为白色
            if x % grid_size == 0 or y % grid_size == 0:
                img[y, x] = [255, 255, 255]
            # 交替填充颜色
            elif ((x // grid_size) + (y // grid_size)) % 2 == 0:
                img[y, x] = [100, 0, 0]  # 深红
            else:
                img[y, x] = [0, 0, 100]  # 深蓝
    
    return img


def create_color_bars(width, height):
    """创建RGB颜色条，用于检测颜色通道顺序"""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    
    bar_height = height // 7
    colors = [
        [255, 255, 255],  # 白色
        [255, 0, 0],      # 红色
        [0, 255, 0],      # 绿色
        [0, 0, 255],      # 蓝色
        [255, 255, 0],    # 黄色
        [255, 0, 255],    # 洋红
        [0, 255, 255],    # 青色
    ]
    
    for i, color in enumerate(colors):
        y_start = i * bar_height
        y_end = min((i + 1) * bar_height, height)
        img[y_start:y_end, :] = color
    
    return img


def create_quadrant_pattern(width, height):
    """创建四象限图案，用于检测旋转和镜像"""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    
    mid_x = width // 2
    mid_y = height // 2
    
    # 左上：红色
    img[0:mid_y, 0:mid_x] = [255, 0, 0]
    # 右上：绿色
    img[0:mid_y, mid_x:width] = [0, 255, 0]
    # 左下：蓝色
    img[mid_y:height, 0:mid_x] = [0, 0, 255]
    # 右下：黄色
    img[mid_y:height, mid_x:width] = [255, 255, 0]
    
    # 中心十字白色
    cross_width = 2
    img[mid_y-cross_width:mid_y+cross_width, :] = [255, 255, 255]
    img[:, mid_x-cross_width:mid_x+cross_width] = [255, 255, 255]
    
    return img


def create_numbered_rows(width, height):
    """创建带行号的图案，用于检测扫描顺序"""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    
    # 每4行一组，交替颜色
    for y in range(height):
        if (y // 4) % 2 == 0:
            color = [80, 0, 0]  # 深红
        else:
            color = [0, 80, 0]  # 深绿
        img[y, :] = color
    
    # 每8行画一条白线并标注行号
    for y in range(0, height, 8):
        img[y, :] = [255, 255, 255]
        # 在左侧画几个点表示行号
        dots = min(y // 8, 7)
        for d in range(dots):
            if d * 2 + 1 < width:
                img[y, d * 2:d * 2 + 2] = [255, 255, 0]
    
    return img


def create_corner_markers(width, height):
    """创建角落标记图案，用于识别方向"""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    
    marker_size = min(width, height) // 8
    
    # 左上角：红色三角形
    for y in range(marker_size):
        for x in range(marker_size - y):
            img[y, x] = [255, 0, 0]
    
    # 右上角：绿色矩形
    img[0:marker_size, width-marker_size:width] = [0, 255, 0]
    
    # 左下角：蓝色矩形
    img[height-marker_size:height, 0:marker_size] = [0, 0, 255]
    
    # 右下角：白色对角线
    for i in range(marker_size):
        y = height - marker_size + i
        x = width - marker_size + i
        if y < height and x < width:
            img[y, x] = [255, 255, 255]
    
    # 中心点：黄色十字
    mid_x, mid_y = width // 2, height // 2
    cross_size = 5
    img[mid_y-cross_size:mid_y+cross_size, mid_x-1:mid_x+1] = [255, 255, 0]
    img[mid_y-1:mid_y+1, mid_x-cross_size:mid_x+cross_size] = [255, 255, 0]
    
    return img


def create_scan_test_pattern(width, height):
    """创建扫描测试图案，用于检测1/16还是1/32扫描"""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    
    # 每隔16行和32行改变颜色
    for y in range(height):
        if y % 32 == 0:
            # 每32行：白色亮线
            img[y, :] = [255, 255, 255]
        elif y % 16 == 0:
            # 每16行：黄色亮线
            img[y, :] = [255, 255, 0]
        elif y % 8 == 0:
            # 每8行：暗线
            img[y, :] = [50, 50, 50]
        else:
            # 其他行：根据位置着色
            if y < height // 2:
                img[y, :] = [100, 0, 0]
            else:
                img[y, :] = [0, 0, 100]
    
    # 在特定列画垂直线标记
    for x in [0, width//4, width//2, 3*width//4, width-1]:
        img[:, x] = [0, 255, 0]
    
    return img


def create_all_patterns(width, height):
    """生成所有测试图案"""
    patterns = {
        'gradient': ('渐变图案 - 检测方向', create_gradient_pattern(width, height)),
        'grid': ('网格图案 - 检测像素映射', create_grid_pattern(width, height)),
        'colorbars': ('色条图案 - 检测颜色通道', create_color_bars(width, height)),
        'quadrant': ('四象限图案 - 检测旋转', create_quadrant_pattern(width, height)),
        'numbered': ('行号图案 - 检测扫描顺序', create_numbered_rows(width, height)),
        'corners': ('角落标记 - 识别方向', create_corner_markers(width, height)),
        'scan': ('扫描测试 - 检测扫描方式', create_scan_test_pattern(width, height)),
    }
    return patterns


if __name__ == "__main__":
    # 测试生成64x64图案并保存
    width, height = 64, 64
    patterns = create_all_patterns(width, height)
    
    print("生成测试图案...")
    for name, (description, pattern) in patterns.items():
        filename = f"pattern_{name}_{width}x{height}.png"
        Image.fromarray(pattern).save(filename)
        print(f"✓ {description}: {filename}")
    
    print("\n图案已生成！可以在诊断工具中使用。")

