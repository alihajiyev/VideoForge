export interface PythonCommand {
  command: string
  args: string[]
  label: string
  detail?: string
}

export interface JobStep {
  /** Kullaniciya gosterilecek etiket */
  label: string
  /** Calistirilacak komut (python + args) */
  cmd: string[]
  /** Adim bitince devam edilsin mi? (haftalik zincir icin) */
  continueWhen?: () => boolean
}
