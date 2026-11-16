import type { ObjectDirective } from 'vue'

const ease = 'cubic-bezier(.22, 1, .36, 1)'

export default defineNuxtPlugin(app => {
  const preference = window.matchMedia('(prefers-reduced-motion: reduce)')
  const animations = new Set<Animation>()
  function animate(element: Element, frames: Keyframe[], duration = 420, options: KeyframeAnimationOptions = {}) {
    if (preference.matches) return
    const animation = element.animate(frames, { duration, easing: ease, ...options })
    animations.add(animation)
    animation.finished.catch(() => {}).finally(() => animations.delete(animation))
    return animation
  }
  const stopMotion = () => {
    if (preference.matches) for (const animation of animations) animation.finish()
  }
  preference.addEventListener('change', stopMotion)
  const finishMotion = () => { for (const animation of animations) animation.finish() }
  window.addEventListener('beforeprint', finishMotion)

  // One shared highlight moves between choices without replacing focused buttons.
  const selections = new WeakMap<HTMLElement, () => void>()
  const selection: ObjectDirective<HTMLElement> = {
    mounted(element) {
      let frame = 0
      let initialized = false
      // Establish the offset parent before the first measurement, including
      // when map controls wrap onto another row on a narrow screen.
      element.classList.add('motion-selection')
      const measure = () => {
        frame = 0
        const active = element.querySelector<HTMLElement>(':scope > .selected, :scope > .active')
        if (!active || !element.offsetWidth) return
        element.style.setProperty('--selection-x', `${active.offsetLeft}px`)
        element.style.setProperty('--selection-y', `${active.offsetTop}px`)
        element.style.setProperty('--selection-width', `${active.offsetWidth}px`)
        element.style.setProperty('--selection-height', `${active.offsetHeight}px`)
        if (!initialized) {
          initialized = true
          // Flush the initial position before enabling transitions.
          frame = requestAnimationFrame(() => { element.classList.add('motion-selection-ready'); frame = 0 })
        }
      }
      const schedule = () => { if (!frame) frame = requestAnimationFrame(measure) }
      const resize = new ResizeObserver(schedule)
      resize.observe(element)
      for (const child of element.children) resize.observe(child)
      const changes = new MutationObserver(schedule)
      changes.observe(element, { subtree: true, attributes: true, attributeFilter: ['class', 'aria-pressed', 'aria-current'], childList: true })
      measure()
      selections.set(element, () => { cancelAnimationFrame(frame); resize.disconnect(); changes.disconnect() })
    },
    beforeUnmount(element) { selections.get(element)?.(); selections.delete(element) }
  }
  app.vueApp.directive('selection-motion', selection)

  // Animate only when content reaches the viewport. Nothing is hidden while
  // waiting, so keyboard navigation and browser Find always reach the content.
  const reveals = new WeakMap<HTMLElement, () => void>()
  const reveal: ObjectDirective<HTMLElement> = {
    mounted(element) {
      const running = new Set<Animation>()
      const observer = new IntersectionObserver(entries => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue
          observer.unobserve(entry.target)
          const animation = animate(entry.target, [{ opacity: 0, transform: 'translateY(12px)' }, { opacity: 1, transform: 'none' }], 540)
          if (animation) {
            running.add(animation)
            animation.finished.catch(() => {}).finally(() => running.delete(animation))
          }
        }
      }, { threshold: .06 })
      const targets = element.querySelectorAll('.panel:not(.calendar-map-panel), .science-banner, .method-flow, .metric-card')
      for (const target of targets.length ? targets : [element]) observer.observe(target)
      reveals.set(element, () => { observer.disconnect(); for (const animation of running) animation.cancel() })
    },
    beforeUnmount(element) { reveals.get(element)?.(); reveals.delete(element) }
  }
  app.vueApp.directive('reveal', reveal)

  // Prepare each item offscreen, then stagger only the items that actually
  // enter the viewport (also respecting nested scrolling containers).
  const staggers = new WeakMap<HTMLElement, () => void>()
  const stagger: ObjectDirective<HTMLElement, 'cells' | 'bars'> = {
    mounted(element, binding) {
      if (preference.matches) return
      const cells = binding.value === 'cells'
      const selector = cells ? '.calendar-cell' : '.bar-track > i'
      const seen = new WeakSet<Element>()
      const pending = new Map<Element, Animation>()
      const running = new Set<Animation>()
      let frame = 0
      const observer = new IntersectionObserver(entries => {
        const order = new Map([...element.querySelectorAll(selector)].map((target, index) => [target, index]))
        const entering = entries.filter(entry => entry.isIntersecting && pending.has(entry.target))
          .sort((a, b) => order.get(a.target)! - order.get(b.target)!)
        entering.forEach((entry, index) => {
          const animation = pending.get(entry.target)!
          pending.delete(entry.target)
          observer.unobserve(entry.target)
          if (preference.matches || animation.playState === 'finished') { animation.finish(); return }
          animation.effect?.updateTiming({ delay: index * (cells ? 8 : 85) })
          animation.play()
        })
      }, { threshold: .15 })
      const scan = () => {
        frame = 0
        for (const target of element.querySelectorAll<HTMLElement>(selector)) {
          if (seen.has(target)) continue
          seen.add(target)
          const frames = cells
            ? [{ opacity: 0, transform: 'translateY(4px) scale(.82)' }, { opacity: 1, transform: 'none' }]
            : [{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }]
          const animation = animate(target, frames, cells ? 280 : 720, { fill: 'backwards' })
          if (!animation) continue
          animation.pause()
          animation.currentTime = 0
          pending.set(target, animation)
          running.add(animation)
          animation.finished.catch(() => {}).finally(() => running.delete(animation))
          observer.observe(target)
        }
        // Filters can remove cells while their entrance is still waiting.
        for (const [target, animation] of pending) {
          if (element.contains(target)) continue
          observer.unobserve(target); animation.cancel(); pending.delete(target)
        }
      }
      const changes = new MutationObserver(() => { if (!frame) frame = requestAnimationFrame(scan) })
      changes.observe(element, { subtree: true, childList: true })
      const showFocused = () => { for (const animation of running) animation.finish() }
      element.addEventListener('focusin', showFocused)
      scan()
      staggers.set(element, () => {
        changes.disconnect(); observer.disconnect(); cancelAnimationFrame(frame)
        element.removeEventListener('focusin', showFocused)
        for (const animation of running) animation.cancel()
      })
    },
    beforeUnmount(element) { staggers.get(element)?.(); staggers.delete(element) }
  }
  app.vueApp.directive('stagger-motion', stagger)

  // Clip each series independently, preserving dashed strokes and missing-data
  // gaps while revealing the exact plot from left to right.
  type DrawOptions = { enabled: boolean; replayKey?: string | number }
  const lineDraws = new WeakMap<SVGSVGElement, { replay: () => void; dispose: () => void }>()
  const drawLines: ObjectDirective<SVGSVGElement, DrawOptions> = {
    mounted(element, binding) {
      if (!binding.value.enabled) return
      let visible = false
      let needsReplay = true
      let revision = 0
      let frame = 0
      let sequence: Animation[] = []
      const play = () => {
        needsReplay = false
        element.dataset.drawState = sequence.length && !preference.matches ? 'drawing' : 'complete'
        const current = revision
        for (const animation of sequence) {
          if (preference.matches) animation.finish()
          else animation.play()
        }
        Promise.allSettled(sequence.map(animation => animation.finished)).then(() => {
          if (current === revision) element.dataset.drawState = 'complete'
        })
      }
      const prepare = () => {
        revision++
        for (const animation of sequence) animation.cancel()
        sequence = []
        for (const [index, clip] of [...element.querySelectorAll('.chart-line-reveal')].entries()) {
          const animation = animate(clip, [{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }], 820, {
            delay: index * 820, fill: 'backwards', easing: 'cubic-bezier(.3, 0, .2, 1)'
          })
          if (!animation) continue
          animation.pause(); animation.currentTime = 0; sequence.push(animation)
        }
        needsReplay = true
        element.dataset.drawState = sequence.length ? 'waiting' : 'complete'
        if (visible) play()
      }
      const replay = () => {
        if (frame) return
        frame = requestAnimationFrame(() => { frame = 0; prepare() })
      }
      const intersection = new IntersectionObserver(entries => {
        visible = entries.some(entry => entry.isIntersecting)
        if (visible && needsReplay) play()
      }, { threshold: .2 })
      const changes = new MutationObserver(replay)
      changes.observe(element, { subtree: true, childList: true, attributes: true, attributeFilter: ['d'] })
      prepare()
      intersection.observe(element)
      lineDraws.set(element, { replay, dispose: () => {
        revision++; intersection.disconnect(); changes.disconnect(); cancelAnimationFrame(frame)
        for (const animation of sequence) animation.cancel()
      } })
    },
    updated(element, binding) {
      if (binding.value.replayKey !== binding.oldValue?.replayKey) lineDraws.get(element)?.replay()
    },
    beforeUnmount(element) { lineDraws.get(element)?.dispose(); lineDraws.delete(element) }
  }
  app.vueApp.directive('draw-lines', drawLines)

  // Soften a data refresh without interpolating scientific values or geometry.
  const charts = new WeakMap<SVGSVGElement, () => void>()
  const chart: ObjectDirective<SVGSVGElement> = {
    mounted(element, binding) {
      if (binding.value === false) return
      let frame = 0
      let animation: Animation | undefined
      const observer = new MutationObserver(() => {
        if (frame) return
        frame = requestAnimationFrame(() => {
          frame = 0
          animation?.cancel()
          animation = animate(element, [{ opacity: .45 }, { opacity: 1 }], 260)
        })
      })
      observer.observe(element, { subtree: true, childList: true, attributes: true, attributeFilter: ['d', 'cx', 'cy'] })
      charts.set(element, () => { observer.disconnect(); cancelAnimationFrame(frame); animation?.cancel() })
    },
    beforeUnmount(element) { charts.get(element)?.(); charts.delete(element) }
  }
  app.vueApp.directive('chart-motion', chart)

  // Keep native details/summary keyboard semantics while animating both directions.
  const disclosures = new WeakMap<HTMLDetailsElement, () => void>()
  const disclosure: ObjectDirective<HTMLDetailsElement> = {
    mounted(element) {
      const summary = element.querySelector('summary')
      if (!summary) return
      let animation: Animation | undefined
      let targetOpen = element.open
      const reset = () => { element.style.height = ''; element.style.overflow = ''; delete element.dataset.closing }
      const click = (event: MouseEvent) => {
        if (event.target instanceof Element && event.target.closest('a, button, input, select')) return
        event.preventDefault()
        summary.focus({ preventScroll: true })
        const start = element.getBoundingClientRect().height
        targetOpen = animation ? !targetOpen : !element.open
        animation?.cancel()
        reset()
        if (preference.matches) { element.open = targetOpen; return }
        element.open = true
        const style = getComputedStyle(element)
        const border = parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth)
        const end = targetOpen ? element.getBoundingClientRect().height : summary.getBoundingClientRect().height + border
        element.dataset.closing = String(!targetOpen)
        element.style.height = `${start}px`
        element.style.overflow = 'hidden'
        animation = animate(element, [{ height: `${start}px` }, { height: `${end}px` }], 340)
        if (animation) animation.onfinish = () => { element.open = targetOpen; animation = undefined; reset() }
      }
      summary.addEventListener('click', click)
      disclosures.set(element, () => { summary.removeEventListener('click', click); animation?.cancel(); reset() })
    },
    beforeUnmount(element) { disclosures.get(element)?.(); disclosures.delete(element) }
  }
  app.vueApp.directive('disclosure-motion', disclosure)
  app.vueApp.onUnmount(() => {
    preference.removeEventListener('change', stopMotion)
    window.removeEventListener('beforeprint', finishMotion)
    for (const animation of animations) animation.cancel()
  })
})
