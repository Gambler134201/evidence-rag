# 阶段 0：环境核对

核对日期：2026-10-21（Asia/Shanghai）。项目：`E:\AIjob\gpt\rag`。

本记录由主脑在执行模型任务受阻后直接核对并编写。只读检查没有安装依赖、启动应用/数据库、连接其他项目数据库或调用产品模型。命令与端口结果是本次快照，未来使用前可能需要重新确认。

## 1. 实际结果

| 检查项 | 检查方式及结果 | 状态与含义 |
|---|---|---|
| Git | `git --version` → `2.56.0.windows.2`；`git status --short --branch` → `docs/stage0-environment-data`；本轮开始时干净，基线 `c60f0c2` | 已确认，可进行版本管理 |
| PATH 上的 Python | `Get-Command python,python3` 指向 `%LOCALAPPDATA%\Microsoft\WindowsApps` 应用执行别名 | 未确认可用于项目；不能由命令名存在推导解释器可运行，本轮不启动应用商店别名 |
| 工具内置 Python | Codex 提供的运行时路径，经绝对路径执行版本命令 → `3.12.14`；`import venv` 成功 | 已确认可执行；属于工具资源，不等于本项目已有依赖环境 |
| 本项目 Python 环境 | 当前没有 `.venv`、`pyproject.toml` 或锁文件 | 未建立；后续为本项目创建独立环境，不复用 Model Desk 的 venv |
| Python 启动器 | `Get-Command py` → 未找到 | 当前 PATH 未发现，不推断整机没有其他 Python |
| Node | `Get-Command node` → `E:\pi\node\node\node.exe`；`node --version` → `v22.23.3` | 已确认命令可运行；未验证项目依赖兼容性，也未锁版本 |
| npm | `Get-Command npm` → `E:\pi\node\node\npm.ps1`；`npm --version` → `10.9.9` | 已确认可运行；本项目尚无 `package.json` |
| pnpm | `Get-Command pnpm` 指向 Codex 工具内置 fallback；`pnpm --version` → `11.25.0` | 已确认可运行；项目尚未选定/锁定包管理器版本 |
| uv / uvx | `Get-Command uv,uvx -ErrorAction SilentlyContinue` → 未找到 | 当前 PATH 未发现；属于可选工具，不把 uv 缺失当作 Python 本身不可用 |
| Docker / Compose | `Get-Command docker,docker-compose` → 未找到 | 当前 PATH 未发现客户端；未做守护进程或 Compose 实际启动验证，不宣称整机绝对未安装 |
| PostgreSQL 客户端 | `Get-Command psql,pg_isready` → 未找到 | 当前 PATH 未发现客户端；不等于不存在远程数据库 |
| 本项目 PostgreSQL | 未配置本项目连接，未执行 SQL，候选 5432 无 TCP 监听 | 未验证；不能因端口空闲就说数据库已准备好 |
| pgvector | 未连接任何数据库，未查询扩展版本 | 未验证 |
| WSL | `Get-Command wsl` → `C:\WINDOWS\system32\wsl.exe` | 只确认入口存在；未枚举发行版、容器、服务或其中的模型配置 |

工具内置 Python 的本机绝对路径（仅作为环境记录，不应硬编码到应用源码或公共启动命令）：

```text
C:\Users\lu150\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
```

主脑使用该路径执行：

```python
import sys, venv
print(sys.version.split()[0])
print(sys.executable)
print("venv_module_available=True")
```

结果为 `3.12.14`、上述可执行路径及 `venv_module_available=True`。本轮没有创建项目 venv，也没有检验 pip、FastAPI、pypdf 或数据库驱动的项目级安装。

## 2. 候选端口

使用 `Get-NetTCPConnection -State Listen` 获取监听快照，再仅筛选下列端口：

| 端口 | TCP Listen 结果 | 用途候选 |
|---|---|---|
| 3000 | 无监听 | 前端 |
| 8000 | 无监听 | API |
| 5432 | 无监听 | PostgreSQL |

未检查 UDP；没有根据进程或端口推断所属项目。无监听也不保证之后绑定一定成功，应在实际启动时处理竞争或保留端口问题。

## 3. 本轮执行中断与修正

原执行任务 `20261021-164052-4c966c` 在写入交付物前触发 Model Desk 记录保护，7 个预期文件当时均不存在，主脑将其记录为受阻，未把 `completed` 或退出码 0 当作完成。

经用户同意由主脑接手后，定位到共享保护器把 `.md` 文件扩展名匹配为 `md` 命令，导致只读 Git 检查被误判。主脑修正该匹配并添加回归检查，保留真实记录写入、删除、别名和上级目录破坏的拦截，以及拒绝后暂停当前执行会话的机制。

在工作台项目中完成的离线验证：策略测试 21 项、DSH 离线运行时检查 32 项、Python 记录保护测试 21 项、Pi 适配器测试 5 项，均通过。没有调用真实推理模型、重启工作台或修改旧会话的暂停状态；后续原生会话验证未做。工作台有预先存在的未提交修改，本轮仅追加修正及测试，未替用户提交或发布该项目。

## 4. 后续动作与边界

1. 可以先用已验证的 Python 可执行文件为本项目建立独立环境，编写纯离线解析测试；工具路径只是本机启动选择，不作为应用分发依赖。
2. PostgreSQL + pgvector 默认路线仍为本项目专用实例。Docker 客户端当前未就绪，需要在安装阶段解决运行环境；本轮不改用其他项目数据库。
3. Node/npm/pnpm 可运行，后续选定项目版本并生成锁文件；工具升级可能改变路径，项目启动说明应有明确运行时要求。
4. 产品生成模型和 Embedding 来源、接口限制与费用边界仍待确认；本轮未尝试探测或借用开发协作模型端点。
5. 本轮仅完成环境快照和合成文档准备。M0 的 PRD、模型方案、真实连通与完整阶段验收尚未完成。

未执行：安装任何应用依赖、下载模型、启动/停止数据库或应用、修改其他项目配置、读取密钥/认证文件、数据库连接或远端发布。

## 5. 2026-10-24 增补（ZCode/GLM 会话，经用户授权）

- uv 0.13.0 现已在 PATH 可用（10-21 审计中未发现）；本项目已用 `uv sync` 建立独立 `.venv`（uv 托管 CPython 3.12.15，不再依赖工具内置解释器），依赖锁定于 `pyproject.toml` + `uv.lock`，当前仅 pypdf 6.21.2 与 pytest 9.1.1（含 dev 组）。原“PATH 上只有 WindowsApps 存根”的结论不再成立，但仍不使用任何全局解释器。
- ~~Docker 客户端仍不可用~~（已由 2026-10-24 当天后续取代）：用户批准容器路线后，Docker Desktop 4.96.3 + WSL2 组件已安装并重启生效；本项目专用 PostgreSQL 16.15 + pgvector 0.8.7 容器已启动并通过冒烟（扩展创建、L2 算子），过程见 `docs/worklog-20261024-zcode.md` §9。
- 本轮未启动任何服务、未调用任何模型；环境其余结论沿用 10-21 快照。
