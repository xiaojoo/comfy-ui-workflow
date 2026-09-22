// Chrome's own title bubble is a system widget: grey, unstyleable, on a ~0.5s schedule,
// and it wraps wherever it likes. Every title attribute that reaches the DOM is taken
// over here and redrawn as a panel-coloured bubble, so a tip looks like the UI it
// annotates.

const SHOW_AFTER = 120 // ms; long enough that tips aren't flashed while sweeping past
const GAP = 6          // px between the control and the bubble
const EDGE = 8         // px the bubble keeps from the viewport edge
const ID = 'tip-bubble'

let bubble, shown, timer, described

// A title of '' is Vue's way of saying "no tip this time" (GateTable's approve button
// binds it to the verdict), so it clears the hand-off rather than being ignored.
function adopt(el) {
  const text = el.getAttribute('title')
  if (text === null) return
  el.removeAttribute('title')
  if (text) el.dataset.tip = text
  else delete el.dataset.tip
  if (el === shown) text ? place(el) : hide()
}

function place(el) {
  const text = el.dataset.tip
  if (!text || !el.isConnected) return hide()
  bubble.textContent = text
  bubble.hidden = false
  // The title attribute used to be this control's accessible description; taking it
  // over means taking that over too -- but never over one an author already set.
  if (described && described !== el) described.removeAttribute('aria-describedby')
  if (!el.hasAttribute('aria-describedby')) {
    el.setAttribute('aria-describedby', ID)
    described = el
  }
  const r = el.getBoundingClientRect()
  const { offsetWidth: w, offsetHeight: h } = bubble
  let top = r.top - h - GAP
  // Above by default; the topbar has no room up there.
  if (top < EDGE) top = Math.min(r.bottom + GAP, innerHeight - h - EDGE)
  bubble.style.top = `${Math.round(top)}px`
  bubble.style.left = `${Math.round(Math.max(EDGE, Math.min(r.left + (r.width - w) / 2, innerWidth - w - EDGE)))}px`
}

function hide() {
  clearTimeout(timer)
  shown = null
  described?.removeAttribute('aria-describedby')
  described = null
  bubble.hidden = true
}

bubble = document.createElement('div')
bubble.className = 'ui-tip'
bubble.id = ID
bubble.hidden = true
document.body.appendChild(bubble)

new MutationObserver((records) => {
  for (const r of records) {
    if (r.type === 'attributes') adopt(r.target)
    else for (const n of r.addedNodes) {
      if (n.nodeType !== 1) continue
      adopt(n)
      if (n.querySelectorAll) for (const el of n.querySelectorAll('[title]')) adopt(el)
    }
  }
  // A re-render can retire the hovered row under a stationary pointer.
  if (shown && !shown.isConnected) hide()
}).observe(document.documentElement, {
  subtree: true, childList: true, attributes: true, attributeFilter: ['title'],
})

document.addEventListener('pointerover', (e) => {
  // Chrome does send pointer events for a disabled control, unlike its native bubble
  // which never shows there -- so the tips on disabled buttons stay hidden as before.
  const el = e.target.closest('[data-tip]')
  const next = el && !el.disabled ? el : null
  if (next === shown) return
  if (!next) return hide()
  clearTimeout(timer)
  shown = next
  timer = setTimeout(place, SHOW_AFTER, next)
})

// pointerout is the only way to notice the pointer leaving the window altogether.
document.addEventListener('pointerout', (e) => {
  if (shown && !e.relatedTarget?.closest('[data-tip]')) hide()
})

document.addEventListener('pointerdown', hide)
addEventListener('keydown', (e) => e.key === 'Escape' && hide())
// The bubble is pinned to the viewport, so anything that moves the control moves it out of place.
addEventListener('scroll', hide, true)
