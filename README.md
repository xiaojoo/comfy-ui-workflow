# comfy-ui-workflow

企业级设计资产流水线：品牌规范驱动，ComfyUI 作执行引擎，**质量门禁是产品本体**。

## 现在有什么

`icon-pipeline/` —— 图标资产线，已端到端跑通并量化：

- **L1 生成** Z-Image Turbo（int8，4s/张）→ **L4 抠图** BiRefNet → **L5 矢量化** vtracer
  → **L5.5 规范** viewBox/居中留白/烘 transform → **L5.6 调色板归约** → **L6 门禁**。
  单张全流程 5s。
- **3D 线** Hunyuan3D 2.1 图生 GLB（25s）+ 降面/焊接/补洞/UV 后处理链。
- **度量本身经过校准**：合成真值图标（6 个）与解析真值球体先验证尺子能分辨，
  再拿去量模型产物。门禁自检断言 6 种定向扰动各自只推动本轴指标、其他轴不动。
- **`server/` + `web/`**：FastAPI + SQLite 的批次队列、生成任务与 Vue3 界面。
  门禁表的列、阈值、逐格是否超预算全部由后端下发，前端不自行推导第二把尺子；
  启动即重跑尺子自检，尺子瞎了拒绝服务。
- **生成已接到引擎**：首页的三步向导真调 ComfyUI（Z-Image Turbo int8 + Qwen-3-4B fp8），
  模型下拉读的是引擎实时 `/object_info`，不是写死的清单。

细节、实测数字和已知缺点见 [icon-pipeline/README.md](icon-pipeline/README.md)。

## 怎么用

3D 与矢量化在 WSL 发行版 `ComfyUI` 内用 ComfyUI 自带的 venv 跑（该发行版无外网）；
后端与前端跑在 Windows 侧（门禁数字与 WSL 逐位一致，已量过）：

```bash
cd /mnt/h/workflow/icon-pipeline
bash run_all.sh                                        # 矢量化→门禁→规范→复量→尺子自检
/data/ComfyUI/venv/bin/python tools/qa_gate.py --dir run/ic
/data/ComfyUI/venv/bin/python tools/mesh_metrics.py <file.glb>
bash tools/run_d0.sh                                   # 抠图→纯色背景→3D→壳结构门禁
```

```bash
cd server && .venv/Scripts/python.exe -m uvicorn app.main:app --port 8191   # 后端
cd web && npm install && npm run dev                                        # 界面 http://localhost:5180
cd server && .venv/Scripts/python.exe -m pytest tests -q                    # 5 项验收
```

阈值、色板、栅格一律读 `icon-pipeline/brand-kit.example.json`，不散落在代码里。
`?lang=en` 或右上角按钮切中英文，默认中文。

## 已知缺点

- `path_nodes` 预算未达成，且已证伪三条后处理路径（详见 icon-pipeline/README）。
- 首页只交付了设计稿那一屏：生成、模板、参数、预览、执行日志、最近任务、存储条是真的；
  左侧另外 8 个导航项是显式「未实现」页，不摆假数据。
- 生成与门禁在界面上还是两次动作，没串成「生成→抠图→矢量化→门禁」一键。
- 模板只有 3 个。设计稿的 6 类里我们只有企业图标这一条实测链路；
  人像写真/电商主图/产品海报既无工作流也无门禁标准，且环境里没有 SDXL。
- 生成耗时冷热差一个量级：稳定态 3 张 1024×1024 实测 4.0–4.1s（显存稳定 ~3.1GB 空闲），
  但紧跟后端重启的那两次是 66.5s 和 160.2s。离群值未定位，最像是 11GiB 权重重新读盘
  （WSL 无 swap），没有证据就不写进结论。
- 看板不显示源图对照：后端只提供 SVG 端点，没有栅格图端点。
- 无鉴权，且 `POST /batches` 会按提交的路径读取后端可读文件、再经 `/svg` 回传。
  单机自用可接受，给多人用之前必须先加允许目录白名单。
- 视频线未开工，且受 WSL 内存上限阻塞（需 `.wslconfig` 提额）。
- 无 API key，所有 `partner/*` 云端节点不可用；矢量只有本地一条路。
