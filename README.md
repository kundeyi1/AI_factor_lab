# AI Factor Lab

AI Factor Lab 是一个独立维护的因子研究网站。FastAPI 同时提供静态网页和回测 API；浏览器负责交互，Python 进程负责读取本地行情、计算因子、执行分层回测并返回净值与绩效指标。

项目仓库：<https://github.com/kundeyi1/AI_factor_lab>

## 功能

- 使用自然语言生成因子表达式（可选，需要 DeepSeek 或 OpenAI API Key）
- 手工编辑并校验因子表达式
- 沪深 300、中证 500、中证 1000 和三者合并股票池
- 日、周、月频分层回测
- 净值曲线和绩效指标展示
- 本地因子收藏

## 数据约定

通过 `QUANT_DATA_ROOT` 指定数据根目录：

```text
$QUANT_DATA_ROOT/
├── market/stock/daily/qfq/*.parquet
└── reference/index_constituents/
    ├── 000300_comp.csv
    ├── 000905_comp.csv
    └── 000852_comp.csv
```

每只股票一个前复权 Parquet，至少包含：

```text
date, open, high, low, close, volume, amount
```

历史成分股文件必须能够解析出 `code`、`indate` 和 `outdate`。没有设置 `QUANT_DATA_ROOT` 时，Windows 会优先检查 `D:/DATA`，macOS/Linux 会优先检查 `~/DATA`，最后使用仓库内的 `data/`。

真实行情和运行结果不进入 Git。

## 本地安装

Docker 不是本地运行的必要条件。Python 3.11 和虚拟环境即可：

```bash
git clone https://github.com/kundeyi1/AI_factor_lab.git
cd AI_factor_lab
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Windows PowerShell 使用：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 启动

macOS/Linux：

```bash
export QUANT_DATA_ROOT="$HOME/DATA"
python -m uvicorn server.main:app --host 127.0.0.1 --port 8010
```

Windows：

```powershell
$env:QUANT_DATA_ROOT = "D:\DATA"
.\start.ps1
```

浏览器访问 <http://127.0.0.1:8010>。

## 独立性验证

下面的 smoke 会在临时目录生成合成行情和历史成分股，不读取另一个 Quant checkout，也不访问网络：

```bash
python scripts/standalone_smoke.py
```

合成数据只用于验证运行框架，不能用于投资结论。

## AI 配置

不使用 AI 时，可以直接编辑表达式并回测。需要 AI 时，通过环境变量提供服务器端密钥：

```bash
export DEEPSEEK_API_KEY="..."
export OPENAI_API_KEY="..."
```

不要把密钥写入源码、`.env` 或提交到 Git。

## 部署说明

Docker 只在目标托管平台需要容器镜像时才需要，例如 Hugging Face Docker Space。项目本身不依赖 Docker；如果改用支持直接启动 Python Web 服务的平台，可以直接安装 `requirements.txt` 并运行 Uvicorn。

部署时需要另外处理行情数据挂载、匿名访问限流、共享因子状态和模型 API 配额。当前仓库首先保证单机和独立环境可复现。
