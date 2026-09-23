// Chrome's autofill probe lists every form control that reaches the page with neither an
// id nor a name: 7 across the three screens with nothing opened, 24 once every parameter
// panel in the catalogue has been shown. The fields are mostly born in loops -- one number
// box per parameter, one row per gate item -- so naming them at the markup sites is a fix
// the next v-for silently undoes. Here a bare control borrows the text that already labels
// it, which is the pairing the probe is asking for.

const FIELDS = 'input, select, textarea'

// Roughly Chrome's own guessing order: an explicit label, the hint inside the box, the
// <label> wrapped around it, the text sitting in front of it.
function labelFor(el) {
  return el.getAttribute('aria-label') || el.placeholder
    || el.closest('label')?.firstChild?.nodeValue || el.previousElementSibling?.textContent || ''
}

function stamp(el) {
  if (el.id || el.hasAttribute('name')) return
  // The labelling text is often a whole hint sentence; the part before its first break
  // is the name, and the rest was never meant to be one.
  const base = labelFor(el).split(/[，,、：:(（]/)[0].trim().replace(/\s+/g, '-').slice(0, 24)
    || el.tagName.toLowerCase()
  // Duplicate names are what trip the next autofill check, so each control keeps its own;
  // a re-render that retired a control hands its suffix back to the next one.
  let name = base
  for (let n = 2; document.getElementsByName(name).length; n++) name = `${base}-${n}`
  el.name = name
}

new MutationObserver((records) => {
  for (const r of records) for (const node of r.addedNodes) {
    if (node.nodeType !== 1) continue
    if (node.matches(FIELDS)) stamp(node)
    for (const el of node.querySelectorAll(FIELDS)) stamp(el)
  }
}).observe(document.documentElement, { childList: true, subtree: true })
