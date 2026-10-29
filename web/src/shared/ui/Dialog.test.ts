import userEvent from '@testing-library/user-event'
import { render, screen, waitFor } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'
import { ref } from 'vue'

import Dialog from './Dialog.vue'

function mount() {
  const open = ref(false)
  render({
    components: { Dialog },
    setup: () => ({ open }),
    template: `
      <button type="button" @click="open = true">Open it</button>
      <Dialog v-model:open="open" title="Add a thing" subtitle="One line about it.">
        <input aria-label="First field" />
        <template #footer>
          <button type="button" @click="open = false">Cancel</button>
          <button type="button">Save</button>
        </template>
      </Dialog>`,
  })
  return open
}

describe('Dialog', () => {
  it('is a labelled, described, modal dialog', async () => {
    // Failure caught: a modal a screen reader cannot name, or one that does not say it is modal.
    const user = userEvent.setup()
    mount()
    await user.click(screen.getByRole('button', { name: 'Open it' }))
    const dialog = await screen.findByRole('dialog', { name: 'Add a thing' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAccessibleDescription('One line about it.')
  })

  it('moves focus in, keeps Tab inside, and wraps both ways', async () => {
    // Failure caught: Tab escaping to the page behind the modal.
    const user = userEvent.setup()
    mount()
    await user.click(screen.getByRole('button', { name: 'Open it' }))
    const field = await screen.findByLabelText('First field')
    await waitFor(() => expect(field).toHaveFocus())
    await user.tab({ shift: true })
    expect(screen.getByRole('button', { name: 'Close' })).toHaveFocus()
    await user.tab({ shift: true }) // above the first control: wraps to the last
    expect(screen.getByRole('button', { name: 'Save' })).toHaveFocus()
    await user.tab() // past the last: wraps to the first
    expect(screen.getByRole('button', { name: 'Close' })).toHaveFocus()
  })

  it('closes on Escape and gives focus back to the opener', async () => {
    // Failure caught: focus dropped to the page top after closing.
    const user = userEvent.setup()
    mount()
    const opener = screen.getByRole('button', { name: 'Open it' })
    await user.click(opener)
    await screen.findByRole('dialog')
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(opener).toHaveFocus()
  })

  it('closes on a click on the backdrop but not inside the panel', async () => {
    // Failure caught: a click inside the form closing it and losing what was typed.
    const user = userEvent.setup()
    mount()
    await user.click(screen.getByRole('button', { name: 'Open it' }))
    await user.click(await screen.findByLabelText('First field'))
    expect(screen.getByRole('dialog')).toBeVisible()
    await user.click(screen.getByTestId('dialog-backdrop'))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('stops the page behind from scrolling while open, and lets it again after', async () => {
    // Failure caught: the page staying locked after the dialog closes.
    const user = userEvent.setup()
    mount()
    await user.click(screen.getByRole('button', { name: 'Open it' }))
    await screen.findByRole('dialog')
    expect(document.body.style.overflow).toBe('hidden')
    await user.keyboard('{Escape}')
    await waitFor(() => expect(document.body.style.overflow).toBe(''))
  })
})
