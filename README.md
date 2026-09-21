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

细节、实测数字和已知缺点见 [icon-pipeline/README.md](icon-pipeline/README.md)。

## 怎么用

全部在 WSL 发行版 `ComfyUI` 内用 ComfyUI 自带的 venv 跑（该发行版无外网）：

```bash
cd /mnt/h/workflow/icon-pipeline
bash run_all.sh                                        # 矢量化→门禁→规范→复量→尺子自检
/data/ComfyUI/venv/bin/python tools/qa_gate.py --dir run/ic
/data/ComfyUI/venv/bin/python tools/mesh_metrics.py <file.glb>
bash tools/run_d0.sh                                   # 抠图→纯色背景→3D→壳结构门禁
```

阈值、色板、栅格一律读 `icon-pipeline/brand-kit.example.json`，不散落在代码里。

## 已知缺点

- 尚无 Web 层：目前只有 CLI 与 ComfyUI HTTP API，没有任务队列与多人界面。
- `path_nodes` 预算未达成，且已证伪三条后处理路径（详见 icon-pipeline/README）。
- 视频线未开工，且受 WSL 内存上限阻塞（需 `.wslconfig` 提额）。
- 无 API key，所有 `partner/*` 云端节点不可用；矢量只有本地一条路。
