import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type {
  AgentRun,
  Bead,
  BeadSnapshot,
  ChildSession,
  ChildState,
  Question,
  Usage,
} from '../types'

const BOARD = 'mill-board'
const QUESTIONS = 'owner-questions'
const TOOL = 'update'
const REFRESH_MS = 5 * 60 * 1000

type Repo = { name: string; dir: string }

// The checkouts whose main-branch bead file the board reads: every folder
// beside the session's repo (or inside the session's folder, when that is not
// a repo itself, such as a workshop folder) that holds `.beads/issues.jsonl`.
async function findRepos(
  fs: { exists: (path: string) => Promise<boolean>; list: (path?: string) => Promise<readonly { name: string; kind: string }[]> },
  cwd: string,
): Promise<Repo[]> {
  const trimmed = cwd.replace(/\/+$/, '') || '/'
  const root = (await fs.exists(`${trimmed}/.git`))
    ? trimmed.replace(/\/[^/]+$/, '') || '/'
    : trimmed
  const base = root === '/' ? '' : root
  const found: Repo[] = []
  for (const entry of await fs.list(root)) {
    if (entry.kind !== 'dir' || entry.name.startsWith('.')) continue
    const dir = `${base}/${entry.name}`
    if (await fs.exists(`${dir}/.beads/issues.jsonl`)) found.push({ name: entry.name, dir })
  }

  return found.sort((a, b) => a.name.localeCompare(b.name))
}

const STATES: ChildState[] = [
  'working',
  'ready-to-merge',
  'post-merge',
  'done',
  'blocked',
  'no-change',
]

// Change a tag when that value's fields change: it declines what an earlier
// version stored, which outlives a reload.
const beads = atom({ plugin: 'mill-board', key: 'beads' } as const, null, {
  shape: 'beads-1',
})
const sessions = atom({ plugin: 'mill-board', key: 'sessions' } as const, [], {
  shape: 'sessions-1',
})
const agents = atom({ plugin: 'mill-board', key: 'agents' } as const, [], {
  shape: 'agents-1',
})
const questions = atom({ plugin: 'mill-board', key: 'questions' } as const, [], {
  shape: 'questions-1',
})
const usage = atom({ plugin: 'mill-board', key: 'usage' } as const, null, {
  shape: 'usage-1',
})
const isRefreshing = atom(
  { plugin: 'mill-board', key: 'isRefreshing' } as const,
  false,
)

type Run = (argv: readonly string[], init?: { timeoutMs?: number }) => Promise<{
  exitCode: number
  stdout: string
  stderr: string
}>

function parseBeads(repo: string, text: string): Bead[] {
  const out: Bead[] = []
  for (const line of text.split('\n')) {
    if (!line.trim()) continue
    try {
      const row = JSON.parse(line) as Record<string, unknown>
      if (typeof row.id !== 'string') continue
      out.push({
        id: row.id,
        repo,
        title: typeof row.title === 'string' ? row.title : '',
        status: typeof row.status === 'string' ? row.status : 'open',
        priority: typeof row.priority === 'number' ? row.priority : null,
        labels: Array.isArray(row.labels) ? row.labels.map(String) : [],
        createdAt: typeof row.created_at === 'string' ? row.created_at : '',
      })
    } catch {
      // A broken line is skipped; the rest of the file still counts.
    }
  }

  return out
}

async function loadBeads(run: Run, repos: readonly Repo[], now: number): Promise<BeadSnapshot> {
  const all: Bead[] = []
  const errors: string[] = []
  if (repos.length === 0) errors.push('no checkout with .beads/issues.jsonl found beside this session')
  for (const repo of repos) {
    try {
      await run(['git', '-C', repo.dir, 'fetch', '-q', 'origin', 'main'], {
        timeoutMs: 20_000,
      })
      const shown = await run(
        ['git', '-C', repo.dir, 'show', 'origin/main:.beads/issues.jsonl'],
        { timeoutMs: 10_000 },
      )
      if (shown.exitCode !== 0) {
        errors.push(`${repo.name}: ${shown.stderr.trim().split('\n')[0] ?? 'no bead file'}`)
        continue
      }
      all.push(...parseBeads(repo.name, shown.stdout))
    } catch (err) {
      errors.push(`${repo.name}: ${String(err).slice(0, 80)}`)
    }
  }

  return { beads: all, refreshedAt: now, errors }
}

