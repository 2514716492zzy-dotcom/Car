# 64x64 LED 面板使用指南

## 快速开始

如果你的 64x64 LED 面板显示不正确，请按照以下步骤操作：

### 第一步：运行自动诊断

```bash
cd examples
python diagnose_panel.py
```

这个工具会自动测试多种配置，找到适合你面板的参数。

### 第二步：观察测试图案

程序会显示**四象限图案**：
- **左上角** 应该是 **红色**
- **右上角** 应该是 **绿色**  
- **左下角** 应该是 **蓝色**
- **右下角** 应该是 **黄色**
- **中间** 有 **白色十字**

### 第三步：根据显示效果反馈

根据实际显示情况，输入对应的按键：

| 显示效果 | 按键 | 说明 |
|---------|------|------|
| 完全正确 | `y` | 保存配置并继续 |
| 颜色反了（红变蓝） | `c` | 将测试 BGR 配置 |
| 方向不对（旋转了） | `r` | 将测试其他方向 |
| 差不多但不完美 | `w` | 记录为候选 |
| 完全错误 | `n` | 跳过此配置 |
| 退出程序 | `q` | 结束诊断 |

### 第四步：使用验证的配置

找到正确配置后，工具会自动生成 `verified_config.py`。

**运行验证：**
```bash
python verified_config.py
```

**在你的代码中使用：**
```python
from verified_config import create_matrix
import numpy as np

# 创建图像数据 (64x64 RGB)
framebuffer = np.zeros((64, 64, 3), dtype=np.uint8)

# 绘制一些内容
framebuffer[10:20, 10:20] = [255, 0, 0]  # 红色方块

# 使用验证的配置
matrix = create_matrix(framebuffer)
matrix.show()

input("按 Enter 退出...")
```

---

## 常见显示问题

### 问题 1：图像压缩或重复在上下两半

**症状：** 
- 64 行的图像只显示在上半部分
- 或者上下各显示一半，内容重复

**原因：** `n_addr_lines` 设置错误

**解决：**
- 如果是**真正的 64x64 单板**，试试 `n_addr_lines=5`
- 如果是**两块 64x32 拼接**，应该用 `n_addr_lines=4`

### 问题 2：颜色完全错误

**症状：**
- 红色显示成蓝色
- 蓝色显示成红色
- 绿色还是绿色

**原因：** 面板使用 BGR 而非 RGB 顺序

**解决：** 使用 BGR 引脚配置
```python
pinout = piomatter.Pinout.AdafruitMatrixBonnetBGR
```

### 问题 3：图像左右镜像或倒置

**症状：**
- 图像上下颠倒
- 或者左右镜像

**原因：** 面板方向或连接方式

**解决：** 调整旋转参数
```python
rotation = piomatter.Orientation.R180  # 旋转180度
# 或者
rotation = piomatter.Orientation.CW   # 顺时针90度
rotation = piomatter.Orientation.CCW  # 逆时针90度
```

### 问题 4：像素错位但有规律

**症状：**
- 每行的像素位置都错了
- 但错位有规律性

**原因：** `serpentine` 参数错误

**解决：**
```python
serpentine = True   # 如果面板是蛇形连接
serpentine = False  # 如果面板是平行连接
```

---

## 手动配置参数说明

如果你想手动尝试配置，以下是参数说明：

### 基本配置示例

```python
import numpy as np
import adafruit_blinka_raspberry_pi5_piomatter as piomatter

# 定义几何参数
geometry = piomatter.Geometry(
    width=64,              # 面板宽度（像素）
    height=64,             # 面板高度（像素）
    n_addr_lines=4,        # 地址线数：4 或 5
    serpentine=False,      # 蛇形模式：True 或 False
    rotation=piomatter.Orientation.Normal  # 旋转方向
)

# 创建帧缓冲（必须是 uint8 类型的 numpy 数组）
framebuffer = np.zeros((64, 64, 3), dtype=np.uint8)

# 初始化驱动
matrix = piomatter.PioMatter(
    colorspace=piomatter.Colorspace.RGB888Packed,
    pinout=piomatter.Pinout.AdafruitMatrixBonnet,
    framebuffer=framebuffer,
    geometry=geometry
)

# 更新显示
matrix.show()
```

### 参数详解

#### `n_addr_lines` (地址线数)

| 值 | 扫描方式 | 适用场景 |
|----|---------|---------|
| 4 | 1/16 扫描 | 两块 64x32 拼接 |
| 5 | 1/32 扫描 | 单块 64x64 面板 |

#### `serpentine` (蛇形布线)

| 值 | 说明 | 适用场景 |
|----|------|---------|
| False | 平行连接 | 单块面板或所有面板同方向 |
| True | 蛇形连接 | 多块面板"之"字形连接 |

#### `pinout` (引脚配置)

