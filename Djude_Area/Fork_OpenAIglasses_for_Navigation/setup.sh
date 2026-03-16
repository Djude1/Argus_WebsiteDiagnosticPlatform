#!/bin/bash
# AI Glass System - Linux/macOS 快速安装脚本

set -e  # 遇到错误立即退出

echo "=========================================="
echo "  AI Glass System - 自动安装脚本"
echo "=========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查 Python 版本
echo "正在检查 Python 版本..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: 未找到 Python 3${NC}"
    echo "请先安装 Python 3.9-3.11"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo -e "${GREEN}✓ 找到 Python $PYTHON_VERSION${NC}"

# 检查 Python 版本是否在支持范围内
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -ne 3 ] || [ "$PYTHON_MINOR" -lt 9 ] || [ "$PYTHON_MINOR" -gt 11 ]; then
    echo -e "${YELLOW}警告: Python 版本 $PYTHON_VERSION 可能不受支持${NC}"
    echo "推荐使用 Python 3.9-3.11"
    read -p "是否继续? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 检查 CUDA（可选）
echo ""
echo "正在检查 CUDA..."
if command -v nvidia-smi &> /dev/null; then
    echo -e "${GREEN}✓ 检测到 NVIDIA GPU${NC}"
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
    HAS_GPU=true
else
    echo -e "${YELLOW}! 未检测到 NVIDIA GPU，将使用 CPU 模式（速度较慢）${NC}"
    HAS_GPU=false
fi

# 创建虚拟环境
echo ""
echo "正在创建虚拟环境..."
if [ -d "venv" ]; then
    echo -e "${YELLOW}虚拟环境已存在${NC}"
    read -p "是否删除并重新创建? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf venv
        python3 -m venv venv
        echo -e "${GREEN}✓ 虚拟环境已重新创建${NC}"
    fi
else
    python3 -m venv venv
    echo -e "${GREEN}✓ 虚拟环境已创建${NC}"
fi

# 激活虚拟环境
echo "正在激活虚拟环境..."
source venv/bin/activate

# 升级 pip
echo ""
echo "正在升级 pip..."
pip install --upgrade pip -q
echo -e "${GREEN}✓ pip 已升级${NC}"

# 安装 PyTorch
echo ""
echo "正在安装 PyTorch..."
if [ "$HAS_GPU" = true ]; then
    echo "安装 GPU 版本 PyTorch (CUDA 11.8)..."
    pip install torch==2.0.1+cu118 torchvision==0.15.2+cu118 --index-url https://download.pytorch.org/whl/cu118 -q
else
    echo "安装 CPU 版本 PyTorch..."
    pip install torch torchvision -q
fi
echo -e "${GREEN}✓ PyTorch 已安装${NC}"

# 验证 PyTorch
echo "验证 PyTorch 安装..."
python3 -c "import torch; print(f'PyTorch 版本: {torch.__version__}'); print(f'CUDA 可用: {torch.cuda.is_available()}')"

# 安装系统依赖（Linux）
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo ""
    echo "正在检查系统依赖..."
    
    # 检测发行版
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
    else
        OS="unknown"
    fi
    
    if [ "$OS" = "ubuntu" ] || [ "$OS" = "debian" ]; then
        echo "检测到 Ubuntu/Debian 系统"
        echo "可能需要 sudo 权限来安装系统依赖..."
        sudo apt-get update -qq
        sudo apt-get install -y -qq portaudio19-dev libgl1-mesa-glx libglib2.0-0
        echo -e "${GREEN}✓ 系统依赖已安装${NC}"
    else
        echo -e "${YELLOW}! 未知的 Linux 发行版，请手动安装依赖${NC}"
        echo "  需要: portaudio19-dev, libgl1-mesa-glx, libglib2.0-0"
    fi
fi

# 安装 Python 依赖
echo ""
echo "正在安装 Python 依赖..."
pip install -r requirements.txt -q
echo -e "${GREEN}✓ Python 依赖已安装${NC}"

# 创建 .env 文件
echo ""
if [ ! -f ".env" ]; then
    echo "正在创建 .env 配置文件..."
    cp .env.example .env
    echo -e "${GREEN}✓ .env 文件已创建${NC}"
    echo -e "${YELLOW}请编辑 .env 文件，填入您的 DASHSCOPE_API_KEY${NC}"
else
    echo -e "${YELLOW}.env 文件已存在，跳过${NC}"
fi

# 创建必要的目录
echo ""
echo "正在创建目录结构..."
mkdir -p recordings model music voice
echo -e "${GREEN}✓ 目录结构已创建${NC}"

# 检查模型文件
echo ""
echo "正在检查模型文件..."
MODELS=("yolo-seg.pt" "yoloe-11l-seg.pt" "shoppingbest5.pt" "trafficlight.pt" "hand_landmarker.task")
MISSING_MODELS=()

for model in "${MODELS[@]}"; do
    if [ -f "model/$model" ]; then
        echo -e "${GREEN}✓ $model${NC}"
    else
        echo -e "${RED}✗ $model (缺失)${NC}"
        MISSING_MODELS+=("$model")
    fi
done

if [ ${#MISSING_MODELS[@]} -gt 0 ]; then
    echo ""
    echo -e "${YELLOW}警告: 缺少以下模型文件:${NC}"
    for model in "${MISSING_MODELS[@]}"; do
        echo "  - $model"
    done
    echo "请将模型文件放入 model/ 目录"
fi

# 完成
echo ""
echo "=========================================="
echo -e "${GREEN}安装完成!${NC}"
echo "=========================================="
echo ""
echo "下一步:"
echo "1. 编辑 .env 文件，填入您的 API 密钥:"
echo "   nano .env"
echo ""
echo "2. 确保所有模型文件已放入 model/ 目录"
echo ""
echo "3. 启动系统:"
echo "   source venv/bin/activate"
echo "   python app_main.py"
echo ""
echo "4. 访问 http://localhost:8081"
echo ""

# 提示激活虚拟环境
echo -e "${YELLOW}注意: 每次使用前请激活虚拟环境:${NC}"
echo "  source venv/bin/activate"
echo ""

