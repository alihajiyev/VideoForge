import { spawn, type ChildProcess } from 'node:child_process'

export interface ExecResult {
  code: number | null
  stdout: string
  stderr: string
  error?: string
}

/**
 * Komutu asenkron calistirir ve ciktiyi toplar.
 * ONEMLI: spawnSync KULLANILMAZ — senkron calistirma ana surec event loop'unu
 * kilitler ve pencere ilk boyamayi yapamaz (envCheck ~4sn kilitleniyordu).
 */
export function execCapture(
  command: string,
  args: string[],
  opts: { cwd?: string; timeoutMs?: number; env?: NodeJS.ProcessEnv } = {},
): Promise<ExecResult> {
  return new Promise<ExecResult>((resolve) => {
    let out = ''
    let err = ''
    let done = false
    let timer: NodeJS.Timeout | undefined

    const finish = (res: ExecResult): void => {
      if (done) return
      done = true
      if (timer) clearTimeout(timer)
      resolve(res)
    }

    let child: ChildProcess
    try {
      child = spawn(command, args, {
        cwd: opts.cwd,
        windowsHide: true,
        env: { ...process.env, PYTHONIOENCODING: 'utf-8', ...opts.env },
      })
    } catch (e) {
      resolve({ code: null, stdout: '', stderr: '', error: String(e) })
      return
    }

    timer = setTimeout(() => {
      try {
        child.kill()
      } catch {
        /* yoksay */
      }
      finish({ code: null, stdout: out, stderr: err, error: `zaman asimi (${opts.timeoutMs ?? 20000}ms)` })
    }, opts.timeoutMs ?? 20_000)

    child.stdout?.on('data', (d: Buffer) => {
      out += d.toString('utf8')
    })
    child.stderr?.on('data', (d: Buffer) => {
      err += d.toString('utf8')
    })
    child.on('error', (e) => finish({ code: null, stdout: out, stderr: err, error: String(e) }))
    child.on('close', (code) => finish({ code, stdout: out, stderr: err }))
  })
}
