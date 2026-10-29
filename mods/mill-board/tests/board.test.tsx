import { expect, mock, test } from 'claude-code/testing'

const pane = (requestId: string) =>
  ({
    plugin: 'mill-board',
    component: 'Pane',
    requestId,
    props: {
      title: requestId,
      isFocused: false,
      bodyColumns: 80,
      placement: 'dock',
      scroll: { offset: 0, bodyRows: 40 },
      view: {},
    },
  }) as const

const BEAD_FILE = [
  JSON.stringify({ id: 'claudiverse-1gn.8', title: 'Phase 1.5 docs', status: 'in_progress', priority: 3, labels: [], created_at: '2026-10-28T10:00:00Z' }),
  JSON.stringify({ id: 'water-mill-8kp', title: 'Eight hex examples', status: 'open', priority: 3, labels: ['auto-mill'], created_at: '2099-01-01T00:00:00Z' }),
  JSON.stringify({ id: 'water-mill-old', title: 'Old bead', status: 'open', priority: 2, labels: [], created_at: '2020-01-01T00:00:00Z' }),
].join('\n')

function engine(on: Parameters<Parameters<typeof test>[1]>[1]) {
  // Nothing sits beneath the plugin: each hook here stands for the engine.
  const clock = mock.clock(on, { now: Date.parse('2026-10-29T12:00:00Z') })
  on('command.register', (_, e) => ({ value: { command: e.name } }))
  on('tool.register', () => ({ value: {} }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.usage', () => ({
    value: {
      startedAt: Date.parse('2026-10-29T11:00:00Z'),
      context: { window: 1_000_000, percent: 18, tokens: 180_000 },
      rateLimits: [{ kind: 'five_hour', percentUsed: 34 }, { kind: 'seven_day', percentUsed: 85 }],
      cost: { usd: 12.5 },
    },
  }))
  // A workshop folder: /work holds water-mill and claudiverse (both with a
  // bead file) and notes, which has none. The session starts in water-mill.
  const files = new Set(['/work/water-mill/.git', '/work/water-mill/.beads/issues.jsonl', '/work/claudiverse/.beads/issues.jsonl'])
  on('fs.exists', (_, e) => ({ value: files.has(e.path) }))
  on('fs.list', (_, e) => ({
    value: e.path === '/work'
      ? [
          { name: 'water-mill', kind: 'dir', size: 0 },
          { name: 'claudiverse', kind: 'dir', size: 0 },
          { name: 'notes', kind: 'dir', size: 0 },
          { name: '.cache', kind: 'dir', size: 0 },
        ]
      : [],
  }))
  on('process.run', (_, e) => {
    const argv = e.argv as readonly string[]
    if (argv.includes('show') && argv[2] === '/work/water-mill') {
      return { value: { exitCode: 0, stdout: BEAD_FILE, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    }
    if (argv.includes('show')) {
      return { value: { exitCode: 128, stdout: '', stderr: 'fatal: no such path', isStdoutTruncated: false, isStderrTruncated: false } }
    }

    return { value: { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })

  return clock
}

test('a question the master sets shows in the questions pane and the band', async ($, on) => {
  const clock = engine(on)
  await $.session.start({ cwd: '/work/water-mill', surface: 'desktop', isInteractive: true })
  await clock.settle()
  await $.tool.call({
    tool: 'mcp__mill-board__update',
    questions: [{ id: 'q1', text: 'Close 1gn.10 as not worth doing?', context: 'No bit-identical speed-up pays off.' }],
  } as never)

  const ui = await $.ui.mount({ ...pane('owner-questions'), surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /Close 1gn\.10/ }))?.text).toContain('Close 1gn.10')
  await ui.press({ key: 'answer-q1' })
  expect((await ui.find({ type: 'Text', text: /Nothing is waiting/ }))?.text).toBe('Nothing is waiting on you.')
  await ui.unmount()
})

test('the band shows the usage windows and context', async ($, on) => {
  const clock = engine(on)
  await $.session.start({ cwd: '/work/water-mill', surface: 'terminal', isInteractive: true })
  await clock.settle()

  const band = await $.ui.mount({
    plugin: 'mill-board',
    component: 'AbovePrompt',
    surface: 'terminal',
    props: { hasSurvey: false, bodyColumns: 100, view: {} },
  } as never)
  expect((await band.find({ type: 'Text', text: /5-hour/ }))?.text).toBe('5-hour 34%')
  expect((await band.find({ type: 'Text', text: /Weekly/ }))?.text).toBe('Weekly 85%')
  expect((await band.find({ type: 'Text', text: /Context/ }))?.text).toBe('Context 18%')
  await band.unmount()
})

test('the board lists sessions, an active bead and only this session\'s follow-ups', async ($, on) => {
  const clock = engine(on)
  await $.session.start({ cwd: '/work/water-mill', surface: 'desktop', isInteractive: true })
  await clock.settle()
  await $.tool.call({
    tool: 'mcp__mill-board__update',
    sessions: [{ id: 's1', title: 'claudiverse mill: 1gn.8', state: 'working', bead: 'claudiverse-1gn.8', pr: '#104' }],
    refreshBeads: true,
  } as never)

  const ui = await $.ui.mount({ ...pane('mill-board'), surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /claudiverse mill: 1gn\.8/ }))?.text).toContain('Working')
  expect((await ui.find({ type: 'Text', text: /water-mill-8kp/ }))?.text).toContain('auto-mill')
  expect(await ui.find({ type: 'Text', text: /water-mill-old/ })).toBeUndefined()
  // Only the two checkouts with a bead file are read; claudiverse's has no main copy.
  const notRead = (await ui.find({ type: 'Text', text: /Not read/ }))?.text ?? ''
  expect(notRead).toContain('claudiverse')
  expect(notRead).not.toContain('notes')
  await ui.unmount()
})
