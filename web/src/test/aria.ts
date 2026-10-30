import { expect } from 'vitest'

const REFERENCES = ['aria-controls', 'aria-labelledby', 'aria-describedby'] as const

/**
 * Fails if any aria-controls / aria-labelledby / aria-describedby inside `root` names an id that
 * is not in the document. A dangling reference is read as broken by assistive technology, and it
 * is what axe reports as `aria-valid-attr-value`. A reference to a panel that is deliberately
 * not rendered while its tab is unselected is allowed only when the control says
 * `aria-selected="false"` or `aria-expanded="false"`, the same exception axe makes.
 */
export function expectAriaReferencesResolve(root: ParentNode = document): void {
  const dangling: string[] = []
  for (const attribute of REFERENCES) {
    for (const el of root.querySelectorAll(`[${attribute}]`)) {
      const closed =
        el.getAttribute('aria-selected') === 'false' || el.getAttribute('aria-expanded') === 'false'
      if (attribute === 'aria-controls' && closed) continue
      const ids = (el.getAttribute(attribute) ?? '').split(/\s+/).filter(Boolean)
      if (ids.length === 0) dangling.push(`${describe(el)} ${attribute} is empty`)
      for (const id of ids) {
        if (!document.getElementById(id)) dangling.push(`${describe(el)} ${attribute}="${id}"`)
      }
    }
  }
  expect(dangling, dangling.join('\n')).toEqual([])
}

function describe(el: Element): string {
  return `<${el.tagName.toLowerCase()}${el.id ? ` id="${el.id}"` : ''}>`
}
