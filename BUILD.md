# 构建和发布指南

## 开发环境设置

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows

# 安装开发依赖
pip install -r requirements-dev.txt

# 安装包（开发模式）
pip install -e .
```

## 运行测试

```bash
# 运行所有测试
pytest

# 运行测试并生成覆盖率报告
pytest --cov=ffmpeg_audio --cov-report=html
```

## 代码格式化

```bash
# 使用 black 格式化代码
black src/ tests/

# 使用 ruff 检查代码
ruff check src/ tests/
```

## 构建包

```bash
# 安装构建工具
pip install build

# 构建源码包和 wheel 包
python -m build

# 构建后的文件会在 dist/ 目录下
```

## 发布到 PyPI

### 测试发布（TestPyPI）

```bash
# 安装 twine
pip install twine

# 上传到 TestPyPI
twine upload --repository testpypi dist/*

# 测试安装
pip install --index-url https://test.pypi.org/simple/ ffmpeg-audio
```

### 正式发布

```bash
# 上传到 PyPI
twine upload dist/*

# 验证安装
pip install ffmpeg-audio
```

## 版本更新

更新版本号：

1. 修改 `pyproject.toml` 中的 `version` 字段
2. 修改 `src/ffmpeg_audio/__init__.py` 中的 `__version__` 变量
3. 提交更改并创建 git tag

```bash
git tag v0.1.0
git push origin v0.1.0
```
