#!/usr/bin/python3
"""
LED 面板自动诊断工具

这个工具会自动测试各种配置组合，帮助你找到正确的面板配置。
使用方法：
    python diagnose_panel.py

按照提示观察显示效果并输入反馈。
"""

import sys
import time
import numpy as np
from pathlib import Path

try:
    import adafruit_blinka_raspberry_pi5_piomatter as piomatter
except ImportError:
    print("错误：无法导入 adafruit_blinka_raspberry_pi5_piomatter")
    print("请确保已安装该库：pip install Adafruit-Blinka-Raspberry-Pi5-Piomatter")
    sys.exit(1)

# 导入测试图案生成器
try:
    from test_pattern_generator import create_all_patterns
except ImportError:
    print("警告：无法导入 test_pattern_generator.py")
    print("将使用简单的测试图案")
    
    def create_all_patterns(width, height):
        """简化版图案生成"""
        patterns = {}
        
        # 简单的四象限图案
        img = np.zeros((height, width, 3), dtype=np.uint8)
        mid_x, mid_y = width // 2, height // 2
        img[0:mid_y, 0:mid_x] = [255, 0, 0]  # 左上红
        img[0:mid_y, mid_x:] = [0, 255, 0]   # 右上绿
        img[mid_y:, 0:mid_x] = [0, 0, 255]   # 左下蓝
        img[mid_y:, mid_x:] = [255, 255, 0]  # 右下黄
        patterns['quadrant'] = ('四象限测试', img)
        
        # 色条图案
        img2 = np.zeros((height, width, 3), dtype=np.uint8)
        bar_height = height // 3
        img2[0:bar_height, :] = [255, 0, 0]           # 红
        img2[bar_height:2*bar_height, :] = [0, 255, 0]  # 绿
        img2[2*bar_height:, :] = [0, 0, 255]          # 蓝
        patterns['colorbars'] = ('RGB色条', img2)
        
        return patterns


