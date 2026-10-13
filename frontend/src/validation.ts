// Mesmas regras do back-end (seção 7.1): username 3–20 [a-zA-Z0-9_], senha 8–72.

export function validateUsername(value: string): string | null {
  if (value.length < 3 || value.length > 20) return 'Use de 3 a 20 caracteres.'
  if (!/^[a-zA-Z0-9_]+$/.test(value)) return 'Use apenas letras, números e _.'
  return null
}

export function validatePassword(value: string): string | null {
  if (value.length < 8) return 'A senha precisa de pelo menos 8 caracteres.'
  if (value.length > 72) return 'A senha pode ter no máximo 72 caracteres.'
  return null
}
