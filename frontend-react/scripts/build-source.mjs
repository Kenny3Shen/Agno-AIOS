import { execFileSync } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const appRoot = resolve(scriptDir, '..')
const viteBin = resolve(appRoot, 'node_modules/vite/bin/vite.js')

execFileSync('node', [viteBin, 'build', '--config', 'vite.static.config.ts'], {
  cwd: appRoot,
  stdio: 'inherit',
})
