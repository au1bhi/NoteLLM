import { useEffect } from "react"

import { MetaService } from "@/client"

// Anti-screenshot watermark. Two layers of the same repeating SVG tile:
//   1. a static layer baked into index.html (#app-watermark) — present from
//      first paint and independent of React, so it survives JS being disabled
//      or the app crashing;
//   2. a JS-managed full-document layer (#app-watermark-doc) covering the
//      region below the current viewport, so full-page / scroll-stitched
//      screenshots of long pages stay marked too.
//
// The tile is a CSS background-image — the text lives inside the SVG data-URI,
// so there is no DOM text node to select or delete.
//
// Removal resistance is defense-in-depth; a determined devtools user can
// always win in the end:
//   - a MutationObserver on <body> re-creates a deleted layer within a
//     microtask, so there is no human-speed "delete then screenshot" gap;
//   - a style/class observer on each layer plus a 1 s timer check the
//     COMPUTED style; whenever a layer looks hidden/clipped/masked/zero-sized
//     by ANY CSS (display, opacity, transform, zoom, filter, clip, mask,
//     offset-path, background-size/background-image, a running transition, …),
//     the whole inline style is replaced with the canonical `!important` set —
//     which beats injected stylesheets and wipes unknown attacker properties;
//   - scroll/resize re-measure the document, covering pages that grow
//     dynamically and full-page captures;
//   - print-color-adjust keeps the mark in print/PDF output.
// The overlays are pointer-events:none, so they never block the UI beneath.

const STATIC_ID = "app-watermark"
const DOC_ID = "app-watermark-doc"
const WM_FALLBACK_TEXT = "notellm.au1bhi.com"
const TILE_W = 260
const TILE_H = 160

function documentWidth(): number {
  return Math.max(
    window.innerWidth,
    document.body.scrollWidth,
    document.documentElement.scrollWidth,
  )
}

function documentHeight(): number {
  return Math.max(
    window.innerHeight,
    document.body.scrollHeight,
    document.documentElement.scrollHeight,
  )
}

