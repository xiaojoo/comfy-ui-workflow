// Chinese first, with an in-app switch. Column labels and nav labels are looked up
// by the key the API sends and fall back to the raw key, so a metric or template
// added on the backend still shows up instead of silently vanishing.
import { reactive, computed } from 'vue'

const dict = {
  zh: {
    app: 'AI 图像生成', brand: 'AI 图像生成 · 企业级创意生产平台',
    tagline: '基于 ComfyUI 工作流引擎，结合质量门禁，产出可交付的设计资产',
    langToggle: 'English',
    search: '搜索模板、任务、工作流…',
    nav: {
      home: '首页', generate: '图像生成', workflows: '工作流管理', tasks: '任务管理',
      models: '模型管理', library: '资源库', batch: '批量任务', schedule: '定时任务',
      gate: 'AI 评估', logs: '日志与监控',
    },
    navTodo: '该模块尚未实现',
    navTodoBody: '这一版只交付首页与「AI 评估」门禁表。此处不放假数据。',
    features: {
      models: ['多模型支持', 'Flux / Z-Image 等'],
      flow: ['可视化工作流', '灵活编排，专业高效'],
      batch: ['批量生成', '提升生产力'],
      gate: ['智能评估', '自动筛选优质结果'],
    },
    wizard: ['选择模板', '配置参数', '预览 & 生成'],
    categoryAll: '全部',
    categories: { enterprise_icon: '企业图标', poster: '产品海报', portrait: '人像写真',
                  ecommerce: '电商设计', style: '风格化', custom: '自定义' },
    verified: '已验证', unverified: '未验证',
    pairMeasured: '已量配对', pairUnmeasured: '权重未量过',
    verifiedTip: '这套权重组合我们跑过 8/8 并通过门禁',
    unverifiedTip: '引擎里有这个权重，但我们没量过它的图标产出',
    paramTitle: '参数配置',
    model: '模型选择', prompt: '正向提示词', negative: '负向提示词',
    size: '图片尺寸', steps: '采样步数', cfg: 'CFG Scale', seed: '随机种子',
    batchN: '单次张数', advanced: '高级参数',
    shift: 'Shift', sampler: '采样器', scheduler: '调度器', denoise: '重绘幅度',
    length: '帧数（须 4k+1）', fps: '帧率', image: '输入图（ComfyUI input 目录内文件名）',
    octree: 'octree 分辨率', threshold: '表面阈值',
    generate: '生成图像', generateVideo: '生成视频', generateModel: '生成网格', generating: '生成中…',
    needPrompt: '提示词不能为空',
    preview: '预览结果', noPreview: '还没有结果。选模板、填提示词，点「生成图像」。',
    variants: '本次结果', taskStatus: '任务状态', execLog: '工作流执行日志',
    download: '下载', favorite: '收藏', favorited: '已收藏',
    progress: '进度', elapsed: '耗时', modelUsed: '模型', created: '生成时间', taskId: '任务 ID',
    state: { queued: '排队中', running: '进行中', done: '已完成', error: '失败' },
    recent: '最近任务', tabAll: '全部', tabRunning: '进行中', tabDone: '已完成', tabFailed: '失败',
    th: { ref: '任务 ID', template: '模板名称', model: '模型', params: '参数',
          state: '状态', created: '创建时间', actions: '操作', asset: '资产', verdict: '判定',
          approved: '审批', actionsBtn: '操作', fails: '不合格项',
          paths: '路径数', path_nodes: '节点数', colors: '颜色数', max_delta_e: '最大色差',
          alpha_iou: '轮廓 IoU', chamfer_grid_px: 'chamfer', hausdorff_p95_grid_px: 'hausdorff p95',
          interior_rmse: '内部 RMSE', interior_rmse_vs_snapped: '内部 RMSE(色板对齐)',
          thumb_ssim_16: '16px SSIM', bbox_center_offset_pct: '居中偏移%', fill_ratio: '填充占比' },
    view: '查看', emptyTasks: '还没有任务。',
    storage: '存储空间', usedOf: '已用',
    engineTitle: '执行引擎', device: '设备', vramFree: '显存空闲', ramFree: '内存空闲', version: '版本',
    gateTitle: '门禁看板', gateSub: '批次队列 · 质量门禁 · 审批',
    // gate board strings
    subtitle: '批次队列 · 质量门禁 · 审批',
    health: '服务', ok: '在线', degraded: '异常', queuedAhead: '队列中',
    newBatch: '新建批次', batchName: '批次名', sourcePng: '源图 PNG 路径', rawSvg: '原始 SVG 路径',
    addRow: '加一行', removeRow: '删',
    itemsHint: '一台机器一次只跑一个资产，源路径须是后端能读到的本地文件。',
    submit: '提交批次', submitting: '提交中…', needName: '批次名不能为空', needRows: '至少填一行',
    batches: '批次', refresh: '刷新', noBatches: '还没有批次。', finished: '完成',
    verdict: { PASS: '通过', FAIL: '拒收', UNVERIFIED: '未验证' },
    approval: { pending: '待审', approved: '已批准', rejected: '已驳回' },
    approve: '批准', reject: '驳回', approveBlocked: '门禁未通过，不可交付',
    limitMax: '≤', limitMin: '≥', limitBand: '目标', limitAdvisory: '参考',
    stages: { raw: '矢量化原始', norm: '规范化', flat: '交付件' },
    selectBatch: '选一个批次看门禁表', loading: '读取中…', errorNone: '无',
    previewTitle: '渲染对照', previewHint: '同一资产三个阶段；24px 是真实落地尺寸。',
    colsNote: '列与阈值都由后端下发，前端不自行推导。',
  },
  en: {
    app: 'AI Image Studio', brand: 'AI Image Studio · enterprise creative production',
    tagline: 'ComfyUI workflow engine plus a measured quality gate, producing shippable design assets',
    langToggle: '中文',
    search: 'Search templates, tasks, workflows…',
    nav: {
      home: 'Home', generate: 'Generation', workflows: 'Workflows', tasks: 'Tasks',
      models: 'Models', library: 'Assets', batch: 'Batch jobs', schedule: 'Scheduled',
      gate: 'AI Review', logs: 'Logs & monitoring',
    },
    navTodo: 'Not implemented yet',
    navTodoBody: 'This build ships the home screen and the AI Review gate table only. No fake data here.',
    features: {
      models: ['Multi-model', 'Flux / Z-Image and more'],
      flow: ['Visual workflows', 'Composable and precise'],
      batch: ['Batch generation', 'Throughput'],
      gate: ['Quality gate', 'Auto-filter the keepers'],
    },
    wizard: ['Choose template', 'Configure parameters', 'Preview & generate'],
    categoryAll: 'All',
    categories: { enterprise_icon: 'Enterprise icons', poster: 'Posters', portrait: 'Portraits',
                  ecommerce: 'E-commerce', style: 'Stylised', custom: 'Custom' },
    verified: 'Verified', unverified: 'Unverified',
    pairMeasured: 'measured pairing', pairUnmeasured: 'weight unmeasured',
    verifiedTip: 'This weight pairing ran 8/8 through vectorise and the gate',
    unverifiedTip: 'The engine has this weight; we have not measured its icon output',
    paramTitle: 'Parameters',
    model: 'Model', prompt: 'Positive prompt', negative: 'Negative prompt',
    size: 'Image size', steps: 'Steps', cfg: 'CFG Scale', seed: 'Seed',
    batchN: 'Images per run', advanced: 'Advanced',
    shift: 'Shift', sampler: 'Sampler', scheduler: 'Scheduler', denoise: 'Denoise',
    length: 'Frames (4k+1)', fps: 'FPS', image: 'Input image (filename in ComfyUI input dir)',
    octree: 'Octree resolution', threshold: 'Surface threshold',
    generate: 'Generate', generateVideo: 'Generate video', generateModel: 'Generate mesh', generating: 'Generating…',
    needPrompt: 'Prompt is required',
    preview: 'Result', noPreview: 'Nothing yet. Pick a template, write a prompt, hit Generate.',
    variants: 'This run', taskStatus: 'Task status', execLog: 'Workflow log',
    download: 'Download', favorite: 'Favorite', favorited: 'Favourited',
    progress: 'Progress', elapsed: 'Elapsed', modelUsed: 'Model', created: 'Created', taskId: 'Task ID',
    state: { queued: 'queued', running: 'running', done: 'done', error: 'error' },
    recent: 'Recent tasks', tabAll: 'All', tabRunning: 'Running', tabDone: 'Done', tabFailed: 'Failed',
    th: { ref: 'Task ID', template: 'Template', model: 'Model', params: 'Params',
          state: 'Status', created: 'Created', actions: 'Actions', asset: 'Asset', verdict: 'Verdict',
          approved: 'Approval', actionsBtn: 'Actions', fails: 'Violations',
          paths: 'Paths', path_nodes: 'Path nodes', colors: 'Colors', max_delta_e: 'Max ΔE',
          alpha_iou: 'Silhouette IoU', chamfer_grid_px: 'Chamfer', hausdorff_p95_grid_px: 'Hausdorff p95',
          interior_rmse: 'Interior RMSE', interior_rmse_vs_snapped: 'Interior RMSE (snapped)',
          thumb_ssim_16: '16px SSIM', bbox_center_offset_pct: 'Centring %', fill_ratio: 'Fill ratio' },
    view: 'View', emptyTasks: 'No tasks yet.',
    storage: 'Storage', usedOf: 'used',
    engineTitle: 'Engine', device: 'Device', vramFree: 'VRAM free', ramFree: 'RAM free', version: 'Version',
    gateTitle: 'Gate board', gateSub: 'Batch queue · quality gate · approval',
    subtitle: 'Batch queue · quality gate · approval',
    health: 'Service', ok: 'online', degraded: 'degraded', queuedAhead: 'queued ahead',
    newBatch: 'New batch', batchName: 'Batch name', sourcePng: 'Source PNG path', rawSvg: 'Raw SVG path',
    addRow: 'Add row', removeRow: 'remove',
    itemsHint: 'One asset runs at a time; paths must be readable by the backend host.',
    submit: 'Submit batch', submitting: 'Submitting…', needName: 'Batch name is required', needRows: 'Add at least one row',
    batches: 'Batches', refresh: 'Refresh', noBatches: 'No batches yet.', finished: 'finished',
    verdict: { PASS: 'PASS', FAIL: 'FAIL', UNVERIFIED: 'UNVERIFIED' },
    approval: { pending: 'pending', approved: 'approved', rejected: 'rejected' },
    approve: 'Approve', reject: 'Reject', approveBlocked: 'Gate says not shippable',
    limitMax: '≤', limitMin: '≥', limitBand: 'target', limitAdvisory: 'ref',
    stages: { raw: 'vectorised', norm: 'normalised', flat: 'deliverable' },
    selectBatch: 'Select a batch to see its gate table', loading: 'Loading…', errorNone: 'none',
    previewTitle: 'Stage render', previewHint: 'Same asset at three stages; 24px is the shipping size.',
    colsNote: 'Columns and limits come from the API; nothing is re-derived here.',
  },
}

// ?lang= wins over the stored choice so a screenshot or a shared link lands in
// the language the sender meant.
const initial = new URLSearchParams(location.search).get('lang')
  || localStorage.getItem('ui-lang') || 'zh'
const store = reactive({ lang: initial === 'en' ? 'en' : 'zh' })
document.documentElement.lang = store.lang === 'zh' ? 'zh-CN' : 'en'

export function useI18n() {
  const t = computed(() => dict[store.lang])
  const col = computed(() => dict[store.lang].th)
  function toggle() {
    store.lang = store.lang === 'zh' ? 'en' : 'zh'
    localStorage.setItem('ui-lang', store.lang)
    document.documentElement.lang = store.lang === 'zh' ? 'zh-CN' : 'en'
  }
  return { t, col, lang: computed(() => store.lang), toggle }
}
