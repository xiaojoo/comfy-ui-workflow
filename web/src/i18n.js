// Chinese first, with an in-app switch. Column labels are looked up by the key
// the API sends and fall back to the raw key, so a metric added on the backend
// still shows up on the board instead of silently vanishing from the table.
import { reactive, computed } from 'vue'

const dict = {
  zh: {
    title: 'Icon 门禁看板',
    subtitle: '批次队列 · 质量门禁 · 审批',
    langToggle: 'English',
    health: '服务', ok: '在线', degraded: '异常', queuedAhead: '队列中',
    newBatch: '新建批次',
    batchName: '批次名', sourcePng: '源图 PNG 路径', rawSvg: '原始 SVG 路径',
    addRow: '加一行', removeRow: '删',
    itemsHint: '一台机器一次只跑一个资产，源路径须是后端能读到的本地文件。',
    submit: '提交批次', submitting: '提交中…',
    needName: '批次名不能为空', needRows: '至少填一行',
    batches: '批次', refresh: '刷新', noBatches: '还没有批次。',
    created: '创建', finished: '完成',
    th: {
      asset: '资产', verdict: '判定', approved: '审批', actions: '操作', fails: '不合格项',
      paths: '路径数', path_nodes: '节点数', colors: '颜色数', max_delta_e: '最大色差',
      alpha_iou: '轮廓 IoU', chamfer_grid_px: 'chamfer', hausdorff_p95_grid_px: 'hausdorff p95',
      interior_rmse: '内部 RMSE', interior_rmse_vs_snapped: '内部 RMSE(色板对齐)',
      thumb_ssim_16: '16px SSIM', bbox_center_offset_pct: '居中偏移%', fill_ratio: '填充占比',
    },
    state: { queued: '排队中', running: '执行中', done: '完成', error: '失败' },
    verdict: { PASS: '通过', FAIL: '拒收', UNVERIFIED: '未验证' },
    approval: { pending: '待审', approved: '已批准', rejected: '已驳回' },
    approve: '批准', reject: '驳回', undo: '撤销审批',
    approveBlocked: '门禁未通过，不可交付',
    limitMax: '≤', limitMin: '≥', limitBand: '目标',
    limitAdvisory: '参考',
    advisory: '仅供参考，不参与判定',
    stages: { raw: '矢量化原始', norm: '规范化', flat: '交付件' },
    selectBatch: '选一个批次看门禁表',
    loading: '读取中…',
    errorNone: '无',
    ruler: '尺子自检',
    previewTitle: '渲染对照', previewHint: '同一资产三个阶段；24px 是真实落地尺寸。',
    sourceTitle: '源图对照',
    colsNote: '列与阈值都由后端下发，前端不自行推导。',
  },
  en: {
    title: 'Icon Gate Board',
    subtitle: 'Batch queue · quality gate · approval',
    langToggle: '中文',
    health: 'Service', ok: 'online', degraded: 'degraded', queuedAhead: 'queued ahead',
    newBatch: 'New batch',
    batchName: 'Batch name', sourcePng: 'Source PNG path', rawSvg: 'Raw SVG path',
    addRow: 'Add row', removeRow: 'remove',
    itemsHint: 'One asset runs at a time; paths must be readable by the backend host.',
    submit: 'Submit batch', submitting: 'Submitting…',
    needName: 'Batch name is required', needRows: 'Add at least one row',
    batches: 'Batches', refresh: 'Refresh', noBatches: 'No batches yet.',
    created: 'created', finished: 'finished',
    th: {
      asset: 'Asset', verdict: 'Verdict', approved: 'Approval', actions: 'Actions', fails: 'Violations',
      paths: 'Paths', path_nodes: 'Path nodes', colors: 'Colors', max_delta_e: 'Max ΔE',
      alpha_iou: 'Silhouette IoU', chamfer_grid_px: 'Chamfer', hausdorff_p95_grid_px: 'Hausdorff p95',
      interior_rmse: 'Interior RMSE', interior_rmse_vs_snapped: 'Interior RMSE (snapped)',
      thumb_ssim_16: '16px SSIM', bbox_center_offset_pct: 'Centring %', fill_ratio: 'Fill ratio',
    },
    state: { queued: 'queued', running: 'running', done: 'done', error: 'error' },
    verdict: { PASS: 'PASS', FAIL: 'FAIL', UNVERIFIED: 'UNVERIFIED' },
    approval: { pending: 'pending', approved: 'approved', rejected: 'rejected' },
    approve: 'Approve', reject: 'Reject', undo: 'Undo',
    approveBlocked: 'Gate says not shippable',
    limitMax: '≤', limitMin: '≥', limitBand: 'target',
    limitAdvisory: 'ref',
    advisory: 'advisory only, not judged',
    stages: { raw: 'vectorised', norm: 'normalised', flat: 'deliverable' },
    selectBatch: 'Select a batch to see its gate table',
    loading: 'Loading…',
    errorNone: 'none',
    ruler: 'Ruler self-test',
    previewTitle: 'Stage render', previewHint: 'Same asset at three stages; 24px is the shipping size.',
    sourceTitle: 'Source comparison',
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
