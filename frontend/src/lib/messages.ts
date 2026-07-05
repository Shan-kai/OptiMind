export const ERROR_MESSAGES: Record<string, string> = {
  UPLOAD_FAILED: '上传失败，请检查网络或文件格式后重试。',
  SEND_FAILED: '消息发送失败，请稍后重试。',
  SOLVER_UNAVAILABLE: '当前求解器不可用，建议切换到 mock 模式继续体验。',
  UNKNOWN: '发生未知错误，请刷新页面重试。',
}

export function getErrorMessage(input: string | undefined, fallbackKey = 'UNKNOWN'): string {
  if (!input) return ERROR_MESSAGES[fallbackKey]
  return ERROR_MESSAGES[input] ?? input
}
