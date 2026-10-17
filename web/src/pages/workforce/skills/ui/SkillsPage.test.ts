import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { Credential, Requirement, SkillGap } from '@/entities/workforce/skills'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

const credential = (over: Partial<Credential> = {}): Credential => ({
  employeeId: 10,
  empNo: 'E001',
  employee: 'Alex Agent',
  kind: 'language',
  name: 'Afrikaans',
  expiresOn: null,
  expired: false,
  ...over,
})

const requirement = (over: Partial<Requirement> = {}): Requirement => ({
  queueId: 1,
  queue: 'QueueA',
  kind: 'language',
  name: 'Afrikaans',
  minPeople: 2,
  ...over,
})

const gap: SkillGap = {
  queueId: 1,
  queue: 'QueueA',
  kind: 'language',
  name: 'Afrikaans',
  day: '2026-05-26',
  shiftCode: 'D1',
  required: 2,
  present: 1,
}

async function open(role = 'planner') {
  seedScheduling()
  backend.credentials = [
    credential(),
    credential({ kind: 'certification', name: 'ITIL', expiresOn: '2020-01-01', expired: true }),
  ]
  backend.requirements = [requirement()]
  backend.gaps = [gap]
  const view = await openScheduling('/skills', role)
  const user = userEvent.setup()
  return { view, user }
}

async function choosePerson(user: ReturnType<typeof userEvent.setup>) {
  await user.selectOptions(await screen.findByLabelText('Employee'), '10')
}

describe('skills', () => {
  it('shows what a person holds and marks an expired credential in words', async () => {
    // Failure caught: an expired certification shown as current (colour alone is not a signal).
    const { user } = await open()
    await choosePerson(user)
    const held = await screen.findByTestId('held')
    expect(held).toHaveTextContent('Language: Afrikaans')
    expect(held).toHaveTextContent('Certification: ITIL (expired 2020-01-01)')
  })

  it('lets a planner replace the set and sends exactly what was typed', async () => {
    // Failure caught: the editor sending blank rows, or dropping the expiry date.
    const { user } = await open('planner')
    await choosePerson(user)
    const editor = await screen.findByTestId('credential-editor')
    await user.click(within(editor).getByRole('button', { name: /Remove credential 2/ }))
    await user.click(within(editor).getByRole('button', { name: 'Add credential' }))
    await user.type(within(editor).getByLabelText('Name of credential 2'), 'Secret')
    await user.selectOptions(within(editor).getByLabelText('Kind of credential 2'), 'clearance')
    await user.type(within(editor).getByLabelText('Expiry of credential 2'), '2030-01-31')
    await user.click(within(editor).getByRole('button', { name: 'Save credentials' }))

    expect(await screen.findByTestId('credentials-saved')).toBeVisible()
    const write = backend.writes.find((w) => w.path === '/api/v1/skills/employees/10/credentials')
    expect(write?.method).toBe('PUT')
    expect(write?.body).toEqual({
      credentials: [
        { kind: 'language', name: 'Afrikaans', expiresOn: null },
        { kind: 'clearance', name: 'Secret', expiresOn: '2030-01-31' },
      ],
    })
  })

  it('shows the refusal in words when the API says no', async () => {
    const { user } = await open('planner')
    await choosePerson(user)
    const editor = await screen.findByTestId('credential-editor')
    backend.nextProblem = {
      status: 422,
      code: 'skills.duplicate',
      title: 'Invalid request',
      detail: 'A credential is listed twice.',
    }
    await user.click(within(editor).getByRole('button', { name: 'Save credentials' }))
    expect(await screen.findByTestId('credentials-error')).toHaveTextContent('listed twice')
  })

  it('does not offer the editors to a lead, who only reads', async () => {
    // Failure caught: write controls shown to a role the API refuses.
    const { user } = await open('lead')
    await choosePerson(user)
    await screen.findByTestId('held')
    expect(screen.queryByTestId('credential-editor')).toBeNull()
    expect(screen.queryByTestId('requirement-editor')).toBeNull()
    expect(screen.queryByTestId('gaps')).toBeNull()
  })

  it('finds who holds a credential through the employee filter', async () => {
    const { user } = await open()
    await user.type(await screen.findByLabelText('Credential name'), 'afrikaans')
    const list = await screen.findByTestId('holders')
    expect(list).toHaveTextContent('Alex Agent (E001)')
    expect(list).not.toHaveTextContent('Sam Planner')
    await user.clear(screen.getByLabelText('Credential name'))
    await user.type(screen.getByLabelText('Credential name'), 'klingon')
    expect(await screen.findByTestId('no-holders')).toBeVisible()
  })

  it('shows the requirement and the shifts that are short of it', async () => {
    await open('planner')
    expect(await screen.findByTestId('requirements')).toHaveTextContent(
      'Language: Afrikaans, at least 2 on every shift',
    )
    const gaps = await screen.findByTestId('gaps')
    expect(within(gaps).getByText('1 of 2')).toBeVisible()
    expect(gaps).toHaveTextContent('2026-05-26')
  })

  it('says so when nothing is short', async () => {
    seedScheduling()
    backend.gaps = []
    await openScheduling('/skills', 'planner')
    expect(await screen.findByTestId('no-gaps')).toBeVisible()
  })

  it('saves a queue requirement', async () => {
    const { user } = await open('planner')
    const editor = await screen.findByTestId('requirement-editor')
    const people = within(editor).getByLabelText('People required for requirement 1')
    await user.clear(people)
    await user.type(people, '3')
    await user.click(within(editor).getByRole('button', { name: 'Save requirements' }))
    await waitFor(() => {
      const write = backend.writes.find((w) => w.path === '/api/v1/skills/queues/1/requirements')
      expect(write?.body).toEqual({
        requirements: [{ kind: 'language', name: 'Afrikaans', minPeople: 3 }],
      })
    })
  })
})
