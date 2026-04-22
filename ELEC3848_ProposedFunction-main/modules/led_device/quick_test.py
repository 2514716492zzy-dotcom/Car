#!/usr/bin/python3
"""
快速测试工具 - 使用简单的测试图案验证配置

这个脚本可以快速测试特定配置，无需交互。
修改下面的配置参数后运行即可。
"""

import numpy as np
import adafruit_blinka_raspberry_pi5_piomatter as piomatter

# ==================== 配置参数 ====================
# 修改这些参数来测试不同的配置

WIDTH = 64
HEIGHT = 64
N_ADDR_LINES = 4  # 尝试 4 或 5
SERPENTINE = False  # True 或 False
PINOUT = piomatter.Pinout.AdafruitMatrixBonnet  # 或 AdafruitMatrixBonnetBGR
ROTATION = piomatter.Orientation.Normal  # Normal, R180, CW, CCW

# 选择测试图案: 'quadrant', 'bars', 'gradient', 'grid'
TEST_PATTERN = 'quadrant'

# ================================================


def create_quadrant_pattern(width, height):
    """四象限图案 - 用于检测方向和旋转"""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    mid_x, mid_y = width // 2, height // 2
    
    # 四个象限不同颜色
    img[0:mid_y, 0:mid_x] = [255, 0, 0]        # 左上：红色
    img[0:mid_y, mid_x:width] = [0, 255, 0]    # 右上：绿色
    img[mid_y:height, 0:mid_x] = [0, 0, 255]   # 左下：蓝色
    img[mid_y:height, mid_x:width] = [255, 255, 0]  # 右下：黄色
    
    # 中心十字白色
    cross_width = 2
    img[mid_y-cross_width:mid_y+cross_width, :] = [255, 255, 255]
    img[:, mid_x-cross_width:mid_x+cross_width] = [255, 255, 255]
    
    return img


def create_bars_pattern(width, height):
    """色条图案 - 用于检测颜色通道"""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    bar_height = height // 7
    
    colors = [
        ([255, 255, 255], "白色"),
        ([255, 0, 0], "红色"),
        ([0, 255, 0], "绿色"),
        ([0, 0, 255], "蓝色"),
        ([255, 255, 0], "黄色"),
        ([255, 0, 255], "洋红"),
        ([0, 255, 255], "青色"),
    ]
    
    for i, (color, name) in enumerate(colors):
        y_start = i * bar_height
        y_end = min((i + 1) * bar_height, height)
        img[y_start:y_end, :] = color
    
    return img


def create_gradient_pattern(width, height):
    """渐变图案 - 用于检测扫描方向"""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    
    # 水平渐变（红色）
    for y in range(height // 2):
        for x in range(width):
            img[y, x] = [int(255 * x / width), 0, 0]
    
    # 垂直渐变（绿色）
    for y in range(height // 2, height):
        intensity = int(255 * (y - height // 2) / (height // 2))
        img[y, :] = [0, intensity, 0]
    
    return img


def create_grid_pattern(width, height):
    """网格图案 - 用于检测像素映射"""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    grid_size = 8
    
    for y in range(height):
        for x in range(width):
            if x % grid_size == 0 or y % grid_size == 0:
                img[y, x] = [255, 255, 255]  # 白色网格线
            elif ((x // grid_size) + (y // grid_size)) % 2 == 0:
                img[y, x] = [100, 0, 0]  # 深红
            else:
                img[y, x] = [0, 0, 100]  # 深蓝
    
    return img


def main():
    print("=" * 60)
    print("快速测试工具")
    print("=" * 60)
    print(f"\n当前配置:")
    print(f"  尺寸: {WIDTH}x{HEIGHT}")
    print(f"  地址线数 (n_addr_lines): {N_ADDR_LINES}")
    print(f"  蛇形模式 (serpentine): {SERPENTINE}")
    print(f"  引脚配置 (pinout): {PINOUT.name}")
    print(f"  旋转方向 (rotation): {ROTATION.name}")
    print(f"  测试图案: {TEST_PATTERN}")
    print("\n" + "-" * 60)
    
    # 创建测试图案
    patterns = {
        'quadrant': create_quadrant_pattern,
        'bars': create_bars_pattern,
        'gradient': create_gradient_pattern,
        'grid': create_grid_pattern,
    }
    
    if TEST_PATTERN not in patterns:
        print(f"错误：未知的测试图案 '{TEST_PATTERN}'")
        print(f"可用图案: {', '.join(patterns.keys())}")
        return
    
    framebuffer = patterns[TEST_PATTERN](WIDTH, HEIGHT)
    
    # 创建几何配置
    geometry = piomatter.Geometry(
        width=WIDTH,
        height=HEIGHT,
        n_addr_lines=N_ADDR_LINES,
        serpentine=SERPENTINE,
        rotation=ROTATION
    )
    
    # 初始化矩阵
    matrix = piomatter.PioMatter(
        colorspace=piomatter.Colorspace.RGB888Packed,
        pinout=PINOUT,
        framebuffer=framebuffer,
        geometry=geometry
    )
    
    # 显示
    matrix.show()
    
    print(f"\n✓ 显示成功！")
    print(f"  FPS: {matrix.fps:.1f}")
    
    if TEST_PATTERN == 'quadrant':
        print("\n预期效果（四象限图案）:")
        print("  左上角：红色")
        print("  右上角：绿色")
        print("  左下角：蓝色")
        print("  右下角：黄色")
        print("  中间：白色十字")
    elif TEST_PATTERN == 'bars':
        print("\n预期效果（色条图案）:")
        print("  从上到下：白、红、绿、蓝、黄、洋红、青")
    elif TEST_PATTERN == 'gradient':
        print("\n预期效果（渐变图案）:")
        print("  上半部分：从左到右红色渐变")
        print("  下半部分：从上到下绿色渐变")
    elif TEST_PATTERN == 'grid':
        print("\n预期效果（网格图案）:")
        print("  白色网格线，红蓝相间的方格")
    
    print("\n如果显示不正确，请修改脚本顶部的配置参数。")
    print("或运行完整诊断工具: python diagnose_panel.py")
    print("\n按 Enter 退出...")
    input()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()