function watermarkBackground(text: string): string {
  // XML-escape the operator-configured text so it cannot break the SVG
  // data-URI. The realistic value is a domain, so & < > is all that matters.
  const cleaned = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${TILE_W}" height="${TILE_H}">` +
    `<g transform="rotate(-30 ${TILE_W / 2} ${TILE_H / 2})">` +
    `<text x="0" y="60" font-size="16" font-family="system-ui, -apple-system, 'Segoe UI', sans-serif" fill="rgba(0,0,0,0.05)">${cleaned}</text>` +
    `<text x="1" y="61" font-size="16" font-family="system-ui, -apple-system, 'Segoe UI', sans-serif" fill="rgba(255,255,255,0.055)">${cleaned}</text>` +
    `</g></svg>`
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`
}

export function Watermark() {
  useEffect(() => {
    let text = WM_FALLBACK_TEXT
    let disposed = false
    // Set when the server says the watermark is disabled; all resilience and
    // layer creation stop and both layers are removed.
    let disabled = false
    const attrObservers = new Map<HTMLElement, MutationObserver>()

    // Canonical inline styles, all !important (beats any stylesheet rule).
    const canonical = (
      doc: boolean,
      textValue: string,
    ): Array<[string, string]> => {
      const base: Array<[string, string]> = [
        ["z-index", "9999"],
        ["pointer-events", "none"],
        ["user-select", "none"],
        ["display", "block"],
        ["visibility", "visible"],
        ["opacity", "1"],
        ["transform", "none"],
        ["translate", "none"],
        ["scale", "none"],
        ["rotate", "none"],
        ["zoom", "1"],
        ["filter", "none"],
        ["backdrop-filter", "none"],
        ["clip-path", "none"],
        ["clip", "auto"],
        ["mask", "none"],
        ["offset-path", "none"],
        ["overflow", "visible"],
        ["mix-blend-mode", "normal"],
        ["contain", "none"],
        ["content-visibility", "visible"],
        ["transition", "none"],
        ["animation", "none"],
        ["background-image", watermarkBackground(textValue)],
        ["background-repeat", "repeat"],
        ["background-size", "auto"],
        ["print-color-adjust", "exact"],
        ["-webkit-print-color-adjust", "exact"],
      ]
      if (doc) {
        const top = window.scrollY + window.innerHeight
        const height = Math.max(0, documentHeight() - top)
        return [
          ["position", "absolute"],
          ["top", `${top}px`],
          ["left", "0px"],
          ["width", `${documentWidth()}px`],
          ["height", `${height}px`],
          ...base,
        ]
      }
      return [
        ["position", "fixed"],
        ["top", "0px"],
        ["left", "0px"],
        ["width", `${documentWidth()}px`],
        ["height", "100vh"],
        ...base,
      ]
    }

    // Has the layer been made invisible / clipped / zero-sized by anything?
    // Compare computed styles, not cssText, so browser-specific serialization
    // and dropped alias properties cannot cause false positives (or loops).
    // `bad(v, good)` treats an empty/unsupported computed value as "fine" so a
    // browser that lacks a property cannot loop on it.
    const bad = (v: string | null | undefined, good: string): boolean =>
      !!v && v !== good
    const isBroken = (el: HTMLElement, doc: boolean): boolean => {
      const cs = getComputedStyle(el)
      const r = el.getBoundingClientRect()
      const opacity = Number.parseFloat(cs.opacity)
      const zoom = Number.parseFloat(cs.zoom || "1")
      const bgImage = cs.backgroundImage || ""
      const bgSize = cs.backgroundSize || ""
      // background-size used value looks like "260px 160px"; a zero dimension
      // means the tile is collapsed.
      const bgSizeZero = bgSize === "0" || /(^|\s)0px(\s|$)/.test(bgSize)
      // The below-viewport layer may legitimately be 0-height when the page
      // fits the viewport; its size/position is kept in sync separately.
      const sizeBroken = doc ? false : r.width <= 0 || r.height <= 0
      return (
        sizeBroken ||
        bad(cs.display, "block") ||
        bad(cs.visibility, "visible") ||
        Number.isNaN(opacity) ||
        opacity < 0.05 ||
        Number.isNaN(zoom) ||
        zoom < 0.05 ||
        bad(cs.transform, "none") ||
        bad(cs.translate, "none") ||
        bad(cs.scale, "none") ||
        bad(cs.rotate, "none") ||
        bad(cs.filter, "none") ||
        bad(cs.backdropFilter, "none") ||
        bad(cs.clipPath, "none") ||
        bad(cs.clip, "auto") ||
        bad(cs.maskImage, "none") ||
        bad(cs.offsetPath, "none") ||
        bad(cs.position, doc ? "absolute" : "fixed") ||
        bad(cs.zIndex, "9999") ||
        bgImage === "none" ||
        bgImage === "" ||
        bgSizeZero
      )
    }

    // Replace the element's inline style with the canonical set (wiping any
    // attacker-injected properties). Only called when the layer is broken, so
    // the observers converge.
    const rebuild = (el: HTMLElement, doc: boolean) => {
      el.style.cssText = ""
      for (const [prop, value] of canonical(doc, text)) {
        el.style.setProperty(prop, value, "important")
      }
    }

    const ensureAll = () => {
      if (disposed || disabled) return

      let staticEl = document.getElementById(STATIC_ID) as HTMLElement | null
      if (!staticEl) {
        staticEl = document.createElement("div")
        staticEl.id = STATIC_ID
        staticEl.setAttribute("aria-hidden", "true")
        document.body.appendChild(staticEl)
      }
      let docEl = document.getElementById(DOC_ID) as HTMLElement | null
      if (!docEl) {
        docEl = document.createElement("div")
        docEl.id = DOC_ID
        docEl.setAttribute("aria-hidden", "true")
        document.body.appendChild(docEl)
      }

      // A layer moved under a transformed ancestor would break its positioning
      // (a transform/filter creates a new containing block) — force both
      // layers to be direct children of <body>.
      for (const el of [staticEl, docEl]) {
        if (el.parentNode !== document.body) document.body.appendChild(el)
      }

      // Repair anything that made a layer invisible, then keep the below-
      // viewport layer's size/position in sync with the document.
      if (isBroken(staticEl, false)) rebuild(staticEl, false)
      if (isBroken(docEl, true)) rebuild(docEl, true)
      const docTop = window.scrollY + window.innerHeight
      const docHeight = Math.max(0, documentHeight() - docTop)
      if (
        docEl.style.top !== `${docTop}px` ||
        docEl.style.height !== `${docHeight}px`
      ) {
        rebuild(docEl, true)
      }

      // Arm a style observer for any attached layer that lacks one (layers
      // recreated after deletion get a fresh observer) and drop observers for
      // detached nodes so repeated attacker deletions do not leak observers.
      for (const el of [staticEl, docEl]) {
        if (!attrObservers.has(el)) {
          const observer = new MutationObserver(ensureAll)
          observer.observe(el, {
            attributes: true,
            attributeFilter: ["style", "class"],
          })
          attrObservers.set(el, observer)
        }
      }
      for (const [el, observer] of attrObservers) {
        if (!document.contains(el)) {
          observer.disconnect()
          attrObservers.delete(el)
        }
      }
    }

    // Server-authoritative text; a failed request (or blank/whitespace
    // response) keeps the built-in default so the watermark is never blank.
    // An explicit `enabled: false` from the server disables the watermark
    // entirely (operator toggled via WATERMARK_ENABLED) — fail-closed: a
    // missing/errored response still renders the mark.
    MetaService.getWatermark()
      .then((meta) => {
        if (disposed) return
        if (meta.enabled === false) {
          disabled = true
          document.getElementById(STATIC_ID)?.remove()
          document.getElementById(DOC_ID)?.remove()
          return
        }
        if (meta.text?.trim()) text = meta.text.trim()
      })
      .catch(() => undefined)
      .finally(() => ensureAll())

    // Draw immediately (with the fallback text) before the fetch resolves.
    ensureAll()

    // Re-create a deleted layer within a microtask of its removal.
    const bodyObserver = new MutationObserver(ensureAll)
    bodyObserver.observe(document.body, { childList: true })

    // Belt-and-suspenders: re-check every second even if the observers are
    // dead, and follow scroll/resize so the below-viewport layer stays put.
    const timer = window.setInterval(ensureAll, 1000)
    window.addEventListener("scroll", ensureAll, { passive: true })
    window.addEventListener("resize", ensureAll)
    window.addEventListener("orientationchange", ensureAll)

    return () => {
      disposed = true
      bodyObserver.disconnect()
      for (const observer of attrObservers.values()) observer.disconnect()
      window.clearInterval(timer)
      window.removeEventListener("scroll", ensureAll)
      window.removeEventListener("resize", ensureAll)
      window.removeEventListener("orientationchange", ensureAll)
      // Only the React-created layer is ours to remove; the static layer is
      // part of index.html.
      document.getElementById(DOC_ID)?.remove()
    }
  }, [])

  return null
}
