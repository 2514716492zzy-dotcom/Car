#!/usr/bin/python3
"""
测试不同的LED矩阵配置
用于诊断显示问题（扩展版）
"""

import pathlib
import numpy as np
import PIL.Image as Image
import adafruit_blinka_raspberry_pi5_piomatter as piomatter

def test_configuration(config_name, n_addr_lines, serpentine, pinout=None, rotation=None):
    """测试指定配置"""
    if pinout is None:
        pinout = piomatter.Pinout.AdafruitMatrixBonnet
    if rotation is None:
        rotation = piomatter.Orientation.Normal
        
    print(f"\n{'='*50}")
    print(f"测试配置: {config_name}")
    print(f"n_addr_lines={n_addr_lines}, serpentine={serpentine}")
    print(f"pinout={pinout.name}, rotation={rotation.name}")
    print(f"{'='*50}")
    
    geometry = piomatter.Geometry(
        width=64, 
        height=64, 
        n_addr_lines=n_addr_lines,
        serpentine=serpentine,
        rotation=rotation
    )
    
    # 尝试加载测试图片，如果不存在则使用简单图案
    image_path = pathlib.Path(__file__).parent / "blinka64x64.png"
    if image_path.exists():
        framebuffer = np.asarray(Image.open(image_path))
    else:
        # 创建简单的四象限测试图案
        framebuffer = np.zeros((64, 64, 3), dtype=np.uint8)
        framebuffer[0:32, 0:32] = [255, 0, 0]    # 左上红
        framebuffer[0:32, 32:64] = [0, 255, 0]   # 右上绿
        framebuffer[32:64, 0:32] = [0, 0, 255]   # 左下蓝
        framebuffer[32:64, 32:64] = [255, 255, 0] # 右下黄
    
    matrix = piomatter.PioMatter(
        colorspace=piomatter.Colorspace.RGB888Packed,
        pinout=pinout,
        framebuffer=framebuffer,
        geometry=geometry
    )
    
    matrix.show()
    print(f"FPS: {matrix.fps:.2f}")
    print("\n查看显示效果，如果正确按 'y'，否则按 Enter 继续测试...")
    
    response = input().strip().lower()
    return response == 'y'

# 配置列表：(名称, n_addr_lines, serpentine, pinout, rotation)
configurations = [
    # 基础 RGB 配置
    ("两个64x32面板-蛇形连接-RGB", 4, True, piomatter.Pinout.AdafruitMatrixBonnet, piomatter.Orientation.Normal),
    ("两个64x32面板-平行连接-RGB", 4, False, piomatter.Pinout.AdafruitMatrixBonnet, piomatter.Orientation.Normal),
    ("单个64x64面板-1/32扫描-RGB", 5, False, piomatter.Pinout.AdafruitMatrixBonnet, piomatter.Orientation.Normal),
    ("单个64x64面板-1/32扫描-蛇形-RGB", 5, True, piomatter.Pinout.AdafruitMatrixBonnet, piomatter.Orientation.Normal),
    
    # BGR 配置（颜色通道反转）
    ("两个64x32面板-平行连接-BGR", 4, False, piomatter.Pinout.AdafruitMatrixBonnetBGR, piomatter.Orientation.Normal),
    ("单个64x64面板-1/32扫描-BGR", 5, False, piomatter.Pinout.AdafruitMatrixBonnetBGR, piomatter.Orientation.Normal),
    
    # 旋转配置
    ("两个64x32面板-平行-旋转180", 4, False, piomatter.Pinout.AdafruitMatrixBonnet, piomatter.Orientation.R180),
    ("单个64x64面板-旋转180", 5, False, piomatter.Pinout.AdafruitMatrixBonnet, piomatter.Orientation.R180),
]

print("="*50)
print("LED矩阵配置测试工具（扩展版）")
print("="*50)
print("\n将依次测试不同配置，找到正确的显示效果")
print("注意：如果没有 blinka64x64.png，将使用四象限测试图案")

for config in configurations:
    try:
        if test_configuration(*config):
            print(f"\n✅ 找到正确配置: {config[0]}")
            print(f"   n_addr_lines={config[1]}")
            print(f"   serpentine={config[2]}")
            print(f"   pinout={config[3].name}")
            print(f"   rotation={config[4].name}")
            break
    except Exception as e:
        print(f"❌ 配置失败: {e}")
        continue
else:
    print("\n⚠️ 所有标准配置都不匹配")
    print("建议运行完整诊断工具: python diagnose_panel.py")

