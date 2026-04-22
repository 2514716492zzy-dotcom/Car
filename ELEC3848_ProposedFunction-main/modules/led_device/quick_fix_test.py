#!/usr/bin/python3
"""
快速测试 - 针对你的具体问题
只显示 0-15 行和 33-48 行的问题
"""

import numpy as np
import adafruit_blinka_raspberry_pi5_piomatter as piomatter

print("="*60)
print("快速修复测试")
print("="*60)
print("\n根据你的症状（只有0-15行和33-48行显示），")
print("我推测可能的配置是：")
print("  - n_addr_lines=4")
print("  - serpentine=True (这是关键！)")
print("\n开始测试...")

# 创建清晰的行测试图案
framebuffer = np.zeros((64, 64, 3), dtype=np.uint8)

# 每16行一种颜色，方便识别
framebuffer[0:16, :]   = [255, 0, 0]      # 第0-15行：红色
framebuffer[16:32, :]  = [0, 255, 0]      # 第16-31行：绿色
framebuffer[32:48, :]  = [0, 0, 255]      # 第32-47行：蓝色
framebuffer[48:64, :]  = [255, 255, 0]    # 第48-63行：黄色

# 在每行左侧画白色标记
for y in range(0, 64, 4):
    framebuffer[y, 0:4] = [255, 255, 255]

print("\n测试配置 1: serpentine=True")
print("-"*60)

geometry = piomatter.Geometry(
    width=64,
    height=64,
    n_addr_lines=4,
    serpentine=True,  # 尝试 True
    rotation=piomatter.Orientation.Normal
)

matrix = piomatter.PioMatter(
    colorspace=piomatter.Colorspace.RGB888Packed,
    pinout=piomatter.Pinout.AdafruitMatrixBonnet,
    framebuffer=framebuffer,
    geometry=geometry
)

matrix.show()

print("\n预期显示（从上到下）：")
print("  第 0-15 行：红色")
print("  第 16-31 行：绿色")
print("  第 32-47 行：蓝色")
print("  第 48-63 行：黄色")
print(f"\nFPS: {matrix.fps:.1f}")

response = input("\n显示是否正确？(y/n): ").strip().lower()

if response == 'y':
    print("\n✓ 太好了！正确的配置是：")
    print("   n_addr_lines=4")
    print("   serpentine=True")
    print("   pinout=AdafruitMatrixBonnet")
else:
    print("\n继续测试其他配置...")
    print("\n测试配置 2: serpentine=False")
    print("-"*60)
    
    geometry2 = piomatter.Geometry(
        width=64,
        height=64,
        n_addr_lines=4,
        serpentine=False,  # 尝试 False
        rotation=piomatter.Orientation.Normal
    )
    
    matrix2 = piomatter.PioMatter(
        colorspace=piomatter.Colorspace.RGB888Packed,
        pinout=piomatter.Pinout.AdafruitMatrixBonnet,
        framebuffer=framebuffer,
        geometry=geometry2
    )
    
    matrix2.show()
    print(f"\nFPS: {matrix2.fps:.1f}")
    
    response2 = input("\n这个配置正确吗？(y/n): ").strip().lower()
    
    if response2 == 'y':
        print("\n✓ 正确的配置是：")
        print("   n_addr_lines=4")
        print("   serpentine=False")
    else:
        print("\n如果两个都不对，请运行:")
        print("   python fix_16row_issue.py")
        print("\n那个工具会测试更多配置。")

print("\n完成！")

