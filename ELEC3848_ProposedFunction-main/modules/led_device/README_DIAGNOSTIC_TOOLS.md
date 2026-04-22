# LED 面板诊断工具使用指南

本目录包含一套完整的 LED 面板诊断工具，帮助你找到正确的面板配置参数。

## 工具列表

### 1. 自动诊断工具（推荐）

**`diagnose_panel.py`** - 全自动诊断工具

这是最推荐的工具，会自动测试多种配置组合。

```bash
python diagnose_panel.py
```

**功能：**
- 自动测试 16+ 种常见配置
- 交互式确认显示效果
- 自动生成正确的配置代码
- 保存到 `verified_config.py`

**使用流程：**
1. 运行程序并输入面板尺寸（默认 64x64）
2. 观察每个测试配置的显示效果
3. 根据提示输入反馈：
   - `y` - 显示正确，保存配置
   - `c` - 颜色不对（将测试 BGR）
   - `r` - 需要旋转
   - `w` - 有点像但不完全对
   - `n` - 完全错误，跳过
   - `q` - 退出
4. 工具会自动保存正确配置到 `verified_config.py`

---

### 2. 快速测试工具

**`quick_test.py`** - 快速验证特定配置

适合已经知道大概配置，需要微调参数的情况。

```bash
python quick_test.py
```

**使用方法：**
1. 编辑 `quick_test.py` 顶部的配置参数：
   ```python
   N_ADDR_LINES = 4  # 改成 4 或 5
   SERPENTINE = False  # 改成 True 或 False
   PINOUT = piomatter.Pinout.AdafruitMatrixBonnet  # 或 BGR
   TEST_PATTERN = 'quadrant'  # 选择测试图案
   ```
2. 运行脚本查看效果
3. 根据显示结果调整参数

**可用测试图案：**
- `quadrant` - 四象限（红绿蓝黄），检测方向
- `bars` - 色条，检测颜色通道
- `gradient` - 渐变，检测扫描方向
- `grid` - 网格，检测像素映射

---

### 3. 配置测试工具

**`test_configurations.py`** - 批量测试预定义配置

测试几种常见的配置组合。

```bash
python test_configurations.py
```

需要 `blinka64x64.png` 图片文件（如果没有会使用简单图案）。

---

### 4. 测试图案生成器

**`test_pattern_generator.py`** - 生成诊断图案

生成各种测试图案的 PNG 文件。

```bash
python test_pattern_generator.py
```

生成的图案可用于其他测试工具。

---

## 常见问题诊断

### 问题 1: 图像上下错位或重复

**可能原因：** `n_addr_lines` 设置错误

**解决方案：**
- 64x64 单板通常用 `n_addr_lines=5`（1/32 扫描）
- 两个 64x32 板拼接用 `n_addr_lines=4`（1/16 扫描）

### 问题 2: 颜色不对（红蓝反了）

**可能原因：** 面板使用 BGR 而非 RGB

**解决方案：**
```python
pinout = piomatter.Pinout.AdafruitMatrixBonnetBGR  # 而不是 RGB
```

### 问题 3: 图像左右镜像或上下颠倒

**可能原因：** 需要旋转或镜像

**解决方案：**
```python
rotation = piomatter.Orientation.R180  # 或 CW, CCW
```

### 问题 4: 显示错位但有规律

**可能原因：** `serpentine` 设置错误

**解决方案：**
- 单块面板通常用 `serpentine=False`
- 多块面板"之"字形连接用 `serpentine=True`

---

## 理解配置参数

### `n_addr_lines` - 地址线数量

决定面板扫描方式：
- `n_addr_lines=4` → 2^5 = 32 行（1/16 扫描）
- `n_addr_lines=5` → 2^6 = 64 行（1/32 扫描）

**如何判断：**
- 真正的 64x64 单板 → 通常是 5
- 两块 64x32 拼接 → 通常是 4

### `serpentine` - 蛇形布线

控制多面板拼接时的数据流向：
- `False` - 所有面板从左到右
- `True` - 偶数行反向（之字形）

```
serpentine=False:    serpentine=True:
→ → → →              → → → →
→ → → →              ← ← ← ←
→ → → →              → → → →
```

### `pinout` - 引脚配置

硬件接口和颜色顺序：
- `AdafruitMatrixBonnet` - RGB 顺序
- `AdafruitMatrixBonnetBGR` - BGR 顺序
- `Active3` / `Active3BGR` - Active-3 板

### `rotation` - 旋转方向

显示方向：
- `Normal` - 正常
- `R180` - 旋转 180°
- `CW` - 顺时针 90°
- `CCW` - 逆时针 90°

---

## 使用验证后的配置

运行 `diagnose_panel.py` 找到正确配置后，会生成 `verified_config.py`。

**方法 1：直接运行验证**
```bash
python verified_config.py
```

**方法 2：在你的代码中导入**
```python
from verified_config import create_matrix
import numpy as np

# 创建你的图像数据
framebuffer = np.zeros((64, 64, 3), dtype=np.uint8)
# ... 绘制你的内容 ...

# 使用验证的配置创建矩阵
matrix = create_matrix(framebuffer)
matrix.show()
```

**方法 3：复制参数到你的代码**
打开 `verified_config.py` 查看参数，复制到你的脚本中。

---

## 故障排除

### 工具无法运行

1. **检查库安装：**
   ```bash
   pip install Adafruit-Blinka-Raspberry-Pi5-Piomatter
   pip install numpy pillow
   ```

2. **检查 PIO 设备：**
   ```bash
   ls -l /dev/pio0
   ```
   应该显示存在且有读写权限。

3. **检查硬件连接：**
   - 电源是否充足（5V 3A+）
   - 排线是否插紧
   - 面板是否上电

### 所有配置都不对

如果标准配置都无效，可能需要：

1. **查看面板型号和数据手册**
2. **尝试调整其他参数：**
   - `n_planes` - 颜色深度（默认 10）
   - `n_temporal_planes` - 时间抖动（默认 2）
3. **使用自定义像素映射**（高级用户）

---

## 进一步帮助

- 查看主项目文档：[RGB Matrix Panels With Raspberry Pi 5](https://learn.adafruit.com/rgb-matrix-panels-with-raspberry-pi-5)
- GitHub Issues：[Adafruit_Blinka_Raspberry_Pi5_Piomatter](https://github.com/adafruit/Adafruit_Blinka_Raspberry_Pi5_Piomatter)
- 确认树莓派 5 固件和内核版本支持 PIO

---

## 工具更新日志

**2024 版本：**
- 新增 `diagnose_panel.py` 全自动诊断
- 新增 `quick_test.py` 快速测试
- 扩展 `test_configurations.py` 支持更多配置
- 新增测试图案生成器

希望这些工具能帮助你快速找到正确的配置！🎉