| 值 | 说明 |
|----|------|
| `piomatter.Pinout.AdafruitMatrixBonnet` | Adafruit 扩展板，RGB 顺序 |
| `piomatter.Pinout.AdafruitMatrixBonnetBGR` | Adafruit 扩展板，BGR 顺序 |
| `piomatter.Pinout.Active3` | Active-3 板，RGB 顺序 |
| `piomatter.Pinout.Active3BGR` | Active-3 板，BGR 顺序 |

#### `rotation` (旋转方向)

| 值 | 说明 |
|----|------|
| `piomatter.Orientation.Normal` | 正常方向 |
| `piomatter.Orientation.R180` | 旋转 180 度 |
| `piomatter.Orientation.CW` | 顺时针 90 度 |
| `piomatter.Orientation.CCW` | 逆时针 90 度 |

---

## 推荐配置组合

### 单块 64x64 面板（常见）

```python
geometry = piomatter.Geometry(
    width=64,
    height=64,
    n_addr_lines=5,      # 1/32 扫描
    serpentine=False,
    rotation=piomatter.Orientation.Normal
)
```

### 两块 64x32 拼接（垂直堆叠）

```python
geometry = piomatter.Geometry(
    width=64,
    height=64,
    n_addr_lines=4,      # 1/16 扫描
    serpentine=False,    # 或 True，取决于连接方式
    rotation=piomatter.Orientation.Normal
)
```

### 颜色反了

```python
# 只需要改 pinout
pinout = piomatter.Pinout.AdafruitMatrixBonnetBGR
```

---

## 其他工具

### quick_test.py - 快速测试

适合快速验证某个特定配置：

1. 编辑 `quick_test.py` 顶部的参数
2. 运行 `python quick_test.py`
3. 观察效果

### test_pattern_generator.py - 图案生成器

生成各种测试图案的 PNG 文件：

```bash
python test_pattern_generator.py
```

生成的图案包括：
- 渐变图案
- 网格图案
- 色条图案
- 四象限图案
- 行号标记
- 角落标记
- 扫描测试

---

## 性能优化

### 提高帧率

如果需要更高的刷新率，可以降低颜色深度：

```python
geometry = piomatter.Geometry(
    width=64,
    height=64,
    n_addr_lines=5,
    serpentine=False,
    n_planes=8,           # 降低到 8（默认 10）
    n_temporal_planes=2   # 时间抖动（默认 2）
)
```

- `n_planes`: 颜色位深度（1-10），越低帧率越高但颜色越少
- `n_temporal_planes`: 时间抖动平面数（0/2/4），可提升帧率但会轻微闪烁

---

## 故障排除

### 完全没有显示

1. **检查电源**：LED 面板需要独立 5V 电源（3A+）
2. **检查连接**：确认排线插紧，方向正确
3. **检查 PIO 设备**：
   ```bash
   ls -l /dev/pio0
   ```
   应该显示存在且有权限

### 显示但不稳定

1. **电源不足**：使用更大功率的电源
2. **排线质量**：使用屏蔽良好的短排线
3. **降低刷新率**：减少 `n_planes`

### 颜色暗淡

1. **增加亮度**：在绘图时提高 RGB 值
2. **检查 Gamma 校正**：默认使用 γ=2.2
3. **检查电源电压**：确保稳定在 5V

---

## 示例代码

### 显示静态图片

```python
import numpy as np
from PIL import Image
from verified_config import create_matrix

# 加载并调整图片大小
img = Image.open("your_image.png")
img = img.resize((64, 64))
framebuffer = np.asarray(img)

# 显示
matrix = create_matrix(framebuffer)
matrix.show()
input("按 Enter 退出...")
```

### 动画效果

```python
import numpy as np
from verified_config import create_matrix
import time

framebuffer = np.zeros((64, 64, 3), dtype=np.uint8)
matrix = create_matrix(framebuffer)

# 移动的方块
for x in range(64):
    framebuffer[:, :] = 0  # 清空
    framebuffer[20:30, x:x+10] = [255, 0, 0]  # 红色方块
    matrix.show()
    time.sleep(0.05)
```

### 实时更新

```python
import numpy as np
from verified_config import create_matrix
import time

framebuffer = np.zeros((64, 64, 3), dtype=np.uint8)
matrix = create_matrix(framebuffer)

try:
    frame = 0
    while True:
        # 更新内容
        framebuffer[:, :] = [
            (frame * 5) % 256,
            (frame * 3) % 256,
            (frame * 7) % 256
        ]
        matrix.show()
        frame += 1
        time.sleep(0.02)  # 约 50 FPS
except KeyboardInterrupt:
    print("\n退出")
```

---

## 需要更多帮助？

1. 阅读 `README_DIAGNOSTIC_TOOLS.md` 了解诊断工具详情
2. 查看官方文档：https://learn.adafruit.com/rgb-matrix-panels-with-raspberry-pi-5
3. 确认面板型号和规格（查看卖家提供的资料）
4. 如果所有配置都不行，可能需要自定义像素映射（高级功能）

祝你使用愉快！🎉