class PanelDiagnostic:
    """面板诊断类"""
    
    def __init__(self, width=64, height=64):
        self.width = width
        self.height = height
        self.successful_configs = []
        self.test_patterns = create_all_patterns(width, height)
        
    def print_header(self, text):
        """打印标题"""
        print("\n" + "=" * 60)
        print(f"  {text}")
        print("=" * 60)
    
    def test_configuration(self, config_name, n_addr_lines, serpentine, 
                          pinout, rotation=piomatter.Orientation.Normal):
        """测试单个配置"""
        self.print_header(f"测试配置: {config_name}")
        
        print(f"  宽度: {self.width}")
        print(f"  高度: {self.height}")
        print(f"  地址线数 (n_addr_lines): {n_addr_lines}")
        print(f"  蛇形模式 (serpentine): {serpentine}")
        print(f"  引脚配置 (pinout): {pinout}")
        print(f"  旋转方向 (rotation): {rotation}")
        print("-" * 60)
        
        try:
            # 创建几何配置
            geometry = piomatter.Geometry(
                width=self.width,
                height=self.height,
                n_addr_lines=n_addr_lines,
                serpentine=serpentine,
                rotation=rotation
            )
            
            # 使用四象限图案作为主要测试
            if 'quadrant' in self.test_patterns:
                pattern_name, pattern_data = 'quadrant', self.test_patterns['quadrant'][1]
            else:
                pattern_name = 'colorbars'
                pattern_data = self.test_patterns['colorbars'][1]
            
            framebuffer = pattern_data.copy()
            
            # 初始化矩阵
            matrix = piomatter.PioMatter(
                colorspace=piomatter.Colorspace.RGB888Packed,
                pinout=pinout,
                framebuffer=framebuffer,
                geometry=geometry
            )
            
            # 显示测试图案
            matrix.show()
            time.sleep(0.5)  # 给硬件一点时间初始化
            
            print(f"\n当前显示: {self.test_patterns.get(pattern_name, (pattern_name,))[0]}")
            print("\n预期效果：")
            print("  左上角：红色")
            print("  右上角：绿色")
            print("  左下角：蓝色")
            print("  右下角：黄色")
            print("  中间：白色十字")
            
            print(f"\nFPS: {matrix.fps:.1f}")
            print("\n请观察显示效果：")
            print("  [y] - 显示正确，保存配置")
            print("  [c] - 颜色不对（RGB/BGR问题）")
            print("  [r] - 需要旋转")
            print("  [w] - 位置错乱但有希望")
            print("  [n] - 完全错误，跳过")
            print("  [q] - 退出诊断")
            
            while True:
                response = input("\n你的选择: ").strip().lower()
                
                if response == 'y':
                    print("✓ 配置正确！保存中...")
                    self.successful_configs.append({
                        'name': config_name,
                        'n_addr_lines': n_addr_lines,
                        'serpentine': serpentine,
                        'pinout': pinout,
                        'rotation': rotation,
                        'fps': matrix.fps
                    })
                    return 'success'
                
                elif response == 'c':
                    print("→ 颜色通道可能反了，将在下一轮测试 BGR 配置")
                    return 'color_issue'
                
                elif response == 'r':
                    print("→ 需要旋转，将测试其他方向")
                    return 'rotation_issue'
                
                elif response == 'w':
                    print("→ 记录为候选配置，继续测试")
                    return 'maybe'
                
                elif response == 'n':
                    print("✗ 跳过此配置")
                    return 'skip'
                
                elif response == 'q':
                    print("退出诊断...")
                    return 'quit'
                
                else:
                    print("无效输入，请输入 y/c/r/w/n/q")
            
        except Exception as e:
            print(f"\n✗ 配置失败: {e}")
            print(f"   错误类型: {type(e).__name__}")
            return 'error'
    
    def run_diagnostic(self):
        """运行完整诊断流程"""
        self.print_header("LED 面板自动诊断工具")
        print("\n本工具将测试多种配置组合，帮助你找到正确的面板参数。")
        print("请确保面板已正确连接到树莓派。")
        print("\n按 Enter 开始诊断...")
        input()
        
        # 测试配置列表
        test_configs = []
        
        # 基础配置：不同的 n_addr_lines 和 serpentine 组合
        for n_addr in [4, 5]:
            for serpentine in [False, True]:
                test_configs.append({
                    'name': f'n_addr={n_addr}, serpentine={serpentine}, RGB',
                    'n_addr_lines': n_addr,
                    'serpentine': serpentine,
                    'pinout': piomatter.Pinout.AdafruitMatrixBonnet,
                    'rotation': piomatter.Orientation.Normal
                })
        
        # BGR 配置
        for n_addr in [4, 5]:
            for serpentine in [False, True]:
                test_configs.append({
                    'name': f'n_addr={n_addr}, serpentine={serpentine}, BGR',
                    'n_addr_lines': n_addr,
                    'serpentine': serpentine,
                    'pinout': piomatter.Pinout.AdafruitMatrixBonnetBGR,
                    'rotation': piomatter.Orientation.Normal
                })
        
        # 旋转配置（针对最常见的设置）
        for rotation in [piomatter.Orientation.R180, piomatter.Orientation.CW, piomatter.Orientation.CCW]:
            test_configs.append({
                'name': f'n_addr=4, serpentine=False, RGB, rotation={rotation}',
                'n_addr_lines': 4,
                'serpentine': False,
                'pinout': piomatter.Pinout.AdafruitMatrixBonnet,
                'rotation': rotation
            })
        
        # 执行测试
        total = len(test_configs)
        for idx, config in enumerate(test_configs, 1):
            print(f"\n进度: [{idx}/{total}]")
            
            result = self.test_configuration(
                config['name'],
                config['n_addr_lines'],
                config['serpentine'],
                config['pinout'],
                config['rotation']
            )
            
            if result == 'success':
                print("\n🎉 找到正确配置！")
                self.save_config()
                
                cont = input("\n继续测试其他配置吗？(y/n): ").strip().lower()
                if cont != 'y':
                    break
            
            elif result == 'quit':
                break
            
            # 短暂延迟
            time.sleep(0.3)
        
        # 总结
        self.print_summary()
    
    def save_config(self):
        """保存成功的配置到文件"""
        if not self.successful_configs:
            return
        
        config = self.successful_configs[-1]
        
        # 生成配置代码
        code = f'''#!/usr/bin/python3
"""
验证通过的 LED 面板配置
由诊断工具自动生成于 {time.strftime('%Y-%m-%d %H:%M:%S')}

配置名称: {config['name']}
测试帧率: {config['fps']:.1f} FPS
"""

import numpy as np
import adafruit_blinka_raspberry_pi5_piomatter as piomatter

# 面板配置参数
PANEL_WIDTH = {self.width}
PANEL_HEIGHT = {self.height}
N_ADDR_LINES = {config['n_addr_lines']}
SERPENTINE = {config['serpentine']}
PINOUT = piomatter.Pinout.{config['pinout'].name}
ROTATION = piomatter.Orientation.{config['rotation'].name}
COLORSPACE = piomatter.Colorspace.RGB888Packed


def create_matrix(framebuffer):
    """
    创建并返回配置好的矩阵对象
    
    参数:
        framebuffer: numpy 数组，形状为 (height, width, 3)，dtype=uint8
    
    返回:
        piomatter.PioMatter 对象
    """
    geometry = piomatter.Geometry(
        width=PANEL_WIDTH,
        height=PANEL_HEIGHT,
        n_addr_lines=N_ADDR_LINES,
        serpentine=SERPENTINE,
        rotation=ROTATION
    )
    
    matrix = piomatter.PioMatter(
        colorspace=COLORSPACE,
        pinout=PINOUT,
        framebuffer=framebuffer,
        geometry=geometry
    )
    
    return matrix


def main():
    """示例：显示测试图案"""
    # 创建测试图案（四象限）
    framebuffer = np.zeros((PANEL_HEIGHT, PANEL_WIDTH, 3), dtype=np.uint8)
    
    mid_x = PANEL_WIDTH // 2
    mid_y = PANEL_HEIGHT // 2
    
    framebuffer[0:mid_y, 0:mid_x] = [255, 0, 0]        # 左上红
    framebuffer[0:mid_y, mid_x:] = [0, 255, 0]         # 右上绿
    framebuffer[mid_y:, 0:mid_x] = [0, 0, 255]         # 左下蓝
    framebuffer[mid_y:, mid_x:] = [255, 255, 0]        # 右下黄
    
    # 创建并显示
    matrix = create_matrix(framebuffer)
    matrix.show()
    
    print(f"配置: {config['name']}")
    print(f"FPS: {{matrix.fps:.1f}}")
    print("\\n按 Enter 退出...")
    input()


if __name__ == "__main__":
    main()
'''
        
        # 保存到文件
        output_file = Path(__file__).parent / "verified_config.py"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(code)
        
        print(f"\n✓ 配置已保存到: {output_file}")
        print("  可以直接运行: python verified_config.py")
        print("  或在你的代码中导入使用")
    
    def print_summary(self):
        """打印诊断总结"""
        self.print_header("诊断总结")
        
        if self.successful_configs:
            print(f"\n找到 {len(self.successful_configs)} 个成功的配置：\n")
            for idx, config in enumerate(self.successful_configs, 1):
                print(f"{idx}. {config['name']}")
                print(f"   - n_addr_lines: {config['n_addr_lines']}")
                print(f"   - serpentine: {config['serpentine']}")
                print(f"   - pinout: {config['pinout'].name}")
                print(f"   - rotation: {config['rotation'].name}")
                print(f"   - FPS: {config['fps']:.1f}")
                print()
            
            print("推荐使用第一个找到的配置。")
            print("配置代码已保存到 verified_config.py\n")
        else:
            print("\n未找到完全匹配的配置。")
            print("\n可能的原因：")
            print("  1. 面板型号特殊，需要自定义像素映射")
            print("  2. 硬件连接问题")
            print("  3. 电源供应不足")
            print("\n建议：")
            print("  1. 检查硬件连接")
            print("  2. 确认面板型号和规格")
            print("  3. 查看面板数据手册")
            print("  4. 尝试运行 test_pattern.py 生成测试图案\n")


def main():
    """主函数"""
    print("LED 面板诊断工具")
    print("=" * 60)
    
    # 获取面板尺寸
    print("\n请输入面板尺寸（直接按 Enter 使用默认值）：")
    
    width_input = input("  宽度 [默认: 64]: ").strip()
    width = int(width_input) if width_input else 64
    
    height_input = input("  高度 [默认: 64]: ").strip()
    height = int(height_input) if height_input else 64
    
    # 创建诊断对象并运行
    diagnostic = PanelDiagnostic(width=width, height=height)
    diagnostic.run_diagnostic()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n诊断已中断。")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

