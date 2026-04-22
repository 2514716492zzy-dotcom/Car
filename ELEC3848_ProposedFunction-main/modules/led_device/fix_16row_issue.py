#!/usr/bin/python3
"""
针对 "只有前16行和33-48行显示" 问题的专门测试工具

这个问题通常是因为：
1. serpentine 参数设置错误
2. 面板内部布线方式特殊
3. 需要自定义像素映射
"""

import numpy as np
import adafruit_blinka_raspberry_pi5_piomatter as piomatter
import time


def create_row_test_pattern(width, height):
    """创建行号测试图案 - 清楚显示每一行的编号"""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    
    # 每4行一组，用不同的颜色
    colors = [
        [255, 0, 0],      # 0-3: 红
        [0, 255, 0],      # 4-7: 绿
        [0, 0, 255],      # 8-11: 蓝
        [255, 255, 0],    # 12-15: 黄
        [255, 0, 255],    # 16-19: 洋红
        [0, 255, 255],    # 20-23: 青
        [255, 128, 0],    # 24-27: 橙
        [128, 0, 255],    # 28-31: 紫
        [255, 255, 255],  # 32-35: 白
        [128, 128, 128],  # 36-39: 灰
        [255, 0, 128],    # 40-43: 粉
        [0, 255, 128],    # 44-47: 青绿
        [128, 255, 0],    # 48-51: 黄绿
        [0, 128, 255],    # 52-55: 天蓝
        [255, 128, 128],  # 56-59: 浅红
        [128, 255, 255],  # 60-63: 浅青
    ]
    
    for y in range(height):
        color_idx = (y // 4) % len(colors)
        img[y, :] = colors[color_idx]
        
        # 每行开头画几个白点表示行号
        if y % 4 == 0:  # 每4行标记一次
            dots = y // 4
            for d in range(min(dots, 15)):
                start_x = d * 4
                if start_x + 2 < width:
                    img[y, start_x:start_x+2] = [255, 255, 255]
    
    return img


def test_config(name, n_addr_lines, serpentine, pinout=None):
    """测试单个配置"""
    if pinout is None:
        pinout = piomatter.Pinout.AdafruitMatrixBonnet
    
    print(f"\n{'='*60}")
    print(f"测试配置: {name}")
    print(f"  n_addr_lines: {n_addr_lines}")
    print(f"  serpentine: {serpentine}")
    print(f"  pinout: {pinout.name}")
    print(f"{'='*60}")
    
    try:
        geometry = piomatter.Geometry(
            width=64,
            height=64,
            n_addr_lines=n_addr_lines,
            serpentine=serpentine,
            rotation=piomatter.Orientation.Normal
        )
        
        # 创建行号测试图案
        framebuffer = create_row_test_pattern(64, 64)
        
        matrix = piomatter.PioMatter(
            colorspace=piomatter.Colorspace.RGB888Packed,
            pinout=pinout,
            framebuffer=framebuffer,
            geometry=geometry
        )
        
        matrix.show()
        time.sleep(0.3)
        
        print("\n当前显示行号测试图案：")
        print("  每 4 行一种颜色")
        print("  行首的白点表示行号（4的倍数）")
        print("\n请检查：")
        print("  - 哪些行有显示？")
        print("  - 颜色顺序是否正确？")
        print("  - 是否有重复或缺失？")
        print(f"\nFPS: {matrix.fps:.1f}")
        
        response = input("\n这个配置正确吗？(y/n): ").strip().lower()
        return response == 'y'
        
    except Exception as e:
        print(f"\n✗ 错误: {e}")
        return False


def main():
    print("="*60)
    print("  专门修复：只有前16行和33-48行显示的问题")
    print("="*60)
    print("\n你的症状：")
    print("  ✓ 第 0-15 行：有显示")
    print("  ✗ 第 16-32 行：无显示")
    print("  ✓ 第 33-48 行：有显示")
    print("  ✗ 第 49-64 行：无显示")
    print("\n这通常是 serpentine 参数或面板连接方式的问题。")
    print("\n按 Enter 开始测试...")
    input()
    
    # 针对性的测试配置
    configs = [
        ("配置1: n_addr=4, serpentine=False, RGB", 4, False, piomatter.Pinout.AdafruitMatrixBonnet),
        ("配置2: n_addr=4, serpentine=True, RGB", 4, True, piomatter.Pinout.AdafruitMatrixBonnet),
        ("配置3: n_addr=5, serpentine=False, RGB", 5, False, piomatter.Pinout.AdafruitMatrixBonnet),
        ("配置4: n_addr=5, serpentine=True, RGB", 5, True, piomatter.Pinout.AdafruitMatrixBonnet),
        ("配置5: n_addr=4, serpentine=False, BGR", 4, False, piomatter.Pinout.AdafruitMatrixBonnetBGR),
        ("配置6: n_addr=4, serpentine=True, BGR", 4, True, piomatter.Pinout.AdafruitMatrixBonnetBGR),
    ]
    
    for name, n_addr, serpentine, pinout in configs:
        if test_config(name, n_addr, serpentine, pinout):
            print(f"\n✓ 找到正确配置！")
            print(f"   配置: {name}")
            print(f"   n_addr_lines={n_addr}")
            print(f"   serpentine={serpentine}")
            print(f"   pinout={pinout.name}")
            
            # 保存配置
            save = input("\n保存这个配置到 verified_config.py？(y/n): ").strip().lower()
            if save == 'y':
                save_config(n_addr, serpentine, pinout)
            break
    else:
        print("\n⚠️ 标准配置无法解决问题")
        print("\n可能需要自定义像素映射。请看下面的说明...")
        print_custom_mapping_info()


def save_config(n_addr_lines, serpentine, pinout):
    """保存配置"""
    import time
    
    code = f'''#!/usr/bin/python3
"""
验证通过的配置 - 修复了 16 行显示问题
生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}
"""

import numpy as np
import adafruit_blinka_raspberry_pi5_piomatter as piomatter

# 面板配置
WIDTH = 64
HEIGHT = 64
N_ADDR_LINES = {n_addr_lines}
SERPENTINE = {serpentine}
PINOUT = piomatter.Pinout.{pinout.name}
ROTATION = piomatter.Orientation.Normal


def create_matrix(framebuffer):
    """创建配置好的矩阵对象"""
    geometry = piomatter.Geometry(
        width=WIDTH,
        height=HEIGHT,
        n_addr_lines=N_ADDR_LINES,
        serpentine=SERPENTINE,
        rotation=ROTATION
    )
    
    matrix = piomatter.PioMatter(
        colorspace=piomatter.Colorspace.RGB888Packed,
        pinout=PINOUT,
        framebuffer=framebuffer,
        geometry=geometry
    )
    
    return matrix


def main():
    """测试显示"""
    framebuffer = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    
    # 四象限测试
    framebuffer[0:32, 0:32] = [255, 0, 0]
    framebuffer[0:32, 32:64] = [0, 255, 0]
    framebuffer[32:64, 0:32] = [0, 0, 255]
    framebuffer[32:64, 32:64] = [255, 255, 0]
    
    matrix = create_matrix(framebuffer)
    matrix.show()
    
    print("配置已加载，显示测试图案")
    print(f"FPS: {{matrix.fps:.1f}}")
    input("按 Enter 退出...")


if __name__ == "__main__":
    main()
'''
    
    with open("verified_config.py", "w", encoding="utf-8") as f:
        f.write(code)
    
    print(f"\n✓ 配置已保存到 verified_config.py")


def print_custom_mapping_info():
    """打印自定义映射信息"""
    print("\n" + "="*60)
    print("  需要自定义像素映射")
    print("="*60)
    print("\n你的面板可能有特殊的内部布线方式。")
    print("根据 '只有第0-15行和33-48行显示' 的症状，")
    print("面板可能是这样布线的：")
    print()
    print("  物理面板          →    逻辑地址")
    print("  第 0-15 行        →    地址 0-15")
    print("  第 16-32 行       →    (未连接或错位)")
    print("  第 33-48 行       →    地址 0-15 (重复)")
    print("  第 49-64 行       →    (未连接或错位)")
    print()
    print("建议：")
    print("1. 检查面板背面的标注（型号、扫描方式）")
    print("2. 查看卖家提供的数据手册")
    print("3. 确认面板是否是单块还是拼接的")
    print("4. 检查排线连接是否完整")
    print()
    print("如果确认硬件无问题，可能需要编写自定义映射。")
    print("这需要了解面板的具体扫描方式。")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n已中断")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()