function ago(now: number, then: number): string {
  const minutes = Math.max(0, Math.round((now - then) / 60_000))
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`

  return `${Math.floor(minutes / 60)}h ${minutes % 60}m ago`
}

function until(now: number, iso?: string): string {
  if (!iso) return ''
  const ms = Date.parse(iso) - now
  if (!Number.isFinite(ms) || ms <= 0) return ''
  const minutes = Math.round(ms / 60_000)
  if (minutes < 60) return ` (resets in ${minutes}m)`
  const hours = Math.floor(minutes / 60)
  if (hours < 48) return ` (resets in ${hours}h ${minutes % 60}m)`

  return ` (resets in ${Math.round(hours / 24)}d)`
}

const WINDOW_LABEL: Record<string, string> = {
  five_hour: '5-hour',
  seven_day: 'Weekly',
  spend_limit: 'Spend',
}

function levelColor(percent: number): 'error' | 'warning' | undefined {
  if (percent >= 95) return 'error'
  if (percent >= 80) return 'warning'

  return undefined
}

const STATE_WORD: Record<ChildState, string> = {
  working: 'Working',
  'ready-to-merge': 'Ready to merge',
  'post-merge': 'Wrapping up',
  done: 'Done',
  blocked: 'Blocked',
  'no-change': 'No change',
}

function stateColor(state: ChildState): 'success' | 'warning' | 'error' | 'suggestion' | undefined {
  if (state === 'done') return 'success'
  if (state === 'blocked') return 'error'
  if (state === 'ready-to-merge' || state === 'no-change') return 'warning'
  if (state === 'working' || state === 'post-merge') return 'suggestion'

  return undefined
}

function asText(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined
}

function toUsage(e: {
  context: { percent?: number }
  rateLimits: readonly { kind: string; percentUsed: number; resetsAt?: string }[]
  cost?: { usd: number }
}): Usage {
  return {
    windows: e.rateLimits.map(w => ({
      kind: w.kind,
      percentUsed: w.percentUsed,
      resetsAt: w.resetsAt,
    })),
    contextPercent: e.context.percent ?? null,
    costUsd: e.cost?.usd ?? null,
  }
}

export const register: Register = on => {
  let repos: Repo[] = []

  on('session.start', async ($, e, next) => {
    try {
      repos = await findRepos({ exists: path => $.fs.exists(path), list: path => $.fs.list(path) }, e.cwd)
    } catch {
      repos = []
    }
    await $.command.register({
      name: 'mill-board',
      description: 'Show active and follow-up beads, child sessions and subagents',
    })
    await $.command.register({
      name: 'owner-questions',
      description: 'Show the open questions waiting on you',
    })
    await $.tool.register({
      name: TOOL,
      description:
        'Update the mill board panes the owner watches. `sessions` replaces the whole list of child sessions ' +
        '(id, title, state, bead, repo, pr, note). `questions` adds or rewrites open questions for the owner by id ' +
        '(id, text, context). `resolve` marks question ids answered. `refreshBeads` re-reads every repo\'s bead file ' +
        'from origin/main. Call it whenever a child session changes state or a question for the owner appears or is settled.',
      isDeferred: false,
      inputSchema: {
        type: 'object',
        properties: {
          sessions: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                id: { type: 'string' },
                title: { type: 'string' },
                state: { type: 'string', enum: STATES },
                bead: { type: 'string' },
                repo: { type: 'string' },
                pr: { type: 'string' },
                note: { type: 'string' },
              },
              required: ['id', 'title', 'state'],
            },
          },
          questions: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                id: { type: 'string' },
                text: { type: 'string' },
                context: { type: 'string' },
              },
              required: ['id', 'text'],
            },
          },
          resolve: { type: 'array', items: { type: 'string' } },
          refreshBeads: { type: 'boolean' },
          diagnose: { type: 'boolean' },
        },
      },
    })

    const run: Run = (argv, init) => $.process.run(argv, init)
    const refresh = async () => {
      if (await read($, isRefreshing)) return
      await update($, isRefreshing, () => true)
      try {
        const snapshot = await loadBeads(run, repos, await $.clock.now())
        await update($, beads, () => snapshot)
      } finally {
        await update($, isRefreshing, () => false)
      }
    }
    $.clock.every(REFRESH_MS, () => void refresh())
    void refresh()

    try {
      const now = await $.session.usage()
      await update($, usage, () => toUsage(now))
    } catch {
      // No figures yet; session.measure fills them in after the first turn.
    }

    void $.ui.open({ id: BOARD, title: 'Mill board' })
    void $.ui.open({ id: QUESTIONS, title: 'Questions for you' })

    return next(e)
  })

  on('command.run', { command: 'mill-board' }, async $ => {
    await $.ui.open({ id: BOARD, title: 'Mill board', focus: true })

    return { text: 'Mill board opened.' }
  })

  on('command.run', { command: 'owner-questions' }, async $ => {
    await $.ui.open({ id: QUESTIONS, title: 'Questions for you', focus: true })

    return { text: 'Questions pane opened.' }
  })

  on('session.measure', async ($, e, next) => {
    await update($, usage, () => toUsage(e))

    return next(e)
  })

  on('tool.call', { tool: `mcp__mill-board__${TOOL}` }, async ($, e) => {
    const input = e as unknown as Record<string, unknown>
    const now = await $.clock.now()
    const said: string[] = []

    if (Array.isArray(input.sessions)) {
      const list: ChildSession[] = []
      for (const raw of input.sessions as Record<string, unknown>[]) {
        const id = asText(raw.id)
        const state = STATES.find(s => s === raw.state)
        if (!id || !state) continue
        list.push({
          id,
          title: asText(raw.title) ?? id,
          state,
          bead: asText(raw.bead),
          repo: asText(raw.repo),
          pr: asText(raw.pr),
          note: asText(raw.note),
          updatedAt: now,
        })
      }
      await update($, sessions, () => list)
      said.push(`${list.length} session(s)`)
    }

    if (Array.isArray(input.questions)) {
      let count = 0
      await update($, questions, list => {
        const next = [...list]
        for (const raw of input.questions as Record<string, unknown>[]) {
          const id = asText(raw.id)
          const text = asText(raw.text)
          if (!id || !text) continue
          count += 1
          const at = next.findIndex(q => q.id === id)
          const kept = at >= 0 ? next[at] : undefined
          const q: Question = {
            id,
            text,
            context: asText(raw.context),
            askedAt: kept?.askedAt ?? now,
            answeredAt: null,
          }
          if (at >= 0) next[at] = q
          else next.push(q)
        }

        return next
      })
      said.push(`${count} question(s) set`)
    }

    if (Array.isArray(input.resolve)) {
      const ids = new Set((input.resolve as unknown[]).map(String))
      await update($, questions, list =>
        list.map(q => (ids.has(q.id) && q.answeredAt === null ? { ...q, answeredAt: now } : q)),
      )
      said.push(`${ids.size} question(s) resolved`)
    }

    if (input.diagnose === true) {
      const surfaces = await $.session.surfaces()
      const board = await $.ui.open({ id: BOARD, title: 'Mill board' })
      const asked = await $.ui.open({ id: QUESTIONS, title: 'Questions for you' })
      said.push(`surfaces=${JSON.stringify(surfaces)}`)
      said.push(`board=${JSON.stringify(board)}`)
      said.push(`questions=${JSON.stringify(asked)}`)
      said.push(`panes=${JSON.stringify(await $.ui.panes())}`)
    }

    if (input.refreshBeads === true) {
      const snapshot = await loadBeads((argv, init) => $.process.run(argv, init), repos, now)
      await update($, beads, () => snapshot)
      said.push(`${snapshot.beads.length} beads re-read`)
    }

    return { result: `Mill board updated: ${said.join(', ') || 'nothing given'}.` }
  }).catch(() => ({ result: 'Mill board update failed; the panes keep what they had.' }))

  on('tool.call', async ($, e, next) => {
    if (e.tool !== 'Agent') return next(e)
    const id = e.tool_use_id ?? `agent-${await $.clock.now()}`
    const run: AgentRun = {
      id,
      kind: e.subagent_type ?? 'general-purpose',
      description: e.description ?? '',
      startedAt: await $.clock.now(),
      endedAt: null,
    }
    await update($, agents, list => [...list, run].slice(-30))
    try {
      return await next(e)
    } finally {
      const endedAt = await $.clock.now()
      await update($, agents, list => list.map(a => (a.id === id ? { ...a, endedAt } : a)))
    }
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'Pane', requestId: BOARD }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const now = await $.clock.now()
    const snapshot = await read($, beads)
    const children = await read($, sessions)
    const runs = await read($, agents)
    const busy = await read($, isRefreshing)
    let since = 0
    try {
      since = (await $.session.usage()).startedAt
    } catch {
      since = 0
    }

    const all = snapshot?.beads ?? []
    const named = new Set(
      children.filter(c => c.state !== 'done' && c.bead).map(c => c.bead as string),
    )
    const active = all.filter(b => b.status === 'in_progress' || named.has(b.id))
    const followUps = all
      .filter(b => b.status !== 'closed' && !named.has(b.id) && b.status !== 'in_progress')
      .filter(b => Date.parse(b.createdAt) >= since)
      .sort((a, b) => (a.priority ?? 9) - (b.priority ?? 9))
    const working = runs.filter(r => r.endedAt === null)
    const recent = runs.filter(r => r.endedAt !== null).slice(-5).reverse()

    const beadLine = (b: Bead) => {
      const tags = b.labels.filter(l => ['auto-mill', 'human', 'fence', 'live-api'].includes(l))
      const status = b.status === 'deferred' ? ' deferred' : b.status === 'in_progress' ? ' in progress' : ''

      return (
        <Text wrap="truncate-end">
          <Text dimColor>P{b.priority ?? '?'}</Text> {b.id}
          <Text dimColor>
            {status}
            {tags.length ? ` [${tags.join(', ')}]` : ''}
          </Text>{' '}
          {b.title}
        </Text>
      )
    }

    return (
      <Box flexDirection="column" gap={1}>
        <Box flexDirection="column">
          <Text bold>Child sessions ({children.filter(c => c.state !== 'done').length} open)</Text>
          {children.length === 0 && <Text dimColor>None reported yet.</Text>}
          {children.map(c => (
            <Text wrap="wrap">
              <Text color={stateColor(c.state)}>{STATE_WORD[c.state]}</Text> {c.title}
              <Text dimColor>
                {c.pr ? ` · ${c.pr}` : ''}
                {c.note ? ` · ${c.note}` : ''}
              </Text>
            </Text>
          ))}
        </Box>

        <Box flexDirection="column">
          <Text bold>Subagents in this session ({working.length} running)</Text>
          {runs.length === 0 && <Text dimColor>None this session.</Text>}
          {working.map(r => (
            <Text wrap="truncate-end">
              <Text color="suggestion">Running</Text> {r.kind}: {r.description}{' '}
              <Text dimColor>since {ago(now, r.startedAt)}</Text>
            </Text>
          ))}
          {recent.map(r => (
            <Text wrap="truncate-end" dimColor>
              Returned {r.kind}: {r.description} ({ago(now, r.endedAt ?? now)})
            </Text>
          ))}
        </Box>

        <Box flexDirection="column">
          <Text bold>Active beads ({active.length})</Text>
          {active.length === 0 && <Text dimColor>No bead is in progress.</Text>}
          {active.map(beadLine)}
        </Box>

        <Box flexDirection="column">
          <Text bold>Follow-up beads filed this session ({followUps.length})</Text>
          {followUps.length === 0 && <Text dimColor>None filed since this session began.</Text>}
          {followUps.map(beadLine)}
        </Box>

        <Box flexDirection="column">
          <Text dimColor wrap="wrap">
            {snapshot
              ? `Beads read from origin/main ${ago(now, snapshot.refreshedAt)}; every 5 minutes.`
              : 'Beads not read yet.'}
            {snapshot?.errors.length ? ` Not read: ${snapshot.errors.join('; ')}` : ''}
          </Text>
          <Box>
            <Button
              key="refresh"
              label={busy ? 'Refreshing' : 'Refresh beads'}
              onPress={async () => {
                if (await read($, isRefreshing)) return
                await update($, isRefreshing, () => true)
                try {
                  const fresh = await loadBeads(
                    (argv, init) => $.process.run(argv, init),
                    repos,
                    await $.clock.now(),
                  )
                  await update($, beads, () => fresh)
                } finally {
                  await update($, isRefreshing, () => false)
                }
              }}
            />
          </Box>
        </Box>
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: QUESTIONS }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const now = await $.clock.now()
    const list = await read($, questions)
    const open = list.filter(q => q.answeredAt === null)
    const answered = list.filter(q => q.answeredAt !== null)

    return (
      <Box flexDirection="column" gap={1}>
        <Text bold>Open questions for you ({open.length})</Text>
        {open.length === 0 && <Text dimColor>Nothing is waiting on you.</Text>}
        {open.map((q, i) => (
          <Box flexDirection="column">
            <Text wrap="wrap">
              {i + 1}. {q.text}
            </Text>
            {q.context && (
              <Text dimColor wrap="wrap">
                {q.context}
              </Text>
            )}
            <Box>
              <Text dimColor>Asked {ago(now, q.askedAt)} </Text>
              <Button
                key={`answer-${q.id}`}
                label="Mark answered"
                onPress={async () => {
                  const at = await $.clock.now()
                  await update($, questions, all =>
                    all.map(one => (one.id === q.id ? { ...one, answeredAt: at } : one)),
                  )
                }}
              />
            </Box>
          </Box>
        ))}
        {answered.length > 0 && (
          <Text dimColor>
            {answered.length} answered: {answered.slice(-3).map(q => q.text.slice(0, 40)).join('; ')}
          </Text>
        )}
      </Box>
    )
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const now = await read($, usage)
    if (e.props.hasSurvey || now === null) return next(e)
    const { Box, Text } = $.ui.resolve(e)
    const at = await $.clock.now()
    const open = (await read($, questions)).filter(q => q.answeredAt === null).length

    return (
      <Box gap={2}>
        {now.windows.length === 0 && <Text dimColor>Usage: no reading yet</Text>}
        {now.windows.map(w => (
          <Text color={levelColor(w.percentUsed)} dimColor={levelColor(w.percentUsed) === undefined}>
            {WINDOW_LABEL[w.kind] ?? w.kind} {w.percentUsed}%{until(at, w.resetsAt)}
          </Text>
        ))}
        {now.contextPercent !== null && (
          <Text color={levelColor(now.contextPercent)} dimColor={levelColor(now.contextPercent) === undefined}>
            Context {now.contextPercent}%
          </Text>
        )}
        {now.costUsd !== null && <Text dimColor>Session ${now.costUsd.toFixed(2)}</Text>}
        {open > 0 && <Text color="warning">{open} question{open === 1 ? '' : 's'} for you</Text>}
      </Box>
    )
  })
}
