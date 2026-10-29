export type Bead = {
  id: string
  repo: string
  title: string
  status: string
  priority: number | null
  labels: string[]
  createdAt: string
}

export type BeadSnapshot = {
  beads: Bead[]
  refreshedAt: number
  errors: string[]
}

export type ChildState =
  | 'working'
  | 'ready-to-merge'
  | 'post-merge'
  | 'done'
  | 'blocked'
  | 'no-change'

export type ChildSession = {
  id: string
  title: string
  state: ChildState
  bead?: string
  repo?: string
  pr?: string
  note?: string
  updatedAt: number
}

export type AgentRun = {
  id: string
  kind: string
  description: string
  startedAt: number
  endedAt: number | null
}

export type Question = {
  id: string
  text: string
  context?: string
  askedAt: number
  answeredAt: number | null
}

export type Usage = {
  windows: { kind: string; percentUsed: number; resetsAt?: string }[]
  contextPercent: number | null
  costUsd: number | null
}

declare module 'claude-code' {
  interface PluginState {
    'mill-board': {
      beads: Shaped<BeadSnapshot | null>
      sessions: Shaped<ChildSession[]>
      agents: Shaped<AgentRun[]>
      questions: Shaped<Question[]>
      usage: Shaped<Usage | null>
      isRefreshing: boolean
    }
  }
}
